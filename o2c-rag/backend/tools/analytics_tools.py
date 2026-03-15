import json
from datetime import datetime
from langchain_core.tools import tool
from db.connection import fetch_all, fetch_one


@tool
async def get_order_analytics(
    period_from: str = "",
    period_to: str = "",
    customer_identifier: str = "",
) -> str:
    """Get sales order analytics — counts, amounts, and status breakdown.
    period_from/period_to: YYYY-MM-DD. Returns totals, averages, and status distribution."""
    conditions = []
    params: list = []
    idx = 1

    if period_from:
        conditions.append(f'so."orderDate" >= ${idx}::timestamp')
        params.append(datetime.fromisoformat(period_from))
        idx += 1
    if period_to:
        conditions.append(f'so."orderDate" <= ${idx}::timestamp')
        params.append(datetime.fromisoformat(period_to + "T23:59:59"))
        idx += 1
    if customer_identifier:
        conditions.append(
            f"""so."customerId" IN (SELECT "id" FROM customers WHERE "customerNumber" = ${idx} OR "id" = ${idx})"""
        )
        params.append(customer_identifier)
        idx += 1

    where = "WHERE " + " AND ".join(conditions) if conditions else ""

    summary = await fetch_one(
        f"""SELECT COUNT(*) as total_orders,
                   COALESCE(SUM("totalGrossAmount"), 0) as total_revenue,
                   COALESCE(AVG("totalGrossAmount"), 0) as avg_order_value,
                   COALESCE(MIN("totalGrossAmount"), 0) as min_order_value,
                   COALESCE(MAX("totalGrossAmount"), 0) as max_order_value
            FROM sales_orders so {where}""",
        *params,
    )

    status_breakdown = await fetch_all(
        f"""SELECT "status"::text as status, COUNT(*) as count,
                   COALESCE(SUM("totalGrossAmount"), 0) as total_amount
            FROM sales_orders so {where}
            GROUP BY "status" ORDER BY count DESC""",
        *params,
    )

    monthly = await fetch_all(
        f"""SELECT TO_CHAR("orderDate", 'YYYY-MM') as month,
                   COUNT(*) as orders,
                   COALESCE(SUM("totalGrossAmount"), 0) as revenue
            FROM sales_orders so {where}
            GROUP BY month ORDER BY month DESC LIMIT 12""",
        *params,
    )

    result = {
        "summary": summary,
        "status_breakdown": status_breakdown,
        "monthly_trend": monthly,
    }
    return json.dumps(result, indent=2)


@tool
async def get_revenue_analytics(
    period_from: str = "",
    period_to: str = "",
    group_by: str = "customer",
) -> str:
    """Get revenue analytics. group_by: 'customer', 'material_group', or 'month'.
    Shows revenue breakdown by the specified dimension."""
    conditions = []
    params: list = []
    idx = 1

    if period_from:
        conditions.append(f'inv."invoiceDate" >= ${idx}::timestamp')
        params.append(datetime.fromisoformat(period_from))
        idx += 1
    if period_to:
        conditions.append(f'inv."invoiceDate" <= ${idx}::timestamp')
        params.append(datetime.fromisoformat(period_to + "T23:59:59"))
        idx += 1

    where = "WHERE " + " AND ".join(conditions) if conditions else ""

    if group_by == "customer":
        rows = await fetch_all(
            f"""SELECT c."customerNumber", c."name" as "customerName",
                       COUNT(DISTINCT inv."id") as invoice_count,
                       COALESCE(SUM(inv."totalGrossAmount"), 0) as total_revenue
                FROM invoices inv
                JOIN customers c ON c."id" = inv."customerId"
                {where}
                GROUP BY c."customerNumber", c."name"
                ORDER BY total_revenue DESC
                LIMIT 50""",
            *params,
        )
    elif group_by == "material_group":
        rows = await fetch_all(
            f"""SELECT m."materialGroup",
                       COUNT(DISTINCT ii."id") as item_count,
                       COALESCE(SUM(ii."netAmount"), 0) as total_revenue
                FROM invoice_items ii
                JOIN materials m ON m."id" = ii."materialId"
                JOIN invoices inv ON inv."id" = ii."invoiceId"
                {where}
                GROUP BY m."materialGroup"
                ORDER BY total_revenue DESC""",
            *params,
        )
    else:  # month
        rows = await fetch_all(
            f"""SELECT TO_CHAR(inv."invoiceDate", 'YYYY-MM') as month,
                       COUNT(*) as invoice_count,
                       COALESCE(SUM(inv."totalGrossAmount"), 0) as total_revenue
                FROM invoices inv
                {where}
                GROUP BY month ORDER BY month DESC""",
            *params,
        )

    total = await fetch_one(
        f"""SELECT COUNT(*) as total_invoices,
                   COALESCE(SUM("totalGrossAmount"), 0) as total_revenue
            FROM invoices inv {where}""",
        *params,
    )

    return json.dumps({"total": total, "breakdown": rows}, indent=2)


