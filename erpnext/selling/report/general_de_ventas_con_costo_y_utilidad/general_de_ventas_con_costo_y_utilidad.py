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
   			"fieldname": "date",
  			"fieldtype": "Date",
  			"label": "Fecha",
			"width": 100
  		},
		{
			"fieldname": "rtn",
   			"fieldtype": "Data",
   			"label": "RTN",
			"width": 120
		},
		{
			"fieldname": "name",
   			"fieldtype": "Data",
   			"label": "Nombre",
			"width": 140
		},
		{
			"fieldname": "document",
   			"fieldtype": "Link",
			"options": "Sales Invoice",
   			"label": "Documento",
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

	conditions = return_filters(filters)
	sales_invoice = frappe.get_all("Sales Invoice", ["*"], filters = conditions, order_by='name')
	
	for sales in sales_invoice:
		customer = frappe.get_doc("Customer", sales.customer)
		type_document = "Factura de venta"
		if(sales.is_return): type_document = "Devolución"

		cost = 0
		utility = 0
		utility_percentage = 0

		sales_invoice_items = frappe.get_all("Sales Invoice Item", ["*"], filters = {"parent": sales.name})

		for item in sales_invoice_items:
			cost += item.incoming_rate
			utility += item.rate - item.incoming_rate
		
		utility_percentage += (utility/cost) * 100

		row = [
			sales.posting_date,
			customer.tax_id,
			sales.customer,
			sales.name,
			type_document,
			sales.exempt_amount,
			sales.taxed_amount_15,
			sales.isv_15,
			sales.taxed_amount_18,
			sales.isv_18,
			sales.discount_amount,
			sales.rounded_total,
			sales.grand_total,
			cost,
			utility,
			utility_percentage
		]
		data.append(row)

	return columns, data

def return_filters(filters):
	conditions = ''

	conditions += "{"
	if filters.get("from_date") and filters.get("to_date"):
		conditions += '"posting_date": ["between", ["{}", "{}"]]'.format(
			filters["from_date"], filters["to_date"]
		)

	if filters.get("company"): conditions += ', "company": "{}"'.format(filters.get("company"))
	conditions += '}'

	return conditions