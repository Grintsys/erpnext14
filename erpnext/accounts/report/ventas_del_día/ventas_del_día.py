# Copyright (c) 2025, Frappe Technologies Pvt. Ltd. and contributors
# For license information, please see license.txt International Systems Group S. de R.L. de C.V.

from __future__ import unicode_literals
import re
from datetime import timedelta
import frappe
from frappe import _
from frappe.utils import flt, getdate

def execute(filters=None):
    filters = filters or {}
    columns = get_columns()
    data = get_data(filters)
    return columns, data

def get_columns():
    # Alineado con "General de ventas"
    return [
        _("Fecha") + "::120",
        _("Serie") + "::160",
        _("Rango") + "::220",
        _("Ventas exentas") + ":Currency:120",
        _("Base 15%") + ":Currency:140",
        _("I.S.V 15%") + ":Currency:110",
        _("Base 18%") + ":Currency:140",
        _("I.S.V 18%") + ":Currency:110",
        _("Descuento") + ":Currency:120",
        _("Monto Bruto") + ":Currency:120",
        _("Total") + ":Currency:120",
        _("Total Redondeado") + ":Currency:140",
    ]

def get_data(filters):
    from_date = getdate(filters.get("from_date"))
    to_date = getdate(filters.get("to_date"))
    company = filters.get("company")
    prefix = filters.get("prefix")

    if not (from_date and to_date and company and prefix):
        return []

    # Conjunto de facturas permitidas por filtros de ítems (warehouse/cost_center)
    allowed = get_allowed_invoice_set(filters)

    # Traer ventas del rango (una sola serie, porque prefix es reqd)
    rows = frappe.db.sql(
        """
        SELECT
            si.name,
            si.posting_date,
            si.naming_series,
            si.exempt_amount,
            si.taxed_amount_15,
            si.isv_15,
            si.taxed_amount_18,
            si.isv_18,
            si.discount_amount,
            si.grand_total,
            si.rounded_total,
            COALESCE(si.is_return, 0) as is_return
        FROM `tabSales Invoice` si
        WHERE
            si.docstatus = 1
            AND si.company = %(company)s
            AND si.posting_date BETWEEN %(from_date)s AND %(to_date)s
            AND si.naming_series = %(prefix)s
        ORDER BY si.posting_date, si.name
        """,
        {
            "company": company,
            "from_date": from_date,
            "to_date": to_date,
            "prefix": prefix,
        },
        as_dict=True,
    )

    # Agrupar por día (serie está fijada por el filtro 'prefix')
    by_date = {}
    for r in rows:
        if int(r.get("is_return") or 0) == 1:
            continue
        if allowed is not None and r["name"] not in allowed:
            continue

        d = getdate(r["posting_date"])
        g = by_date.setdefault(
            d,
            {
                "min_no": None,
                "max_no": None,
                "total_exempt": 0.0,
                "taxed_15": 0.0,
                "isv_15": 0.0,
                "taxed_18": 0.0,
                "isv_18": 0.0,
                "discount": 0.0,
                "grand_total": 0.0,
                "rounded_total": 0.0,
                "has_data": False,
            },
        )

        # Acumular
        g["total_exempt"] += flt(r.get("exempt_amount"))
        g["taxed_15"] += flt(r.get("taxed_amount_15"))
        g["isv_15"] += flt(r.get("isv_15"))
        g["taxed_18"] += flt(r.get("taxed_amount_18"))
        g["isv_18"] += flt(r.get("isv_18"))
        g["discount"] += flt(r.get("discount_amount"))
        g["grand_total"] += flt(r.get("grand_total"))
        g["rounded_total"] += flt(r.get("rounded_total"))
        g["has_data"] = True

        # Rango: extraer correlativo final del name
        num = extract_last_number(r["name"])
        if num is not None:
            g["min_no"] = num if g["min_no"] is None else min(g["min_no"], num)
            g["max_no"] = num if g["max_no"] is None else max(g["max_no"], num)

    # Construir salida garantizando UNA FILA POR DÍA del rango
    out = []
    cur = from_date
    while cur <= to_date:
        g = by_date.get(
            cur,
            {
                "min_no": None,
                "max_no": None,
                "total_exempt": 0.0,
                "taxed_15": 0.0,
                "isv_15": 0.0,
                "taxed_18": 0.0,
                "isv_18": 0.0,
                "discount": 0.0,
                "grand_total": 0.0,
                "rounded_total": 0.0,
                "has_data": False,
            },
        )

        # Rango: si hay datos, formatear "00000001 - 00000005"; si no, "-"
        rango = "-"
        if g["has_data"] and g["min_no"] is not None and g["max_no"] is not None:
            rango = format_range(g["min_no"], g["max_no"])

        monto_bruto = (
            flt(g["total_exempt"]) + flt(g["taxed_15"]) + flt(g["taxed_18"]) - flt(g["discount"])
        )

        row = [
            cur,                 # Fecha del día (aunque no haya ventas)
            prefix,              # Serie (del filtro)
            rango,               # Rango formateado o "-"
            g["total_exempt"],
            g["taxed_15"],
            g["isv_15"],
            g["taxed_18"],
            g["isv_18"],
            g["discount"],
            monto_bruto,
            g["grand_total"],
            g["rounded_total"],
        ]
        out.append(row)

        cur = cur + timedelta(days=1)

    return out

def extract_last_number(name):
    """Devuelve el último grupo de dígitos en el nombre como int (para el rango)."""
    m = re.findall(r"(\d+)", name or "")
    if not m:
        return None
    try:
        return int(m[-1])
    except Exception:
        return None

def format_range(min_no, max_no, min_width=8):
    """Formatea el rango con ceros a la izquierda: 00000001 - 00000005.
    Si los números reales son más largos, se toma ese ancho.
    """
    width = max(min_width, len(str(min_no)), len(str(max_no)))
    return f"{str(min_no).zfill(width)} - {str(max_no).zfill(width)}"

def get_allowed_invoice_set(filters):
    """Restringe por Warehouse/Cost Center a nivel de ítems."""
    warehouse = filters.get("warehouse")
    cost_center = filters.get("cost_center")
    if not warehouse and not cost_center:
        return None

    where = ["si.docstatus = 1"]
    params = {}

    # Respetar filtros base del reporte
    if filters.get("company"):
        where.append("si.company = %(company)s")
        params["company"] = filters["company"]
    if filters.get("from_date") and filters.get("to_date"):
        where.append("si.posting_date BETWEEN %(from_date)s AND %(to_date)s")
        params["from_date"] = filters["from_date"]
        params["to_date"] = filters["to_date"]
    if filters.get("prefix"):
        where.append("si.naming_series = %(prefix)s")
        params["prefix"] = filters["prefix"]

    # Filtros por ítem
    if warehouse:
        where.append("sii.warehouse = %(warehouse)s")
        params["warehouse"] = warehouse
    if cost_center:
        where.append("sii.cost_center = %(cost_center)s")
        params["cost_center"] = cost_center

    names = frappe.db.sql(
        f"""
        SELECT DISTINCT sii.parent
        FROM `tabSales Invoice Item` sii
        INNER JOIN `tabSales Invoice` si ON si.name = sii.parent
        WHERE {' AND '.join(where)}
        """,
        params,
        as_list=True,
    )
    return {n[0] for n in names} if names else set()