@tool
async def get_payment_analytics(
    period_from: str = "",
    period_to: str = "",
) -> str:
    """Get payment collection analytics — collection rate, average days to pay,
    payment method breakdown."""
    conditions = []
    params: list = []
    idx = 1

    if period_from:
        conditions.append(f'p."paymentDate" >= ${idx}::timestamp')
        params.append(datetime.fromisoformat(period_from))
        idx += 1
    if period_to:
        conditions.append(f'p."paymentDate" <= ${idx}::timestamp')
        params.append(datetime.fromisoformat(period_to + "T23:59:59"))
        idx += 1

    where = "WHERE " + " AND ".join(conditions) if conditions else ""

    summary = await fetch_one(
        f"""SELECT COUNT(*) as total_payments,
                   COALESCE(SUM(CASE WHEN "status"::text = 'CLEARED' THEN "amount" ELSE 0 END), 0) as total_collected,
                   COALESCE(SUM(CASE WHEN "status"::text = 'REVERSED' THEN "amount" ELSE 0 END), 0) as total_reversed,
                   COUNT(CASE WHEN "status"::text = 'CLEARED' THEN 1 END) as cleared_count,
                   COUNT(CASE WHEN "status"::text = 'REVERSED' THEN 1 END) as reversed_count
            FROM payments p {where}""",
        *params,
    )

    method_breakdown = await fetch_all(
        f"""SELECT "paymentMethod"::text as method,
                   COUNT(*) as count,
                   COALESCE(SUM("amount"), 0) as total_amount
            FROM payments p {where}
            GROUP BY "paymentMethod" ORDER BY total_amount DESC""",
        *params,
    )

    avg_days = await fetch_one(
        f"""SELECT COALESCE(AVG(EXTRACT(EPOCH FROM (p."paymentDate" - inv."invoiceDate")) / 86400), 0) as avg_days_to_pay
            FROM payments p
            JOIN invoices inv ON inv."id" = p."invoiceId"
            {("WHERE p.\"status\"::text = 'CLEARED'" + (" AND " + " AND ".join(conditions) if conditions else ""))
             if conditions else "WHERE p.\"status\"::text = 'CLEARED'"}""",
        *params,
    )

    total_invoiced = await fetch_one(
        """SELECT COALESCE(SUM("totalGrossAmount"), 0) as total
           FROM invoices WHERE "status"::text != 'CANCELLED'""",
    )
    collection_rate = (
        round(summary["total_collected"] / total_invoiced["total"] * 100, 1)
        if total_invoiced["total"] > 0 else 0
    )

    return json.dumps({
        "summary": summary,
        "collection_rate_pct": collection_rate,
        "avg_days_to_pay": round(avg_days["avg_days_to_pay"], 1) if avg_days else 0,
        "method_breakdown": method_breakdown,
    }, indent=2)


@tool
async def get_delivery_performance(
    period_from: str = "",
    period_to: str = "",
) -> str:
    """Get delivery performance analytics — status distribution, carrier performance,
    and fulfillment metrics."""
    conditions = []
    params: list = []
    idx = 1

    if period_from:
        conditions.append(f'd."deliveryDate" >= ${idx}::timestamp')
        params.append(datetime.fromisoformat(period_from))
        idx += 1
    if period_to:
        conditions.append(f'd."deliveryDate" <= ${idx}::timestamp')
        params.append(datetime.fromisoformat(period_to + "T23:59:59"))
        idx += 1

    where = "WHERE " + " AND ".join(conditions) if conditions else ""

    status_breakdown = await fetch_all(
        f"""SELECT "status"::text as status, COUNT(*) as count
            FROM deliveries d {where}
            GROUP BY "status" ORDER BY count DESC""",
        *params,
    )

    carrier_perf = await fetch_all(
        f"""SELECT "carrier", COUNT(*) as deliveries,
                   COUNT(CASE WHEN "status"::text = 'DELIVERED' THEN 1 END) as delivered,
                   COALESCE(SUM("totalWeight"), 0) as total_weight
            FROM deliveries d {where}
            WHERE "carrier" IS NOT NULL
            GROUP BY "carrier" ORDER BY deliveries DESC""",
        *params,
    )

    total = await fetch_one(
        f'SELECT COUNT(*) as total FROM deliveries d {where}', *params
    )
    delivered = await fetch_one(
        f"""SELECT COUNT(*) as count FROM deliveries d
            {"WHERE " + " AND ".join(conditions + ['"status"::text = \'DELIVERED\'']) if conditions
             else "WHERE \"status\"::text = 'DELIVERED'"}""",
        *params,
    )
    on_time_rate = (
        round(delivered["count"] / total["total"] * 100, 1)
        if total["total"] > 0 else 0
    )

    return json.dumps({
        "total_deliveries": total["total"],
        "delivered_count": delivered["count"],
        "delivery_completion_rate_pct": on_time_rate,
        "status_breakdown": status_breakdown,
        "carrier_performance": carrier_perf,
    }, indent=2)


