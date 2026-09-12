import unittest
import frappe
from erpnext.selling.page.precio_y_utilidades.precio_y_utilidades import (
    calculate_pricing_metrics,
    calculate_target_price_and_margin,
    apply_rounding,
    apply_bulk_prices,
    process_bulk_price_updates_worker
)

class TestPrecioYUtilidades(unittest.TestCase):
    """
    Pruebas unitarias para el motor de cálculo, actualización garantizada e indicadores.
    """

    def test_caso_a_fiscal(self):
        res = calculate_pricing_metrics(cost=50, final_price=115, tax_rate=15)
        self.assertEqual(res["net_price"], 100.0)
        self.assertEqual(res["isv_amount"], 15.0)
        self.assertEqual(res["utility"], 50.0)
        self.assertEqual(res["margin"], 50.0)

    def test_caso_b_fiscal(self):
        res = calculate_pricing_metrics(cost=300, final_price=500, tax_rate=15)
        self.assertEqual(res["net_price"], 434.78)
        self.assertEqual(res["isv_amount"], 65.22)
        self.assertEqual(res["utility"], 134.78)
        self.assertEqual(res["margin"], 31.0)

    def test_caso_c_margen_meta(self):
        res = calculate_target_price_and_margin(cost=300, target_margin=40, tax_rate=15, rounding_strategy="none")
        self.assertEqual(res["net_price"], 500.0)
        self.assertEqual(res["final_price"], 575.0)
        self.assertEqual(res["utility"], 200.0)
        self.assertEqual(res["margin"], 40.0)

    def test_caso_d_directo(self):
        res = calculate_pricing_metrics(cost=300, final_price=575, tax_rate=15)
        self.assertEqual(res["net_price"], 500.0)
        self.assertEqual(res["utility"], 200.0)
        self.assertEqual(res["margin"], 40.0)

    def test_redondeo_y_recalculo_margen_real(self):
        res = calculate_target_price_and_margin(cost=300, target_margin=35, tax_rate=15, rounding_strategy="ceil")
        self.assertEqual(res["final_price"], 531.0)
        self.assertEqual(res["margin"], 35.03)

    def test_item_sin_costo(self):
        res = calculate_pricing_metrics(cost=0, final_price=100, tax_rate=15, has_cost=False)
        self.assertEqual(res["net_price"], 86.96)
        self.assertIsNone(res["utility"])
        self.assertIsNone(res["margin"])

    def test_apply_bulk_prices_updates_db(self):
        item_code = frappe.db.get_value("Item", {}, "name") or "001"
        payload = [{
            "item_code": item_code,
            "new_price": 550.0,
            "cost_at_analysis": None,
            "price_at_analysis": None
        }]
        
        company = frappe.defaults.get_user_default("Company") or "GRINTSYS S.A. DE C.V."
        res = apply_bulk_prices(company, "Venta estándar", payload)
        
        self.assertEqual(res["status"], "completed")
        self.assertEqual(res["updated"], 1)

    def test_worker_concurrencia_costo_modificado(self):
        item_code = frappe.db.get_value("Item", {}, "name") or "001"
        payload = [{
            "item_code": item_code,
            "new_price": 500.0,
            "cost_at_analysis": 99999.99, # Costo desalineado
            "price_at_analysis": None
        }]
        
        company = frappe.defaults.get_user_default("Company") or "GRINTSYS S.A. DE C.V."
        res = process_bulk_price_updates_worker(
            company=company,
            price_list="Venta estándar",
            items=payload
        )
        self.assertEqual(res["updated"], 0)
        self.assertEqual(res["stale_skipped"], 1)
