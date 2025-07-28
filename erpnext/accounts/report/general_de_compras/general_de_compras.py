from __future__ import unicode_literals
import frappe
from frappe.utils import flt
from frappe import _, msgprint

def execute(filters=None):
	if not filters: filters = {}

	columns = [
		{"fieldname": "date", "fieldtype": "Date", "label": "Fecha", "width": 100},
		{"fieldname": "warehouse", "fieldtype": "Linnk","options": "Warehouse", "label": "Almacén", "width": 150},
		{"fieldname": "document", "fieldtype": "Link", "options": "Purchase Invoice", "label": "Documento", "width": 140},
		{"fieldname": "provider", "fieldtype": "Link", "options": "Supplier", "label": "Proveedor", "width": 140},
		{"fieldname": "monto_bruto", "fieldtype": "Currency", "label": "Monto Bruto", "width": 110},
		{"fieldname": "isv_15%", "fieldtype": "Currency", "label": "ISV 15%", "width": 110},
		{"fieldname": "isv_18%", "fieldtype": "Currency", "label": "ISV 18%", "width": 110},
		{"fieldname": "grand_total", "fieldtype": "Currency", "label": "Total Neto", "width": 110},
		{"fieldname": "rounded_total", "fieldtype": "Currency", "label": "Total Redondeado", "width": 110},
  		{"fieldname": "debit", "fieldtype": "Currency", "label": "Total Contado", "width": 110},
		{"fieldname": "credit%", "fieldtype": "Currency", "label": "Total Credito", "width": 110}
	]

	data = []

	conditions = return_filters(filters)
 
	fields = [
		"name", "posting_date", "supplier",
		"exempt_amount", "isv_15","taxed_amount_15",
		"isv_18","taxed_amount_18", "discount_amount",
		"grand_total", "rounded_total","total_advance",
		"outstanding_amount", "set_warehouse","disable_rounded_total"
	]

	purchase_invoces = frappe.get_all("Purchase Invoice", fields=fields, filters=conditions, order_by="name")

	for purchase in purchase_invoces:

		# Calcular monto bruto
		monto_bruto = (
			flt(purchase.exempt_amount)
			+ flt(purchase.taxed_amount_15)
			+ flt(purchase.taxed_amount_18)
			- flt(purchase.discount_amount)
		)

		total_debit = 0

		if(purchase.disable_rounded_total):
			total_debit = purchase.grand_total - purchase.outstanding_amount
		else:
			total_debit = purchase.rounded_total - purchase.outstanding_amount

		row = [
			purchase.posting_date,
			purchase.set_warehouse,
			purchase.name,
			purchase.supplier,
			monto_bruto,
			purchase.isv_15,
			purchase.isv_18,
			purchase.grand_total,
			purchase.rounded_total,
			total_debit,
			purchase.outstanding_amount
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