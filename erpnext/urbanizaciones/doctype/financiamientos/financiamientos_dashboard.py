from frappe import _

def get_data():
    return {
        "fieldname": "financiamiento",
        "non_standard_fieldnames": {
            "Cancelar Financiamiento": "financiamientos"
        },
        "transactions": [
            {
                "label": _("Operaciones y Facturación"),
                "items": [
                    "Generar Factura",
                    "Sales Invoice"
                ]
            },
            {
                "label": _("Ajustes y Cancelación"),
                "items": [
                    "Modificar Mora",
                    "Cancelar Financiamiento"
                ]
            }
        ]
    }