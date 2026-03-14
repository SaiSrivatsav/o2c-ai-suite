import json
import uuid
from datetime import datetime
from langchain_core.tools import tool
from langgraph.types import interrupt
from db.connection import fetch_all, fetch_one, execute, fetch_val


@tool
async def get_sales_order(identifier: str) -> str:
    """Get a sales order with all its items, partners, and pricing conditions.
    identifier: order number (SO-XXXX) or order ID."""
    order = await fetch_one(
        """SELECT so.*, c."customerNumber", c."name" as "customerName"
           FROM sales_orders so
           JOIN customers c ON c."id" = so."customerId"
           WHERE so."orderNumber" = $1 OR so."id" = $1""",
        identifier,
    )
    if not order:
        return f"No sales order found: {identifier}"

    oid = order["id"]
    items = await fetch_all(
        """SELECT soi.*, m."materialNumber"
           FROM sales_order_items soi
           JOIN materials m ON m."id" = soi."materialId"
           WHERE soi."salesOrderId" = $1 ORDER BY soi."itemNumber" """,
        oid,
    )
    partners = await fetch_all(
        """SELECT sp.*, c."customerNumber", c."name" as "partnerName"
           FROM sales_partners sp
           JOIN customers c ON c."id" = sp."customerId"
           WHERE sp."salesOrderId" = $1""",
        oid,
    )
    pricing = await fetch_all(
        """SELECT pc.*, soi."itemNumber"
           FROM pricing_conditions pc
           JOIN sales_order_items soi ON soi."id" = pc."salesOrderItemId"
           WHERE soi."salesOrderId" = $1""",
        oid,
    )

    result = {
        "order": order,
        "items": items,
        "partners": partners,
        "pricing_conditions": pricing,
    }
    return json.dumps(result, indent=2)


@tool
async def list_sales_orders(
    customer_identifier: str = "",
    status: str = "",
    date_from: str = "",
    date_to: str = "",
    min_amount: float = 0,
    max_amount: float = 999999999,
    limit: int = 50,
) -> str:
    """Search sales orders with filters. Returns at most `limit` rows (default 50).
    status: DRAFT, OPEN, IN_DELIVERY, COMPLETED, CANCELLED. date_from/date_to: YYYY-MM-DD format."""
    conditions = []
    params: list = []
    idx = 1

    if customer_identifier:
        conditions.append(
            f"""so."customerId" IN (SELECT "id" FROM customers WHERE "customerNumber" = ${idx} OR "id" = ${idx})"""
        )
        params.append(customer_identifier)
        idx += 1
    if status:
        conditions.append(f'so."status"::text = ${idx}')
        params.append(status)
        idx += 1
    if date_from:
        conditions.append(f'so."orderDate" >= ${idx}')
        params.append(datetime.fromisoformat(date_from))
        idx += 1
    if date_to:
        conditions.append(f'so."orderDate" <= ${idx}')
        params.append(datetime.fromisoformat(date_to + "T23:59:59"))
        idx += 1

    conditions.append(f'so."totalGrossAmount" >= ${idx}')
    params.append(min_amount)
    idx += 1
    conditions.append(f'so."totalGrossAmount" <= ${idx}')
    params.append(max_amount)

    where = " AND ".join(conditions) if conditions else "TRUE"
    actual_limit = min(limit, 200)
    params.append(actual_limit)
    rows = await fetch_all(
        f"""SELECT so.*, c."customerNumber", c."name" as "customerName"
            FROM sales_orders so
            JOIN customers c ON c."id" = so."customerId"
            WHERE {where}
            ORDER BY so."orderDate" DESC
            LIMIT ${len(params)}""",
        *params,
    )
    if not rows:
        return "No sales orders found matching the criteria."
    total = await fetch_val(
        f'SELECT COUNT(*) FROM sales_orders so WHERE {where}', *params[:-1]
    )
    header = f"Showing {len(rows)} of {total} orders.\n" if total > len(rows) else ""
    return header + json.dumps(rows, indent=2)


