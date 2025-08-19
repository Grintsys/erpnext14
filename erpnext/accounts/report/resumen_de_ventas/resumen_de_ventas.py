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
        _("Facturas") + ":Int:80",
        _("Ventas exentas") + ":Currency:120",
        _("Base 15%") + ":Currency:140",
        _("I.S.V 15%") + ":Currency:110",
        _("Base 18%") + ":Currency:140",
        _("I.S.V 18%") + ":Currency:110",
        _("Descuento") + ":Currency:120",
        _("Monto Bruto") + ":Currency:120",
        _("Total") + ":Currency:120",
        _("Total Redondeado") + ":Currency:140"
    ]

def get_data(filters):
    company = filters.get("company")
    from_date = getdate(filters.get("from_date"))
    to_date = getdate(filters.get("to_date"))
    prefix = (filters.get("prefix") or "").strip()

    if not (company and from_date and to_date):
        return []

    # Base query: facturas válidas en rango
    where = [
        "si.docstatus = 1",
        "si.company = %(company)s",
        "si.posting_date BETWEEN %(from_date)s AND %(to_date)s"
    ]
    params = {"company": company, "from_date": from_date, "to_date": to_date}

    # Serie de facturación (opcional). Si se deja en blanco: todas.
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

    # Agregar por día (excluye devoluciones)
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
                "rounded": 0.0
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

    # Una fila por día del rango (si no hay ventas, count=0 y montos 0.00)
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
                "rounded": 0.0
            }
        )
        monto_bruto = flt(g["exempt"]) + flt(g["taxed15"]) + flt(g["taxed18"]) - flt(g["discount"])
        out.append([
            cur,
            g["count"],
            g["exempt"],
            g["taxed15"],
            g["isv15"],
            g["taxed18"],
            g["isv18"],
            g["discount"],
            monto_bruto,
            g["total"],
            g["rounded"]
        ])
        cur = cur + timedelta(days=1)

    return out
