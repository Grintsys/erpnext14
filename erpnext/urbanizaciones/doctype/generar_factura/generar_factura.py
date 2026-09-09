# Copyright (c) 2026, Frappe Technologies Pvt. Ltd. and contributors
# For license information, please see license.txt

import frappe
from frappe import _
from frappe.model.document import Document
from frappe.utils import today, flt


def get_pos_payment_amount(invoice):
    """Return the exact POS payment amount after ERPNext has calculated invoice totals."""
    if getattr(invoice, "disable_rounded_total", False):
        total = invoice.grand_total
    else:
        total = getattr(invoice, "rounded_total", 0) or invoice.grand_total

    return flt(total, invoice.precision("paid_amount"))


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
        # OBTENER POLÍTICAS DEL FINANCIAMIENTO
        # ==========================
        politicas = financiamiento.get_politicas_snapshot()

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

        # Validar cobertura de mora exigida por política
        if politicas.get("exigir_cobertura_mora", 1) == 1 and flt(cuota.mora) > 0:
            if monto_recibido_val > 0 and monto_recibido_val < total_a_pagar_esperado:
                frappe.throw(
                    _("La política de la urbanización exige la cobertura completa de mora y cuota. No se permiten pagos parciales cuando existe mora pendiente.")
                )

        es_pago_parcial = (monto_recibido_val > 0) and (monto_recibido_val < total_a_pagar_esperado)

        if es_pago_parcial and politicas.get("permitir_pagos_parciales_sin_mora", 1) == 0:
            frappe.throw(
                _("La política del financiamiento no permite realizar pagos parciales.")
            )

        if monto_recibido_val > total_a_pagar_esperado and politicas.get("permitir_monto_mayor", 1) == 0:
            frappe.throw(
                _("La política del financiamiento no permite recibir montos superiores al total a pagar.")
            )

        target_cuota_adelanto = None
        monto_adelanto_aplicar = 0.0
        net_cuota_a_facturar = net_cuota_pendiente
        monto_abono_extraordinario = 0.0
        tipo_abono_extraordinario = None

        if es_pago_parcial:
            if not getattr(configuracion, "item_adelantos", None):
                frappe.throw(
                    _("Debe configurar el Item a facturar como Adelantos en la Configuración de Urbanización.")
                )

            target_cuota_adelanto = cuota
            monto_adelanto_aplicar = monto_recibido_val
            net_cuota_a_facturar = 0.0

        else:
            # Pago completo o excedente
            excedente = monto_recibido_val - total_a_pagar_esperado if monto_recibido_val > total_a_pagar_esperado else 0.0
            modo_aplicar = self.get("aplicar") or politicas.get("politica_excedentes")

            if excedente > 0:
                if modo_aplicar == "Vuelto en caja":
                    if politicas.get("permitir_vuelto_efectivo", 1) == 0:
                        frappe.throw(_("La política del financiamiento no permite la devolución de vuelto en efectivo."))
                elif modo_aplicar == "Abona a siguiente cuota":
                    if politicas.get("permitir_anticipo_siguiente_cuota", 1) == 0:
                        frappe.throw(_("La política del financiamiento no permite realizar anticipos a la siguiente cuota."))
                    monto_adelanto_aplicar = excedente
                elif modo_aplicar == "Abono a Capital":
                    if politicas.get("permitir_abono_capital", 1) == 0:
                        frappe.throw(_("La política del financiamiento no permite abonos extraordinarios a capital."))
                    monto_abono_extraordinario = excedente
                    tipo_abono_extraordinario = "Capital"
                elif modo_aplicar == "Abono a Intereses":
                    if politicas.get("permitir_abono_interes", 1) == 0:
                        frappe.throw(_("La política del financiamiento no permite abonos extraordinarios a intereses."))
                    monto_abono_extraordinario = excedente
                    tipo_abono_extraordinario = "Intereses"

            if (modo_aplicar == "Abona a siguiente cuota" or self.get("abonar_siguiente_cuota") in ("Abona a siguiente cuota", "1", 1)) and (monto_adelanto_aplicar > 0 or flt(self.get("monto_adelanto")) > 0):
                if monto_adelanto_aplicar == 0:
                    monto_adelanto_aplicar = flt(self.get("monto_adelanto"))

                if flt(cuota.mora) > 0 or flt(self.get("total_mora")) > 0:
                    frappe.throw(
                        _("No se permite realizar pagos adelantados mientras existan cuotas pendientes con mora.")
                    )

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

                regla_monto = politicas.get("regla_monto_siguiente_cuota", "Coincidencia Exacta")
                if regla_monto == "Coincidencia Exacta":
                    if abs(monto_adelanto_aplicar - saldo_pendiente_siguiente) > 0.01:
                        frappe.throw(
                            _("La política requiere coincidencia exacta con el monto de la siguiente cuota (L {0}). Para montos diferentes debe utilizar Abono a Capital.")
                            .format(saldo_pendiente_siguiente)
                        )
                elif monto_adelanto_aplicar > saldo_pendiente_siguiente:
                    frappe.throw(
                        _("El monto del adelanto (L {0}) supera el saldo pendiente de la siguiente cuota (L {1}). Para montos superiores debe utilizarse Abono a Capital.")
                        .format(monto_adelanto_aplicar, saldo_pendiente_siguiente)
                    )

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
        # ITEM ABONO EXTRAORDINARIO (Capital o Intereses)
        # ==========================
        if monto_abono_extraordinario > 0 and tipo_abono_extraordinario:
            if not getattr(configuracion, "item_adelantos", None):
                frappe.throw(_("Debe configurar el Item a facturar como Adelantos en la Configuración de Urbanización."))

            row = invoice.append("items", {})
            row.item_code = configuracion.item_adelantos
            row.qty = 1
            row.rate = monto_abono_extraordinario
            row.cost_center = financiamiento.centro_costo
            row.description = f"Abono extraordinario a {tipo_abono_extraordinario}"

        # ==========================
        # REFERENCIAS OPCIONALES Y MODO DE PAGO POS
        # ==========================
        if hasattr(invoice, "financiamiento"):
            invoice.financiamiento = financiamiento.name

        if pos_profile.payments:
            default_payment = next((p for p in pos_profile.payments if p.default), pos_profile.payments[0])
            invoice.append("payments", {
                "mode_of_payment": default_payment.mode_of_payment,
                "amount": 0,
                "default": 1
            })

        # ==========================
        # GUARDAR Y SOMETER FACTURA
        # ==========================
        invoice.insert(ignore_permissions=True)

        # ERPNext applies the POS profile and calculates the final totals during insert.
        # Synchronize the payment afterwards so disabled rounding preserves all cents.
        default_payment = next((payment for payment in invoice.payments if payment.default), None)
        if not default_payment:
            frappe.throw(_("La factura POS no tiene un modo de pago predeterminado."))

        default_payment.amount = get_pos_payment_amount(invoice)
        invoice.save(ignore_permissions=True)

        outstanding_amount = flt(invoice.outstanding_amount, invoice.precision("outstanding_amount"))
        if outstanding_amount != 0:
            frappe.throw(
                _(
                    "El pago POS no coincide con el total de la factura. "
                    "Revise el perfil POS y los montos antes de continuar."
                )
            )

        invoice.submit()

        # ==========================
        # EJECUTAR REAMORTIZACIÓN SI APLICA ABONO EXTRAORDINARIO
        # ==========================
        if monto_abono_extraordinario > 0 and tipo_abono_extraordinario:
            financiamiento_reload = frappe.get_doc("Financiamientos", financiamiento.name)
            if tipo_abono_extraordinario == "Capital":
                financiamiento_reload.reamortizar_por_abono_capital(monto_abono_extraordinario)
            elif tipo_abono_extraordinario == "Intereses":
                financiamiento_reload.reamortizar_por_abono_interes(monto_abono_extraordinario)




        # ==========================
        # GUARDAR REFERENCIA
        # ==========================
        if hasattr(cuota, "name") and cuota.name:
            frappe.db.set_value("Cuota de financiamiento", cuota.name, "sales_invoice", invoice.name, update_modified=False)

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
                    "<b>Factura {0} creada y sometida correctamente.</b><br>"
                    "Cobro procesado para la cuota #{1} del financiamiento {2}."
                ).format(
                    invoice.name,
                    cuota.numero_cuota,
                    financiamiento.name
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
