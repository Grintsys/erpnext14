# Copyright (c) 2025, Frappe Technologies Pvt. Ltd. and contributors
# For license information, please see license.txt

import frappe
from frappe.model.document import Document

class ModificarMora(Document):
    def on_submit(self):
        """
        Al enviar el documento, actualizar la mora de la cuota más antigua pendiente
        """
        if not self.financiamiento or not self.mora_negociada:
            return

        # Obtener el documento Financiamientos
        fin = frappe.get_doc('Financiamientos', self.financiamiento)

        # Buscar la cuota más antigua pendiente (la que corresponde a este registro)
        cuotas = fin.get('cuotas', [])
        pendientes = [c for c in cuotas if (c.status or '').lower() == 'pendiente' and c.mora]

        if not pendientes:
            frappe.throw('No se encontraron cuotas pendientes para actualizar.')

        # Ordenar por fecha de vencimiento
        pendientes.sort(key=lambda c: c.fecha_vencimiento_cuota or '')

        # Obtener la cuota más antigua
        cuota = pendientes[0]

        # Verificar que sea la misma cuota registrada en este documento
        if cuota.numero_cuota != self.numero_cuota:
            frappe.throw(f'La cuota más antigua no coincide. Esperada: {self.numero_cuota}, Encontrada: {cuota.numero_cuota}')

        # Actualizar la mora de la cuota
        cuota.mora = self.mora_negociada

        # Guardar el Financiamiento
        fin.save(ignore_permissions=True)

        # Crear un comentario en el documento para auditoría
        # frappe.share.add(
        #     doctype='Financiamientos',
        #     name=self.financiamiento,
        #     user=frappe.session.user,
        #     perm_level=1
        # )

        frappe.msgprint(
            f'Mora actualizada exitosamente. Cuota {cuota.numero_cuota}: {cuota.mora}',
            title='Éxito'
        )
