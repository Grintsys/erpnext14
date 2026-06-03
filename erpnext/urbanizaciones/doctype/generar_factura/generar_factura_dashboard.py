from frappe import _

def get_data():
    return {
        "fieldname": "invoice_generate",
        "transactions": [
            {
                "label": _("Facturación"),
                "items": [
                    "Sales Invoice"
                ]
            }
        ]
    }