@tool
async def create_sales_order(
    customer_identifier: str,
    items_json: str,
    requested_delivery_date: str = "",
    payment_terms: str = "NET30",
    sales_org: str = "1000",
    distribution_channel: str = "10",
    division: str = "00",
) -> str:
    """Create a new sales order. customer_identifier: customer number or ID.
    items_json: JSON array of items, each with materialIdentifier (MAT-XXXX), quantity, and optional unitPrice.
    Example items_json: [{"materialIdentifier":"MAT-0001","quantity":10}]
    If unitPrice is omitted, the material's base price is used."""
    # Validate customer
    customer = await fetch_one(
        'SELECT "id","customerNumber","creditLimit" FROM customers WHERE "customerNumber" = $1 OR "id" = $1',
        customer_identifier,
    )
    if not customer:
        return f"Customer not found: {customer_identifier}"

    items = json.loads(items_json)
    if not items:
        return "At least one item is required."

    order_id = str(uuid.uuid4())
    last = await fetch_one(
        'SELECT "orderNumber" FROM sales_orders ORDER BY "orderNumber" DESC LIMIT 1'
    )
    if last:
        num = int(last["orderNumber"].split("-")[1]) + 1
        order_number = f"SO-{num:04d}"
    else:
        order_number = "SO-0001"

    total_net = 0.0
    total_tax = 0.0
    item_records = []

    for i, itm in enumerate(items):
        mat = await fetch_one(
            'SELECT * FROM materials WHERE "materialNumber" = $1 OR "id" = $1',
            itm["materialIdentifier"],
        )
        if not mat:
            return f"Material not found: {itm['materialIdentifier']}"

        qty = float(itm["quantity"])
        price = float(itm.get("unitPrice", mat["basePrice"]))
        net = round(qty * price, 2)
        tax = round(net * 0.18, 2)  # 18% tax
        total_net += net
        total_tax += tax

        item_records.append({
            "id": str(uuid.uuid4()),
            "salesOrderId": order_id,
            "itemNumber": (i + 1) * 10,
            "materialId": mat["id"],
            "description": mat["description"],
            "quantity": qty,
            "unitOfMeasure": mat["unitOfMeasure"],
            "unitPrice": price,
            "netAmount": net,
            "taxAmount": tax,
            "currency": mat["currency"],
        })

    total_gross = round(total_net + total_tax, 2)

    # Check credit limit
    outstanding = await fetch_val(
        """SELECT COALESCE(SUM("totalGrossAmount"), 0) FROM invoices
           WHERE "customerId" = $1 AND "status" IN ('OPEN','PARTIALLY_PAID')""",
        customer["id"],
    ) or 0
    if float(outstanding) + total_gross > customer["creditLimit"]:
        approval = interrupt({
            "type": "credit_limit_exceeded",
            "customer": customer["customerNumber"],
            "credit_limit": customer["creditLimit"],
            "current_outstanding": float(outstanding),
            "new_order_amount": total_gross,
            "total_exposure": float(outstanding) + total_gross,
            "message": (
                f"Order total ${total_gross:,.2f} would exceed credit limit "
                f"(${customer['creditLimit']:,.2f}) for {customer['customerNumber']}. "
                f"Current outstanding: ${float(outstanding):,.2f}. Approve?"
            ),
        })
        if not approval.get("approved"):
            return f"Sales order creation rejected — credit limit exceeded for {customer['customerNumber']}."

    # Insert order
    req_date = datetime.fromisoformat(requested_delivery_date) if requested_delivery_date else None
    await execute(
        """INSERT INTO sales_orders
           ("id","orderNumber","customerId","orderDate","requestedDeliveryDate",
            "salesOrg","distributionChannel","division","totalNetAmount",
            "totalTaxAmount","totalGrossAmount","currency","status","paymentTerms",
            "createdAt","updatedAt")
           VALUES ($1,$2,$3,NOW(),$4,$5,$6,$7,$8,$9,$10,'USD','OPEN'::\"SalesOrderStatus\",$11,NOW(),NOW())""",
        order_id, order_number, customer["id"], req_date,
        sales_org, distribution_channel, division,
        total_net, total_tax, total_gross, payment_terms,
    )

    # Insert items
    for itm in item_records:
        await execute(
            """INSERT INTO sales_order_items
               ("id","salesOrderId","itemNumber","materialId","description",
                "quantity","unitOfMeasure","unitPrice","netAmount","taxAmount",
                "currency","status","createdAt","updatedAt")
               VALUES ($1,$2,$3,$4,$5,$6,$7,$8,$9,$10,$11,'OPEN'::"SalesOrderItemStatus",NOW(),NOW())""",
            itm["id"], itm["salesOrderId"], itm["itemNumber"], itm["materialId"],
            itm["description"], itm["quantity"], itm["unitOfMeasure"],
            itm["unitPrice"], itm["netAmount"], itm["taxAmount"], itm["currency"],
        )

    # Insert SOLD_TO partner
    await execute(
        """INSERT INTO sales_partners ("id","salesOrderId","customerId","partnerFunction","createdAt")
           VALUES ($1,$2,$3,'SOLD_TO'::"PartnerFunction",NOW())""",
        str(uuid.uuid4()), order_id, customer["id"],
    )

    return json.dumps({
        "message": f"Sales order {order_number} created successfully",
        "orderNumber": order_number,
        "orderId": order_id,
        "totalNetAmount": total_net,
        "totalTaxAmount": total_tax,
        "totalGrossAmount": total_gross,
        "itemCount": len(item_records),
    })


