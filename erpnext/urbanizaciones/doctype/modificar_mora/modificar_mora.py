# Copyright (c) 2026, Frappe Technologies Pvt. Ltd. and contributors
# For license information, please see license.txt

import frappe
from frappe import _
from frappe.model.document import Document
from frappe.utils import getdate, nowdate, flt


class ModificarMora(Document):
	def validate(self):
		self.validate_fecha_limite()
		self.validate_and_calculate_totals()

	def validate_fecha_limite(self):
		if not self.fecha_limite_acuerdo:
			frappe.throw(_("Debe especificar una Fecha Límite para el Acuerdo."))
		
		if getdate(self.fecha_limite_acuerdo) < getdate(nowdate()):
			frappe.throw(_("La Fecha Límite del Acuerdo no puede ser anterior a la fecha actual ({0}).").format(nowdate()))

	def validate_and_calculate_totals(self):
		if not self.get("cuotas_detalle"):
			frappe.throw(_("Debe incluir al menos una cuota en la tabla de detalle para negociar."))

		tot_actual = 0.0
		tot_negociada = 0.0

		for row in self.cuotas_detalle:
			if row.mora_negociada is None or flt(row.mora_negociada) < 0:
				frappe.throw(
					_("La mora negociada para la cuota #{0} no puede ser negativa.").format(row.numero_cuota)
				)

			row.descuento = flt(flt(row.mora_actual) - flt(row.mora_negociada), 2)
			tot_actual += flt(row.mora_actual)
			tot_negociada += flt(row.mora_negociada)

		self.total_mora_actual = flt(tot_actual, 2)
		self.total_mora_negociada = flt(tot_negociada, 2)
		self.total_descuento = flt(tot_actual - tot_negociada, 2)

	def on_submit(self):
		"""
		Aplica las moras negociadas a las cuotas seleccionadas y fija la fecha de congelamiento.
		"""
		for row in self.cuotas_detalle:
			if not row.cuota_name:
				continue

			frappe.db.set_value(
				"Cuota de financiamiento",
				row.cuota_name,
				{
					"mora": flt(row.mora_negociada),
					"mora_congelada_hasta": self.fecha_limite_acuerdo
				},
				update_modified=False
			)

		frappe.db.commit()
		frappe.msgprint(
			_("Se aplicaron las moras negociadas para {0} cuotas con fecha límite de congelamiento hasta el {1}.").format(
				len(self.cuotas_detalle), self.fecha_limite_acuerdo
			),
			title=_("Acuerdo de Mora Aplicado")
		)

	def on_cancel(self):
		"""
		Al cancelar el acuerdo, remueve el congelamiento y recalcula la mora estándar.
		"""
		from erpnext.urbanizaciones.doctype.financiamientos.financiamientos import update_overdue_mora

		for row in self.cuotas_detalle:
			if not row.cuota_name:
				continue

			frappe.db.set_value(
				"Cuota de financiamiento",
				row.cuota_name,
				{
					"mora_congelada_hasta": None
				},
				update_modified=False
			)

		update_overdue_mora()
		frappe.db.commit()
		frappe.msgprint(
			_("Se ha cancelado el acuerdo de mora y restablecido el cálculo estándar de mora."),
			title=_("Acuerdo Cancelado")
		)


@frappe.whitelist()
def get_vencidas_cuotas(financiamiento):
	"""
	Obtiene todas las cuotas pendientes vencidas para un financiamiento,
	calculando los días de atraso y la mora actual acumulada.
	"""
	if not financiamiento:
		return []

	today = nowdate()
	fin = frappe.get_doc("Financiamientos", financiamiento)
	mora_diaria = flt(fin.mora_diaria or 0)

	cuotas = []
	for c in fin.cuotas:
		if c.status == "Pendiente" and c.fecha_vencimiento_cuota and getdate(c.fecha_vencimiento_cuota) < getdate(today):
			dias = (getdate(today) - getdate(c.fecha_vencimiento_cuota)).days
			# Si ya tiene una mora calculada o la calculamos
			mora_sistema = flt(c.total_cuota * (mora_diaria / 100.0) * dias, 2)
			mora_actual = flt(c.mora) if flt(c.mora) > 0 else mora_sistema

			cuotas.append({
				"cuota_name": c.name,
				"numero_cuota": c.numero_cuota,
				"fecha_vencimiento_cuota": c.fecha_vencimiento_cuota,
				"total_cuota": flt(c.total_cuota, 2),
				"dias_mora": dias,
				"mora_actual": mora_actual,
				"mora_negociada": mora_actual,
				"descuento": 0.0
			})

	# Ordenar por número de cuota ascendente
	cuotas.sort(key=lambda x: x["numero_cuota"])
	return cuotas
