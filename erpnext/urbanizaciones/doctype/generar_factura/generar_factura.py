# Copyright (c) 2026, Frappe Technologies Pvt. Ltd. and contributors
# For license information, please see license.txt

import frappe
from frappe import _
from frappe.model.document import Document
from frappe.utils import today, flt


class GenerarFactura(Document):

    def validate(self):
        self.load_pending_quota()

    def on_submit(self):
        self.create_sales_invoice()

    def load_pending_quota(self):

        if not self.financiamiento:
            return

        financiamiento = frappe.get_doc(
            "Financiamientos",
            self.financiamiento
        )

        cuotas_pendientes = sorted(
            [
                cuota
                for cuota in financiamiento.cuotas
                if cuota.status == "Pendiente"
            ],
            key=lambda x: (
                x.fecha_vencimiento_cuota,
                x.numero_cuota
            )
        )

        if not cuotas_pendientes:
            return

        cuota = cuotas_pendientes[0]

        self.customer = financiamiento.customer
        self.date_quote_financing = cuota.fecha_vencimiento_cuota
        self.total_cuota = cuota.total_cuota

        if hasattr(self, "total_mora"):
            self.total_mora = cuota.mora

    def create_sales_invoice(self):

        # ==========================
        # VALIDAR FINANCIAMIENTO
        # ==========================
        if not self.financiamiento:
            frappe.throw(_("Debe seleccionar un financiamiento."))

        financiamiento = frappe.get_doc(
            "Financiamientos",
            self.financiamiento
        )

        # ==========================
        # CONFIGURACIÓN
        # ==========================
        if not financiamiento.configuracion_financiamiento:
            frappe.throw(
                _("El financiamiento no tiene una configuración asignada.")
            )

        configuracion = frappe.get_doc(
            "Configuracion de Urbanizacion",
            financiamiento.configuracion_financiamiento
        )

        if not configuracion.item_cuota:
            frappe.throw(
                _("Debe configurar el Item a facturar como Cuota.")
            )

        if not configuracion.prefix:
            frappe.throw(
                _("Debe configurar el Prefijo de Facturación.")
            )

        # ==========================
        # OBTENER CUOTA PENDIENTE
        # ==========================
        cuotas_pendientes = sorted(
            [
                cuota
                for cuota in financiamiento.cuotas
                if cuota.status == "Pendiente"
            ],
            key=lambda x: (
                x.fecha_vencimiento_cuota,
                x.numero_cuota
            )
        )

        if not cuotas_pendientes:
            frappe.throw(
                _("No existen cuotas pendientes para este financiamiento.")
            )

        cuota = cuotas_pendientes[0]

        # ==========================
        # VALIDAR FACTURA EXISTENTE
        # ==========================
        # Requiere agregar el campo:
        # sales_invoice (Link -> Sales Invoice)
        # en Cuota de financiamiento

        if hasattr(cuota, "sales_invoice"):
            if cuota.sales_invoice:
                frappe.throw(
                    _("La cuota #{0} ya fue facturada en {1}")
                    .format(
                        cuota.numero_cuota,
                        cuota.sales_invoice
                    )
                )

        # ==========================
        # CREAR FACTURA
        # ==========================
        invoice = frappe.new_doc("Sales Invoice")

        invoice.naming_series = configuracion.prefix
        invoice.customer = financiamiento.customer
        invoice.due_date = today()
        invoice.ignore_pricing_rule = 1
        invoice.invoice_generate = self.name
        invoice.date_quote_financing = cuota.fecha_vencimiento_cuota

        # Si manejas centro de costo a nivel encabezado
        if hasattr(invoice, "cost_center"):
            invoice.cost_center = financiamiento.centro_costo

        # ==========================
        # ITEM CUOTA
        # ==========================
        row = invoice.append("items", {})

        row.item_code = configuracion.item_cuota
        row.qty = 1
        row.rate = cuota.total_cuota
        row.cost_center = financiamiento.centro_costo

        row.description = (
            f"Cuota #{cuota.numero_cuota} "
            f"con vencimiento "
            f"{cuota.fecha_vencimiento_cuota}"
        )

        # ==========================
        # ITEM MORA
        # ==========================
        if flt(cuota.mora) > 0:

            if not configuracion.item_mora:
                frappe.throw(
                    _("Debe configurar el Item a facturar como Mora.")
                )

            row = invoice.append("items", {})

            row.item_code = configuracion.item_mora
            row.qty = 1
            row.rate = cuota.mora
            row.cost_center = financiamiento.centro_costo

            row.description = (
                f"Mora correspondiente a la "
                f"cuota #{cuota.numero_cuota}"
            )

        # ==========================
        # REFERENCIAS OPCIONALES
        # ==========================
        if hasattr(invoice, "financiamiento"):
            invoice.financiamiento = financiamiento.name

        # ==========================
        # GUARDAR FACTURA
        # ==========================
        invoice.insert(ignore_permissions=True)

        # ==========================
        # GUARDAR REFERENCIA
        # ==========================
        if hasattr(cuota, "sales_invoice"):
            cuota.sales_invoice = invoice.name
            financiamiento.save(ignore_permissions=True)

        # ==========================
        # ACTUALIZAR DOCUMENTO
        # ==========================
        self.db_set("total_cuota", cuota.total_cuota)
        self.db_set("total_mora", cuota.mora)
        self.db_set(
            "date_quote_financing",
            cuota.fecha_vencimiento_cuota
        )

        frappe.msgprint(
            _("Factura {0} creada correctamente.")
            .format(invoice.name)
        )

@frappe.whitelist()
def get_financiamientos(customer):
    """Obtiene los financiamientos activos de un cliente"""
    if not customer:
        return []
    
    financiamientos = frappe.get_all(
        "Financiamientos",
        filters={
            "customer": customer,
            "status": ["in", ["Activo", "Refinanciado"]]
        },
        fields=["urbanizaciones"]
    )
    
    return financiamientos
