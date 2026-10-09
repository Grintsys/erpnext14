// Copyright (c) 2026, Frappe Technologies Pvt. Ltd. and contributors
// For license information, please see license.txt

function setup_financiamiento_query(frm) {
    frm.set_query('financiamiento', function() {
        let filters = {
            status: ['Activo', 'Refinanciado']
        };
        if (frm.doc.customer) {
            filters.customer = frm.doc.customer;
        }
        if (frm.doc.company) {
            filters.company = frm.doc.company;
        }
        return {
            query: 'erpnext.urbanizaciones.doctype.financiamientos.financiamientos.financiamiento_query',
            filters: filters
        };
    });
}

frappe.ui.form.on('Generar Factura', {
    setup: function(frm) {
        frm.set_df_property('conversion_rate', 'read_only', 1);
    },
    refresh: function(frm) {
        setup_financiamiento_query(frm);
        if (frm.doc.docstatus === 0 && frm.doc.financiamiento && !frm.doc.total_a_pagar) {
            fetch_pending_quota(frm);
        } else {
            calculate_payment_totals(frm);
        }

        if (frm.doc.docstatus === 1) {
            frm.savecancel = function() {
                frappe.confirm(
                    __('¿Está seguro de que desea cancelar esta factura ({0})?<br><br>Se anulará únicamente esta factura y su factura de venta vinculada, restaurando las cuotas a su estado anterior en el financiamiento.', [frm.doc.name]),
                    function() {
                        frappe.call({
                            method: 'frappe.client.cancel',
                            args: {
                                doctype: frm.doc.doctype,
                                name: frm.doc.name
                            },
                            freeze: true,
                            freeze_message: __('Cancelando factura y revirtiendo cuotas...'),
                            callback: function(r) {
                                if (!r.exc) {
                                    frm.reload_doc();
                                }
                            }
                        });
                    }
                );
            };
            frm.page.set_secondary_action(__('Cancel'), () => frm.savecancel());
        }
    },
    onload: function(frm) {
        setup_financiamiento_query(frm);
        if (frm.doc.docstatus === 0 && frm.doc.financiamiento) {
            fetch_pending_quota(frm);
        }
    },
    financiamiento: function(frm) {
        if (frm.doc.financiamiento) {
            fetch_pending_quota(frm);
        } else {
            frm.set_value('date_quote_financing', null);
            frm.set_value('total_cuota_financiamiento', 0);
            frm.set_value('total_mora_financiamiento', 0);
            frm.set_value('total_a_pagar_financiamiento', 0);
            frm.set_value('total_cuota', 0);
            frm.set_value('total_mora', 0);
            frm.set_value('total_a_pagar', 0);
            calculate_payment_totals(frm);
        }
    },
    pos_profile: function(frm) {
        if (frm.doc.pos_profile) {
            frappe.db.get_value('POS Profile', frm.doc.pos_profile, ['currency', 'company'], function(r) {
                if (r) {
                    if (r.currency) {
                        frm.set_value('currency', r.currency);
                    }
                    if (r.company && !frm.doc.company) {
                        frm.set_value('company', r.company);
                    }
                }
                if (frm.doc.financiamiento) {
                    fetch_pending_quota(frm);
                }
            });
        }
    },
    conversion_rate: function(frm) {
        let rate = flt(frm.doc.conversion_rate) || 1.0;
        let cuota_finan = flt(frm.doc.total_cuota_financiamiento);
        let mora_finan = flt(frm.doc.total_mora_financiamiento);

        frm.set_value('total_cuota', flt(cuota_finan * rate, 2));
        frm.set_value('total_mora', flt(mora_finan * rate, 2));
        frm.set_value('total_a_pagar', flt((cuota_finan + mora_finan) * rate, 2));
        calculate_payment_totals(frm);
    },
    total_cuota: function(frm) {
        calculate_payment_totals(frm);
    },
    total_mora: function(frm) {
        calculate_payment_totals(frm);
    },
    monto_recibido: function(frm) {
        calculate_payment_totals(frm);
    },
    aplicar: function(frm) {
        if (flt(frm.doc.total_mora) > 0 && frm.doc.aplicar === 'Abona a siguiente cuota') {
            frappe.msgprint(__('No se permite realizar pagos adelantados mientras existan cuotas pendientes con mora.'));
            frm.set_value('aplicar', '');
            return;
        }
        calculate_payment_totals(frm);
    },
    customer: function(frm) {
        frm.set_value('financiamiento', '');
        setup_financiamiento_query(frm);
    }
});

