# Copyright (c) 2025, Frappe Technologies Pvt. Ltd. and contributors
# For license information, please see license.txt

import frappe
from frappe import _
from frappe.model.document import Document


class CancelarFinanciamiento(Document):
	def on_submit(self):
		"""
		When this Cancelar Financiamiento is submitted, perform the cancel
		operation on the linked Financiamientos (if applicable) and update
		child cuotas statuses. The operation is transactional: on error we
		rollback and prevent submission.
		"""
		financ_name = self.financiamientos
		if not financ_name:
			return

		try:
			# fetch current status to decide whether to update parent status
			current_status = frappe.db.get_value('Financiamientos', financ_name, 'status')

			# If the financiamiento is submitted, try to cancel it first so we
			# can modify its data (cancel runs its own hooks)
			financ_doc = frappe.get_doc('Financiamientos', financ_name)
			if getattr(financ_doc, 'docstatus', 0) == 1:
				try:
					financ_doc.cancel()
				except Exception as cancel_err:
					frappe.log_error(frappe.get_traceback(), 'CancelarFinanciamiento.cancel_failed')
					frappe.throw(_('No se pudo cancelar el financiamiento antes de actualizar: {0}').format(str(cancel_err)))

			# After attempting cancellation, re-check docstatus
			docstatus_parent = frappe.db.get_value('Financiamientos', financ_name, 'docstatus')

			# Only change parent status to 'Cancelado' if it's currently 'Activo'
			if (current_status or '').strip() == 'Activo':
				if docstatus_parent == 2:
					# parent is cancelled; update status via DB to avoid "Cannot edit cancelled document"
					frappe.db.set_value('Financiamientos', financ_name, 'status', 'Cancelado')
				else:
					# safe to update via Document
					financ = frappe.get_doc('Financiamientos', financ_name)
					financ.status = 'Cancelado'
					financ.save(ignore_permissions=True)

			# update child cuotas statuses where Pendiente -> Cancelado
			frappe.db.sql(
				"""
				UPDATE `tabCuota de financiamiento`
				SET `status` = %s
				WHERE `parent` = %s AND `status` = %s
				""",
				('Cancelado', financ_name, 'Pendiente')
			)

			frappe.db.commit()

			# Refresh the status field on this Cancelar Financiamiento so the
			# client-side fetch_from reflects the updated value immediately.
			try:
				latest_status = frappe.db.get_value('Financiamientos', financ_name, 'status')
				if latest_status is not None:
					frappe.db.set_value('Cancelar Financiamiento', self.name, 'status', latest_status)
			except Exception:
				frappe.log_error(frappe.get_traceback(), 'CancelarFinanciamiento.sync_status')

		except Exception as e:
			# ensure DB transaction is rolled back explicitly and prevent submit
			try:
				frappe.db.rollback()
			except Exception:
				pass

			frappe.log_error(frappe.get_traceback(), 'CancelarFinanciamiento.on_submit')
			frappe.throw(_('Error actualizando Financiamientos: {0}').format(str(e)))
