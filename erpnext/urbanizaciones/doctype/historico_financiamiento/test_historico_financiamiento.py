import frappe
from frappe.tests.utils import FrappeTestCase
from erpnext.urbanizaciones.doctype.financiamientos.financiamientos import activo_disponible_query


class TestHistoricoFinanciamiento(FrappeTestCase):
	def setUp(self):
		frappe.db.rollback()

	def test_activo_and_centro_costo_validations(self):
		company_name = "GRINTSYS"

		# 1. Test doc without activos
		doc = frappe.new_doc("Historico Financiamiento")
		doc.company = company_name
		doc.urbanizaciones = "URB-00004"
		doc.activos = None
		doc.centro_costo = "Principal - GR"
		with self.assertRaises(frappe.ValidationError):
			doc.validate_activos_and_centro_costo()

		# 2. Test doc with group cost center
		doc.activos = "LOT-00024"
		doc.centro_costo = "GRINTSYS - GR"  # is_group: 1
		with self.assertRaises(frappe.ValidationError):
			doc.validate_activos_and_centro_costo()

		# 3. Test doc with cost center of another company
		doc.company = "OTHER_COMPANY"
		doc.centro_costo = "Principal - GR"  # belongs to GRINTSYS
		with self.assertRaises(frappe.ValidationError):
			doc.validate_activos_and_centro_costo()

		# 4. Test doc with activo belonging to a different urbanización
		doc.company = company_name
		doc.centro_costo = "Principal - GR"
		doc.urbanizaciones = "URB-00001"  # LOT-00024 belongs to URB-00004
		with self.assertRaises(frappe.ValidationError):
			doc.validate_activos_and_centro_costo()

		# 5. Test auto-population of centro_costo when not provided
		doc.urbanizaciones = "URB-00004"
		doc.centro_costo = None
		# LOT-00020 has centro_de_costo = "Tela - GR"
		doc.activos = "LOT-00020"
		# Temporarily test auto population logic
		try:
			doc.validate_activos_and_centro_costo()
		except frappe.ValidationError:
			pass
		self.assertEqual(doc.centro_costo, "Tela - GR")

	def test_activo_disponible_query_with_historico(self):
		# Ensure query executes without SQL syntax error
		res = activo_disponible_query(
			"Activos",
			"",
			"name",
			0,
			20,
			{"urbanizaciones": "URB-00004", "current_doc": "HFIN-TEST-0001"}
		)
		self.assertIsInstance(res, (list, tuple))


def run_tests():
	import unittest
	suite = unittest.TestLoader().loadTestsFromTestCase(TestHistoricoFinanciamiento)
	runner = unittest.TextTestRunner(verbosity=2)
	res = runner.run(suite)
	if not res.wasSuccessful():
		raise Exception("Historico Financiamiento unit tests failed!")
	print("All Historico Financiamiento tests passed successfully!")
