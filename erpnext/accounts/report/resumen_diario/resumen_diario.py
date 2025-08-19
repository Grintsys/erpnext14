# Copyright (c) 2025, Frappe Technologies Pvt. Ltd. and contributors
# For license information, please see license.txt

from __future__ import unicode_literals
from datetime import timedelta
import re
import frappe
from frappe import _
from frappe.utils import flt, getdate

def execute(filters=None):
    filters = filters or {}
    columns = get_columns()
    data = get_data(filters)
    return columns, data

def get_columns():
    return [
        _("Fecha") + "::120",
        _("Rango") + "::180",                # ######## - ######## (8 dígitos)
        _("Facturas") + ":Int:80",
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
    company = filters.get("company")
    from_date = getdate(filters.get("from_date"))
    to_date = getdate(filters.get("to_date"))
    prefix = (filters.get("prefix") or "").strip()

    if not (company and from_date and to_date):
        return []

    # Base query (excluye borradores/boletas anuladas)
    where = [
        "si.docstatus = 1",
        "si.company = %(company)s",
        "si.posting_date BETWEEN %(from_date)s AND %(to_date)s"
    ]
    params = {"company": company, "from_date": from_date, "to_date": to_date}

    # Serie opcional: si no se indica, se incluyen todas
    if prefix:
        where.append("si.naming_series = %(prefix)s")
        params["prefix"] = prefix

    rows = frappe.db.sql(
        f"""
        SELECT
            si.name,
            si.posting_date,
            COALESCE(si.is_return, 0) AS is_return,
            si.exempt_amount,
            si.taxed_amount_15,
            si.isv_15,
            si.taxed_amount_18,
            si.isv_18,
            si.discount_amount,
            si.grand_total,
            si.rounded_total
        FROM `tabSales Invoice` si
        WHERE {" AND ".join(where)}
        ORDER BY si.posting_date, si.name
        """,
        params,
        as_dict=True
    )

    # Agregación por día (ignorando devoluciones)
    daily = {}
    for r in rows:
        if int(r.get("is_return") or 0) == 1:
            continue

        d = getdate(r["posting_date"])
        g = daily.setdefault(
            d,
            {
                "count": 0,
                "exempt": 0.0,
                "taxed15": 0.0,
                "isv15": 0.0,
                "taxed18": 0.0,
                "isv18": 0.0,
                "discount": 0.0,
                "total": 0.0,
                "rounded": 0.0,
                "min_no": None,
                "max_no": None,
            }
        )
        g["count"] += 1
        g["exempt"] += flt(r.get("exempt_amount"))
        g["taxed15"] += flt(r.get("taxed_amount_15"))
        g["isv15"] += flt(r.get("isv_15"))
        g["taxed18"] += flt(r.get("taxed_amount_18"))
        g["isv18"] += flt(r.get("isv_18"))
        g["discount"] += flt(r.get("discount_amount"))
        g["total"] += flt(r.get("grand_total"))
        g["rounded"] += flt(r.get("rounded_total"))

        # Rango: tomar último grupo de dígitos del name
        num = extract_last_number(r["name"])
        if num is not None:
            g["min_no"] = num if g["min_no"] is None else min(g["min_no"], num)
            g["max_no"] = num if g["max_no"] is None else max(g["max_no"], num)

    # Construir salida: UNA FILA POR DÍA (si no hay ventas, rango "-" y montos 0.00)
    out = []
    cur = from_date
    while cur <= to_date:
        g = daily.get(
            cur,
            {
                "count": 0,
                "exempt": 0.0,
                "taxed15": 0.0,
                "isv15": 0.0,
                "taxed18": 0.0,
                "isv18": 0.0,
                "discount": 0.0,
                "total": 0.0,
                "rounded": 0.0,
                "min_no": None,
                "max_no": None,
            }
        )

        # Rango con 8 dígitos si hay datos; si no, "-"
        rango = "-"
        if g["count"] > 0 and g["min_no"] is not None and g["max_no"] is not None:
            rango = format_range(g["min_no"], g["max_no"])

        monto_bruto = flt(g["exempt"]) + flt(g["taxed15"]) + flt(g["taxed18"]) - flt(g["discount"])

        out.append([
            cur,
            rango,
            g["count"],
            g["exempt"],
            g["taxed15"],
            g["isv15"],
            g["taxed18"],
            g["isv18"],
            g["discount"],
            monto_bruto,
            g["total"],
            g["rounded"],
        ])
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
    """Formatea 00000001 - 00000005 (mín. 8 dígitos; si hay más, se adapta)."""
    width = max(min_width, len(str(min_no)), len(str(max_no)))
    return f"{str(min_no).zfill(width)} - {str(max_no).zfill(width)}"
