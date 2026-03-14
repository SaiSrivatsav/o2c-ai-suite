import json
import uuid
from datetime import datetime
from langchain_core.tools import tool
from db.connection import fetch_all, fetch_one, execute


@tool
async def get_delivery(identifier: str) -> str:
    """Get delivery details with items and tracking info.
    identifier: delivery number (DL-XXXX) or ID."""
    delivery = await fetch_one(
        """SELECT d.*, so."orderNumber"
           FROM deliveries d
           JOIN sales_orders so ON so."id" = d."salesOrderId"
           WHERE d."deliveryNumber" = $1 OR d."id" = $1""",
        identifier,
    )
    if not delivery:
        return f"No delivery found: {identifier}"

    items = await fetch_all(
        """SELECT di.*, m."materialNumber", m."description" as "materialDescription"
           FROM delivery_items di
           JOIN materials m ON m."id" = di."materialId"
           WHERE di."deliveryId" = $1 ORDER BY di."itemNumber" """,
        delivery["id"],
    )

    result = {"delivery": delivery, "items": items}
    return json.dumps(result, indent=2)


@tool
async def list_deliveries(
    order_identifier: str = "",
    status: str = "",
    carrier: str = "",
    date_from: str = "",
    date_to: str = "",
    limit: int = 50,
) -> str:
    """Search deliveries. Returns at most `limit` rows (default 50).
    status: PLANNED, PICKED, PACKED, SHIPPED, DELIVERED. date_from/date_to: YYYY-MM-DD."""
    conditions = []
    params: list = []
    idx = 1

    if order_identifier:
        conditions.append(
            f"""d."salesOrderId" IN (SELECT "id" FROM sales_orders WHERE "orderNumber" = ${idx} OR "id" = ${idx})"""
        )
        params.append(order_identifier)
        idx += 1
    if status:
        conditions.append(f'd."status"::text = ${idx}')
        params.append(status)
        idx += 1
    if carrier:
        conditions.append(f'd."carrier" ILIKE ${idx}')
        params.append(f"%{carrier}%")
        idx += 1
    if date_from:
        conditions.append(f'd."deliveryDate" >= ${idx}')
        params.append(datetime.fromisoformat(date_from))
        idx += 1
    if date_to:
        conditions.append(f'd."deliveryDate" <= ${idx}')
        params.append(datetime.fromisoformat(date_to + "T23:59:59"))
        idx += 1

    where = " AND ".join(conditions) if conditions else "TRUE"
    actual_limit = min(limit, 200)
    params.append(actual_limit)
    rows = await fetch_all(
        f"""SELECT d.*, so."orderNumber"
            FROM deliveries d
            JOIN sales_orders so ON so."id" = d."salesOrderId"
            WHERE {where} ORDER BY d."deliveryDate" DESC
            LIMIT ${len(params)}""",
        *params,
    )
    if not rows:
        return "No deliveries found matching the criteria."
    return json.dumps(rows, indent=2)


