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