function fetch_pending_quota(frm) {
    if (!frm.doc.financiamiento) return;

    frappe.call({
        method: 'erpnext.urbanizaciones.doctype.generar_factura.generar_factura.get_pending_quota_details',
        args: {
            financiamiento: frm.doc.financiamiento,
            pos_profile: frm.doc.pos_profile || ''
        },
        callback: function(r) {
            if (r.message && Object.keys(r.message).length > 0) {
                let data = r.message;
                if (!frm.doc.customer && data.customer) {
                    frm.set_value('customer', data.customer);
                }
                if (data.company && !frm.doc.company) {
                    frm.set_value('company', data.company);
                }
                frm.set_value('currency_financiamiento', data.currency_financiamiento || 'USD');
                if (data.currency) {
                    frm.set_value('currency', data.currency);
                }
                frm.set_value('conversion_rate', data.conversion_rate || 1.0);
                frm.set_value('date_quote_financing', data.date_quote_financing);
                frm.set_value('total_cuota_financiamiento', data.total_cuota_financiamiento);
                frm.set_value('total_mora_financiamiento', data.total_mora_financiamiento);
                frm.set_value('total_a_pagar_financiamiento', data.total_a_pagar_financiamiento);
                frm.set_value('total_cuota', data.total_cuota);
                frm.set_value('total_mora', data.total_mora);
                frm.set_value('total_a_pagar', data.total_a_pagar);
            }
            calculate_payment_totals(frm);
        }
    });
}

function calculate_payment_totals(frm) {
    if (frm.doc.docstatus === 1) {
        return;
    }

    let total_cuota = flt(frm.doc.total_cuota);
    let total_mora = flt(frm.doc.total_mora);
    let total_a_pagar = total_cuota + total_mora;

    frm.set_value('total_a_pagar', total_a_pagar);

    let monto_recibido = flt(frm.doc.monto_recibido);

    // Caso A: Pago Parcial en la cuota actual (monto_recibido < total_a_pagar)
    if (monto_recibido > 0 && monto_recibido < total_a_pagar) {
        if (total_mora > 0) {
            frappe.show_alert({
                message: __('No se permiten pagos parciales si existe mora pendiente.'),
                indicator: 'orange'
            });
        }
        if (frm.doc.aplicar === 'Abona a siguiente cuota') {
            frm.set_value('aplicar', '', null, true);
        }
        frm.set_value('vuelto', 0.0);
        frm.set_value('monto_adelanto', monto_recibido);
        frm.set_value('total_facturar', monto_recibido);
        return;
    }

    // Caso B: Pago Completo o Mayor (monto_recibido >= total_a_pagar)
    if (total_mora > 0) {
        if (frm.doc.aplicar === 'Abona a siguiente cuota') {
            frm.set_value('aplicar', '', null, true);
        }
    }

    let diferencia = monto_recibido - total_a_pagar;
    let vuelto = 0.0;
    let monto_adelanto = 0.0;

    if (diferencia > 0) {
        if (frm.doc.aplicar === 'Vuelto en caja') {
            vuelto = diferencia;
            monto_adelanto = 0.0;
        } else if (frm.doc.aplicar === 'Abona a siguiente cuota' || frm.doc.aplicar === 'Abono a Capital' || frm.doc.aplicar === 'Abono a Intereses') {
            vuelto = 0.0;
            monto_adelanto = diferencia;
        } else {
            vuelto = diferencia;
            monto_adelanto = 0.0;
        }
    }

    frm.set_value('vuelto', vuelto);
    frm.set_value('monto_adelanto', monto_adelanto);

    let total_facturar = (monto_recibido > 0) ? (total_a_pagar + monto_adelanto) : total_a_pagar;
    frm.set_value('total_facturar', total_facturar);
}
