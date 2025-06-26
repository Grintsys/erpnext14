# Copyright (c) 2025, Frappe Technologies Pvt. Ltd. and contributors
# For license information, please see license.txt

from __future__ import unicode_literals
import frappe
from frappe.utils import flt
from frappe import _, msgprint

def execute(filters=None):
    if not filters: filters = {}

    columns = [
        { "fieldname": "date", "fieldtype": "Date", "label": "Fecha", "width": 100 },
        { "fieldname": "document", "fieldtype": "Link", "options": "Sales Invoice", "label": "Documento", "width": 100 },
        { "fieldname": "name", "fieldtype": "Data", "label": "Nombre", "width": 140 },
        { "fieldname": "rtn", "fieldtype": "Data", "label": "RTN", "width": 120 },
        { "fieldname": "type_document", "fieldtype": "Data", "label": "Tipo de documento", "width": 180 },
        { "fieldname": "total_exempt", "fieldtype": "Currency", "label": "Total Exento", "width": 110 },
        { "fieldname": "base_isv_15%", "fieldtype": "Currency", "label": "Base ISV 15%", "width": 110 },
        { "fieldname": "isv_15%", "fieldtype": "Currency", "label": "ISV 15%", "width": 110 },
        { "fieldname": "base_isv_18%", "fieldtype": "Currency", "label": "Base ISV 18%", "width": 110 },
        { "fieldname": "isv_18%", "fieldtype": "Currency", "label": "ISV 18%", "width": 110 },
        { "fieldname": "discount_amount", "fieldtype": "Currency", "label": "Descuento", "width": 110 },
        { "fieldname": "gross_amount", "fieldtype": "Currency", "label": "Monto Bruto", "width": 110 },
        { "fieldname": "total", "fieldtype": "Currency", "label": "Total", "width": 110 },
        { "fieldname": "total_final", "fieldtype": "Currency", "label": "Total Final", "width": 110 },
        { "fieldname": "cost", "fieldtype": "Currency", "label": "Costo", "width": 110 },
        { "fieldname": "utility", "fieldtype": "Currency", "label": "Utilidad", "width": 110 },
        { "fieldname": "utility_percentage", "fieldtype": "Currency", "label": "% Utilidad", "width": 110 }
    ]

    data = []
    customer_tax_ids = {}
    conditions = return_filters(filters)

    sales_invoice = frappe.get_all("Sales Invoice", [
        "name", "customer", "posting_date", "exempt_amount",
        "taxed_amount_15", "isv_15", "taxed_amount_18", "isv_18",
        "discount_amount", "rounded_total", "grand_total", "is_return"
    ], filters=conditions, order_by='name')

    for sales in sales_invoice:
        if sales.customer not in customer_tax_ids:
            customer_tax_ids[sales.customer] = frappe.db.get_value("Customer", sales.customer, "tax_id")
        tax_id = customer_tax_ids[sales.customer]

        type_document = "Factura de venta"
        if sales.is_return:
            type_document = "Devolución"

        cost = 0
        utility = 0
        utility_percentage = 0

        items = frappe.get_all("Sales Invoice Item", [
            "incoming_rate", "rate", "qty"
        ], filters={"parent": sales.name})

        cost = 0
        total_sale_amount = 0

        for item in items:
            item_cost = flt(item.incoming_rate) * flt(item.qty)
            item_total = flt(item.rate) * flt(item.qty)
            cost += item_cost
            total_sale_amount += item_total

        gross_amount = flt(sales.exempt_amount) + flt(sales.taxed_amount_15) + flt(sales.taxed_amount_18) - flt(sales.discount_amount)
        utility = gross_amount - cost
        utility_percentage = (utility / gross_amount * 100) if gross_amount > 0 else 0

        row = [
            sales.posting_date,
            type_document,
            sales.customer,
            tax_id,
            sales.name,
            sales.exempt_amount,
            sales.taxed_amount_15,
            sales.isv_15,
            sales.taxed_amount_18,
            sales.isv_18,
            sales.discount_amount,
            gross_amount,
            sales.rounded_total,
            sales.grand_total,
            cost,
            utility,
            utility_percentage
        ]
        data.append(row)

    return columns, data

def return_filters(filters):
    conditions = {}
    if filters.get("from_date") and filters.get("to_date"):
        conditions["posting_date"] = ["between", [filters["from_date"], filters["to_date"]]]
    if filters.get("company"):
        conditions["company"] = filters.get("company")
    return conditions
