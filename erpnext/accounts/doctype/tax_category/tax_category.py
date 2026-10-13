import frappe
from frappe.model.document import Document


class TaxCategory(Document):
	pass


def create_default_tax_categories():
	"""
	Crea las 4 categorias fiscales estándar de Honduras (SAR) si no existen:
	1. Contribuyente (Por defecto)
	2. No contribuyente
	3. Exportacion
	4. Exonerado
	"""
	default_categories = [
		"Contribuyente",
		"No contribuyente",
		"Exportacion",
		"Exonerado",
	]

	for category in default_categories:
		if not frappe.db.exists("Tax Category", category):
			doc = frappe.new_doc("Tax Category")
			doc.title = category
			doc.flags.ignore_permissions = True
			doc.flags.ignore_mandatory = True
			doc.insert()

	if frappe.db.table_exists("Customer"):
		frappe.db.sql(
			"""
			UPDATE `tabCustomer`
			SET tax_category = 'Contribuyente'
			WHERE tax_category IS NULL OR tax_category = ''
			"""
		)
		frappe.db.commit()
