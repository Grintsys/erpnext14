import frappe
from erpnext.accounts.doctype.tax_category.tax_category import (
	cleanup_accidental_naming_series_property_setters,
	setup_standard_sales_tax_templates,
)


def execute():
	cleanup_accidental_naming_series_property_setters()
	setup_standard_sales_tax_templates()
