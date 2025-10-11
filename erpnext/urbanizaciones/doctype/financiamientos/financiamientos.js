// Copyright (c) 2025, Frappe Technologies Pvt. Ltd. and contributors
// For license information, please see license.txt

frappe.ui.form.on('Financiamientos', {
    onload: function(frm)
    {
		// Calculate capital_financiado on load if fields already have values
        calculate_capital_financiero(frm);
        calculate_cuota_estimada(frm);
        calculate_proxima_fecha(frm);
        calculate_saldo_actual(frm);
    },

    // add refresh to create the button and manage its state
    refresh: function(frm) {
        // create the button once (always enabled)
        if (!frm.__btn_generar) {
            frm.__btn_generar = frm.add_custom_button(__('Generar cuotas'), function() {
                // NOTE: button always enabled. If required data is missing, do nothing.
                const required_fields = [
                    'customer',
                    'urbanizaciones',
                    'activos',
                    'fecha_inicio',
                    'monto_contrato',
                    'configuracion_financiamiento',
                    'prima',
                    'capital_financiado',
                    'plazo_meses',
                    'interes_anual',
                    'dia_vencimiento_cuota',
                    'mora_diaria',
                ];

                const allFilled = required_fields.every(fn => {
                    const v = frm.doc[fn];
                    return v !== undefined && v !== null && v !== '' && !(typeof v === 'number' && isNaN(v));
                });

                // If basic required fields are not present, do nothing (silent)
                if (!allFilled) {
                    frappe.show_alert({ message: __('Complete todos los campos requeridos para generar las cuotas'), indicator: 'red' });
                    return;
                }

                // prevent double click immediately
                frm.__btn_generar.prop('disabled', true);

                const call_generate = () => {
                    frappe.call({
                        method: 'erpnext.urbanizaciones.doctype.financiamientos.financiamientos.generar_cuotas',
                        args: { docname: frm.doc.name },
                    }).then(() => {
                        frm.reload_doc();
                        frappe.show_alert({ message: __('Cuotas generadas'), indicator: 'green' });
                        // mark as generated to avoid duplicate generation
                        frm.__cuotas_generadas = true;
                        if (frm.__btn_generar) frm.__btn_generar.prop('disabled', true);
                    }).catch((err) => {
                        console.error(err);
                        frappe.msgprint(__('Error generando cuotas'));
                        // re-enable button on error
                        if (frm.__btn_generar) frm.__btn_generar.prop('disabled', false);
                    });
                };

                // If the document is new or has unsaved changes, save it first so it exists in DB.
                if (frm.is_new() || frm.is_dirty()) {
                    frm.save().then(() => {
                        call_generate();
                    }).catch(() => {
                        // save failed or was cancelled -> re-enable button
                        if (frm.__btn_generar) frm.__btn_generar.prop('disabled', false);
                    });
                } else {
                    call_generate();
                }
            });

            // ensure custom button starts enabled
            frm.__btn_generar.prop('disabled', false);
        }
    },

    monto_contrato: function(frm)
    {
        calculate_capital_financiero(frm);
        calculate_cuota_estimada(frm);        
    },

    prima: function(frm)
    {
        calculate_capital_financiero(frm);
        calculate_cuota_estimada(frm);
    },

    interes_anual: function(frm)
    {
        calculate_cuota_estimada(frm);
    },

    plazo_meses: function(frm)
    {
        calculate_cuota_estimada(frm);
    },

    fecha_inicio: function(frm)
    {
        calculate_proxima_fecha(frm);
    },

    dia_vencimiento_cuota: function(frm)
    {
        calculate_proxima_fecha(frm);
    },

    capital_financiado: function(frm)
    {
        calculate_saldo_actual(frm);        
    }
});

// Function to calculate capital_financiado
function calculate_capital_financiero(frm)
{
    let monto = frm.doc.monto_contrato || 0;
    let prima = frm.doc.prima || 0;

    frm.set_value('capital_financiado', monto - prima);
}

// Function to calculate cuota_estimada
function calculate_cuota_estimada(frm)
{
    let interes_anual = frm.doc.interes_anual || 0;
    let capital = frm.doc.capital_financiado || 0;
    let cuotas = frm.doc.plazo_meses || 0;

    if (interes_anual > 0 && capital > 0 && cuotas > 0)
    {
        let r = (interes_anual / 100) / 12;
        let n = cuotas;
        let pv = capital;

        let cuota = (r * pv) / (1 - Math.pow(1 + r, -n));

        frm.set_value('cuota_estimada', Math.round(cuota * 100) / 100);
    }
    else
    {
        frm.set_value('cuota_estimada', 0);
    }
}

function calculate_proxima_fecha(frm)
{
    //Todo: si ya existe el plan de pago, mostrar la fecha de vencimiento de la cuota correspondiente
    
    const fecha_inicio = frm.doc.fecha_inicio;
    const dia_vencimiento = frm.doc.dia_vencimiento_cuota;

    if (fecha_inicio && dia_vencimiento)
    {
        let fecha = frappe.datetime.str_to_obj(fecha_inicio);
        
        fecha.setMonth(fecha.getMonth() + 1);
        fecha.setDate(dia_vencimiento);

        frm.set_value('fecha_vencimiento_cuota', frappe.datetime.obj_to_str(fecha));
    }
    else
    {
        frm.set_value('fecha_vencimiento_cuota', null);
    }
}

function calculate_saldo_actual(frm)
{
    // Todo: Hacer el calculo correspondiente al capital a medida se pagan las cuotas
    frm.set_value('saldo_actual', frm.doc.capital_financiado);
}