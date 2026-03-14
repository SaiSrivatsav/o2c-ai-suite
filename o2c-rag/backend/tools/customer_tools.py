import json
import uuid
from langchain_core.tools import tool
from db.connection import fetch_all, fetch_one, execute, fetch_val


@tool
async def get_customer(identifier: str) -> str:
    """Get customer details by customer ID or customer number (e.g. CUST-0001).
    Returns full customer record including credit limit, payment terms, and contact info."""
    row = await fetch_one(
        'SELECT * FROM customers WHERE "customerNumber" = $1 OR "id" = $1',
        identifier,
    )
    if not row:
        return f"No customer found with identifier: {identifier}"
    return json.dumps(row, indent=2)


@tool
async def list_customers(
    name: str = "",
    customer_group: str = "",
    country: str = "",
    is_active: bool = True,
    min_credit_limit: float = 0,
    max_credit_limit: float = 999999999,
    limit: int = 50,
) -> str:
    """Search and filter customers. All parameters are optional. Returns at most `limit` rows (default 50).
    customer_group can be DOMESTIC, EXPORT, or INTERCOMPANY."""
    conditions = ['"isActive" = $1']
    params: list = [is_active]
    idx = 2

    if name:
        conditions.append(f'"name" ILIKE ${idx}')
        params.append(f"%{name}%")
        idx += 1
    if customer_group:
        conditions.append(f'"customerGroup"::text = ${idx}')
        params.append(customer_group)
        idx += 1
    if country:
        conditions.append(f'"country" ILIKE ${idx}')
        params.append(f"%{country}%")
        idx += 1

    conditions.append(f'"creditLimit" >= ${idx}')
    params.append(min_credit_limit)
    idx += 1
    conditions.append(f'"creditLimit" <= ${idx}')
    params.append(max_credit_limit)

    where = " AND ".join(conditions)
    actual_limit = min(limit, 200)
    idx_limit = idx
    rows = await fetch_all(
        f'SELECT * FROM customers WHERE {where} ORDER BY "customerNumber" LIMIT ${idx_limit}',
        *params, actual_limit,
    )
    if not rows:
        return "No customers found matching the criteria."
    total = await fetch_val(f'SELECT COUNT(*) FROM customers WHERE {where}', *params)
    header = f"Showing {len(rows)} of {total} customers.\n" if total > len(rows) else ""
    return header + json.dumps(rows, indent=2)


@tool
async def create_customer(
    name: str,
    email: str,
    phone: str,
    address: str,
    city: str,
    country: str,
    postal_code: str,
    credit_limit: float,
    payment_terms: str = "NET30",
    customer_group: str = "DOMESTIC",
    state_province: str = "",
) -> str:
    """Create (onboard) a new customer in the O2C system.
    payment_terms: NET30, NET60, NET90. customer_group: DOMESTIC, EXPORT, INTERCOMPANY."""
    customer_id = str(uuid.uuid4())

    last = await fetch_one(
        'SELECT "customerNumber" FROM customers ORDER BY "customerNumber" DESC LIMIT 1'
    )
    if last:
        num = int(last["customerNumber"].split("-")[1]) + 1
        customer_number = f"CUST-{num:04d}"
    else:
        customer_number = "CUST-0001"

    await execute(
        """INSERT INTO customers
           ("id","customerNumber","name","email","phone","address","city",
            "state","postalCode","country","creditLimit","paymentTerms",
            "customerGroup","isActive","createdAt","updatedAt")
           VALUES ($1,$2,$3,$4,$5,$6,$7,$8,$9,$10,$11,$12,$13::\"CustomerGroup\",true,NOW(),NOW())""",
        customer_id, customer_number, name, email, phone, address, city,
        state_province or None, postal_code, country, credit_limit,
        payment_terms, customer_group,
    )
    return json.dumps({
        "message": f"Customer {customer_number} ({name}) created successfully",
        "customerId": customer_id,
        "customerNumber": customer_number,
    })


