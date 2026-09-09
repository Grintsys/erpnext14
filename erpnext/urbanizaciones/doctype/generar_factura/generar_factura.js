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
        return {
            query: 'erpnext.urbanizaciones.doctype.financiamientos.financiamientos.financiamiento_query',
            filters: filters
        };
    });
}

frappe.ui.form.on('Generar Factura', {
    refresh: function(frm) {
        setup_financiamiento_query(frm);
        if (frm.doc.docstatus === 0 && frm.doc.financiamiento && !frm.doc.total_a_pagar) {
            fetch_pending_quota(frm);
        } else {
            calculate_payment_totals(frm);
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
            frm.set_value('total_cuota', 0);
            frm.set_value('total_mora', 0);
            frm.set_value('total_a_pagar', 0);
            calculate_payment_totals(frm);
        }
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
            financiamiento: frm.doc.financiamiento
        },
        callback: function(r) {
            if (r.message && Object.keys(r.message).length > 0) {
                if (!frm.doc.customer && r.message.customer) {
                    frm.set_value('customer', r.message.customer);
                }
                frm.set_value('date_quote_financing', r.message.date_quote_financing);
                frm.set_value('total_cuota', r.message.total_cuota);
                frm.set_value('total_mora', r.message.total_mora);
                frm.set_value('total_a_pagar', r.message.total_a_pagar);
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
    let vuelto = diferencia > 0 ? diferencia : 0.0;

    frm.set_value('vuelto', vuelto);

    let monto_adelanto = 0.0;
    if (frm.doc.aplicar === 'Abona a siguiente cuota' && total_mora <= 0 && diferencia > 0) {
        monto_adelanto = vuelto;
    }

    let total_facturar = (monto_recibido > 0) ? (total_a_pagar + monto_adelanto) : total_a_pagar;

    frm.set_value('monto_adelanto', monto_adelanto);
    frm.set_value('total_facturar', total_facturar);
}

