# Copyright (c) 2025, Frappe Technologies Pvt. Ltd. and contributors
# For license information, please see license.txt

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
        {"fieldname": "total", "fieldtype": "Currency", "label": "Total", "width": 110},
        {"fieldname": "total_final", "fieldtype": "Currency", "label": "Total Final", "width": 110},
        {"fieldname": "cost", "fieldtype": "Currency", "label": "Costo", "width": 110},
        {"fieldname": "utility", "fieldtype": "Currency", "label": "Utilidad", "width": 110},
        {"fieldname": "utility_percentage", "fieldtype": "Currency", "label": "% Utilidad", "width": 110}
    ]

    data = []

    warehouses = frappe.get_all("Warehouse", ["name"])

    for warehouse in warehouses:
        row = add_row(filters, warehouse.name, "Factura de venta", 0)
        if row and row[10] != 0:
            data.append(row)

        row_return = add_row(filters, warehouse.name, "Devolución", 1)
        if row_return and row_return[10] != 0:
            data.append(row_return)

    return columns, data

def add_row(filters, warehouse_name, type_document, is_return):
    total_exempt = base_isv_15 = isv_15 = base_isv_18 = isv_18 = discount_amount = 0
    total = total_final = cost = utility = utility_percentage = 0

    profiles = frappe.get_all("POS Profile", ["name"], filters={"warehouse": warehouse_name})

    for profile in profiles:
        conditions = return_filters(filters, profile.name, is_return)
        sales_invoices = frappe.get_all("Sales Invoice", [
            "name", "exempt_amount", "taxed_amount_15", "isv_15",
            "taxed_amount_18", "isv_18", "discount_amount",
            "rounded_total", "grand_total"
        ], filters=conditions, order_by='name')

        for sale in sales_invoices:
            items = frappe.get_all("Sales Invoice Item", ["incoming_rate", "rate"], filters={"parent": sale.name})

            for item in items:
                cost += flt(item.incoming_rate)
                utility += flt(item.rate) - flt(item.incoming_rate)

            if cost > 0:
                utility_percentage = (utility / cost) * 100

            total_exempt += flt(sale.exempt_amount)
            base_isv_15 += flt(sale.taxed_amount_15)
            isv_15 += flt(sale.isv_15)
            base_isv_18 += flt(sale.taxed_amount_18)
            isv_18 += flt(sale.isv_18)
            discount_amount += flt(sale.discount_amount)
            total += flt(sale.rounded_total)
            total_final += flt(sale.grand_total)

    gross_amount = total_exempt + base_isv_15 + base_isv_18 - discount_amount

    row = [
        warehouse_name,
        type_document,
        total_exempt,
        base_isv_15,
        isv_15,
        base_isv_18,
        isv_18,
        discount_amount,
        gross_amount,
        total,
        total_final,
        cost,
        utility,
        utility_percentage
    ]

    return row

def return_filters(filters, pos_profile, is_return):
    conditions = {}
    if filters.get("from_date") and filters.get("to_date"):
        conditions["posting_date"] = ["between", [filters["from_date"], filters["to_date"]]]
    if filters.get("company"):
        conditions["company"] = filters.get("company"]
    conditions["pos_profile"] = pos_profile
    conditions["is_return"] = is_return
    return conditions
