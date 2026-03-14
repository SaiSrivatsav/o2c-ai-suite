import json
import uuid
from datetime import datetime
from langchain_core.tools import tool
from langgraph.types import interrupt
from db.connection import fetch_all, fetch_one, execute


CREDIT_MEMO_APPROVAL_THRESHOLD = 5000.0


@tool
async def get_credit_memo(identifier: str) -> str:
    """Get credit memo details. identifier: credit memo number (CM-XXXX) or ID."""
    row = await fetch_one(
        """SELECT cm.*, inv."invoiceNumber", so."orderNumber",
                  c."customerNumber", c."name" as "customerName"
           FROM credit_memos cm
           JOIN invoices inv ON inv."id" = cm."invoiceId"
           JOIN sales_orders so ON so."id" = cm."salesOrderId"
           JOIN customers c ON c."id" = cm."customerId"
           WHERE cm."creditMemoNumber" = $1 OR cm."id" = $1""",
        identifier,
    )
    if not row:
        return f"No credit memo found: {identifier}"
    return json.dumps(row, indent=2)


@tool
async def list_credit_memos(
    customer_identifier: str = "",
    status: str = "",
    reason: str = "",
    date_from: str = "",
    date_to: str = "",
    limit: int = 50,
) -> str:
    """Search credit memos. Returns at most `limit` rows (default 50).
    status: DRAFT, APPROVED, POSTED, CANCELLED. reason: free text search (e.g. 'damaged', 'pricing error')."""
    conditions = []
    params: list = []
    idx = 1

    if customer_identifier:
        conditions.append(
            f"""cm."customerId" IN (SELECT "id" FROM customers WHERE "customerNumber" = ${idx} OR "id" = ${idx})"""
        )
        params.append(customer_identifier)
        idx += 1
    if status:
        conditions.append(f'cm."status"::text = ${idx}')
        params.append(status)
        idx += 1
    if reason:
        conditions.append(f'cm."reason" ILIKE ${idx}')
        params.append(f"%{reason}%")
        idx += 1
    if date_from:
        conditions.append(f'cm."creditDate" >= ${idx}')
        params.append(datetime.fromisoformat(date_from))
        idx += 1
    if date_to:
        conditions.append(f'cm."creditDate" <= ${idx}')
        params.append(datetime.fromisoformat(date_to + "T23:59:59"))
        idx += 1

    where = " AND ".join(conditions) if conditions else "TRUE"
    actual_limit = min(limit, 200)
    params.append(actual_limit)
    rows = await fetch_all(
        f"""SELECT cm.*, inv."invoiceNumber", c."customerNumber", c."name" as "customerName"
            FROM credit_memos cm
            JOIN invoices inv ON inv."id" = cm."invoiceId"
            JOIN customers c ON c."id" = cm."customerId"
            WHERE {where} ORDER BY cm."creditDate" DESC
            LIMIT ${len(params)}""",
        *params,
    )
    if not rows:
        return "No credit memos found matching the criteria."
    return json.dumps(rows, indent=2)


