import json
import uuid
from datetime import datetime
from langchain_core.tools import tool
from langgraph.types import interrupt
from db.connection import fetch_all, fetch_one, execute


@tool
async def get_payment(identifier: str) -> str:
    """Get payment details. identifier: payment number (PAY-XXXX) or ID."""
    row = await fetch_one(
        """SELECT p.*, inv."invoiceNumber", c."customerNumber", c."name" as "customerName"
           FROM payments p
           JOIN invoices inv ON inv."id" = p."invoiceId"
           JOIN customers c ON c."id" = p."customerId"
           WHERE p."paymentNumber" = $1 OR p."id" = $1""",
        identifier,
    )
    if not row:
        return f"No payment found: {identifier}"
    return json.dumps(row, indent=2)


@tool
async def list_payments(
    customer_identifier: str = "",
    invoice_identifier: str = "",
    payment_method: str = "",
    status: str = "",
    date_from: str = "",
    date_to: str = "",
    limit: int = 50,
) -> str:
    """Search payments. Returns at most `limit` rows (default 50).
    payment_method: BANK_TRANSFER, CREDIT_CARD, CHECK, CASH. status: PENDING, CLEARED, REVERSED."""
    conditions = []
    params: list = []
    idx = 1

    if customer_identifier:
        conditions.append(
            f"""p."customerId" IN (SELECT "id" FROM customers WHERE "customerNumber" = ${idx} OR "id" = ${idx})"""
        )
        params.append(customer_identifier)
        idx += 1
    if invoice_identifier:
        conditions.append(
            f"""p."invoiceId" IN (SELECT "id" FROM invoices WHERE "invoiceNumber" = ${idx} OR "id" = ${idx})"""
        )
        params.append(invoice_identifier)
        idx += 1
    if payment_method:
        conditions.append(f'p."paymentMethod"::text = ${idx}')
        params.append(payment_method)
        idx += 1
    if status:
        conditions.append(f'p."status"::text = ${idx}')
        params.append(status)
        idx += 1
    if date_from:
        conditions.append(f'p."paymentDate" >= ${idx}')
        params.append(datetime.fromisoformat(date_from))
        idx += 1
    if date_to:
        conditions.append(f'p."paymentDate" <= ${idx}')
        params.append(datetime.fromisoformat(date_to + "T23:59:59"))
        idx += 1

    where = " AND ".join(conditions) if conditions else "TRUE"
    actual_limit = min(limit, 200)
    params.append(actual_limit)
    rows = await fetch_all(
        f"""SELECT p.*, inv."invoiceNumber", c."customerNumber", c."name" as "customerName"
            FROM payments p
            JOIN invoices inv ON inv."id" = p."invoiceId"
            JOIN customers c ON c."id" = p."customerId"
            WHERE {where} ORDER BY p."paymentDate" DESC
            LIMIT ${len(params)}""",
        *params,
    )
    if not rows:
        return "No payments found matching the criteria."
    return json.dumps(rows, indent=2)


