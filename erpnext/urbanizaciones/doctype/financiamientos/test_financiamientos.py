import frappe
from frappe.tests.utils import FrappeTestCase
from decimal import Decimal, ROUND_HALF_UP


class TestFinanciamientos(FrappeTestCase):
	def test_overdue_mora_calculation(self):
		total_cuota = Decimal("1000.00")
		mora_pct = 0.5  # 0.5%
		days = 2
		twoplaces = Decimal("0.01")

		mora_amount = (total_cuota * (Decimal(str(mora_pct)) / Decimal("100")) * Decimal(days))
		mora_amount = mora_amount.quantize(twoplaces, rounding=ROUND_HALF_UP)

		self.assertEqual(float(mora_amount), 10.00)

	def test_financial_totals_case_1(self):
		doc = frappe.new_doc("Financiamientos")
		doc.cuota_estimada = 1000.00
		doc.plazo_meses = 12
		doc.prima = 5000.00
		doc.calculate_financial_totals()
		self.assertEqual(doc.saldo_actual, 12000.00)
		self.assertEqual(doc.total_financiado, 17000.00)

	def test_financial_totals_case_2(self):
		doc = frappe.new_doc("Financiamientos")
		doc.cuota_estimada = 2500.00
		doc.plazo_meses = 24
		doc.prima = 10000.00
		doc.calculate_financial_totals()
		self.assertEqual(doc.saldo_actual, 60000.00)
		self.assertEqual(doc.total_financiado, 70000.00)

	def test_financial_totals_case_3_zero_prima(self):
		doc = frappe.new_doc("Financiamientos")
		doc.cuota_estimada = 1500.00
		doc.plazo_meses = 12
		doc.prima = 0.00
		doc.calculate_financial_totals()
		self.assertEqual(doc.saldo_actual, 18000.00)
		self.assertEqual(doc.total_financiado, 18000.00)

	def test_financial_totals_case_4_empty_values(self):
		doc = frappe.new_doc("Financiamientos")
		doc.cuota_estimada = None
		doc.plazo_meses = None
		doc.prima = None
		doc.calculate_financial_totals()
		self.assertEqual(doc.saldo_actual, 0.00)
		self.assertEqual(doc.total_financiado, 0.00)