@tool
async def create_credit_memo(
    invoice_identifier: str,
    reason: str,
    amount: float,
    credit_date: str = "",
) -> str:
    """Create a credit memo against an invoice. Starts in DRAFT status.
    Reasons: damaged goods, pricing error, quantity discrepancy, late delivery, wrong item, duplicate charge."""
    invoice = await fetch_one(
        """SELECT inv.*, so."id" as "so_id"
           FROM invoices inv
           JOIN sales_orders so ON so."id" = inv."salesOrderId"
           WHERE inv."invoiceNumber" = $1 OR inv."id" = $1""",
        invoice_identifier,
    )
    if not invoice:
        return f"No invoice found: {invoice_identifier}"

    if amount > invoice["totalGrossAmount"]:
        return (
            f"Credit memo amount ${amount:,.2f} exceeds invoice total "
            f"${invoice['totalGrossAmount']:,.2f}."
        )

    cm_id = str(uuid.uuid4())
    last = await fetch_one(
        'SELECT "creditMemoNumber" FROM credit_memos ORDER BY "creditMemoNumber" DESC LIMIT 1'
    )
    if last:
        num = int(last["creditMemoNumber"].split("-")[1]) + 1
        cm_number = f"CM-{num:04d}"
    else:
        cm_number = "CM-0001"

    c_date = datetime.fromisoformat(credit_date) if credit_date else datetime.now()

    await execute(
        """INSERT INTO credit_memos
           ("id","creditMemoNumber","invoiceId","salesOrderId","customerId",
            "creditDate","reason","totalAmount","currency","status","createdAt","updatedAt")
           VALUES ($1,$2,$3,$4,$5,$6,$7,$8,'USD','DRAFT'::"CreditMemoStatus",NOW(),NOW())""",
        cm_id, cm_number, invoice["id"], invoice["so_id"],
        invoice["customerId"], c_date, reason, amount,
    )

    return json.dumps({
        "message": f"Credit memo {cm_number} created in DRAFT status",
        "creditMemoNumber": cm_number,
        "creditMemoId": cm_id,
        "amount": amount,
        "reason": reason,
        "note": "Call approve_credit_memo to approve and post this credit memo."
            if amount > CREDIT_MEMO_APPROVAL_THRESHOLD
            else "Credit memo is ready to be approved.",
    })


@tool
async def approve_credit_memo(credit_memo_identifier: str) -> str:
    """Approve a credit memo and post it. For amounts over $5,000 human approval is required.
    Transitions: DRAFT -> APPROVED -> POSTED."""
    memo = await fetch_one(
        """SELECT cm.*, inv."invoiceNumber", c."customerNumber"
           FROM credit_memos cm
           JOIN invoices inv ON inv."id" = cm."invoiceId"
           JOIN customers c ON c."id" = cm."customerId"
           WHERE cm."creditMemoNumber" = $1 OR cm."id" = $1""",
        credit_memo_identifier,
    )
    if not memo:
        return f"No credit memo found: {credit_memo_identifier}"
    if memo["status"] not in ("DRAFT", "APPROVED"):
        return f"Credit memo {memo['creditMemoNumber']} is {memo['status']}, cannot approve."

    # Human-in-the-loop for high-value credit memos
    if memo["status"] == "DRAFT" and memo["totalAmount"] > CREDIT_MEMO_APPROVAL_THRESHOLD:
        approval = interrupt({
            "type": "credit_memo_approval",
            "creditMemoNumber": memo["creditMemoNumber"],
            "amount": memo["totalAmount"],
            "reason": memo["reason"],
            "invoiceNumber": memo["invoiceNumber"],
            "customer": memo["customerNumber"],
            "message": (
                f"Credit memo {memo['creditMemoNumber']} for ${memo['totalAmount']:,.2f} "
                f"(reason: {memo['reason']}) requires approval. Approve?"
            ),
        })
        if not approval.get("approved"):
            await execute(
                """UPDATE credit_memos SET "status" = 'CANCELLED'::"CreditMemoStatus", "updatedAt" = NOW()
                   WHERE "id" = $1""",
                memo["id"],
            )
            return f"Credit memo {memo['creditMemoNumber']} was rejected and cancelled."

    # Approve then post
    await execute(
        """UPDATE credit_memos SET "status" = 'POSTED'::"CreditMemoStatus", "updatedAt" = NOW()
           WHERE "id" = $1""",
        memo["id"],
    )

    return json.dumps({
        "message": f"Credit memo {memo['creditMemoNumber']} approved and posted.",
        "creditMemoNumber": memo["creditMemoNumber"],
        "amount": memo["totalAmount"],
        "status": "POSTED",
    })


all_credit_memo_tools = [
    get_credit_memo,
    list_credit_memos,
    create_credit_memo,
    approve_credit_memo,
]
