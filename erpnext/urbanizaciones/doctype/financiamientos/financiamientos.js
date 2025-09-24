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

        // Ensure button state is evaluated on load
        if (typeof toggle_generar_button === 'function') {
            toggle_generar_button(frm);
        }
    },

    // add refresh to create the button and manage its state
    refresh: function(frm) {
        // create the button once
        if (!frm.__btn_generar) {
            frm.__btn_generar = frm.add_custom_button(__('Generar cuotas'), function() {
                // prevent double click immediately
                frm.__btn_generar.prop('disabled', true);

                // call server to generate child table rows
                frappe.call({
                    // server method path - adjust if your python module is different
                    method: 'erpnext.urbanizaciones.doctype.financiamientos.financiamientos.generar_cuotas',
                    args: { docname: frm.doc.name },
                }).then(() => {
                    frm.reload_doc();
                    frappe.show_alert({ message: __('Cuotas generadas'), indicator: 'green' });
                    // mark as generated to avoid duplicate generation
                    frm.__cuotas_generadas = true;
                    // keep button disabled
                    if (frm.__btn_generar) frm.__btn_generar.prop('disabled', true);
                }).catch(() => {
                    frappe.msgprint(__('Error generando cuotas'));
                    // re-evaluate to allow retry
                    toggle_generar_button(frm);
                });
            });
        }

        // evaluate button enabled/disabled state on refresh
        toggle_generar_button(frm);
    },

    monto_contrato: function(frm)
    {
        calculate_capital_financiero(frm);
        calculate_cuota_estimada(frm);
        // re-evaluate button state
        toggle_generar_button(frm);
    },

    prima: function(frm)
    {
        calculate_capital_financiero(frm);
        calculate_cuota_estimada(frm);
        toggle_generar_button(frm);
    },

    interes_anual: function(frm)
    {
        calculate_cuota_estimada(frm);
        toggle_generar_button(frm);
    },

    plazo_meses: function(frm)
    {
        calculate_cuota_estimada(frm);
        toggle_generar_button(frm);
    },

    fecha_inicio: function(frm)
    {
        calculate_proxima_fecha(frm);
        toggle_generar_button(frm);
    },

    dia_vencimiento_cuota: function(frm)
    {
        calculate_proxima_fecha(frm);
        toggle_generar_button(frm);
    },

    capital_financiado: function(frm)
    {
        calculate_saldo_actual(frm);
        toggle_generar_button(frm);
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

// Helper: enable the "Generar cuotas" button only when required fields are present
function toggle_generar_button(frm) {
    // if button was already used to generate cuotas, keep it disabled
    if (frm.__cuotas_generadas) {
        if (frm.__btn_generar) frm.__btn_generar.prop('disabled', true);
        return;
    }

    // fieldnames required to allow generation - adjust as needed
    const required_fields = [
        'monto_contrato',
        'prima',
        'interes_anual',
        'plazo_meses',
        'fecha_inicio'
    ];

    const allFilled = required_fields.every(fn => {
        const v = frm.doc[fn];
        return v !== undefined && v !== null && v !== '' && !(typeof v === 'number' && isNaN(v));
    });

    const plazo_ok = Number(frm.doc.plazo_meses) > 0;
    const capital_ok = Number(frm.doc.capital_financiado) > 0;

    const enabled = allFilled && plazo_ok && capital_ok;

    if (frm.__btn_generar) {
        frm.__btn_generar.prop('disabled', !enabled);
    }
}