@tool
async def create_delivery(
    order_identifier: str,
    shipping_address: str,
    shipping_point: str = "SP01",
    carrier: str = "",
    delivery_date: str = "",
) -> str:
    """Create a delivery for a sales order. Only OPEN items will be included.
    delivery_date: YYYY-MM-DD (defaults to today)."""
    order = await fetch_one(
        'SELECT * FROM sales_orders WHERE "orderNumber" = $1 OR "id" = $1',
        order_identifier,
    )
    if not order:
        return f"No order found: {order_identifier}"
    if order["status"] not in ("OPEN", "IN_DELIVERY"):
        return f"Cannot create delivery for order in {order['status']} status."

    open_items = await fetch_all(
        """SELECT soi.*, m."weight", m."weightUnit"
           FROM sales_order_items soi
           JOIN materials m ON m."id" = soi."materialId"
           WHERE soi."salesOrderId" = $1 AND soi."status"::text = 'OPEN'""",
        order["id"],
    )
    if not open_items:
        return f"No open items on order {order['orderNumber']} to deliver."

    delivery_id = str(uuid.uuid4())
    last = await fetch_one(
        'SELECT "deliveryNumber" FROM deliveries ORDER BY "deliveryNumber" DESC LIMIT 1'
    )
    if last:
        num = int(last["deliveryNumber"].split("-")[1]) + 1
        delivery_number = f"DL-{num:04d}"
    else:
        delivery_number = "DL-0001"

    total_weight = sum(
        (itm.get("weight") or 0) * itm["quantity"] for itm in open_items
    )
    del_date = datetime.fromisoformat(delivery_date) if delivery_date else datetime.now()

    await execute(
        """INSERT INTO deliveries
           ("id","deliveryNumber","salesOrderId","deliveryDate","shippingPoint",
            "shippingAddress","trackingNumber","carrier","status","totalWeight",
            "weightUnit","createdAt","updatedAt")
           VALUES ($1,$2,$3,$4,$5,$6,NULL,$7,'PLANNED'::"DeliveryStatus",$8,'KG',NOW(),NOW())""",
        delivery_id, delivery_number, order["id"], del_date,
        shipping_point, shipping_address, carrier or None, total_weight,
    )

    # Create delivery items
    for i, itm in enumerate(open_items):
        batch_number = f"BATCH-{uuid.uuid4().hex[:5].upper()}"
        await execute(
            """INSERT INTO delivery_items
               ("id","deliveryId","salesOrderItemId","itemNumber","materialId",
                "deliveredQuantity","unitOfMeasure","batchNumber","createdAt","updatedAt")
               VALUES ($1,$2,$3,$4,$5,$6,$7,$8,NOW(),NOW())""",
            str(uuid.uuid4()), delivery_id, itm["id"], (i + 1) * 10,
            itm["materialId"], itm["quantity"], itm["unitOfMeasure"], batch_number,
        )

    # Update SO item statuses to DELIVERED and order to IN_DELIVERY
    for itm in open_items:
        await execute(
            """UPDATE sales_order_items SET "status" = 'DELIVERED'::"SalesOrderItemStatus", "updatedAt" = NOW()
               WHERE "id" = $1""",
            itm["id"],
        )
    if order["status"] == "OPEN":
        await execute(
            """UPDATE sales_orders SET "status" = 'IN_DELIVERY'::"SalesOrderStatus", "updatedAt" = NOW()
               WHERE "id" = $1""",
            order["id"],
        )

    return json.dumps({
        "message": f"Delivery {delivery_number} created for order {order['orderNumber']}",
        "deliveryNumber": delivery_number,
        "deliveryId": delivery_id,
        "itemCount": len(open_items),
        "totalWeight": round(total_weight, 3),
    })


@tool
async def update_delivery_status(delivery_identifier: str, new_status: str) -> str:
    """Update delivery status. Valid transitions: PLANNED->PICKED->PACKED->SHIPPED->DELIVERED."""
    delivery = await fetch_one(
        'SELECT "id","deliveryNumber","status" FROM deliveries WHERE "deliveryNumber" = $1 OR "id" = $1',
        delivery_identifier,
    )
    if not delivery:
        return f"No delivery found: {delivery_identifier}"

    valid_transitions = {
        "PLANNED": ["PICKED"],
        "PICKED": ["PACKED"],
        "PACKED": ["SHIPPED"],
        "SHIPPED": ["DELIVERED"],
        "DELIVERED": [],
    }
    current = delivery["status"]
    if new_status not in valid_transitions.get(current, []):
        return f"Invalid transition: {current} -> {new_status}. Allowed: {valid_transitions.get(current, [])}"

    await execute(
        """UPDATE deliveries SET "status" = $1::"DeliveryStatus", "updatedAt" = NOW()
           WHERE "id" = $2""",
        new_status, delivery["id"],
    )
    return f"Delivery {delivery['deliveryNumber']} status updated: {current} -> {new_status}"


@tool
async def update_tracking_info(
    delivery_identifier: str,
    tracking_number: str,
    carrier: str = "",
) -> str:
    """Update tracking number and carrier for a delivery."""
    delivery = await fetch_one(
        'SELECT "id","deliveryNumber" FROM deliveries WHERE "deliveryNumber" = $1 OR "id" = $1',
        delivery_identifier,
    )
    if not delivery:
        return f"No delivery found: {delivery_identifier}"

    updates = ['"trackingNumber" = $1']
    params: list = [tracking_number]
    idx = 2
    if carrier:
        updates.append(f'"carrier" = ${idx}')
        params.append(carrier)
        idx += 1
    updates.append('"updatedAt" = NOW()')
    params.append(delivery["id"])

    await execute(
        f'UPDATE deliveries SET {", ".join(updates)} WHERE "id" = ${idx}',
        *params,
    )
    return f"Tracking updated for {delivery['deliveryNumber']}: {tracking_number}"


all_delivery_tools = [
    get_delivery,
    list_deliveries,
    create_delivery,
    update_delivery_status,
    update_tracking_info,
]
