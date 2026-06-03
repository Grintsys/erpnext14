# Copyright (c) 2025, Frappe Technologies Pvt. Ltd. and contributors
# For license information, please see license.txt

import frappe
from frappe import _
from frappe.model.document import Document

class CancelarFinanciamiento(Document):
	def before_save(self):
		"""
		Validate that linked Financiamientos is 'Activo' before allowing save.
		If not active, prevent save and inform the user.
		"""
		financ_name = getattr(self, 'financiamientos', None)
		if not financ_name:
			return

		status = frappe.db.get_value('Financiamientos', financ_name, 'status')
		if (status or '').strip() != 'Activo' and (status or '').strip() != 'Refinanciado':
			frappe.msgprint(_('El financiamiento {0} no está activo. No se guardará el documento.').format(financ_name))
			frappe.throw(_('El financiamiento no está activo'))

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

		activo_name = self.activos
		if not activo_name:
			return

		try:
			# fetch current status to decide whether to update parent status
			current_status = frappe.db.get_value('Financiamientos', financ_name, 'status')

			# Only change parent status to 'Cancelado' if it's currently 'Activo'
			if (current_status or '').strip() == 'Activo' or (current_status or '').strip() == 'Refinanciado':
				# update via db
				frappe.db.set_value('Financiamientos', financ_name, 'status', 'Cancelado')

			# update child cuotas statuses where Pendiente -> Cancelado
			frappe.db.sql(
				"""
				UPDATE `tabCuota de financiamiento`
				SET `status` = %s
				WHERE `parent` = %s AND (`status` = %s or `status` = %s)
				""",
				('Cancelado', financ_name, 'Pendiente', 'Refinanciado')
			)

			# Cambiar el estado del activo a 'Disponible'		
			activo = frappe.get_doc('Activos', activo_name)
			activo.status = 'Disponible'
			activo.save(ignore_permissions=True)

			# Commit the transaction
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
