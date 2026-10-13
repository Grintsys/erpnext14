import frappe
from frappe.model.document import Document
from frappe.utils import flt


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


def cleanup_accidental_naming_series_property_setters():
	"""
	Elimina Property Setters de naming_series que fueron exportados por error,
	restaurando las secuencias originales de cada servidor (Document Naming Settings).
	"""
	if frappe.db.table_exists("Property Setter"):
		frappe.db.sql(
			"""
			DELETE FROM `tabProperty Setter`
			WHERE name IN (
				'Sales Invoice-naming_series-options',
				'Sales Invoice-naming_series-default',
				'Customer-naming_series-options',
				'Customer-naming_series-hidden',
				'Customer-naming_series-reqd'
			)
			"""
		)
		frappe.db.commit()
		frappe.clear_cache(doctype="Customer")
		frappe.clear_cache(doctype="Sales Invoice")


def setup_standard_sales_tax_templates(company=None):
	"""
	Estandariza las 4 plantillas de impuestos sobre ventas (Honduras),
	las 3 plantillas de impuestos por producto (Item Tax Templates) y sus Tax Rules:
	1. ISV 15% (Por defecto)
	2. ISV 18%
	3. Exento
	4. Exonerado
	"""
	create_default_tax_categories()

	companies = [company] if company else frappe.get_all("Company", pluck="name")
	if not companies:
		return

	for comp in companies:
		abbr = frappe.get_cached_value("Company", comp, "abbr")
		if not abbr:
			continue

		# Buscar grupo de impuestos pasivos
		tax_group = frappe.db.get_value("Account", {"company": comp, "account_type": "Tax", "is_group": 1}, "name")
		if not tax_group:
			tax_group = frappe.db.get_value("Account", {"company": comp, "account_name": ["like", "%IMPUESTOS%"], "is_group": 1}, "name")
		if not tax_group:
			tax_group = frappe.db.get_value("Account", {"company": comp, "root_type": "Liability", "is_group": 1}, "name")

		def get_or_create_tax_account(acc_name, parent_group):
			full_name = f"{acc_name} - {abbr}"
			if not frappe.db.exists("Account", full_name):
				acc = frappe.get_doc({
					"doctype": "Account",
					"account_name": acc_name,
					"company": comp,
					"parent_account": parent_group,
					"account_type": "Tax",
					"root_type": "Liability",
					"is_group": 0
				})
				acc.flags.ignore_permissions = True
				acc.insert()
				return acc.name
			else:
				frappe.db.set_value("Account", full_name, "is_group", 0)
				return full_name

		acc_15 = get_or_create_tax_account("Débito Fiscal ISV 15%", tax_group)
		acc_18 = get_or_create_tax_account("Débito Fiscal ISV 18%", tax_group)
		acc_exo = get_or_create_tax_account("Débito Fiscal ISV Exonerado 0%", tax_group)
		acc_exento = get_or_create_tax_account("Débito Fiscal ISV Exento 0%", tax_group)

		# 2 Plantillas estándar de Ventas: "Honduras Tax" (General) y "Exonerado"
		templates_data = [
			{
				"title": "Honduras Tax",
				"is_default": 1,
				"tax_category": None,
				"taxes": [
					{
						"charge_type": "On Net Total",
						"account_head": acc_15,
						"description": "ISV 15% (Incluido)",
						"rate": 15.0,
						"included_in_print_rate": 1
					}
				]
			},
			{
				"title": "Exonerado",
				"is_default": 0,
				"tax_category": "Exonerado",
				"taxes": [
					{
						"charge_type": "On Net Total",
						"account_head": acc_exo,
						"description": "ISV Exonerado 0%",
						"rate": 0.0,
						"included_in_print_rate": 1
					}
				]
			}
		]

		created_templates = {}
		for t_data in templates_data:
			tpl_name = frappe.db.get_value(
				"Sales Taxes and Charges Template",
				{"company": comp, "title": t_data["title"]},
				"name"
			)
			if not tpl_name:
				tpl_name = frappe.db.get_value(
					"Sales Taxes and Charges Template",
					{"name": ["in", [t_data["title"], f"{t_data['title']} - {abbr}"]]},
					"name"
				)

			if not tpl_name:
				doc = frappe.get_doc({
					"doctype": "Sales Taxes and Charges Template",
					"title": t_data["title"],
					"company": comp,
					"is_default": t_data["is_default"],
					"tax_category": t_data["tax_category"] if t_data["tax_category"] else None,
					"taxes": t_data["taxes"]
				})
				doc.flags.ignore_permissions = True
				doc.insert()
				created_templates[t_data["title"]] = doc.name
			else:
				created_templates[t_data["title"]] = tpl_name
				if t_data["is_default"]:
					frappe.db.set_value("Sales Taxes and Charges Template", tpl_name, "is_default", 1)
				if t_data["tax_category"]:
					frappe.db.set_value("Sales Taxes and Charges Template", tpl_name, "tax_category", t_data["tax_category"])

		# Vincular Tax Category con las plantillas mediante Tax Rules
		rules_config = [
			{"tax_category": "Contribuyente", "template": created_templates.get("Honduras Tax")},
			{"tax_category": "No contribuyente", "template": created_templates.get("Honduras Tax")},
			{"tax_category": "Exonerado", "template": created_templates.get("Exonerado")},
			{"tax_category": "Exportacion", "template": created_templates.get("Honduras Tax")},
		]

		for r_cfg in rules_config:
			if not r_cfg["template"]:
				continue
			existing_rule = frappe.db.get_value("Tax Rule", {
				"company": comp,
				"tax_category": r_cfg["tax_category"],
				"tax_type": "Sales"
			}, "name")

			if not existing_rule:
				rule = frappe.get_doc({
					"doctype": "Tax Rule",
					"tax_type": "Sales",
					"tax_category": r_cfg["tax_category"],
					"sales_tax_template": r_cfg["template"],
					"company": comp,
					"priority": 1
				})
				rule.flags.ignore_permissions = True
				rule.insert()
			else:
				frappe.db.set_value("Tax Rule", existing_rule, "sales_tax_template", r_cfg["template"])

		# Limpiar plantillas innecesarias previas si no tienen facturas asociadas
		for old_title in ["ISV 15%", "ISV 18%", "Exento"]:
			old_tpl = frappe.db.get_value("Sales Taxes and Charges Template", {"company": comp, "title": old_title}, "name")
			if not old_tpl:
				old_tpl = frappe.db.get_value("Sales Taxes and Charges Template", {"name": f"{old_title} - {abbr}"}, "name")
			if old_tpl and not frappe.db.count("Sales Invoice", {"taxes_and_charges": old_tpl}):
				frappe.delete_doc("Sales Taxes and Charges Template", old_tpl, force=True, ignore_permissions=True)

		# Obtener la cuenta de impuesto exacta utilizada por "Honduras Tax"
		ht_tpl = created_templates.get("Honduras Tax")
		ht_tax_account = None
		if ht_tpl:
			ht_tax_account = frappe.db.get_value("Sales Taxes and Charges", {"parent": ht_tpl}, "account_head")
		if not ht_tax_account:
			ht_tax_account = acc_15

		# Estandarizar Item Tax Templates (ISV15%, ISV18%, EXENTO)
		item_templates_data = [
			{"title": "ISV15%", "account": ht_tax_account, "rate": 15.0},
			{"title": "ISV18%", "account": ht_tax_account, "rate": 18.0},
			{"title": "EXENTO", "account": ht_tax_account, "rate": 0.0},
		]

		for it_data in item_templates_data:
			existing_it = frappe.db.get_value(
				"Item Tax Template",
				{"company": comp, "title": it_data["title"]},
				"name"
			)
			if not existing_it:
				existing_it = frappe.db.get_value(
					"Item Tax Template",
					{"name": ["in", [it_data["title"], f"{it_data['title']} - {abbr}"]]},
					"name"
				)

			if not existing_it:
				it_doc = frappe.get_doc({
					"doctype": "Item Tax Template",
					"title": it_data["title"],
					"company": comp,
					"taxes": [
						{
							"tax_type": it_data["account"],
							"tax_rate": it_data["rate"]
						}
					]
				})
				it_doc.flags.ignore_permissions = True
				it_doc.insert()
			else:
				tax_detail = frappe.db.get_value(
					"Item Tax Template Detail",
					{"parent": existing_it, "tax_type": it_data["account"]},
					["name", "tax_rate"],
					as_dict=True
				)
				if not tax_detail:
					frappe.get_doc({
						"doctype": "Item Tax Template Detail",
						"parent": existing_it,
						"parenttype": "Item Tax Template",
						"parentfield": "taxes",
						"tax_type": it_data["account"],
						"tax_rate": it_data["rate"]
					}).insert(ignore_permissions=True)
				elif abs(flt(tax_detail.tax_rate) - it_data["rate"]) > 0.01:
					frappe.db.set_value("Item Tax Template Detail", tax_detail.name, "tax_rate", it_data["rate"])

	# Desactivar scripts antiguos de base de datos para que la lógica corra exclusivamente en código nativo versionado
	if frappe.db.table_exists("Client Script"):
		frappe.db.sql(
			"""
			UPDATE `tabClient Script`
			SET enabled = 0
			WHERE name = 'SAR Exoneracion - Sales Invoice Handler'
			"""
		)
	if frappe.db.table_exists("Server Script"):
		frappe.db.sql(
			"""
			UPDATE `tabServer Script`
			SET disabled = 1
			WHERE name = 'SAR Exoneracion - Sales Invoice Server Logic'
			"""
		)
	frappe.db.commit()

