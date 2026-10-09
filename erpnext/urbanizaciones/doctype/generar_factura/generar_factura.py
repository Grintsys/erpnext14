import json
import frappe
from frappe import _
from frappe.model.document import Document
from frappe.utils import today, flt
from erpnext.urbanizaciones.utils.currency_helper import get_daily_exchange_rate


def get_pos_payment_amount(invoice):
    """Return the exact POS payment amount after ERPNext has calculated invoice totals."""
    if getattr(invoice, "disable_rounded_total", False):
        total = invoice.grand_total
    else:
        total = getattr(invoice, "rounded_total", 0) or invoice.grand_total

    return flt(total, invoice.precision("paid_amount"))


def capture_financing_snapshot(financiamiento_doc):
    """
    Captura el estado completo de un financiamiento y sus cuotas
    antes de aplicar cualquier cobro o modificación.
    """
    cuotas_data = []
    for c in financiamiento_doc.cuotas:
        cuotas_data.append({
            "name": c.name,
            "numero_cuota": c.numero_cuota,
            "fecha_vencimiento_cuota": str(c.fecha_vencimiento_cuota) if c.fecha_vencimiento_cuota else None,
            "capital": flt(c.capital),
            "intereses": flt(c.intereses),
            "total_cuota": flt(c.total_cuota),
            "saldo_anterior": flt(c.saldo_anterior),
            "saldo": flt(c.saldo),
            "mora": flt(c.mora),
            "status": c.status,
            "monto_adelantado": flt(getattr(c, "monto_adelantado", 0.0)),
            "sales_invoice": getattr(c, "sales_invoice", None),
            "notas": getattr(c, "notas", None)
        })

    snapshot = {
        "financiamiento": financiamiento_doc.name,
        "status": financiamiento_doc.status,
        "saldo_actual": flt(financiamiento_doc.saldo_actual),
        "fecha_vencimiento_cuota": str(financiamiento_doc.fecha_vencimiento_cuota) if financiamiento_doc.fecha_vencimiento_cuota else None,
        "cuotas": cuotas_data
    }
    return json.dumps(snapshot, ensure_ascii=False)


