# Copyright (c) 2026, Frappe Technologies Pvt. Ltd. and contributors
# For license information, please see license.txt

import frappe
from frappe.model.document import Document

class GenerarFactura(Document):
    pass

@frappe.whitelist()
def get_financiamientos(customer):
    """Obtiene los financiamientos activos de un cliente"""
    if not customer:
        return []
    
    financiamientos = frappe.get_all(
        "Financiamientos",
        filters={
            "customer": customer,
            "status": ["in", ["Activo", "Refinanciado"]]
        },
        fields=["urbanizaciones"]
    )
    
    return financiamientos
