import json
import uuid
from datetime import datetime, timedelta
from langchain_core.tools import tool
from db.connection import fetch_all, fetch_one, execute


@tool
async def get_invoice(identifier: str) -> str:
    """Get invoice details with items and payment status.
    identifier: invoice number (INV-XXXX) or ID."""
    invoice = await fetch_one(
        """SELECT inv.*, so."orderNumber", c."customerNumber", c."name" as "customerName",
                  d."deliveryNumber"
           FROM invoices inv
           JOIN sales_orders so ON so."id" = inv."salesOrderId"
           JOIN customers c ON c."id" = inv."customerId"
           JOIN deliveries d ON d."id" = inv."deliveryId"
           WHERE inv."invoiceNumber" = $1 OR inv."id" = $1""",
        identifier,
    )
    if not invoice:
        return f"No invoice found: {identifier}"

    items = await fetch_all(
        """SELECT ii.*, m."materialNumber", m."description" as "materialDescription"
           FROM invoice_items ii
           JOIN materials m ON m."id" = ii."materialId"
           WHERE ii."invoiceId" = $1 ORDER BY ii."itemNumber" """,
        invoice["id"],
    )
    payments = await fetch_all(
        'SELECT * FROM payments WHERE "invoiceId" = $1 ORDER BY "paymentDate"',
        invoice["id"],
    )
    total_paid = sum(p["amount"] for p in payments if p["status"] == "CLEARED")

    result = {
        "invoice": invoice,
        "items": items,
        "payments": payments,
        "balance_remaining": round(invoice["totalGrossAmount"] - total_paid, 2),
    }
    return json.dumps(result, indent=2)


@tool
async def list_invoices(
    customer_identifier: str = "",
    status: str = "",
    date_from: str = "",
    date_to: str = "",
    overdue_only: bool = False,
    limit: int = 50,
) -> str:
    """Search invoices. Returns at most `limit` rows (default 50).
    status: OPEN, PARTIALLY_PAID, PAID, CANCELLED.
    overdue_only=true shows invoices past due date that are not fully paid."""
    conditions = []
    params: list = []
    idx = 1

    if customer_identifier:
        conditions.append(
            f"""inv."customerId" IN (SELECT "id" FROM customers WHERE "customerNumber" = ${idx} OR "id" = ${idx})"""
        )
        params.append(customer_identifier)
        idx += 1
    if status:
        conditions.append(f'inv."status"::text = ${idx}')
        params.append(status)
        idx += 1
    if date_from:
        conditions.append(f'inv."invoiceDate" >= ${idx}')
        params.append(datetime.fromisoformat(date_from))
        idx += 1
    if date_to:
        conditions.append(f'inv."invoiceDate" <= ${idx}')
        params.append(datetime.fromisoformat(date_to + "T23:59:59"))
        idx += 1
    if overdue_only:
        conditions.append(f'inv."dueDate" < ${idx}')
        params.append(datetime.now())
        idx += 1
        conditions.append('inv."status"::text IN (\'OPEN\',\'PARTIALLY_PAID\')')

    where = " AND ".join(conditions) if conditions else "TRUE"
    actual_limit = min(limit, 200)
    params.append(actual_limit)
    rows = await fetch_all(
        f"""SELECT inv.*, c."customerNumber", c."name" as "customerName",
                   so."orderNumber"
            FROM invoices inv
            JOIN customers c ON c."id" = inv."customerId"
            JOIN sales_orders so ON so."id" = inv."salesOrderId"
            WHERE {where} ORDER BY inv."invoiceDate" DESC
            LIMIT ${len(params)}""",
        *params,
    )
    if not rows:
        return "No invoices found matching the criteria."
    return json.dumps(rows, indent=2)


