# Copyright (c) 2025, Frappe Technologies Pvt. Ltd. and contributors
# For license information, please see license.txt

import frappe
from frappe.model.document import Document

class ModificarMora(Document):
    def on_submit(self):
        """
        Al enviar el documento, actualizar la mora de la cuota más antigua pendiente
        usando la API de base de datos en vez del API de documentos (document API).
        """
        if not self.financiamiento or self.mora_negociada is None:
            return

        # Buscar la cuota más antigua pendiente para este financiamiento
        try:
            filas = frappe.db.sql(
                """
                SELECT name, numero_cuota, fecha_vencimiento_cuota
                FROM `tabCuota de financiamiento`
                WHERE parent = %s
                  AND LOWER(COALESCE(status, '')) = %s
                ORDER BY (fecha_vencimiento_cuota IS NULL), fecha_vencimiento_cuota ASC, name ASC
                LIMIT 1
                """,
                (self.financiamiento, 'pendiente'),
                as_dict=True,
            )
        except Exception:
            frappe.log_error(frappe.get_traceback(), 'ModificarMora.on_submit - sql')
            frappe.throw('Error buscando cuotas en la base de datos.')

        if not filas:
            frappe.throw('No se encontraron cuotas pendientes para actualizar.')

        cuota = filas[0]

        # Verificar que la cuota encontrada coincida con la registrada en este documento
        if getattr(self, 'numero_cuota', None) is not None:
            try:
                numero = int(cuota.get('numero_cuota')) if cuota.get('numero_cuota') is not None else None
            except Exception:
                numero = cuota.get('numero_cuota')

            if numero is not None and str(numero) != str(self.numero_cuota):
                frappe.throw(f'La cuota más antigua no coincide. Esperada: {self.numero_cuota}, Encontrada: {cuota.get("numero_cuota")}')

        # Actualizar la columna `mora` directamente en la tabla de la child table
        try:
            frappe.db.set_value('Cuota de financiamiento', cuota.name, 'mora', float(self.mora_negociada), update_modified=False)
            frappe.db.commit()
        except Exception:
            frappe.log_error(frappe.get_traceback(), 'ModificarMora.on_submit - set_value')
            frappe.throw('Error actualizando la mora en la base de datos.')

        # Mensaje de confirmación
        frappe.msgprint(
            f'Mora actualizada exitosamente. Cuota {cuota.get("numero_cuota")}: {self.mora_negociada}',
            title='Éxito'
        )
