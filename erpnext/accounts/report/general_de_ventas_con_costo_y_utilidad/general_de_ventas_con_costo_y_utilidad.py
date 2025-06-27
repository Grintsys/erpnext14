from __future__ import unicode_literals
import frappe
from frappe.utils import flt

def execute(filters=None):
	if not filters: filters = {}

	columns = [
		{"fieldname": "date", "fieldtype": "Date", "label": "Fecha", "width": 100},
		{"fieldname": "type_document", "fieldtype": "Data", "label": "Documento", "width": 100},
  		{"fieldname": "document", "fieldtype": "Link", "options": "Sales Invoice", "label": "Documento", "width": 180},
		{"fieldname": "name", "fieldtype": "Data", "label": "Nombre", "width": 140},
		{"fieldname": "rtn", "fieldtype": "Data", "label": "RTN", "width": 120},
		{"fieldname": "total_exempt", "fieldtype": "Currency", "label": "Total Exento", "width": 110},
		{"fieldname": "base_isv_15%", "fieldtype": "Currency", "label": "Base ISV 15%", "width": 110},
		{"fieldname": "isv_15%", "fieldtype": "Currency", "label": "ISV 15%", "width": 110},
		{"fieldname": "base_isv_18%", "fieldtype": "Currency", "label": "Base ISV 18%", "width": 110},
		{"fieldname": "isv_18%", "fieldtype": "Currency", "label": "ISV 18%", "width": 110},
		{"fieldname": "discount_amount", "fieldtype": "Currency", "label": "Descuento", "width": 110},
		{"fieldname": "monto_bruto", "fieldtype": "Currency", "label": "Monto Bruto", "width": 110},
		{"fieldname": "total", "fieldtype": "Currency", "label": "Total", "width": 110},
		{"fieldname": "total_final", "fieldtype": "Currency", "label": "Total Final", "width": 110},
		{"fieldname": "cost", "fieldtype": "Currency", "label": "Costo", "width": 110},
		{"fieldname": "utility", "fieldtype": "Currency", "label": "Utilidad", "width": 110},
		{"fieldname": "utility_percentage", "fieldtype": "Percent", "label": "% Utilidad", "width": 110}
	]

	data = []

	conditions = return_filters(filters)

	sales_invoices = frappe.get_all(
		"Sales Invoice",
		fields=["name", "posting_date", "customer", "is_return", "exempt_amount", "taxed_amount_15", "isv_15", "taxed_amount_18", "isv_18", "discount_amount", "rounded_total", "grand_total"],
		filters=conditions,
		order_by="name"
	)

	# Obtener clientes únicos de un solo viaje
	customers = {
		c.name: c.tax_id for c in frappe.get_all(
			"Customer",
			fields=["name", "tax_id"],
			filters={"name": ["in", [inv.customer for inv in sales_invoices]]}
		)
	}

	for sales in sales_invoices:
		type_document = "Devolución" if sales.is_return else "Factura"

		# Calcular costo
		cost = sum(flt(item.qty) * flt(item.incoming_rate) for item in frappe.get_all(
			"Sales Invoice Item",
			fields=["qty", "incoming_rate"],
			filters={"parent": sales.name}
		))

		# Calcular Monto Bruto
		monto_bruto = (
			flt(sales.exempt_amount)
			+ flt(sales.taxed_amount_15)
			+ flt(sales.taxed_amount_18)
			- flt(sales.discount_amount)
		)

		# Calcular Utilidad y % Utilidad
		utility = monto_bruto - cost
		utility_percentage = (utility / monto_bruto * 100) if monto_bruto > 0 else 0
		utility_percentage = min(utility_percentage, 100)

		row = [
			sales.posting_date,
   			type_document,		
   			sales.name,
			sales.customer,		
   			customers.get(sales.customer),
			sales.exempt_amount,
			sales.taxed_amount_15,
			sales.isv_15,
			sales.taxed_amount_18,
			sales.isv_18,
			sales.discount_amount,
			monto_bruto,
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