@tool
async def update_customer(
    identifier: str,
    name: str = "",
    email: str = "",
    phone: str = "",
    address: str = "",
    city: str = "",
    country: str = "",
    postal_code: str = "",
    credit_limit: float = -1,
    payment_terms: str = "",
    customer_group: str = "",
    state_province: str = "",
) -> str:
    """Update an existing customer's fields. Only non-empty values are applied.
    identifier: customer number (CUST-XXXX) or ID."""
    customer = await fetch_one(
        'SELECT * FROM customers WHERE "customerNumber" = $1 OR "id" = $1',
        identifier,
    )
    if not customer:
        return f"No customer found: {identifier}"

    updates, params = [], []
    idx = 1
    field_map = {
        "name": name, "email": email, "phone": phone,
        "address": address, "city": city, "country": country,
        "postalCode": postal_code, "paymentTerms": payment_terms,
        "state": state_province,
    }
    for col, val in field_map.items():
        if val:
            updates.append(f'"{col}" = ${idx}')
            params.append(val)
            idx += 1
    if customer_group:
        updates.append(f'"customerGroup" = ${idx}::"CustomerGroup"')
        params.append(customer_group)
        idx += 1
    if credit_limit >= 0:
        updates.append(f'"creditLimit" = ${idx}')
        params.append(credit_limit)
        idx += 1

    if not updates:
        return "No fields to update."

    updates.append('"updatedAt" = NOW()')
    params.append(customer["id"])

    await execute(
        f'UPDATE customers SET {", ".join(updates)} WHERE "id" = ${idx}',
        *params,
    )
    return f"Customer {customer['customerNumber']} updated successfully."


@tool
async def deactivate_customer(identifier: str) -> str:
    """Deactivate (soft-delete) a customer. identifier: customer number or ID."""
    customer = await fetch_one(
        'SELECT "id","customerNumber" FROM customers WHERE "customerNumber" = $1 OR "id" = $1',
        identifier,
    )
    if not customer:
        return f"No customer found: {identifier}"
    await execute(
        'UPDATE customers SET "isActive" = false, "updatedAt" = NOW() WHERE "id" = $1',
        customer["id"],
    )
    return f"Customer {customer['customerNumber']} has been deactivated."


@tool
async def get_customer_360(identifier: str) -> str:
    """Get a complete 360-degree view of a customer — all orders, invoices, payments,
    credit memos, outstanding balance, and credit utilization."""
    customer = await fetch_one(
        'SELECT * FROM customers WHERE "customerNumber" = $1 OR "id" = $1',
        identifier,
    )
    if not customer:
        return f"No customer found: {identifier}"

    cid = customer["id"]

    orders = await fetch_all(
        """SELECT "orderNumber","orderDate","totalGrossAmount","currency","status"
           FROM sales_orders WHERE "customerId" = $1 ORDER BY "orderDate" DESC LIMIT 50""",
        cid,
    )
    invoices = await fetch_all(
        """SELECT "invoiceNumber","invoiceDate","dueDate","totalGrossAmount","status"
           FROM invoices WHERE "customerId" = $1 ORDER BY "invoiceDate" DESC LIMIT 50""",
        cid,
    )
    payments = await fetch_all(
        """SELECT "paymentNumber","paymentDate","amount","paymentMethod","status"
           FROM payments WHERE "customerId" = $1 ORDER BY "paymentDate" DESC LIMIT 50""",
        cid,
    )
    credit_memos = await fetch_all(
        """SELECT "creditMemoNumber","creditDate","totalAmount","reason","status"
           FROM credit_memos WHERE "customerId" = $1 ORDER BY "creditDate" DESC LIMIT 50""",
        cid,
    )

    total_outstanding = sum(
        inv["totalGrossAmount"]
        for inv in invoices
        if inv["status"] in ("OPEN", "PARTIALLY_PAID")
    )
    total_paid = sum(p["amount"] for p in payments if p["status"] == "CLEARED")
    total_credits = sum(
        cm["totalAmount"] for cm in credit_memos if cm["status"] == "POSTED"
    )
    balance = total_outstanding - total_paid - total_credits
    credit_limit = customer["creditLimit"]
    utilization = round(balance / credit_limit * 100, 1) if credit_limit > 0 else 0

    result = {
        "customer": customer,
        "summary": {
            "total_orders": len(orders),
            "total_invoices": len(invoices),
            "total_payments": len(payments),
            "total_credit_memos": len(credit_memos),
            "outstanding_balance": round(balance, 2),
            "credit_limit": credit_limit,
            "credit_utilization_pct": utilization,
        },
        "orders": orders,
        "invoices": invoices,
        "payments": payments,
        "credit_memos": credit_memos,
    }
    return json.dumps(result, indent=2)


# Convenience list for agent registration
all_customer_tools = [
    get_customer,
    list_customers,
    create_customer,
    update_customer,
    deactivate_customer,
    get_customer_360,
]
