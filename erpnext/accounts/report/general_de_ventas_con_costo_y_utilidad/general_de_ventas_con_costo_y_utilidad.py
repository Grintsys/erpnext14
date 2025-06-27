import frappe
from frappe.utils import flt

def execute(filters=None):
    columns = get_columns()
    data = get_data(filters)
    return columns, data

def get_columns():
    return [
        {"label": "Documento", "fieldname": "name", "fieldtype": "Link", "options": "Sales Invoice", "width": 120},
        {"label": "Fecha", "fieldname": "posting_date", "fieldtype": "Date", "width": 100},
        {"label": "Cliente", "fieldname": "customer_name", "fieldtype": "Data", "width": 200},
        {"label": "Código", "fieldname": "item_code", "fieldtype": "Data", "width": 100},
        {"label": "Descripción", "fieldname": "item_name", "fieldtype": "Data", "width": 200},
        {"label": "Cantidad", "fieldname": "qty", "fieldtype": "Float", "width": 80},
        {"label": "Precio", "fieldname": "rate", "fieldtype": "Currency", "width": 80},
        {"label": "Descuentos", "fieldname": "discount_amount", "fieldtype": "Currency", "width": 100},
        {"label": "Exento", "fieldname": "exento", "fieldtype": "Currency", "width": 100},
        {"label": "Base 15%", "fieldname": "base_15", "fieldtype": "Currency", "width": 100},
        {"label": "Base 18%", "fieldname": "base_18", "fieldtype": "Currency", "width": 100},
        {"label": "Monto Bruto", "fieldname": "monto_bruto", "fieldtype": "Currency", "width": 120},
        {"label": "Costo", "fieldname": "costo_total", "fieldtype": "Currency", "width": 100},
        {"label": "Utilidad", "fieldname": "utilidad", "fieldtype": "Currency", "width": 100},
        {"label": "% Utilidad", "fieldname": "porc_utilidad", "fieldtype": "Percent", "width": 100},
    ]

def get_data(filters):
    condiciones = ""
    if filters.get("from_date"):
        condiciones += f" AND si.posting_date >= '{filters['from_date']}'"
    if filters.get("to_date"):
        condiciones += f" AND si.posting_date <= '{filters['to_date']}'"

    resultados = frappe.db.sql(f"""
        SELECT 
            si.name,
            si.posting_date,
            si.customer_name,
            sii.item_code,
            sii.item_name,
            sii.qty,
            sii.rate,
            sii.discount_amount,
            sii.base_net_amount,
            sii.base_amount,
            sii.item_tax_rate,
            sii.base_net_amount * sii.qty as base_total,
            sii.cost_center,
            sii.income_account,
            sii.expense_account,
            sii.base_rate,
            sii.base_net_rate,
            sii.base_net_amount / NULLIF(sii.qty, 0) as costo_unitario
        FROM 
            `tabSales Invoice Item` sii
        INNER JOIN `tabSales Invoice` si ON sii.parent = si.name
        WHERE si.docstatus = 1 {condiciones}
    """, as_dict=True)

    datos = []
    for row in resultados:
        # Simulación simple de cómo diferenciar impuestos
        base_15 = row.base_amount * 0.15 if "15" in str(row.item_tax_rate) else 0
        base_18 = row.base_amount * 0.18 if "18" in str(row.item_tax_rate) else 0
        exento = 0 if base_15 or base_18 else row.base_amount

        monto_bruto = flt(exento) + flt(base_15) + flt(base_18) - flt(row.discount_amount)
        costo_total = flt(row.costo_unitario) * flt(row.qty)
        utilidad = monto_bruto - costo_total
        porc_utilidad = (utilidad / monto_bruto * 100) if monto_bruto else 0
        porc_utilidad = min(porc_utilidad, 100)

        datos.append({
            "name": row.name,
            "posting_date": row.posting_date,
            "customer_name": row.customer_name,
            "item_code": row.item_code,
            "item_name": row.item_name,
            "qty": row.qty,
            "rate": row.rate,
            "discount_amount": row.discount_amount,
            "exento": exento,
            "base_15": base_15,
            "base_18": base_18,
            "monto_bruto": monto_bruto,
            "costo_total": costo_total,
            "utilidad": utilidad,
            "porc_utilidad": porc_utilidad,
        })

    return datos
