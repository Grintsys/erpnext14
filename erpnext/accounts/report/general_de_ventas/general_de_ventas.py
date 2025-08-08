from __future__ import unicode_literals
import frappe
from frappe.utils import flt
from frappe import _, msgprint

def execute(filters=None):
    if not filters:
        filters = {}

    columns = [
        {"fieldname": "date", "fieldtype": "Date", "label": "Fecha", "width": 100},
        {"fieldname": "type_document", "fieldtype": "Data", "label": "Tipo", "width": 150},
        {"fieldname": "document", "fieldtype": "Link", "options": "Sales Invoice", "label": "Documento", "width": 140},
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
        {"fieldname": "total_rounded", "fieldtype": "Currency", "label": "Total Redondeado", "width": 110}
    ]

    # ---------- NUEVO: construir WHERE dinámico con fecha y hora ----------
    where_clauses = ["si.docstatus = 1"]
    params = {}

    # Filtro por compañía (igual que antes)
    if filters.get("company"):
        where_clauses.append("si.company = %(company)s")
        params["company"] = filters["company"]

    # Fechas (igual que antes)
    if filters.get("from_date") and filters.get("to_date"):
        where_clauses.append("si.posting_date BETWEEN %(from_date)s AND %(to_date)s")
        params["from_date"] = filters["from_date"]
        params["to_date"] = filters["to_date"]

    # Horas (NUEVO)
    from_time = (filters.get("from_time") or None)
    to_time = (filters.get("to_time") or None)

    if from_time and to_time:
        # Caso A: ventana normal (ej. 03:00 → 17:00)
        if from_time <= to_time:
            where_clauses.append("si.posting_time BETWEEN %(from_time)s AND %(to_time)s")
            params["from_time"] = from_time
            params["to_time"] = to_time
        else:
            # Caso B: cruza medianoche (ej. 22:00 → 02:00)
            where_clauses.append("(si.posting_time >= %(from_time)s OR si.posting_time <= %(to_time)s)")
            params["from_time"] = from_time
            params["to_time"] = to_time
    # Si solo te pasan uno de los dos, no aplicamos filtro de hora (evitamos resultados raros)

    where_sql = " AND ".join(where_clauses)

    # Traer solo los campos que usás después (equivalente a tu get_all original)
    rows = frappe.db.sql(
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
        as_dict=True,
    )

    data = []
    for sales in rows:
        rtn = frappe.db.get_value("Customer", sales.customer, "tax_id")
        type_document = "Devolución" if sales.is_return else "Factura"

        # Calcular monto bruto
        monto_bruto = (
            flt(sales.exempt_amount)
            + flt(sales.taxed_amount_15)
            + flt(sales.taxed_amount_18)
            - flt(sales.discount_amount)
        )

        # El "total" ya lo tenés como grand_total; acá lo mantenemos como antes
        row = [
            sales.posting_date,
            type_document,
            sales.name,
            sales.customer,
            rtn,
            sales.exempt_amount,
            sales.taxed_amount_15,
            sales.isv_15,
            sales.taxed_amount_18,
            sales.isv_18,
            sales.discount_amount,
            monto_bruto,
            sales.grand_total,
            sales.rounded_total
        ]
        data.append(row)

    return columns, data
