from frappe import _

def get_data():
	return {
		"fieldname": "activos",
		"transactions": [
			{"label": _("Financiamiento y Contratos"), "items": ["Financiamientos", "Cancelar Financiamiento"]},
		],
	}