@tool
async def update_sales_order_status(order_identifier: str, new_status: str) -> str:
    """Update a sales order's status. Valid transitions:
    DRAFT -> OPEN, OPEN -> IN_DELIVERY, IN_DELIVERY -> COMPLETED, any -> CANCELLED."""
    order = await fetch_one(
        'SELECT "id","orderNumber","status" FROM sales_orders WHERE "orderNumber" = $1 OR "id" = $1',
        order_identifier,
    )
    if not order:
        return f"No order found: {order_identifier}"

    valid_transitions = {
        "DRAFT": ["OPEN", "CANCELLED"],
        "OPEN": ["IN_DELIVERY", "CANCELLED"],
        "IN_DELIVERY": ["COMPLETED", "CANCELLED"],
        "COMPLETED": [],
        "CANCELLED": [],
    }
    current = order["status"]
    if new_status not in valid_transitions.get(current, []):
        return f"Invalid transition: {current} -> {new_status}. Allowed: {valid_transitions.get(current, [])}"

    await execute(
        """UPDATE sales_orders SET "status" = $1::"SalesOrderStatus", "updatedAt" = NOW()
           WHERE "id" = $2""",
        new_status, order["id"],
    )
    return f"Order {order['orderNumber']} status updated: {current} -> {new_status}"


@tool
async def add_sales_order_item(
    order_identifier: str,
    material_identifier: str,
    quantity: float,
    unit_price: float = -1,
) -> str:
    """Add a line item to an existing DRAFT or OPEN sales order."""
    order = await fetch_one(
        'SELECT * FROM sales_orders WHERE "orderNumber" = $1 OR "id" = $1',
        order_identifier,
    )
    if not order:
        return f"No order found: {order_identifier}"
    if order["status"] not in ("DRAFT", "OPEN"):
        return f"Cannot add items to order in {order['status']} status."

    mat = await fetch_one(
        'SELECT * FROM materials WHERE "materialNumber" = $1 OR "id" = $1',
        material_identifier,
    )
    if not mat:
        return f"Material not found: {material_identifier}"

    last_item = await fetch_one(
        'SELECT MAX("itemNumber") as max_num FROM sales_order_items WHERE "salesOrderId" = $1',
        order["id"],
    )
    next_item_num = (last_item["max_num"] or 0) + 10

    price = unit_price if unit_price >= 0 else mat["basePrice"]
    net = round(quantity * price, 2)
    tax = round(net * 0.18, 2)

    await execute(
        """INSERT INTO sales_order_items
           ("id","salesOrderId","itemNumber","materialId","description",
            "quantity","unitOfMeasure","unitPrice","netAmount","taxAmount",
            "currency","status","createdAt","updatedAt")
           VALUES ($1,$2,$3,$4,$5,$6,$7,$8,$9,$10,$11,'OPEN'::"SalesOrderItemStatus",NOW(),NOW())""",
        str(uuid.uuid4()), order["id"], next_item_num, mat["id"],
        mat["description"], quantity, mat["unitOfMeasure"],
        price, net, tax, mat["currency"],
    )

    # Update order totals
    new_net = order["totalNetAmount"] + net
    new_tax = order["totalTaxAmount"] + tax
    new_gross = new_net + new_tax
    await execute(
        """UPDATE sales_orders SET "totalNetAmount"=$1, "totalTaxAmount"=$2,
           "totalGrossAmount"=$3, "updatedAt"=NOW() WHERE "id"=$4""",
        new_net, new_tax, new_gross, order["id"],
    )
    return f"Item {next_item_num} ({mat['description']}) added to {order['orderNumber']}. New total: ${new_gross:,.2f}"


