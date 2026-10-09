import frappe
from frappe.model.document import Document

class Pagodecuota(Document):
	def validate(self):
		if not self.company:
			if self.financiamiento:
				self.company = frappe.db.get_value("Financiamientos", self.financiamiento, "company")
			if not self.company:
				self.company = frappe.defaults.get_user_default("Company") or frappe.db.get_single_value("Global Defaults", "default_company")

