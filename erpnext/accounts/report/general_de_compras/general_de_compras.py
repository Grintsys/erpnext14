# Copyright (c) 2025
from __future__ import unicode_literals
import frappe
from frappe.utils import flt
from frappe import _

def execute(filters=None):
    filters = filters or {}

    # Orden de columnas: datos -> bases e impuestos -> descuento -> totales
    columns = [
        {"fieldname": "date",          "fieldtype": "Date",    "label": _("Fecha"),              "width": 100},
        {"fieldname": "warehouse",     "fieldtype": "Link",    "options": "Warehouse",           "label": _("Almacén"),           "width": 150},
        {"fieldname": "document",      "fieldtype": "Link",    "options": "Purchase Invoice",    "label": _("Documento"),         "width": 140},
        {"fieldname": "provider",      "fieldtype": "Link",    "options": "Supplier",            "label": _("Proveedor"),         "width": 160},

        {"fieldname": "exempt_amount", "fieldtype": "Currency","label": _("Exento"),             "width": 110},
        {"fieldname": "base_15",       "fieldtype": "Currency","label": _("Base 15%"),           "width": 110},
        {"fieldname": "isv_15",        "fieldtype": "Currency","label": _("ISV 15%"),            "width": 110},
        {"fieldname": "base_18",       "fieldtype": "Currency","label": _("Base 18%"),           "width": 110},
        {"fieldname": "isv_18",        "fieldtype": "Currency","label": _("ISV 18%"),            "width": 110},
        {"fieldname": "discount_amount","fieldtype": "Currency","label": _("Descuento"),         "width": 110},

        {"fieldname": "monto_bruto",   "fieldtype": "Currency","label": _("Monto Bruto"),        "width": 120},
        {"fieldname": "grand_total",   "fieldtype": "Currency","label": _("Total Neto"),         "width": 120},
        {"fieldname": "rounded_total", "fieldtype": "Currency","label": _("Total Redondeado"),   "width": 130},
        {"fieldname": "debit",         "fieldtype": "Currency","label": _("Total Contado"),      "width": 120},
        {"fieldname": "credit",        "fieldtype": "Currency","label": _("Total Crédito"),      "width": 120},
    ]

    data = []

    conditions = get_filters(filters)

    fields = [
        "name", "posting_date", "supplier",
        "exempt_amount", "isv_15", "taxed_amount_15",
        "isv_18", "taxed_amount_18", "discount_amount",
        "grand_total", "rounded_total", "total_advance",
        "outstanding_amount", "set_warehouse", "disable_rounded_total",
    ]

    invoices = frappe.get_all(
        "Purchase Invoice",
        fields=fields,
        filters=conditions,
        order_by="posting_date asc, name asc",
    )

    for pi in invoices:
        # Monto Bruto = Exento + Base15 + Base18 - Descuento adicional
        monto_bruto = (
            flt(pi.exempt_amount)
            + flt(pi.taxed_amount_15)
            + flt(pi.taxed_amount_18)
            - flt(pi.discount_amount)
        )

        # Total Contado (pagado) = Total - Pendiente (respetando redondeo)
        if pi.disable_rounded_total:
            debit = flt(pi.grand_total) - flt(pi.outstanding_amount)
        else:
            debit = flt(pi.rounded_total) - flt(pi.outstanding_amount)

        data.append({
            "date":            pi.posting_date,
            "warehouse":       pi.set_warehouse,
            "document":        pi.name,
            "provider":        pi.supplier,

            # nuevas columnas visibles
            "exempt_amount":   flt(pi.exempt_amount),
            "base_15":         flt(pi.taxed_amount_15),
            "isv_15":          flt(pi.isv_15),
            "base_18":         flt(pi.taxed_amount_18),
            "isv_18":          flt(pi.isv_18),
            "discount_amount": flt(pi.discount_amount),

            # ya existentes
            "monto_bruto":     monto_bruto,
            "grand_total":     flt(pi.grand_total),
            "rounded_total":   flt(pi.rounded_total),
            "debit":           debit,
            "credit":          flt(pi.outstanding_amount),
        })

    return columns, data


def get_filters(filters):
    conditions = {"docstatus": 1}

    if filters.get("from_date") and filters.get("to_date"):
        conditions["posting_date"] = ["between", [filters["from_date"], filters["to_date"]]]

    if filters.get("company"):
        conditions["company"] = filters["company"]

    # Si más adelante agregas filtros en el .js, ya están listos:
    if filters.get("warehouse"):
        conditions["set_warehouse"] = filters["warehouse"]
    if filters.get("supplier"):
        conditions["supplier"] = filters["supplier"]

    return conditions
