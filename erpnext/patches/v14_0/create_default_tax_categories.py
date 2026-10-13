import frappe
from erpnext.accounts.doctype.tax_category.tax_category import create_default_tax_categories


def execute():
	create_default_tax_categories()