@tool
async def record_payment(
    invoice_identifier: str,
    amount: float,
    payment_method: str = "BANK_TRANSFER",
    reference_number: str = "",
    payment_date: str = "",
) -> str:
    """Record a payment against an invoice. Automatically updates invoice status
    (PARTIALLY_PAID or PAID). payment_method: BANK_TRANSFER, CREDIT_CARD, CHECK, CASH."""
    invoice = await fetch_one(
        """SELECT inv.*, c."customerNumber", c."id" as "cust_id"
           FROM invoices inv
           JOIN customers c ON c."id" = inv."customerId"
           WHERE inv."invoiceNumber" = $1 OR inv."id" = $1""",
        invoice_identifier,
    )
    if not invoice:
        return f"No invoice found: {invoice_identifier}"
    if invoice["status"] in ("PAID", "CANCELLED"):
        return f"Invoice {invoice['invoiceNumber']} is already {invoice['status']}."

    # Calculate existing cleared payments
    existing = await fetch_all(
        """SELECT "amount" FROM payments
           WHERE "invoiceId" = $1 AND "status"::text = 'CLEARED'""",
        invoice["id"],
    )
    total_cleared = sum(p["amount"] for p in existing)
    remaining = invoice["totalGrossAmount"] - total_cleared

    if amount > remaining + 0.01:
        return (
            f"Payment amount ${amount:,.2f} exceeds remaining balance "
            f"${remaining:,.2f} on invoice {invoice['invoiceNumber']}."
        )

    payment_id = str(uuid.uuid4())
    last = await fetch_one(
        'SELECT "paymentNumber" FROM payments ORDER BY "paymentNumber" DESC LIMIT 1'
    )
    if last:
        num = int(last["paymentNumber"].split("-")[1]) + 1
        payment_number = f"PAY-{num:04d}"
    else:
        payment_number = "PAY-0001"

    ref = reference_number or f"REF-{uuid.uuid4().hex[:8].upper()}"
    pay_date = datetime.fromisoformat(payment_date) if payment_date else datetime.now()

    await execute(
        """INSERT INTO payments
           ("id","paymentNumber","invoiceId","customerId","paymentDate",
            "amount","currency","paymentMethod","referenceNumber","status",
            "createdAt","updatedAt")
           VALUES ($1,$2,$3,$4,$5,$6,'USD',$7::"PaymentMethod",$8,'CLEARED'::"PaymentStatus",NOW(),NOW())""",
        payment_id, payment_number, invoice["id"], invoice["cust_id"],
        pay_date, amount, payment_method, ref,
    )

    # Update invoice status
    new_total = total_cleared + amount
    new_status = "PAID" if abs(new_total - invoice["totalGrossAmount"]) < 0.01 else "PARTIALLY_PAID"
    await execute(
        'UPDATE invoices SET "status" = $1::"InvoiceStatus", "updatedAt" = NOW() WHERE "id" = $2',
        new_status, invoice["id"],
    )

    return json.dumps({
        "message": f"Payment {payment_number} of ${amount:,.2f} recorded for {invoice['invoiceNumber']}",
        "paymentNumber": payment_number,
        "invoiceStatus": new_status,
        "remainingBalance": round(invoice["totalGrossAmount"] - new_total, 2),
    })


@tool
async def reverse_payment(payment_identifier: str) -> str:
    """Reverse a cleared payment. Requires human approval. Recalculates invoice status."""
    payment = await fetch_one(
        """SELECT p.*, inv."invoiceNumber", inv."totalGrossAmount"
           FROM payments p
           JOIN invoices inv ON inv."id" = p."invoiceId"
           WHERE p."paymentNumber" = $1 OR p."id" = $1""",
        payment_identifier,
    )
    if not payment:
        return f"No payment found: {payment_identifier}"
    if payment["status"] != "CLEARED":
        return f"Payment {payment['paymentNumber']} is {payment['status']}, cannot reverse."

    # Human approval required for all reversals
    approval = interrupt({
        "type": "payment_reversal",
        "paymentNumber": payment["paymentNumber"],
        "amount": payment["amount"],
        "invoiceNumber": payment["invoiceNumber"],
        "message": (
            f"Reverse payment {payment['paymentNumber']} for ${payment['amount']:,.2f} "
            f"on invoice {payment['invoiceNumber']}? This will change the invoice status."
        ),
    })
    if not approval.get("approved"):
        return f"Payment reversal for {payment['paymentNumber']} was rejected."

    await execute(
        """UPDATE payments SET "status" = 'REVERSED'::"PaymentStatus", "updatedAt" = NOW()
           WHERE "id" = $1""",
        payment["id"],
    )

    # Recalculate invoice status
    remaining_cleared = await fetch_all(
        """SELECT "amount" FROM payments
           WHERE "invoiceId" = $1 AND "status"::text = 'CLEARED'""",
        payment["invoiceId"],
    )
    total_still_paid = sum(p["amount"] for p in remaining_cleared)
    if total_still_paid <= 0:
        new_inv_status = "OPEN"
    elif total_still_paid < payment["totalGrossAmount"]:
        new_inv_status = "PARTIALLY_PAID"
    else:
        new_inv_status = "PAID"

    await execute(
        'UPDATE invoices SET "status" = $1::"InvoiceStatus", "updatedAt" = NOW() WHERE "id" = $2',
        new_inv_status, payment["invoiceId"],
    )

    return json.dumps({
        "message": f"Payment {payment['paymentNumber']} reversed. Invoice {payment['invoiceNumber']} is now {new_inv_status}.",
        "paymentNumber": payment["paymentNumber"],
        "invoiceStatus": new_inv_status,
    })


all_payment_tools = [
    get_payment,
    list_payments,
    record_payment,
    reverse_payment,
]
