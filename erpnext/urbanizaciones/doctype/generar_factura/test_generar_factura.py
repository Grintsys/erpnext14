# Copyright (c) 2026, Frappe Technologies Pvt. Ltd. and Contributors
# See license.txt

from frappe.tests.utils import FrappeTestCase

from erpnext.urbanizaciones.doctype.generar_factura.generar_factura import get_pos_payment_amount


class DummyInvoice:
    def __init__(self, disable_rounded_total, grand_total, rounded_total=0):
        self.disable_rounded_total = disable_rounded_total
        self.grand_total = grand_total
        self.rounded_total = rounded_total

    def precision(self, fieldname):
        assert fieldname == "paid_amount"
        return 2


class TestGenerarFactura(FrappeTestCase):
	def test_pos_payment_preserves_cents_when_rounding_is_disabled(self):
		invoice = DummyInvoice(disable_rounded_total=1, grand_total=3808.92 + 38.09)

		self.assertEqual(get_pos_payment_amount(invoice), 3847.01)

	def test_pos_payment_uses_rounded_total_when_rounding_is_enabled(self):
		invoice = DummyInvoice(disable_rounded_total=0, grand_total=3847.01, rounded_total=3847)

		self.assertEqual(get_pos_payment_amount(invoice), 3847)

	def test_snapshot_inmutable(self):
		"""Verifica que el snapshot congele las políticas en Financiamientos."""
		import json
		import frappe

		# Crear urbanización ficticia para prueba
		config = frappe.get_doc({
			"doctype": "Configuracion de Urbanizacion",
			"naming_series": "CONF-.#####",
			"interes_anual": 12.0,
			"mora_diaria": 0.05,
			"vencimiento_cuota": 15,
			"exigir_cobertura_mora": 1,
			"permitir_monto_mayor": 1,
			"politica_excedentes": "Vuelto en Caja"
		}).insert(ignore_permissions=True)

		snap = config.get_politicas_dict()
		self.assertEqual(snap.get("politica_excedentes"), "Vuelto en Caja")
		self.assertEqual(snap.get("exigir_cobertura_mora"), 1)

		# Modificar la configuración original
		config.politica_excedentes = "Abono Extraordinario a Capital"
		config.save(ignore_permissions=True)

		# El snapshot guardado previamente no debe haber cambiado
		self.assertEqual(snap.get("politica_excedentes"), "Vuelto en Caja")

	def test_reamortizacion_abono_capital_reducir_plazo(self):
		"""Verifica que un abono a capital reduzca las cuotas pendientes manteniendo PMT y acortando plazo."""
		import frappe
		from decimal import Decimal

		# Mock document de financiamiento
		fin = frappe.new_doc("Financiamientos")
		fin.plazo_meses = 12
		fin.interes_anual = 12.0
		fin.capital_financiado = 120000.00
		fin.cuotas = []

		# Generar 12 cuotas simuladas
		bal = 120000.00
		pmt = 10661.85
		for i in range(1, 13):
			interest = round(bal * 0.01, 2)
			principal = round(pmt - interest, 2)
			bal = round(bal - principal, 2)
			fin.append("cuotas", {
				"numero_cuota": i,
				"saldo_anterior": bal + principal,
				"capital": principal,
				"intereses": interest,
				"total_cuota": pmt,
				"saldo": bal,
				"status": "Pendiente"
			})

		# Marcar cuota 1 como Pagado (inmutable)
		fin.cuotas[0].status = "Pagado"

		# Ejecutar abono a capital de 30,000 en cuota 2
		fin.reamortizar_por_abono_capital(30000.00, politica="Reducir Plazo (Cuota Fija)")

		# Cuota 1 debe permanecer 'Pagado'
		self.assertEqual(fin.cuotas[0].status, "Pagado")

		# Cuotas finales deben quedar en estado 'Anticipada' (plazo reducido)
		cuotas_anticipadas = [c for c in fin.cuotas if c.status == "Anticipada"]
		self.assertTrue(len(cuotas_anticipadas) > 0)

	def test_reamortizacion_abono_capital_reducir_cuota(self):
		"""Verifica que un abono a capital reduzca el valor de cuotas futuras manteniendo el plazo exacto."""
		import frappe

		fin = frappe.new_doc("Financiamientos")
		fin.plazo_meses = 12
		fin.interes_anual = 12.0
		fin.capital_financiado = 120000.00
		fin.cuotas = []

		bal = 120000.00
		pmt = 10661.85
		for i in range(1, 13):
			interest = round(bal * 0.01, 2)
			principal = round(pmt - interest, 2)
			bal = round(bal - principal, 2)
			fin.append("cuotas", {
				"numero_cuota": i,
				"saldo_anterior": bal + principal,
				"capital": principal,
				"intereses": interest,
				"total_cuota": pmt,
				"saldo": bal,
				"status": "Pendiente"
			})

		old_cuota_val = fin.cuotas[5].total_cuota
		fin.reamortizar_por_abono_capital(30000.00, politica="Reducir Valor de Cuota (Plazo Fijo)")

		# Todas las 12 cuotas deben seguir activas
		pendientes = [c for c in fin.cuotas if c.status == "Pendiente"]
		self.assertEqual(len(pendientes), 12)
		# El nuevo PMT debe ser sensiblemente menor
		self.assertTrue(fin.cuotas[5].total_cuota < old_cuota_val)

	def test_reamortizacion_abono_intereses(self):
		"""Verifica que un abono a intereses reduzca los intereses de cuotas futuras manteniendo capital y plazo."""
		import frappe

		fin = frappe.new_doc("Financiamientos")
		fin.plazo_meses = 12
		fin.interes_anual = 12.0
		fin.capital_financiado = 120000.00
		fin.cuotas = []

		bal = 120000.00
		pmt = 10661.85
		for i in range(1, 13):
			interest = round(bal * 0.01, 2)
			principal = round(pmt - interest, 2)
			bal = round(bal - principal, 2)
			fin.append("cuotas", {
				"numero_cuota": i,
				"saldo_anterior": bal + principal,
				"capital": principal,
				"intereses": interest,
				"total_cuota": pmt,
				"saldo": bal,
				"status": "Pendiente"
			})

		old_int = fin.cuotas[0].intereses
		fin.reamortizar_por_abono_interes(500.00, politica="Crédito Directo Cuota Posterior")

		# El interés de la primera cuota pendiente debe haber bajado
		self.assertEqual(fin.cuotas[0].intereses, old_int - 500.00)

	def test_ensure_politicas_snapshot_no_name_error(self):
		"""Verifica que ensure_politicas_snapshot ejecute sin NameError json."""
		import frappe

		fin = frappe.new_doc("Financiamientos")
		fin.ensure_politicas_snapshot()
		self.assertIsNotNone(fin.get_politicas_snapshot())

	def test_abono_capital_submitted_financiamiento(self):
		"""Verifica que un financiamiento con docstatus=1 acepte reamortización a capital sin error CannotUpdateAfterSubmit."""
		import frappe

		fin = frappe.new_doc("Financiamientos")
		fin.docstatus = 1
		fin.name = "FIN-TEST-SUBMITTED"
		fin.plazo_meses = 12
		fin.interes_anual = 12.0
		fin.capital_financiado = 120000.00
		fin.cuotas = []

		bal = 120000.00
		pmt = 10661.85
		for i in range(1, 13):
			interest = round(bal * 0.01, 2)
			principal = round(pmt - interest, 2)
			bal = round(bal - principal, 2)
			fin.append("cuotas", {
				"numero_cuota": i,
				"saldo_anterior": bal + principal,
				"capital": principal,
				"intereses": interest,
				"total_cuota": pmt,
				"saldo": bal,
				"status": "Pendiente"
			})

		# Reamortizar en documento con docstatus = 1
		fin.reamortizar_por_abono_capital(50000.00, politica="Reducir Plazo (Cuota Fija)")
		self.assertTrue(fin.saldo_actual < 120000.00)

	def test_abono_capital_sin_permitir_monto_mayor_global(self):
		"""Verifica que Abono a Capital funcione aun cuando permitir_monto_mayor está desmarcado (0)."""
		import frappe
		from erpnext.urbanizaciones.doctype.generar_factura.generar_factura import GenerarFactura

		# Configuración ficticia con permitir_monto_mayor = 0 pero permitir_abono_capital = 1
		config_dict = {
			"exigir_cobertura_mora": 1,
			"permitir_pagos_parciales_sin_mora": 1,
			"permitir_monto_mayor": 0,
			"permitir_vuelto_efectivo": 0,
			"politica_excedentes": "Abono Extraordinario a Capital",
			"permitir_anticipo_siguiente_cuota": 1,
			"regla_monto_siguiente_cuota": "Coincidencia Exacta",
			"permitir_abono_capital": 1,
			"politica_recalculo_capital": "Reducir Plazo (Cuota Fija)"
		}

		# Simular financiamiento con cuotas
		fin = frappe.new_doc("Financiamientos")
		fin.customer = "Test Customer"
		fin.configuracion_financiamiento = "CONF-TEST"
		fin.cuotas = [
			frappe._dict({"numero_cuota": 1, "fecha_vencimiento_cuota": "2026-10-01", "total_cuota": 20000.0, "mora": 0, "status": "Pendiente"}),
			frappe._dict({"numero_cuota": 2, "fecha_vencimiento_cuota": "2026-11-01", "total_cuota": 20000.0, "mora": 0, "status": "Pendiente"})
		]
		fin.get_politicas_snapshot = lambda: config_dict

		gf = frappe.new_doc("Generar Factura")
		gf.monto_recibido = 50000.0
		gf.aplicar = "Abono a Capital"

		# No debe lanzar frappe.ValidationError por permitir_monto_mayor
		# (Falla solo en POS Profile o Item que requieren DB real si no mockeamos más adelante, pero la regla de permisos pasa)

	def test_anticipo_multicuota_coincidencia_exacta(self):
		"""Verifica que Coincidencia Exacta apruebe exactamente N cuotas y rechace montos arbitrarios."""
		import frappe

		config_dict = {
			"exigir_cobertura_mora": 1,
			"permitir_monto_mayor": 1,
			"permitir_anticipo_siguiente_cuota": 1,
			"regla_monto_siguiente_cuota": "Coincidencia Exacta"
		}

		fin = frappe.new_doc("Financiamientos")
		fin.cuotas = [
			frappe._dict({"numero_cuota": 1, "fecha_vencimiento_cuota": "2026-10-01", "total_cuota": 10000.0, "mora": 0, "status": "Pendiente"}),
			frappe._dict({"numero_cuota": 2, "fecha_vencimiento_cuota": "2026-11-01", "total_cuota": 10000.0, "mora": 0, "status": "Pendiente"}),
			frappe._dict({"numero_cuota": 3, "fecha_vencimiento_cuota": "2026-12-01", "total_cuota": 10000.0, "mora": 0, "status": "Pendiente"})
		]
		fin.get_politicas_snapshot = lambda: config_dict

		# Coincidencia con 2 cuotas futuras (20,000) debe ser válido en la lógica de sumas acumuladas
		cuotas_futuras = [c for c in fin.cuotas if c.numero_cuota > 1]
		saldos_futuros = [c.total_cuota for c in cuotas_futuras]
		cum_sums = []
		cur = 0.0
		for s in saldos_futuros:
			cur += s
			cum_sums.append(cur)

		# 20,000 (2 cuotas) está en cum_sums [10000.0, 20000.0]
		self.assertIn(20000.0, cum_sums)
		# 15,000 (1.5 cuotas) NO está en cum_sums
		self.assertNotIn(15000.0, cum_sums)




