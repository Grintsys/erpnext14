# Copyright (c) 2025, Frappe Technologies Pvt. Ltd. and contributors
# For license information, please see license.txt

from __future__ import unicode_literals
import frappe
from frappe.utils import flt
from frappe import _, msgprint


def execute(filters=None):
	if not filters: filters = {}

	columns = [
		{
			"fieldname": "warehouse",
   			"fieldtype": "Link",
			"options": "Warehouse",
   			"label": "Almacen",
			"width": 140
		},
		{
			"fieldname": "type_document",
   			"fieldtype": "Data",
   			"label": "Tipo de documento",
			"width": 140
		},
		{
   			"fieldname": "total_exempt",
  			"fieldtype": "Currency",
  			"label": "Total Exento",
			"width": 110
  		},
		{
			"fieldname": "base_isv_15%",
   			"fieldtype": "Currency",
   			"label": "Base ISV 15%",
			"width": 110
		},
		{
			"fieldname": "isv_15%",
   			"fieldtype": "Currency",
   			"label": "ISV 15%",
			"width": 110
		}		,
		{
			"fieldname": "base_isv_18%",
   			"fieldtype": "Currency",
   			"label": "Base ISV 18%",
			"width": 110
		},
		{
			"fieldname": "isv_18%",
   			"fieldtype": "Currency",
   			"label": "ISV 18%",
			"width": 110
		},
		{
			"fieldname": "discount_amount",
   			"fieldtype": "Currency",
   			"label": "Descuento",
			"width": 110
		},
		{
			"fieldname": "total",
   			"fieldtype": "Currency",
   			"label": "Total",
			"width": 110
		},		
		{
			"fieldname": "total_final",
   			"fieldtype": "Currency",
   			"label": "Total Final",
			"width": 110
		},		
		{
			"fieldname": "cost",
   			"fieldtype": "Currency",
   			"label": "Costo",
			"width": 110
		},		
		{
			"fieldname": "utility",
   			"fieldtype": "Currency",
   			"label": "Utilidad",
			"width": 110
		},		
		{
			"fieldname": "utility_percentage",
   			"fieldtype": "Currency",
   			"label": "% Utilidad",
			"width": 110
		}
	]

	data = []

	warehouses = frappe.get_all("Warehouse", ["*"])

	for warehouse in warehouses:
		row = addRow(filters, warehouse, "Factura de venta", 0)
		if row and row[8] != 0:
			data.append(row)

		row_return = addRow(filters, warehouse, "Devolución", 1)
		if row_return and row_return[8] != 0:
			data.append(row_return)

	return columns, data

def addRow(filters, warehouse, type_document, is_return):
	total_exempt = 0
	base_isv_15 = 0
	isv_15 = 0
	base_isv_18 = 0
	isv_18 = 0
	discount_amount = 0
	total = 0
	total_final = 0
	cost = 0
	utility = 0
	utility_percentage = 0

	profiles = frappe.get_all("POS Profile", ["*"], filters = {"warehouse": warehouse.name})

	for profile in profiles:
		conditions = return_filters(filters, profile.name, is_return)
		sales_invoice = frappe.get_all("Sales Invoice", ["*"], filters = conditions, order_by='name')

		for sale in sales_invoice:

			sales_invoice_items = frappe.get_all("Sales Invoice Item", ["*"], filters = {"parent": sale.name})

			for item in sales_invoice_items:
				cost += item.incoming_rate
				utility += item.rate - item.incoming_rate
			
			if cost > 0:
    			utility_percentage = (utility / cost) * 100
				
			total_exempt += sale.exempt_amount
			base_isv_15 += sale.taxed_amount_15
			isv_15 += sale.isv_15
			base_isv_18 += sale.taxed_amount_18
			isv_18 += sale.isv_18
			discount_amount += sale.discount_amount
			total += sale.rounded_total
			total_final += sale.grand_total
		
	row = [
		warehouse.name,
		type_document,
		total_exempt,
		base_isv_15,
		isv_15,
		base_isv_18,
		isv_18,
		discount_amount,
		total,
		total_final,
		cost,
		utility,
		utility_percentage
	]

	return row

def return_filters(filters, pos_profile, is_return):
	conditions = ''

	conditions += "{"
	if filters.get("from_date") and filters.get("to_date"):
		conditions += '"posting_date": ["between", ["{}", "{}"]]'.format(
			filters["from_date"], filters["to_date"]
		)

	if filters.get("company"): conditions += ', "company": "{}"'.format(filters.get("company"))
	conditions += ', "pos_profile": "{}"'.format(pos_profile)
	conditions += ', "is_return": {}'.format(is_return)
	conditions += '}'

	return conditions