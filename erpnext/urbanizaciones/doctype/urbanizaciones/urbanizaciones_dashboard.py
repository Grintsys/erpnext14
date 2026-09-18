from frappe import _

def get_data():
	return {
		"fieldname": "urbanizaciones",
		"transactions": [
			{"label": _("Inventario y Ventas"), "items": ["Activos", "Financiamientos"]},
		],
	}