@tool
async def get_customer_aging_report() -> str:
    """Get accounts receivable aging report by customer — shows outstanding balance
    per customer with aging buckets."""
    rows = await fetch_all(
        """SELECT c."customerNumber", c."name" as "customerName",
                  COUNT(inv."id") as open_invoices,
                  COALESCE(SUM(inv."totalGrossAmount"), 0) as total_outstanding,
                  COALESCE(SUM(CASE WHEN inv."dueDate" >= NOW() THEN inv."totalGrossAmount" ELSE 0 END), 0) as current_amount,
                  COALESCE(SUM(CASE WHEN NOW() - inv."dueDate" BETWEEN INTERVAL '0 days' AND INTERVAL '30 days' THEN inv."totalGrossAmount" ELSE 0 END), 0) as "1_30_days",
                  COALESCE(SUM(CASE WHEN NOW() - inv."dueDate" BETWEEN INTERVAL '30 days' AND INTERVAL '60 days' THEN inv."totalGrossAmount" ELSE 0 END), 0) as "31_60_days",
                  COALESCE(SUM(CASE WHEN NOW() - inv."dueDate" BETWEEN INTERVAL '60 days' AND INTERVAL '90 days' THEN inv."totalGrossAmount" ELSE 0 END), 0) as "61_90_days",
                  COALESCE(SUM(CASE WHEN NOW() - inv."dueDate" > INTERVAL '90 days' THEN inv."totalGrossAmount" ELSE 0 END), 0) as "90_plus_days"
           FROM customers c
           JOIN invoices inv ON inv."customerId" = c."id"
           WHERE inv."status"::text IN ('OPEN','PARTIALLY_PAID')
           GROUP BY c."customerNumber", c."name"
           ORDER BY total_outstanding DESC
           LIMIT 100""",
    )
    if not rows:
        return "No outstanding receivables."

    grand_total = sum(r["total_outstanding"] for r in rows)
    return json.dumps({
        "grand_total_outstanding": round(grand_total, 2),
        "customer_aging": rows,
    }, indent=2)


@tool
async def get_pipeline_summary() -> str:
    """Get full O2C pipeline summary — open orders, pending deliveries, unpaid invoices,
    and pending payments. Gives a snapshot of the entire order-to-cash flow."""
    open_orders = await fetch_one(
        """SELECT COUNT(*) as count, COALESCE(SUM("totalGrossAmount"), 0) as total
           FROM sales_orders WHERE "status"::text IN ('DRAFT','OPEN','IN_DELIVERY')""",
    )
    pending_deliveries = await fetch_one(
        """SELECT COUNT(*) as count
           FROM deliveries WHERE "status"::text IN ('PLANNED','PICKED','PACKED','SHIPPED')""",
    )
    unpaid_invoices = await fetch_one(
        """SELECT COUNT(*) as count, COALESCE(SUM("totalGrossAmount"), 0) as total
           FROM invoices WHERE "status"::text IN ('OPEN','PARTIALLY_PAID')""",
    )
    pending_payments = await fetch_one(
        """SELECT COUNT(*) as count, COALESCE(SUM("amount"), 0) as total
           FROM payments WHERE "status"::text = 'PENDING'""",
    )
    recent_credit_memos = await fetch_one(
        """SELECT COUNT(*) as count, COALESCE(SUM("totalAmount"), 0) as total
           FROM credit_memos WHERE "status"::text IN ('DRAFT','APPROVED')""",
    )

    # Order status distribution
    order_statuses = await fetch_all(
        """SELECT "status"::text as status, COUNT(*) as count
           FROM sales_orders GROUP BY "status" """,
    )

    return json.dumps({
        "pipeline": {
            "open_orders": open_orders,
            "pending_deliveries": pending_deliveries,
            "unpaid_invoices": unpaid_invoices,
            "pending_payments": pending_payments,
            "pending_credit_memos": recent_credit_memos,
        },
        "order_status_distribution": order_statuses,
    }, indent=2)


all_analytics_tools = [
    get_order_analytics,
    get_revenue_analytics,
    get_payment_analytics,
    get_delivery_performance,
    get_customer_aging_report,
    get_pipeline_summary,
]