@tool
async def create_invoice(
    delivery_identifier: str,
    due_days: int = 30,
) -> str:
    """Create an invoice from a delivered delivery. due_days: number of days until payment is due (default 30)."""
    delivery = await fetch_one(
        """SELECT d.*, so."customerId", so."orderNumber"
           FROM deliveries d
           JOIN sales_orders so ON so."id" = d."salesOrderId"
           WHERE d."deliveryNumber" = $1 OR d."id" = $1""",
        delivery_identifier,
    )
    if not delivery:
        return f"No delivery found: {delivery_identifier}"

    # Get delivery items with pricing from SO items
    del_items = await fetch_all(
        """SELECT di.*, soi."unitPrice", soi."netAmount", soi."taxAmount",
                  soi."currency", soi."materialId"
           FROM delivery_items di
           JOIN sales_order_items soi ON soi."id" = di."salesOrderItemId"
           WHERE di."deliveryId" = $1""",
        delivery["id"],
    )
    if not del_items:
        return f"No items found on delivery {delivery['deliveryNumber']}."

    invoice_id = str(uuid.uuid4())
    last = await fetch_one(
        'SELECT "invoiceNumber" FROM invoices ORDER BY "invoiceNumber" DESC LIMIT 1'
    )
    if last:
        num = int(last["invoiceNumber"].split("-")[1]) + 1
        invoice_number = f"INV-{num:04d}"
    else:
        invoice_number = "INV-0001"

    total_net = sum(float(di["netAmount"]) for di in del_items)
    total_tax = sum(float(di["taxAmount"]) for di in del_items)
    total_gross = round(total_net + total_tax, 2)
    invoice_date = datetime.now()
    due_date = invoice_date + timedelta(days=due_days)

    await execute(
        """INSERT INTO invoices
           ("id","invoiceNumber","salesOrderId","deliveryId","customerId",
            "invoiceDate","dueDate","totalNetAmount","totalTaxAmount",
            "totalGrossAmount","currency","status","createdAt","updatedAt")
           VALUES ($1,$2,$3,$4,$5,$6,$7,$8,$9,$10,'USD','OPEN'::"InvoiceStatus",NOW(),NOW())""",
        invoice_id, invoice_number, delivery["salesOrderId"], delivery["id"],
        delivery["customerId"], invoice_date, due_date,
        total_net, total_tax, total_gross,
    )

    for i, di in enumerate(del_items):
        await execute(
            """INSERT INTO invoice_items
               ("id","invoiceId","salesOrderItemId","deliveryItemId","materialId",
                "itemNumber","quantity","unitPrice","netAmount","taxAmount","currency","createdAt")
               VALUES ($1,$2,$3,$4,$5,$6,$7,$8,$9,$10,'USD',NOW())""",
            str(uuid.uuid4()), invoice_id, di["salesOrderItemId"], di["id"],
            di["materialId"], (i + 1) * 10, di["deliveredQuantity"],
            di["unitPrice"], di["netAmount"], di["taxAmount"],
        )

    return json.dumps({
        "message": f"Invoice {invoice_number} created for delivery {delivery['deliveryNumber']}",
        "invoiceNumber": invoice_number,
        "invoiceId": invoice_id,
        "totalGrossAmount": total_gross,
        "dueDate": due_date.isoformat(),
    })


@tool
async def get_overdue_invoices() -> str:
    """Get all overdue invoices — past due date with OPEN or PARTIALLY_PAID status."""
    rows = await fetch_all(
        """SELECT inv.*, c."customerNumber", c."name" as "customerName",
                  so."orderNumber",
                  (NOW() - inv."dueDate") as "days_overdue"
           FROM invoices inv
           JOIN customers c ON c."id" = inv."customerId"
           JOIN sales_orders so ON so."id" = inv."salesOrderId"
           WHERE inv."dueDate" < NOW()
             AND inv."status"::text IN ('OPEN','PARTIALLY_PAID')
           ORDER BY inv."dueDate" ASC
           LIMIT 100""",
    )
    if not rows:
        return "No overdue invoices found."
    return json.dumps(rows, indent=2)


@tool
async def get_invoice_aging() -> str:
    """Get invoice aging report — outstanding invoices grouped into aging buckets:
    Current (not yet due), 1-30 days, 31-60 days, 61-90 days, 90+ days overdue."""
    rows = await fetch_all(
        """SELECT inv."invoiceNumber", inv."totalGrossAmount", inv."dueDate",
                  inv."status"::text as "status",
                  c."customerNumber", c."name" as "customerName",
                  CASE
                    WHEN inv."dueDate" >= NOW() THEN 'CURRENT'
                    WHEN NOW() - inv."dueDate" <= INTERVAL '30 days' THEN '1-30_DAYS'
                    WHEN NOW() - inv."dueDate" <= INTERVAL '60 days' THEN '31-60_DAYS'
                    WHEN NOW() - inv."dueDate" <= INTERVAL '90 days' THEN '61-90_DAYS'
                    ELSE '90+_DAYS'
                  END as "aging_bucket"
           FROM invoices inv
           JOIN customers c ON c."id" = inv."customerId"
           WHERE inv."status"::text IN ('OPEN','PARTIALLY_PAID')
           ORDER BY inv."dueDate" ASC
           LIMIT 200""",
    )
    if not rows:
        return "No outstanding invoices."

    buckets = {"CURRENT": [], "1-30_DAYS": [], "31-60_DAYS": [], "61-90_DAYS": [], "90+_DAYS": []}
    for r in rows:
        buckets[r["aging_bucket"]].append(r)

    summary = {}
    for bucket, items in buckets.items():
        summary[bucket] = {
            "count": len(items),
            "total_amount": round(sum(i["totalGrossAmount"] for i in items), 2),
            "invoices": items,
        }
    return json.dumps(summary, indent=2)


all_invoice_tools = [
    get_invoice,
    list_invoices,
    create_invoice,
    get_overdue_invoices,
    get_invoice_aging,
]
