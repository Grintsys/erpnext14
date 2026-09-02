// Copyright (c) 2026, Frappe Technologies Pvt. Ltd. and contributors
// For license information, please see license.txt

frappe.ui.form.on('Generar Factura', {
    refresh: function(frm) {
        calculate_payment_totals(frm);
    },
    onload: function(frm) {
        calculate_payment_totals(frm);
    },
    financiamiento: function(frm) {
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
        // Limpia el campo de financiamiento cuando cambia el cliente
        frm.set_value('financiamiento', '');
        
        // Actualiza las opciones del campo financiamiento
        if (frm.doc.customer) {
            frappe.call({
                method: 'erpnext.urbanizaciones.doctype.generar_factura.generar_factura.get_financiamientos',
                args: {
                    customer: frm.doc.customer
                },
                callback: function(r) {
                    if (r.message) {
                        // Actualiza el filtro del campo
                        frm.fields_dict.financiamiento.get_query = function() {
                            return {
                                filters: {
                                    "customer": frm.doc.customer,
                                    "status": ["in", ["Activo", "Refinanciado"]]
                                }
                            };
                        };
                    }
                }
            });
        }
    }
});

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
        frm.set_df_property('aplicar', 'read_only', 1);
        frm.set_value('aplicar', '', null, true);
        frm.set_value('vuelto', 0.0);
        frm.set_value('monto_adelanto', monto_recibido);
        frm.set_value('total_facturar', monto_recibido);
        return;
    }

    // Caso B: Pago Completo o Mayor (monto_recibido >= total_a_pagar)
    if (total_mora > 0) {
        frm.set_df_property('aplicar', 'read_only', 1);
        if (frm.doc.aplicar === 'Abona a siguiente cuota') {
            frm.set_value('aplicar', '', null, true);
        }
    } else {
        frm.set_df_property('aplicar', 'read_only', 0);
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
