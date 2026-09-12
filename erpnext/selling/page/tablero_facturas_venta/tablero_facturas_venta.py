# -*- coding: utf-8 -*-
import frappe
from frappe import _
from frappe.utils import flt, getdate, add_days, today, format_date

@frappe.whitelist()
def get_dashboard_data(
    company=None,
    from_date=None,
    to_date=None,
    customer=None,
    customer_group=None,
    territory=None,
    pos_profile=None,
    periodicity="Monthly"
):
    """
    API Backend para el Cuadro de Mandos de Facturas de Venta.
    Agrupa KPIs, gráficos de tendencias, formas de pago, clientes y productos estrella.
    """
    if not frappe.has_permission("Sales Invoice", "read"):
        frappe.throw(_("No tiene permisos para consultar Facturas de Venta"), frappe.PermissionError)

    if not company:
        company = frappe.defaults.get_user_default("Company") or frappe.db.get_single_value("Global Defaults", "default_company")

    if not to_date:
        to_date = today()
    if not from_date:
        # Por defecto los últimos 30 días del año activo
        from_date = add_days(to_date, -30)

    # 1. Filtros Base para Sales Invoice (Facturas Emitidas y Aprobadas docstatus = 1)
    where_clauses = ["si.docstatus = 1"]
    params = {
        "company": company,
        "from_date": from_date,
        "to_date": to_date
    }

    if company:
        where_clauses.append("si.company = %(company)s")

    where_clauses.append("si.posting_date BETWEEN %(from_date)s AND %(to_date)s")

    if customer:
        where_clauses.append("si.customer = %(customer)s")
        params["customer"] = customer

    if customer_group:
        where_clauses.append("si.customer_group = %(customer_group)s")
        params["customer_group"] = customer_group

    if territory:
        where_clauses.append("si.territory = %(territory)s")
        params["territory"] = territory

    if pos_profile:
        where_clauses.append("si.pos_profile = %(pos_profile)s")
        params["pos_profile"] = pos_profile

    where_sql = " AND ".join(where_clauses)

    # --- A. RESUMEN DE KPIS GENERALES ---
    kpi_query = f"""
        SELECT 
            COUNT(si.name) AS invoice_count,
            COALESCE(SUM(si.grand_total), 0) AS total_grand_total,
            COALESCE(SUM(si.net_total), 0) AS total_net_total,
            COALESCE(SUM(si.paid_amount), 0) AS total_paid,
            COALESCE(SUM(si.outstanding_amount), 0) AS total_outstanding,
            COALESCE(SUM(si.total_taxes_and_charges), 0) AS total_taxes
        FROM `tabSales Invoice` si
        WHERE {where_sql}
    """
    kpi_res = frappe.db.sql(kpi_query, params, as_dict=True)[0]

    invoice_count = cint_val(kpi_res["invoice_count"])
    grand_total = flt(kpi_res["total_grand_total"], 2)
    net_total = flt(kpi_res["total_net_total"], 2)
    paid_amount = flt(kpi_res["total_paid"], 2)
    outstanding_amount = flt(kpi_res["total_outstanding"], 2)
    total_taxes = flt(kpi_res["total_taxes"], 2)
    avg_ticket = flt(grand_total / invoice_count, 2) if invoice_count > 0 else 0.0

    kpis = {
        "invoice_count": invoice_count,
        "grand_total": grand_total,
        "net_total": net_total,
        "paid_amount": paid_amount,
        "outstanding_amount": outstanding_amount,
        "total_taxes": total_taxes,
        "avg_ticket": avg_ticket
    }

    # --- B. GRÁFICO DE TENDENCIAS (FACTURADO VS COBRADO POR TIEMPO) ---
    date_group_sql = "%%Y-%%m" if periodicity == "Monthly" else "%%Y-%%m-%%d"
    trend_query = f"""
        SELECT 
            DATE_FORMAT(si.posting_date, '{date_group_sql}') AS period,
            SUM(si.grand_total) AS grand_total,
            SUM(si.paid_amount) AS paid_amount
        FROM `tabSales Invoice` si
        WHERE {where_sql}
        GROUP BY period
        ORDER BY period ASC
    """
    trend_raw = frappe.db.sql(trend_query, params, as_dict=True)

    trend_labels = [r["period"] for r in trend_raw]
    trend_grand = [flt(r["grand_total"], 2) for r in trend_raw]
    trend_paid = [flt(r["paid_amount"], 2) for r in trend_raw]

    trend_chart = {
        "labels": trend_labels,
        "datasets": [
            {"name": _("Facturado"), "values": trend_grand},
            {"name": _("Cobrado"), "values": trend_paid}
        ]
    }

    # --- C. DISTRIBUCIÓN POR FORMA DE PAGO ---
    payment_query = f"""
        SELECT 
            COALESCE(sip.mode_of_payment, 'Crédito / Directo') AS mode_of_payment,
            SUM(COALESCE(sip.amount, si.grand_total)) AS total_amount
        FROM `tabSales Invoice` si
        LEFT JOIN `tabSales Invoice Payment` sip ON sip.parent = si.name
        WHERE {where_sql}
        GROUP BY mode_of_payment
        ORDER BY total_amount DESC
    """
    payment_raw = frappe.db.sql(payment_query, params, as_dict=True)

    payment_labels = [r["mode_of_payment"] for r in payment_raw]
    payment_values = [flt(r["total_amount"], 2) for r in payment_raw]

    payment_chart = {
        "labels": payment_labels,
        "values": payment_values
    }

    # --- D. TOP 10 CLIENTES POR FACTURACIÓN ---
    customers_query = f"""
        SELECT 
            si.customer_name AS customer,
            SUM(si.grand_total) AS total_amount
        FROM `tabSales Invoice` si
        WHERE {where_sql}
        GROUP BY si.customer
        ORDER BY total_amount DESC
        LIMIT 10
    """
    cust_raw = frappe.db.sql(customers_query, params, as_dict=True)
    cust_labels = [r["customer"] for r in cust_raw]
    cust_values = [flt(r["total_amount"], 2) for r in cust_raw]

    top_customers = {
        "labels": cust_labels,
        "values": cust_values
    }

    # --- E. TOP 10 PRODUCTOS MÁS FACTURADOS ---
    products_query = f"""
        SELECT 
            sii.item_code,
            sii.item_name,
            SUM(sii.qty) AS total_qty,
            SUM(sii.amount) AS total_amount
        FROM `tabSales Invoice` si
        INNER JOIN `tabSales Invoice Item` sii ON sii.parent = si.name
        WHERE {where_sql}
        GROUP BY sii.item_code
        ORDER BY total_amount DESC
        LIMIT 10
    """
    products_raw = frappe.db.sql(products_query, params, as_dict=True)

    top_products = [
        {
            "item_code": p["item_code"],
            "item_name": p["item_name"],
            "qty": flt(p["total_qty"], 2),
            "amount": flt(p["total_amount"], 2)
        } for p in products_raw
    ]

    # --- F. RECIENTES FACTURAS DESTACADAS (TOP 15) ---
    recent_query = f"""
        SELECT 
            si.name,
            si.posting_date,
            si.customer_name,
            si.grand_total,
            si.outstanding_amount,
            si.status,
            si.currency
        FROM `tabSales Invoice` si
        WHERE {where_sql}
        ORDER BY si.posting_date DESC, si.creation DESC
        LIMIT 15
    """
    recent_raw = frappe.db.sql(recent_query, params, as_dict=True)

    recent_invoices = [
        {
            "name": r["name"],
            "posting_date": format_date(r["posting_date"]),
            "customer": r["customer_name"],
            "grand_total": flt(r["grand_total"], 2),
            "outstanding_amount": flt(r["outstanding_amount"], 2),
            "status": r["status"],
            "currency": r["currency"] or "HNL"
        } for r in recent_raw
    ]

    return {
        "kpis": kpis,
        "trend_chart": trend_chart,
        "payment_chart": payment_chart,
        "top_customers": top_customers,
        "top_products": top_products,
        "recent_invoices": recent_invoices
    }

def cint_val(val):
    try:
        return int(val)
    except Exception:
        return 0