@tool
async def cancel_sales_order(order_identifier: str) -> str:
    """Cancel a sales order. If deliveries or invoices exist, human approval is required."""
    order = await fetch_one(
        'SELECT * FROM sales_orders WHERE "orderNumber" = $1 OR "id" = $1',
        order_identifier,
    )
    if not order:
        return f"No order found: {order_identifier}"
    if order["status"] == "CANCELLED":
        return f"Order {order['orderNumber']} is already cancelled."
    if order["status"] == "COMPLETED":
        return f"Cannot cancel a completed order."

    deliveries = await fetch_all(
        'SELECT "deliveryNumber","status" FROM deliveries WHERE "salesOrderId" = $1',
        order["id"],
    )
    invoices = await fetch_all(
        'SELECT "invoiceNumber","status" FROM invoices WHERE "salesOrderId" = $1',
        order["id"],
    )

    if deliveries or invoices:
        approval = interrupt({
            "type": "order_cancellation",
            "orderNumber": order["orderNumber"],
            "deliveries": deliveries,
            "invoices": invoices,
            "message": (
                f"Order {order['orderNumber']} has {len(deliveries)} deliveries "
                f"and {len(invoices)} invoices. Confirm cancellation?"
            ),
        })
        if not approval.get("approved"):
            return f"Cancellation of {order['orderNumber']} was rejected."

    await execute(
        """UPDATE sales_orders SET "status" = 'CANCELLED'::"SalesOrderStatus", "updatedAt" = NOW()
           WHERE "id" = $1""",
        order["id"],
    )
    await execute(
        """UPDATE sales_order_items SET "status" = 'CANCELLED'::"SalesOrderItemStatus", "updatedAt" = NOW()
           WHERE "salesOrderId" = $1""",
        order["id"],
    )
    return f"Sales order {order['orderNumber']} and all its items have been cancelled."


@tool
async def get_sales_order_history(order_identifier: str) -> str:
    """Get the full document flow for a sales order: order -> deliveries -> invoices -> payments -> credit memos."""
    order = await fetch_one(
        """SELECT so.*, c."customerNumber", c."name" as "customerName"
           FROM sales_orders so JOIN customers c ON c."id" = so."customerId"
           WHERE so."orderNumber" = $1 OR so."id" = $1""",
        order_identifier,
    )
    if not order:
        return f"No order found: {order_identifier}"

    oid = order["id"]
    deliveries = await fetch_all(
        'SELECT * FROM deliveries WHERE "salesOrderId" = $1 ORDER BY "deliveryDate"', oid
    )
    invoices = await fetch_all(
        'SELECT * FROM invoices WHERE "salesOrderId" = $1 ORDER BY "invoiceDate"', oid
    )

    payment_ids = [inv["id"] for inv in invoices]
    payments = []
    for inv_id in payment_ids:
        pays = await fetch_all(
            'SELECT * FROM payments WHERE "invoiceId" = $1 ORDER BY "paymentDate"', inv_id
        )
        payments.extend(pays)

    credit_memos = await fetch_all(
        'SELECT * FROM credit_memos WHERE "salesOrderId" = $1 ORDER BY "creditDate"', oid
    )

    result = {
        "order": order,
        "document_flow": {
            "deliveries": deliveries,
            "invoices": invoices,
            "payments": payments,
            "credit_memos": credit_memos,
        },
    }
    return json.dumps(result, indent=2)


all_order_tools = [
    get_sales_order,
    list_sales_orders,
    create_sales_order,
    update_sales_order_status,
    add_sales_order_item,
    cancel_sales_order,
    get_sales_order_history,
]
