# Copyright (c) 2025, Frappe Technologies Pvt. Ltd. and contributors
# For license information, please see license.txt

import frappe
from frappe.model.document import Document

class ConfiguraciondeUrbanizacion(Document):
	
	@frappe.whitelist()
	def get_prefix(self):
		transaction = "Sales Invoice"

		prefixes = ""

		try:
			options = frappe.get_meta(transaction).get_naming_series_options()
			prefixes = "\n".join(sorted(options))
		except Exception as e:
			frappe.log_error(frappe.get_traceback(), str(e))

		return {
            "prefix": prefixes
        }
