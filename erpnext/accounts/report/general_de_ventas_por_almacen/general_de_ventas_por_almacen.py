
# Copyright (c) 2025, Frappe Technologies Pvt. Ltd. and contributors
# For license information, please see license.txt

from __future__ import unicode_literals
import frappe
from frappe.utils import flt
from frappe import _


def execute(filters=None):
    if not filters:
        filters = {}

    columns = [
        {"fieldname": "warehouse", "fieldtype": "Link", "options": "Warehouse", "label": "Almacen", "width": 140},
        {"fieldname": "type_document", "fieldtype": "Data", "label": "Tipo de documento", "width": 140},
        {"fieldname": "total_exempt", "fieldtype": "Currency", "label": "Total Exento", "width": 110},
        {"fieldname": "base_isv_15", "fieldtype": "Currency", "label": "Base ISV 15%", "width": 110},
        {"fieldname": "isv_15", "fieldtype": "Currency", "label": "ISV 15%", "width": 110},
        {"fieldname": "base_isv_18", "fieldtype": "Currency", "label": "Base ISV 18%", "width": 110},
        {"fieldname": "isv_18", "fieldtype": "Currency", "label": "ISV 18%", "width": 110},
        {"fieldname": "discount_amount", "fieldtype": "Currency", "label": "Descuento", "width": 110},
        {"fieldname": "monto_bruto", "fieldtype": "Currency", "label": "Monto Bruto", "width": 110},
        {"fieldname": "total", "fieldtype": "Currency", "label": "Total", "width": 110},
        {"fieldname": "total_final", "fieldtype": "Currency", "label": "Total Final", "width": 110},
        {"fieldname": "cost", "fieldtype": "Currency", "label": "Costo", "width": 110},
        {"fieldname": "utility", "fieldtype": "Currency", "label": "Utilidad", "width": 110},
        {"fieldname": "utility_percentage", "fieldtype": "Percent", "label": "% Utilidad", "width": 110}
    ]

    data = []
    warehouses = frappe.get_all("Warehouse", ["name"])
    for warehouse in warehouses:
        row = add_row(filters, warehouse.name, "Factura de venta", 0)
        if row and row["total"] != 0:
            data.append(row)
        row_return = add_row(filters, warehouse.name, "Devolución", 1)
        if row_return and row_return["total"] != 0:
            data.append(row_return)

    return columns, [format_row(r) for r in data]


def add_row(filters, warehouse_name, type_document, is_return):
    total_exempt = base_isv_15 = isv_15 = base_isv_18 = isv_18 = discount_amount = total = total_final = cost = 0

    profiles = frappe.get_all("POS Profile", filters={"warehouse": warehouse_name}, pluck="name")
    if not profiles:
        return None

    invoices = frappe.get_all("Sales Invoice", 
        filters={
            "pos_profile": ["in", profiles],
            "is_return": is_return,
            "warehouse": warehouse_name,
            "posting_date": ["between", [filters.get("from_date"), filters.get("to_date")]],
            "company": filters.get("company") if filters.get("company") else ["!=", ""]
        },
        fields=["name", "exempt_amount", "taxed_amount_15", "isv_15", "taxed_amount_18", "isv_18", "discount_amount", "rounded_total", "grand_total"]
    )

    for sale in invoices:
        total_exempt += flt(sale.exempt_amount)
        base_isv_15 += flt(sale.taxed_amount_15)
        isv_15 += flt(sale.isv_15)
        base_isv_18 += flt(sale.taxed_amount_18)
        isv_18 += flt(sale.isv_18)
        discount_amount += flt(sale.discount_amount)
        total += flt(sale.rounded_total)
        total_final += flt(sale.grand_total)

        items = frappe.get_all("Sales Invoice Item", filters={"parent": sale.name}, fields=["qty", "rate", "incoming_rate"])
        for item in items:
            cost += flt(item.qty) * flt(item.incoming_rate)

    monto_bruto = total_exempt + base_isv_15 + base_isv_18 - discount_amount
    utility = monto_bruto - cost
    utility_percentage = (utility / monto_bruto * 100) if monto_bruto else 0
    utility_percentage = min(utility_percentage, 100)

    return {
        "warehouse": warehouse_name,
        "type_document": type_document,
        "total_exempt": total_exempt,
        "base_isv_15": base_isv_15,
        "isv_15": isv_15,
        "base_isv_18": base_isv_18,
        "isv_18": isv_18,
        "discount_amount": discount_amount,
        "monto_bruto": monto_bruto,
        "total": total,
        "total_final": total_final,
        "cost": cost,
        "utility": utility,
        "utility_percentage": utility_percentage
    }


def format_row(row_dict):
    return [
        row_dict["warehouse"],
        row_dict["type_document"],
        row_dict["total_exempt"],
        row_dict["base_isv_15"],
        row_dict["isv_15"],
        row_dict["base_isv_18"],
        row_dict["isv_18"],
        row_dict["discount_amount"],
        row_dict["monto_bruto"],
        row_dict["total"],
        row_dict["total_final"],
        row_dict["cost"],
        row_dict["utility"],
        row_dict["utility_percentage"]
    ]
