import json
import frappe
from frappe.model.document import Document
from frappe.utils import cint


class ConfiguraciondeUrbanizacion(Document):
	def validate(self):
		if not self.moneda_financiamiento:
			if self.company:
				self.moneda_financiamiento = frappe.get_cached_value("Company", self.company, "default_currency")
			if not self.moneda_financiamiento:
				self.moneda_financiamiento = frappe.db.get_single_value("Global Defaults", "default_currency") or "HNL"

	def get_politicas_dict(self):
		return {
			"exigir_cobertura_mora": cint(getattr(self, "exigir_cobertura_mora", 1)),
			"permitir_pagos_parciales_sin_mora": cint(getattr(self, "permitir_pagos_parciales_sin_mora", 1)),
			"permitir_monto_mayor": cint(getattr(self, "permitir_monto_mayor", 1)),
			"permitir_vuelto_efectivo": cint(getattr(self, "permitir_vuelto_efectivo", 1)),
			"politica_excedentes": getattr(self, "politica_excedentes", "Selección por Usuario en Caja") or "Selección por Usuario en Caja",
			"permitir_anticipo_siguiente_cuota": cint(getattr(self, "permitir_anticipo_siguiente_cuota", 1)),
			"regla_monto_siguiente_cuota": getattr(self, "regla_monto_siguiente_cuota", "Coincidencia Exacta") or "Coincidencia Exacta",
			"permitir_abono_capital": cint(getattr(self, "permitir_abono_capital", 1)),
			"politica_recalculo_capital": getattr(self, "politica_recalculo_capital", "Reducir Plazo (Cuota Fija)") or "Reducir Plazo (Cuota Fija)",
			"permitir_abono_interes": cint(getattr(self, "permitir_abono_interes", 1)),
			"politica_recalculo_interes": getattr(self, "politica_recalculo_interes", "Crédito Directo Cuota Posterior") or "Crédito Directo Cuota Posterior",
			"version_politica": str(getattr(self, "modified", "") or ""),
		}