class GenerarFactura(Document):

    def validate(self):
        if not self.company:
            if self.financiamiento:
                self.company = frappe.db.get_value("Financiamientos", self.financiamiento, "company")
            if not self.company and getattr(self, "pos_profile", None):
                self.company = frappe.db.get_value("POS Profile", self.pos_profile, "company")
            if not self.company:
                self.company = frappe.defaults.get_user_default("Company") or frappe.db.get_single_value("Global Defaults", "default_company")
        self.load_pending_quota()

    def on_submit(self):
        self.create_sales_invoice()

    def on_cancel(self):
        self.validate_lifo_cancellation()
        self.cancel_sales_invoice()

    def validate_lifo_cancellation(self):
        """
        Valida que la cancelación se realice en orden cronológico inverso (LIFO).
        Impide anular una factura si existen facturas posteriores activas para el mismo financiamiento.
        """
        if not self.financiamiento or not getattr(self, "creation", None):
            return

        later_invoices = frappe.db.sql(
            """
            SELECT name, creation, modified
            FROM `tabGenerar Factura`
            WHERE financiamiento = %s
              AND docstatus = 1
              AND name != %s
              AND (creation > %s OR (creation = %s AND modified > %s) OR name > %s)
            ORDER BY creation DESC, name DESC
            """,
            (self.financiamiento, self.name, self.creation, self.creation, self.modified, self.name),
            as_dict=True
        )

        really_later = [inv for inv in later_invoices if inv["name"] != self.name]

        if really_later:
            nombres = ", ".join(f["name"] for f in really_later)
            frappe.throw(
                _(
                    "No se puede cancelar la factura <b>{0}</b> porque existen facturas posteriores activas para este financiamiento: <b>{1}</b>.<br><br>"
                    "Para preservar la integridad contable y de saldos, debe cancelar primero las facturas más recientes en orden inverso."
                ).format(self.name, nombres),
                title=_("Cancelación Bloqueada por Integridad")
            )

    def cancel_sales_invoice(self):
        invoice_name = getattr(self, "sales_invoice", None)
        if not invoice_name:
            invoices = frappe.get_all(
                "Sales Invoice",
                filters={"invoice_generate": self.name, "docstatus": 1},
                fields=["name"]
            )
            if invoices:
                invoice_name = invoices[0].name

        if invoice_name and frappe.db.exists("Sales Invoice", invoice_name):
            si_doc = frappe.get_doc("Sales Invoice", invoice_name)
            if si_doc.docstatus == 1 and not getattr(si_doc.flags, "in_cancel", False):
                si_doc.flags.ignore_permissions = True
                si_doc.flags.in_cancel = True
                si_doc.cancel()

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
        self.currency_financiamiento = getattr(financiamiento, "currency", None) or "USD"

        # Moneda del perfil POS o moneda local de la empresa
        company = self.company or financiamiento.company
        company_currency = None
        if company:
            company_currency = frappe.get_cached_value("Company", company, "default_currency")
        if not company_currency:
            company_currency = frappe.db.get_single_value("Global Defaults", "default_currency") or "HNL"

        if self.pos_profile:
            self.currency = frappe.db.get_value("POS Profile", self.pos_profile, "currency") or company_currency
        elif not self.currency:
            self.currency = company_currency

        # Factor de cambio
        if self.currency_financiamiento != self.currency:
            self.conversion_rate = get_daily_exchange_rate(
                self.currency_financiamiento,
                self.currency,
                self.date_quote_financing or today(),
                company=company
            )
        else:
            self.conversion_rate = 1.0

        rate = flt(self.conversion_rate) or 1.0

        # Montos en moneda del financiamiento
        self.total_cuota_financiamiento = net_cuota
        self.total_mora_financiamiento = flt(cuota.mora)
        self.total_a_pagar_financiamiento = net_cuota + flt(cuota.mora)

        # Montos convertidos a la moneda de facturación (Caja)
        self.total_cuota = flt(net_cuota * rate, 2)
        self.total_mora = flt(flt(cuota.mora) * rate, 2)
        self.total_a_pagar = flt(self.total_cuota + self.total_mora, 2)

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

        # Capturar snapshot del estado previo del financiamiento antes de aplicar cambios
        snapshot_json = capture_financing_snapshot(financiamiento)
        self.estado_previo_financiamiento = snapshot_json
        if not self.is_new():
            self.db_set("estado_previo_financiamiento", snapshot_json, update_modified=False)

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

        # Net cuota to be billed (total_cuota - monto_adelantado) en moneda de financiamiento
        net_cuota_pendiente_finan = flt(cuota.total_cuota) - flt(getattr(cuota, "monto_adelantado", 0.0))
        if net_cuota_pendiente_finan < 0:
            net_cuota_pendiente_finan = 0.0

        rate_conv = flt(self.conversion_rate) or 1.0
        company_currency = None
        if self.company:
            company_currency = frappe.get_cached_value("Company", self.company, "default_currency")
        if not company_currency:
            company_currency = frappe.db.get_single_value("Global Defaults", "default_currency") or "HNL"

        pos_currency = getattr(self, "currency", None) or getattr(pos_profile, "currency", None) or company_currency
        fin_currency = getattr(self, "currency_financiamiento", None) or getattr(financiamiento, "currency", None) or company_currency

        # Totales esperados en moneda de facturación (Caja)
        net_cuota_esperada_factura = flt(net_cuota_pendiente_finan * rate_conv, 2)
        mora_esperada_factura = flt(flt(cuota.mora) * rate_conv, 2)
        total_a_pagar_esperado = net_cuota_esperada_factura + mora_esperada_factura
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

        target_cuota_adelanto = None
        monto_adelanto_aplicar = 0.0
        net_cuota_a_facturar = net_cuota_esperada_factura
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
                if modo_aplicar == "Vuelto en caja" or not modo_aplicar:
                    if politicas.get("permitir_monto_mayor", 1) == 0:
                        frappe.throw(_("La política del financiamiento no permite recibir montos superiores al total a pagar."))
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

                saldos_futuros = [
                    (flt(c.total_cuota) - flt(getattr(c, "monto_adelantado", 0.0))) * rate_conv
                    for c in cuotas_futuras
                ]
                saldo_total_futuro = sum(saldos_futuros)

                if saldo_total_futuro <= 0:
                    frappe.throw(
                        _("No existen cuotas posteriores pendientes con saldo para aplicar el pago adelantado.")
                    )

                regla_monto = politicas.get("regla_monto_siguiente_cuota", "Coincidencia Exacta")

                if regla_monto == "Coincidencia Exacta":
                    cum_sums = []
                    current_sum = 0.0
                    for s in saldos_futuros:
                        current_sum += s
                        cum_sums.append(current_sum)

                    match_found = any(abs(monto_adelanto_aplicar - cum_s) <= 0.05 for cum_s in cum_sums)

                    if not match_found:
                        frappe.throw(
                            _(
                                "La política de 'Coincidencia Exacta' requiere que el anticipo cubra exactamente el total de 1 o más cuotas completas posteriores. El monto entregado ({0} {1}) no coincide con ninguna combinación exacta de cuotas futuras."
                            ).format(pos_currency, monto_adelanto_aplicar)
                        )

                elif monto_adelanto_aplicar > saldo_total_futuro + 0.05:
                    frappe.throw(
                        _(
                            "El monto del adelanto ({0} {1}) supera el saldo total pendiente de todas las cuotas futuras ({0} {2}). Para montos superiores debe utilizar Abono Extraordinario a Capital."
                        ).format(pos_currency, monto_adelanto_aplicar, saldo_total_futuro)
                    )

                target_cuota_adelanto = cuotas_futuras[0]

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

        if getattr(self, "company", None):
            invoice.company = self.company
        elif getattr(financiamiento, "company", None):
            invoice.company = financiamiento.company
        elif getattr(pos_profile, "company", None):
            invoice.company = pos_profile.company

        invoice.naming_series = pos_profile.prefix
        invoice.is_pos = 1
        invoice.pos_profile = self.pos_profile
        invoice.customer = financiamiento.customer
        invoice.due_date = today()
        invoice.ignore_pricing_rule = 1
        invoice.invoice_generate = self.name
        invoice.date_quote_financing = cuota.fecha_vencimiento_cuota
        invoice.currency = pos_currency

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

            if pos_currency != fin_currency and rate_conv != 1.0:
                row.description = (
                    f"Cuota #{cuota.numero_cuota} "
                    f"({fin_currency} {net_cuota_pendiente_finan:.2f} @ TC {rate_conv:.4f}) "
                    f"con vencimiento {cuota.fecha_vencimiento_cuota}"
                )
            else:
                row.description = (
                    f"Cuota #{cuota.numero_cuota} "
                    f"con vencimiento {cuota.fecha_vencimiento_cuota}"
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
            row.rate = mora_esperada_factura
            row.cost_center = financiamiento.centro_costo

            if pos_currency != fin_currency and rate_conv != 1.0:
                row.description = (
                    f"Mora correspondiente a la cuota #{cuota.numero_cuota} "
                    f"({fin_currency} {flt(cuota.mora):.2f} @ TC {rate_conv:.4f})"
                )
            else:
                row.description = (
                    f"Mora correspondiente a la cuota #{cuota.numero_cuota}"
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
        # ACTUALIZAR FINANCIAMIENTO (EN MONEDA DE CONTRATO USD)
        # ==========================
        # Convertir montos a la moneda del contrato antes de actualizar saldos de financiamiento
        advance_in_fin_curr = flt(monto_adelanto_aplicar / rate_conv, 4) if rate_conv > 0 else monto_adelanto_aplicar
        abono_in_fin_curr = flt(monto_abono_extraordinario / rate_conv, 4) if rate_conv > 0 else monto_abono_extraordinario

        if es_pago_parcial:
            adelanto_previo = flt(getattr(cuota, "monto_adelantado", 0.0))
            nuevo_adelanto = adelanto_previo + advance_in_fin_curr
            frappe.db.set_value("Cuota de financiamiento", cuota.name, "monto_adelantado", nuevo_adelanto, update_modified=False)
        else:
            frappe.db.set_value("Cuota de financiamiento", cuota.name, "status", "Pagado", update_modified=False)
            if target_cuota_adelanto and advance_in_fin_curr > 0:
                adelanto_previo_futuro = flt(getattr(target_cuota_adelanto, "monto_adelantado", 0.0))
                nuevo_adelanto_futuro = adelanto_previo_futuro + advance_in_fin_curr
                target_cuota_total = flt(target_cuota_adelanto.total_cuota)
                if abs(nuevo_adelanto_futuro - target_cuota_total) <= 0.05 or nuevo_adelanto_futuro >= target_cuota_total:
                    frappe.db.set_value("Cuota de financiamiento", target_cuota_adelanto.name, {
                        "status": "Anticipada",
                        "monto_adelantado": nuevo_adelanto_futuro
                    }, update_modified=False)
                else:
                    frappe.db.set_value("Cuota de financiamiento", target_cuota_adelanto.name, "monto_adelantado", nuevo_adelanto_futuro, update_modified=False)

        # Actualizar saldo_actual del financiamiento
        capital_cuota = flt(cuota.capital)
        saldo_actual_prev = flt(financiamiento.saldo_actual)
        nuevo_saldo = saldo_actual_prev - capital_cuota if not es_pago_parcial else saldo_actual_prev
        if nuevo_saldo < 0:
            nuevo_saldo = 0.0
        frappe.db.set_value("Financiamientos", financiamiento.name, "saldo_actual", nuevo_saldo, update_modified=False)

        # ==========================
        # EJECUTAR REAMORTIZACIÓN SI APLICA ABONO EXTRAORDINARIO
        # ==========================
        if abono_in_fin_curr > 0 and tipo_abono_extraordinario:
            financiamiento_reload = frappe.get_doc("Financiamientos", financiamiento.name)
            if tipo_abono_extraordinario == "Capital":
                financiamiento_reload.reamortizar_por_abono_capital(abono_in_fin_curr, invoice_name=invoice.name)
            elif tipo_abono_extraordinario == "Intereses":
                financiamiento_reload.reamortizar_por_abono_interes(abono_in_fin_curr, invoice_name=invoice.name)

        # ==========================
        # GUARDAR REFERENCIA
        # ==========================
        if hasattr(cuota, "name") and cuota.name:
            frappe.db.set_value("Cuota de financiamiento", cuota.name, "sales_invoice", invoice.name, update_modified=False)

        self.db_set("sales_invoice", invoice.name)
        self.sales_invoice = invoice.name

        # ==========================
        # ACTUALIZAR DOCUMENTO
        # ==========================
        self.db_set("total_cuota", net_cuota_a_facturar)
        self.db_set("total_mora", mora_esperada_factura)
        self.db_set("total_a_pagar", total_a_pagar_esperado)
        self.db_set("monto_adelanto", monto_adelanto_aplicar)
        self.db_set("total_facturar", invoice.grand_total or (net_cuota_a_facturar + mora_esperada_factura + monto_adelanto_aplicar))
        self.db_set("date_quote_financing", cuota.fecha_vencimiento_cuota)
        self.db_set("estado_previo_financiamiento", snapshot_json)

        self.total_cuota = net_cuota_a_facturar
        self.total_mora = mora_esperada_factura
        self.total_a_pagar = total_a_pagar_esperado
        self.monto_adelanto = monto_adelanto_aplicar
        self.total_facturar = invoice.grand_total or (net_cuota_a_facturar + mora_esperada_factura + monto_adelanto_aplicar)
        self.sales_invoice = invoice.name
        self.estado_previo_financiamiento = snapshot_json

        if es_pago_parcial:
            saldo_restante_cuota = total_a_pagar_esperado - monto_recibido_val
            if saldo_restante_cuota < 0:
                saldo_restante_cuota = 0.0
            frappe.msgprint(
                _(
                    "Se registró un abono parcial de {0} {1} a la cuota #{2}.<br>"
                    "Saldo pendiente restante de la cuota: {0} {3}.<br><br>"
                    "<b>Factura {4} creada correctamente.</b>"
                ).format(
                    pos_currency,
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
                    "Cobro procesado para la cuota #{1} del financiamiento {2} ({3} {4})."
                ).format(
                    invoice.name,
                    cuota.numero_cuota,
                    financiamiento.name,
                    pos_currency,
                    self.total_facturar
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
def get_pending_quota_details(financiamiento, pos_profile=None):
    """Obtiene los detalles de la cuota pendiente para un financiamiento con conversión cambiaria"""
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
    net_cuota_finan = flt(cuota.total_cuota) - flt(getattr(cuota, "monto_adelantado", 0.0))
    if net_cuota_finan < 0:
        net_cuota_finan = 0.0

    total_mora_finan = flt(cuota.mora)
    total_a_pagar_finan = net_cuota_finan + total_mora_finan

    company = financiamiento_doc.company or frappe.defaults.get_user_default("Company")
    company_currency = None
    if company:
        company_currency = frappe.get_cached_value("Company", company, "default_currency")
    if not company_currency:
        company_currency = frappe.db.get_single_value("Global Defaults", "default_currency") or "HNL"

    currency_finan = getattr(financiamiento_doc, "currency", None) or "USD"
    currency_pos = company_currency
    if pos_profile:
        currency_pos = frappe.db.get_value("POS Profile", pos_profile, "currency") or company_currency

    conversion_rate = get_daily_exchange_rate(
        currency_finan,
        currency_pos,
        cuota.fecha_vencimiento_cuota or today(),
        company=company
    )

    rate = flt(conversion_rate) or 1.0

    return {
        "customer": financiamiento_doc.customer,
        "company": financiamiento_doc.company,
        "currency_financiamiento": currency_finan,
        "currency": currency_pos,
        "conversion_rate": rate,
        "date_quote_financing": cuota.fecha_vencimiento_cuota,
        "total_cuota_financiamiento": net_cuota_finan,
        "total_mora_financiamiento": total_mora_finan,
        "total_a_pagar_financiamiento": total_a_pagar_finan,
        "total_cuota": flt(net_cuota_finan * rate, 2),
        "total_mora": flt(total_mora_finan * rate, 2),
        "total_a_pagar": flt(total_a_pagar_finan * rate, 2),
        "cuota_numero": cuota.numero_cuota
    }
