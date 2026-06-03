import frappe
from frappe import _
from frappe.utils import flt, getdate, nowdate

from erpnext.accounts.report.sales_register import sales_register

COLUMNS = [
    {"label": _("Documento"),        "fieldname": "voucher_no",      "fieldtype": "Link",      "options": "Sales Invoice", "width": 180},
    {"label": _("Fecha"),            "fieldname": "posting_date",    "fieldtype": "Date",                              "width": 100},
    {"label": _("Cliente"),          "fieldname": "customer",        "fieldtype": "Link",      "options": "Customer",      "width": 180},
    {"label": _("Nombre Cliente"),   "fieldname": "customer_name",   "fieldtype": "Data",                              "width": 180},
    {"label": _("Forma de Pago"),    "fieldname": "mode_of_payment", "fieldtype": "Data",                              "width": 140},
    {"label": _("Usuario"),          "fieldname": "owner",           "fieldtype": "Data",                              "width": 100},
    #{"label": _("Centro de Costo"),  "fieldname": "cost_center",     "fieldtype": "Data",                              "width": 140},
    #{"label": _("Almacén"),          "fieldname": "warehouse",       "fieldtype": "Data",                              "width": 140},

    {"label": _("Neto"),             "fieldname": "net_total",       "fieldtype": "Currency",  "options": "currency",      "width": 120},
    {"label": _("Impuestos"),        "fieldname": "tax_total",       "fieldtype": "Currency",  "options": "currency",      "width": 120},
    {"label": _("Total"),            "fieldname": "grand_total",     "fieldtype": "Currency",  "options": "currency",      "width": 120},
    #{"label": _("Redondeo"),         "fieldname": "rounded_total",   "fieldtype": "Currency",  "options": "currency",      "width": 120},
    {"label": _("Pendiente"),        "fieldname": "outstanding_amount","fieldtype": "Currency","options": "currency",      "width": 120},
    # {"label": _("Moneda"),         "fieldname": "currency",        "fieldtype": "Data",                              "width": 80},
]


def execute(filters=None):
    filters = frappe._dict(filters or {})
    _normalize_filters(filters)

    # 1) Traer facturas base
    invoices = sales_register.get_invoices(filters, additional_query_columns=None)

    if not invoices:
        return COLUMNS, [], _("No se encontraron registros"), None, []

    # 2) Mapas auxiliares (reutilizamos utilidades sólidas del sales_register)
    invoice_income_map = sales_register.get_invoice_income_map(invoices)
    internal_invoice_map = sales_register.get_internal_invoice_map(invoices)

    income_accounts = []  # No generamos columnas dinámicas por cuenta; mantenemos neto/impuestos
    invoice_income_map, invoice_tax_map = sales_register.get_invoice_tax_map(
        invoices, invoice_income_map, income_accounts, include_payments=False
    )
    invoice_cc_wh_map = sales_register.get_invoice_cc_wh_map(invoices)
    invoice_so_dn_map = sales_register.get_invoice_so_dn_map(invoices)
    mode_of_payments = sales_register.get_mode_of_payments([inv.name for inv in invoices])

    # 3) Moneda de compañía (por si deseas mostrarla en el resumen)
    company_currency = None
    if filters.get("company"):
        company_currency = frappe.get_cached_value("Company", filters.company, "default_currency")

    # 4) Construir filas con SOLO las columnas que definimos
    data = []
    for inv in invoices:
        sales_order = list(set(invoice_so_dn_map.get(inv.name, {}).get("sales_order", [])))
        delivery_note = list(set(invoice_so_dn_map.get(inv.name, {}).get("delivery_note", [])))
        cc_list = list(set(invoice_cc_wh_map.get(inv.name, {}).get("cost_center", [])))
        wh_list = list(set(invoice_cc_wh_map.get(inv.name, {}).get("warehouse", [])))

        # Impuestos calculados (suma de todas las cuentas de impuestos)
        tax_map = invoice_tax_map.get(inv.name, {}) or {}
        tax_total = sum(flt(v) for v in tax_map.values())

        row = {
            "voucher_no": inv.name,
            "posting_date": inv.posting_date,
            "customer": inv.customer,
            "customer_name": inv.customer_name,
            "mode_of_payment": ", ".join(mode_of_payments.get(inv.name, [])),
            "tax_id": getattr(inv, "tax_id", None),
            "owner": inv.owner,
            #"cost_center": ", ".join(cc_list),
            #"warehouse": ", ".join(wh_list),

            # Totales (usamos los base_* ya calculados por ERPNext)
            "net_total": inv.base_net_total,
            "tax_total": tax_total,
            "grand_total": inv.base_grand_total,
            #"rounded_total": inv.base_rounded_total,
            "outstanding_amount": inv.outstanding_amount,
            # "currency": company_currency or _get_currency_fallback(filters),
        }

        data.append(row)

    # 5) Resumen / gráfico opcional: desglose de pagos
    report_summary, chart = _payment_summary_and_chart(filters, data)

    # Ordenar por fecha y documento
    data.sort(key=lambda r: (r.get("posting_date") or "", r.get("voucher_no") or ""))

    return COLUMNS, data, None, chart, report_summary


