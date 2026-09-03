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
        net_cuota = flt(cuota.total_cuota) - flt(getattr(cuota, "monto_adelantado", 0.0))
        if net_cuota < 0:
            net_cuota = 0.0

        self.customer = financiamiento.customer
        self.date_quote_financing = cuota.fecha_vencimiento_cuota
        self.total_cuota = net_cuota

        if hasattr(self, "total_mora"):
            self.total_mora = flt(cuota.mora)

        if hasattr(self, "total_a_pagar"):
            self.total_a_pagar = net_cuota + flt(self.total_mora)

        if hasattr(self, "total_facturar") and not self.total_facturar:
            self.total_facturar = self.total_a_pagar

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

        pos_profile = frappe.get_doc(
            "POS Profile",
            self.pos_profile
        )

        if not pos_profile.prefix:
            frappe.throw(
                _("Debe configurar el Prefijo de Facturación en el Perfil de POS.")
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

        # Net cuota to be billed (total_cuota - monto_adelantado)
        net_cuota_pendiente = flt(cuota.total_cuota) - flt(getattr(cuota, "monto_adelantado", 0.0))
        if net_cuota_pendiente < 0:
            net_cuota_pendiente = 0.0

        total_a_pagar_esperado = net_cuota_pendiente + flt(cuota.mora)
        monto_recibido_val = flt(self.monto_recibido)

        es_pago_parcial = (monto_recibido_val > 0) and (monto_recibido_val < total_a_pagar_esperado)

        target_cuota_adelanto = None
        monto_adelanto_aplicar = 0.0
        net_cuota_a_facturar = net_cuota_pendiente

        if es_pago_parcial:
            # Regla 0: No se permiten pagos parciales si hay mora pendiente
            if flt(cuota.mora) > 0 or flt(self.get("total_mora")) > 0:
                frappe.throw(
                    _("No se permiten pagos parciales ni adelantados si existen cuotas pendientes con mora. Debe cancelar la mora y el total a pagar.")
                )

            # Regla de Pago Parcial: El dinero ingresado es un adelanto abonado a la cuota actual
            if not getattr(configuracion, "item_adelantos", None):
                frappe.throw(
                    _("Debe configurar el Item a facturar como Adelantos en la Configuración de Urbanización.")
                )

            target_cuota_adelanto = cuota
            monto_adelanto_aplicar = monto_recibido_val
            net_cuota_a_facturar = 0.0

        else:
            # Pago completo de la cuota actual
            if (self.get("aplicar") == "Abona a siguiente cuota" or self.get("abonar_siguiente_cuota") in ("Abona a siguiente cuota", "1", 1)) and flt(self.get("monto_adelanto")) > 0:
                monto_adelanto_aplicar = flt(self.get("monto_adelanto"))

                # Regla 1: No se permiten adelantos si la cuota actual tiene mora
                if flt(cuota.mora) > 0 or flt(self.get("total_mora")) > 0:
                    frappe.throw(
                        _("No se permite realizar pagos adelantados mientras existan cuotas pendientes con mora.")
                    )

                # Regla 2: Buscar la siguiente cuota pendiente en secuencia
                cuotas_futuras = sorted(
                    [
                        c for c in financiamiento.cuotas
                        if c.status == "Pendiente" and c.numero_cuota > cuota.numero_cuota
                    ],
                    key=lambda x: x.numero_cuota
                )

                if not cuotas_futuras:
                    frappe.throw(
                        _("No existen cuotas posteriores pendientes para aplicar el pago adelantado.")
                    )

                target_cuota_adelanto = cuotas_futuras[0]
                saldo_pendiente_siguiente = flt(target_cuota_adelanto.total_cuota) - flt(getattr(target_cuota_adelanto, "monto_adelantado", 0.0))

                # Regla 3: El adelanto no puede superar el saldo pendiente de la siguiente cuota
                if monto_adelanto_aplicar > saldo_pendiente_siguiente:
                    frappe.throw(
                        _("El monto del adelanto (L {0}) supera el saldo pendiente de la siguiente cuota (L {1}). Para montos superiores debe utilizarse Abono a Capital.")
                        .format(monto_adelanto_aplicar, saldo_pendiente_siguiente)
                    )

                # Regla 4: Debe existir item_adelantos configurado
                if not getattr(configuracion, "item_adelantos", None):
                    frappe.throw(
                        _("Debe configurar el Item a facturar como Adelantos en la Configuración de Urbanización.")
                    )

        # ==========================
        # VALIDAR FACTURA EXISTENTE
        # ==========================
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

        invoice.naming_series = pos_profile.prefix
        invoice.is_pos = 1
        invoice.pos_profile = self.pos_profile
        invoice.customer = financiamiento.customer
        invoice.due_date = today()
        invoice.ignore_pricing_rule = 1
        invoice.invoice_generate = self.name
        invoice.date_quote_financing = cuota.fecha_vencimiento_cuota

        if hasattr(invoice, "cost_center"):
            invoice.cost_center = financiamiento.centro_costo

        # ==========================
        # ITEM CUOTA (Solo si no es pago parcial puro)
        # ==========================
        if net_cuota_a_facturar > 0:
            row = invoice.append("items", {})

            row.item_code = configuracion.item_cuota
            row.qty = 1
            row.rate = net_cuota_a_facturar
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
        # ITEM ADELANTO (Parcial o Siguiente cuota)
        # ==========================
        if target_cuota_adelanto and monto_adelanto_aplicar > 0:
            row = invoice.append("items", {})

            row.item_code = configuracion.item_adelantos
            row.qty = 1
            row.rate = monto_adelanto_aplicar
            row.cost_center = financiamiento.centro_costo

            row.description = (
                f"Pago adelantado aplicado a la "
                f"cuota #{target_cuota_adelanto.numero_cuota}"
            )

        # ==========================
        # REFERENCIAS OPCIONALES Y MODO DE PAGO POS
        # ==========================
        if hasattr(invoice, "financiamiento"):
            invoice.financiamiento = financiamiento.name

        total_a_facturar_monto = net_cuota_a_facturar + flt(cuota.mora) + monto_adelanto_aplicar
        if pos_profile.payments:
            default_payment = next((p for p in pos_profile.payments if p.default), pos_profile.payments[0])
            invoice.append("payments", {
                "mode_of_payment": default_payment.mode_of_payment,
                "amount": total_a_facturar_monto,
                "default": 1
            })

        # ==========================
        # GUARDAR Y SOMETER FACTURA
        # ==========================
        invoice.insert(ignore_permissions=True)
        invoice.submit()




        # ==========================
        # GUARDAR REFERENCIA
        # ==========================
        if hasattr(cuota, "sales_invoice"):
            cuota.sales_invoice = invoice.name
            financiamiento.save(ignore_permissions=True)

        # ==========================
        # ACTUALIZAR DOCUMENTO
        # ==========================
        self.db_set("total_cuota", net_cuota_pendiente)
        self.db_set("total_mora", cuota.mora)
        self.db_set("total_a_pagar", net_cuota_pendiente + flt(cuota.mora))
        self.db_set("monto_adelanto", monto_adelanto_aplicar)
        self.db_set("total_facturar", invoice.grand_total or (net_cuota_a_facturar + flt(cuota.mora) + monto_adelanto_aplicar))
        self.db_set("date_quote_financing", cuota.fecha_vencimiento_cuota)

        # Actualizar atributos en memoria para que el formulario Desk conserve los montos sin ponerse dirty/no guardado
        self.total_cuota = net_cuota_pendiente
        self.total_mora = cuota.mora
        self.total_a_pagar = net_cuota_pendiente + flt(cuota.mora)
        self.monto_adelanto = monto_adelanto_aplicar
        self.total_facturar = invoice.grand_total or (net_cuota_a_facturar + flt(cuota.mora) + monto_adelanto_aplicar)

        if es_pago_parcial:
            saldo_restante_cuota = net_cuota_pendiente - monto_recibido_val
            if saldo_restante_cuota < 0:
                saldo_restante_cuota = 0.0
            frappe.msgprint(
                _(
                    "Se registró un abono parcial de L {0} a la cuota #{1}.<br>"
                    "Saldo pendiente restante de la cuota: L {2}.<br><br>"
                    "<b>Factura {3} creada correctamente.</b>"
                ).format(
                    monto_recibido_val,
                    cuota.numero_cuota,
                    saldo_restante_cuota,
                    invoice.name
                )
            )
        else:
            frappe.msgprint(
                _(
                    "Cuota #{0} del financiamiento {1} marcada como pagada.<br><br>"
                    "<b>Factura {2} creada correctamente.</b>"
                ).format(
                    cuota.numero_cuota,
                    financiamiento.name,
                    invoice.name
                )
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


@frappe.whitelist()
def get_pending_quota_details(financiamiento):
    """Obtiene los detalles de la cuota pendiente para un financiamiento en tiempo real"""
    if not financiamiento:
        return {}

    financiamiento_doc = frappe.get_doc("Financiamientos", financiamiento)

    cuotas_pendientes = sorted(
        [
            cuota
            for cuota in financiamiento_doc.cuotas
            if cuota.status == "Pendiente"
        ],
        key=lambda x: (
            x.fecha_vencimiento_cuota,
            x.numero_cuota
        )
    )

    if not cuotas_pendientes:
        return {}

    cuota = cuotas_pendientes[0]
    net_cuota = flt(cuota.total_cuota) - flt(getattr(cuota, "monto_adelantado", 0.0))
    if net_cuota < 0:
        net_cuota = 0.0

    total_mora = flt(cuota.mora)
    total_a_pagar = net_cuota + total_mora

    return {
        "customer": financiamiento_doc.customer,
        "date_quote_financing": cuota.fecha_vencimiento_cuota,
        "total_cuota": net_cuota,
        "total_mora": total_mora,
        "total_a_pagar": total_a_pagar,
        "cuota_numero": cuota.numero_cuota
    }

