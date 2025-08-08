from __future__ import unicode_literals
import frappe
from frappe.utils import flt

def execute(filters=None):
    if not filters:
        filters = {}

    columns = [
        {"fieldname": "warehouse", "fieldtype": "Link", "options": "Warehouse", "label": "Almacen", "width": 140},
        {"fieldname": "type_document", "fieldtype": "Data", "label": "Tipo de documento", "width": 140},
        {"fieldname": "total_exempt", "fieldtype": "Currency", "label": "Total Exento", "width": 110},
        {"fieldname": "base_isv_15%", "fieldtype": "Currency", "label": "Base ISV 15%", "width": 110},
        {"fieldname": "isv_15%", "fieldtype": "Currency", "label": "ISV 15%", "width": 110},
        {"fieldname": "base_isv_18%", "fieldtype": "Currency", "label": "Base ISV 18%", "width": 110},
        {"fieldname": "isv_18%", "fieldtype": "Currency", "label": "ISV 18%", "width": 110},
        {"fieldname": "discount_amount", "fieldtype": "Currency", "label": "Descuento", "width": 110},
        {"fieldname": "gross_amount", "fieldtype": "Currency", "label": "Monto Bruto", "width": 110},
        {"fieldname": "grand_total", "fieldtype": "Currency", "label": "Total", "width": 110},
        {"fieldname": "total_rounded", "fieldtype": "Currency", "label": "Total Redondeado", "width": 110},
        {"fieldname": "cost", "fieldtype": "Currency", "label": "Costo", "width": 110},
        {"fieldname": "utility", "fieldtype": "Currency", "label": "Utilidad", "width": 110},
        {"fieldname": "utility_percentage", "fieldtype": "Percent", "label": "% Utilidad", "width": 110},
    ]

    # --- WHERE dinámico por fecha/hora/empresa ---
    where = ["si.docstatus = 1"]
    params = {}

    # Compañía
    if filters.get("company"):
        where.append("si.company = %(company)s")
        params["company"] = filters["company"]

    # Fechas
    if filters.get("from_date") and filters.get("to_date"):
        where.append("si.posting_date BETWEEN %(from_date)s AND %(to_date)s")
        params["from_date"] = filters["from_date"]
        params["to_date"] = filters["to_date"]

    # Horas (incluye cruce de medianoche)
    from_time = filters.get("from_time") or None
    to_time = filters.get("to_time") or None
    if from_time and to_time:
        if from_time <= to_time:
            where.append("si.posting_time BETWEEN %(from_time)s AND %(to_time)s")
        else:
            where.append("(si.posting_time >= %(from_time)s OR si.posting_time <= %(to_time)s)")
        params["from_time"] = from_time
        params["to_time"] = to_time

    where_sql = " AND ".join(where)

    # --- SQL: agrupar por almacén (desde POS Profile) y por is_return ---
    rows = frappe.db.sql(
        f"""
        SELECT
            pp.warehouse                              AS warehouse,
            si.is_return                               AS is_return,
            SUM(si.exempt_amount)                      AS total_exempt,
            SUM(si.taxed_amount_15)                    AS base_isv_15,
            SUM(si.isv_15)                             AS isv_15,
            SUM(si.taxed_amount_18)                    AS base_isv_18,
            SUM(si.isv_18)                             AS isv_18,
            SUM(si.discount_amount)                    AS discount_amount,
            SUM(si.grand_total)                        AS grand_total,
            SUM(si.rounded_total)                      AS total_rounded,
            COALESCE(SUM(sii.qty * sii.incoming_rate), 0) AS cost
        FROM `tabSales Invoice` si
        JOIN `tabPOS Profile` pp ON pp.name = si.pos_profile
        LEFT JOIN `tabSales Invoice Item` sii ON sii.parent = si.name
        WHERE {where_sql}
        GROUP BY pp.warehouse, si.is_return
        ORDER BY pp.warehouse, si.is_return
        """,
        params,
        as_dict=True
    )

    # Armar filas finales y cálculos derivados
    data = []
    for r in rows:
        warehouse = r.warehouse
        type_document = "Devolución" if flt(r.is_return) == 1 else "Factura de venta"

        total_exempt = flt(r.total_exempt)
        base_isv_15 = flt(r.base_isv_15)
        isv_15 = flt(r.isv_15)
        base_isv_18 = flt(r.base_isv_18)
        isv_18 = flt(r.isv_18)
        discount_amount = flt(r.discount_amount)
        grand_total = flt(r.grand_total)
        total_rounded = flt(r.total_rounded)
        cost = flt(r.cost)

        # Monto bruto SIN impuestos
        gross_amount = total_exempt + base_isv_15 + base_isv_18 - discount_amount

        # Utilidad / % Utilidad
        utility = gross_amount - cost
        utility_percentage = (utility * 100 / gross_amount) if gross_amount > 0 else 0
        utility_percentage = max(0, min(utility_percentage, 100))

        # (opcional) imitar tu filtro anterior: solo mostrar filas con Total != 0
        if grand_total == 0:
            continue

        data.append([
            warehouse,
            type_document,
            total_exempt,
            base_isv_15,
            isv_15,
            base_isv_18,
            isv_18,
            discount_amount,
            gross_amount,
            grand_total,
            total_rounded,
            cost,
            utility,
            utility_percentage
        ])

    return columns, data
