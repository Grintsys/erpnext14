from __future__ import unicode_literals
import frappe
from frappe.utils import flt
from frappe import _, msgprint

def execute(filters=None):
	if not filters: filters = {}

	columns = [
		{"fieldname": "date", "fieldtype": "Date", "label": "Fecha", "width": 100},
		{"fieldname": "type_document", "fieldtype": "Data", "label": "Tipo", "width": 150},
		{"fieldname": "document", "fieldtype": "Link", "options": "Sales Invoice", "label": "Documento", "width": 140},
		{"fieldname": "name", "fieldtype": "Data", "label": "Nombre", "width": 140},
		{"fieldname": "rtn", "fieldtype": "Data", "label": "RTN", "width": 120},
  		{"fieldname": "total_exempt", "fieldtype": "Currency", "label": "Total Exento", "width": 110},
		{"fieldname": "base_isv_15%", "fieldtype": "Currency", "label": "Base ISV 15%", "width": 110},
		{"fieldname": "isv_15%", "fieldtype": "Currency", "label": "ISV 15%", "width": 110},
		{"fieldname": "base_isv_18%", "fieldtype": "Currency", "label": "Base ISV 18%", "width": 110},
		{"fieldname": "isv_18%", "fieldtype": "Currency", "label": "ISV 18%", "width": 110},
		{"fieldname": "discount_amount", "fieldtype": "Currency", "label": "Descuento", "width": 110},
		{"fieldname": "monto_bruto", "fieldtype": "Currency", "label": "Monto Bruto", "width": 110},
		{"fieldname": "total", "fieldtype": "Currency", "label": "Total", "width": 110},  # calculado
		{"fieldname": "total_rounded", "fieldtype": "Currency", "label": "Total Redondeado", "width": 110}  # antes "Total Final"
	]

	data = []

	conditions = return_filters(filters)
 
	fields = [
		"name", "posting_date", "customer", "is_return",
		"exempt_amount", "taxed_amount_15", "isv_15",
		"taxed_amount_18", "isv_18", "discount_amount",
		"rounded_total"
	]

	sales_invoices = frappe.get_all("Sales Invoice", fields=fields, filters=conditions, order_by="name")

	for sales in sales_invoices:
		rtn = frappe.db.get_value("Customer", sales.customer, "tax_id")
		type_document = "Devolución" if sales.is_return else "Factura"

		# Calcular monto bruto
		monto_bruto = (
			flt(sales.exempt_amount)
			+ flt(sales.taxed_amount_15)
			+ flt(sales.taxed_amount_18)
			- flt(sales.discount_amount)
		)

		# Nuevo cálculo del total
		total = (
			flt(sales.exempt_amount)
			+ flt(sales.taxed_amount_15) + flt(sales.isv_15)
			+ flt(sales.taxed_amount_18) + flt(sales.isv_18)
			- flt(sales.discount_amount)
		)

		row = [
			sales.posting_date,
			type_document,
			sales.name,
			sales.customer,
			rtn,
			sales.exempt_amount,
			sales.taxed_amount_15,
			sales.isv_15,
			sales.taxed_amount_18,
			sales.isv_18,
			sales.discount_amount,
			monto_bruto,
			total,
			sales.rounded_total  # ahora es Total Redondeado
		]
		data.append(row)

	return columns, data


def return_filters(filters):
	conditions = {
		"docstatus": 1  # Solo facturas validadas
	}

	if filters.get("from_date") and filters.get("to_date"):
		conditions["posting_date"] = ["between", [filters["from_date"], filters["to_date"]]]

	if filters.get("company"):
		conditions["company"] = filters["company"]

	return conditions

