from __future__ import unicode_literals
import frappe
from frappe.utils import flt

def execute(filters=None):
    if not filters:
        filters = {}

    columns = [
        {"fieldname": "date", "fieldtype": "Date", "label": "Fecha", "width": 100},
        {"fieldname": "type_document", "fieldtype": "Data", "label": "Documento", "width": 100},
        {"fieldname": "document", "fieldtype": "Link", "options": "Sales Invoice", "label": "Documento", "width": 180},
        {"fieldname": "name", "fieldtype": "Data", "label": "Nombre", "width": 140},
        {"fieldname": "rtn", "fieldtype": "Data", "label": "RTN", "width": 120},
        {"fieldname": "total_exempt", "fieldtype": "Currency", "label": "Total Exento", "width": 110},
        {"fieldname": "base_isv_15%", "fieldtype": "Currency", "label": "Base ISV 15%", "width": 110},
        {"fieldname": "isv_15%", "fieldtype": "Currency", "label": "ISV 15%", "width": 110},
        {"fieldname": "base_isv_18%", "fieldtype": "Currency", "label": "Base ISV 18%", "width": 110},
        {"fieldname": "isv_18%", "fieldtype": "Currency", "label": "ISV 18%", "width": 110},
        {"fieldname": "discount_amount", "fieldtype": "Currency", "label": "Descuento", "width": 110},
        {"fieldname": "monto_bruto", "fieldtype": "Currency", "label": "Monto Bruto", "width": 110},
        {"fieldname": "grand_total", "fieldtype": "Currency", "label": "Total", "width": 110},
        {"fieldname": "total_rounded", "fieldtype": "Currency", "label": "Total Redondeado", "width": 110},
        {"fieldname": "cost", "fieldtype": "Currency", "label": "Costo", "width": 110},
        {"fieldname": "utility", "fieldtype": "Currency", "label": "Utilidad", "width": 110},
        {"fieldname": "utility_percentage", "fieldtype": "Percent", "label": "% Utilidad", "width": 110}
    ]

    # ---------- WHERE dinámico con fecha/hora ----------
    where = ["si.docstatus = 1"]
    params = {}

    if filters.get("company"):
        where.append("si.company = %(company)s")
        params["company"] = filters["company"]

    if filters.get("from_date") and filters.get("to_date"):
        where.append("si.posting_date BETWEEN %(from_date)s AND %(to_date)s")
        params["from_date"] = filters["from_date"]
        params["to_date"] = filters["to_date"]

    from_time = filters.get("from_time") or None
    to_time = filters.get("to_time") or None
    if from_time and to_time:
        if from_time <= to_time:
            # ventana normal (ej. 03:00 → 17:00)
            where.append("si.posting_time BETWEEN %(from_time)s AND %(to_time)s")
            params["from_time"] = from_time
            params["to_time"] = to_time
        else:
            # cruza medianoche (ej. 22:00 → 02:00)
            where.append("(si.posting_time >= %(from_time)s OR si.posting_time <= %(to_time)s)")
            params["from_time"] = from_time
            params["to_time"] = to_time

    where_sql = " AND ".join(where)

    # Traemos los campos necesarios de Sales Invoice
    invoices = frappe.db.sql(
        f"""
        SELECT
            si.name,
            si.posting_date,
            si.customer,
            si.is_return,
            si.exempt_amount,
            si.taxed_amount_15,
            si.isv_15,
            si.taxed_amount_18,
            si.isv_18,
            si.discount_amount,
            si.grand_total,
            si.rounded_total
        FROM `tabSales Invoice` si
        WHERE {where_sql}
        ORDER BY si.posting_date, si.posting_time, si.name
        """,
        params,
        as_dict=True
    )

    # Obtener RTN de clientes en una sola consulta
    if invoices:
        customer_names = list({inv["customer"] for inv in invoices})
        customer_tax_ids = {
            c.name: c.tax_id
            for c in frappe.get_all("Customer", fields=["name", "tax_id"], filters={"name": ["in", customer_names]})
        }
    else:
        customer_tax_ids = {}

    data = []
    for si in invoices:
        type_document = "Devolución" if si.is_return else "Factura"

        # Costo (suma qty * incoming_rate por items de la factura)
        cost = sum(
            flt(item.qty) * flt(item.incoming_rate)
            for item in frappe.get_all(
                "Sales Invoice Item",
                fields=["qty", "incoming_rate"],
                filters={"parent": si.name}
            )
        )

        monto_bruto = (
            flt(si.exempt_amount)
            + flt(si.taxed_amount_15)
            + flt(si.taxed_amount_18)
            - flt(si.discount_amount)
        )

        utility = monto_bruto - cost
        utility_percentage = (utility / monto_bruto * 100) if monto_bruto > 0 else 0
        utility_percentage = min(utility_percentage, 100)

        row = [
            si.posting_date,
            type_document,
            si.name,
            si.customer,
            customer_tax_ids.get(si.customer),
            si.exempt_amount,
            si.taxed_amount_15,
            si.isv_15,
            si.taxed_amount_18,
            si.isv_18,
            si.discount_amount,
            monto_bruto,
            si.grand_total,
            si.rounded_total,
            cost,
            utility,
            utility_percentage
        ]
        data.append(row)

    return columns, data
