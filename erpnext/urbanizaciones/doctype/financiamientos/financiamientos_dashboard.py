from frappe import _

def get_data():
    return {
        "fieldname": "financiamiento",
        "transactions": [
            {
                "label": _("Facturación"),
                "items": [
                    "Generar Factura"
                ]
            }
        ]
    }