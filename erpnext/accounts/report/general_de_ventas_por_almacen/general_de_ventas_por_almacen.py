from __future__ import unicode_literals
import frappe
from frappe.utils import flt
from frappe import _

def execute(filters=None):
	if not filters: filters = {}

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
		{"fieldname": "total_rounded", "fieldtype": "Currency", "label": "Total Redondeado", "width": 110},
		{"fieldname": "cost", "fieldtype": "Currency", "label": "Costo", "width": 110},
		{"fieldname": "utility", "fieldtype": "Currency", "label": "Utilidad", "width": 110},
		{"fieldname": "utility_percentage", "fieldtype": "Percent", "label": "% Utilidad", "width": 110},
	]

	data = []
	warehouses = frappe.get_all("Warehouse", pluck="name")

	for warehouse in warehouses:
		row = add_row(filters, warehouse, "Factura de venta", 0)
		if row and row[9] != 0:
			data.append(row)

		row_return = add_row(filters, warehouse, "Devolución", 1)
		if row_return and row_return[9] != 0:
			data.append(row_return)

	return columns, data

def add_row(filters, warehouse, type_document, is_return):
	total_exempt = base_isv_15 = isv_15 = base_isv_18 = isv_18 = 0
	discount_amount = total = total_rounded = cost = utility = 0

	profiles = frappe.get_all("POS Profile", pluck="name", filters={"warehouse": warehouse})

	for profile in profiles:
		conditions = build_conditions(filters, profile, is_return)
		sales_invoices = frappe.get_all("Sales Invoice", filters=conditions, fields=[
			"name", "exempt_amount", "taxed_amount_15", "isv_15", "taxed_amount_18",
			"isv_18", "discount_amount", "rounded_total"
		])

		for sale in sales_invoices:
			items = frappe.get_all("Sales Invoice Item", filters={"parent": sale.name}, fields=["qty", "incoming_rate"])
			for item in items:
				cost += flt(item.qty) * flt(item.incoming_rate)

			total_exempt += flt(sale.exempt_amount)
			base_isv_15 += flt(sale.taxed_amount_15)
			isv_15 += flt(sale.isv_15)
			base_isv_18 += flt(sale.taxed_amount_18)
			isv_18 += flt(sale.isv_18)
			discount_amount += flt(sale.discount_amount)
			total_rounded += flt(sale.rounded_total)

	# monto bruto SIN impuestos
	monto_bruto = flt(total_exempt) + flt(base_isv_15) + flt(base_isv_18) - flt(discount_amount)

	# total CON impuestos
	total = flt(total_exempt) + flt(base_isv_15) + flt(isv_15) + flt(base_isv_18) + flt(isv_18) - flt(discount_amount)
	utility = monto_bruto - flt(cost)
	utility_percentage = (utility * 100 / monto_bruto) if monto_bruto > 0 else 0
	utility_percentage = max(0, min(utility_percentage, 100))

	return [
		warehouse,
		type_document,
		total_exempt,
		base_isv_15,
		isv_15,
		base_isv_18,
		isv_18,
		discount_amount,
		monto_bruto,
		total,
		total_rounded,
		cost,
		utility,
		utility_percentage
	]

def build_conditions(filters, pos_profile, is_return):
	conditions = {
		"pos_profile": pos_profile,
		"is_return": is_return
	}
	if filters.get("from_date") and filters.get("to_date"):
		conditions["posting_date"] = ["between", [filters["from_date"], filters["to_date"]]]
	if filters.get("company"):
		conditions["company"] = filters["company"]

	return conditions