# =========================
# Utilidades del reporte
# =========================

def _normalize_filters(filters):
    if not filters.get("to_date"):
        filters.to_date = nowdate()
    if not filters.get("from_date"):
        # por defecto: primer día del mes de to_date
        to_d = getdate(filters.to_date)
        filters.from_date = f"{to_d.year}-{str(to_d.month).zfill(2)}-01"
    # No hacemos obligatorio company; si lo tienes, ayuda al rendimiento por índices.


def _get_currency_fallback(filters):
    if filters.get("company"):
        return frappe.get_cached_value("Company", filters.company, "default_currency")
    return frappe.get_cached_value("Global Defaults", "Global Defaults", "default_currency")


def _payment_summary_and_chart(filters, data_rows):
    """
    Resumen por formas de pago detectadas en las facturas del dataset, más:
    - Total Ingresos (suma de pagos)
    - Total Crédito (suma de outstanding)
    - Total Cancelado (ventas - crédito)
    - (F) Total Facturas
    """
    invoices = [r["voucher_no"] for r in data_rows if r.get("voucher_no")]
    if not invoices:
        return [], None

    # Totales por MOP registrados en la factura
    payment_totals = _fetch_payment_totals_chunked(invoices)

    # Si filtran por MOP, aplicarlo SOLO al resumen de pagos (no al dataset base)
    if filters.get("mode_of_payment"):
        mop = filters.mode_of_payment
        payment_totals = {k: v for k, v in payment_totals.items() if (k or "") == mop}

    # Totales del dataset
    total_ventas = sum(flt(r.get("grand_total")) for r in data_rows)
    total_credito = sum(flt(r.get("outstanding_amount")) for r in data_rows)
    total_contado = flt(total_ventas) - flt(total_credito)
    total_ingresos = flt(sum(payment_totals.values()) or 0.0)
    #factura_count = len(data_rows)

    currency = _get_currency_fallback(filters)

    summary = [
        {"label": _("Total Ventas"),   "value": total_ventas,   "datatype": "Currency", "currency": currency},
        {"label": _("Total Contado"),  "value": total_contado,  "datatype": "Currency", "currency": currency},
        {"label": _("Total Crédito"),  "value": total_credito,  "datatype": "Currency", "currency": currency},
        #{"label": _("Total Ingresos"), "value": total_ingresos, "datatype": "Currency", "currency": currency},
    ]

    # Desglose dinámico por MOP
    for mop, amt in sorted(payment_totals.items(), key=lambda x: (x[0] or "").lower()):
        summary.append({
            "label": _("Total {0}").format(mop),
            "value": flt(amt),
            "datatype": "Currency",
            "currency": currency,
        })

    # Conteo de facturas
    #if factura_count:
    #    summary.append({"label": _("(F) Total Facturas"), "value": int(factura_count), "datatype": "Int"})

    # Gráfico forma de pago
    if not payment_totals:
        return summary, None

    labels, values = [], []
    for mop, amt in sorted(payment_totals.items(), key=lambda x: (x[0] or "").lower()):
        labels.append(mop)
        values.append(flt(amt))

    chart = {
        "data": {"labels": labels, "datasets": [{"name": _("Total"), "values": values}]},
        "type": "bar",
        "fieldtype": "Currency",
        "options": {"currency": currency},
    }
    return summary, chart


def _fetch_payment_totals_chunked(invoice_names):
    """Suma base_amount por modo de pago en chunks (robusto para listas grandes)."""
    totals = {}
    chunk = 1000
    for i in range(0, len(invoice_names), chunk):
        subset = invoice_names[i:i+chunk]
        rows = frappe.db.sql(
            """
            SELECT mode_of_payment, SUM(base_amount) AS total
            FROM `tabSales Invoice Payment`
            WHERE parent IN %(parents)s
            GROUP BY mode_of_payment
            """,
            {"parents": subset},
            as_dict=True,
        )
        for r in rows:
            if not r.mode_of_payment:
                continue
            totals[r.mode_of_payment] = totals.get(r.mode_of_payment, 0) + flt(r.total)
    return totals
