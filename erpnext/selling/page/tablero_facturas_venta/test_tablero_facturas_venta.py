# -*- coding: utf-8 -*-
import frappe
import unittest
from erpnext.selling.page.tablero_facturas_venta.tablero_facturas_venta import get_dashboard_data

class TestTableroFacturasVenta(unittest.TestCase):
    def test_get_dashboard_data(self):
        company = frappe.defaults.get_user_default("Company") or frappe.db.get_single_value("Global Defaults", "default_company")
        res = get_dashboard_data(company=company)
        self.assertIn("kpis", res)
        self.assertIn("trend_chart", res)
        self.assertIn("payment_chart", res)
        self.assertIn("top_customers", res)
        self.assertIn("top_products", res)
        self.assertIn("recent_invoices", res)
