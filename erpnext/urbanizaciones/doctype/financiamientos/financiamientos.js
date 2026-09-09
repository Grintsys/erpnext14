// Copyright (c) 2025, Frappe Technologies Pvt. Ltd. and contributors
// For license information, please see license.txt

frappe.ui.form.on('Financiamientos', {
    setup: function(frm) {
        frm.set_query('activos', function() {
            return {
                filters: {
                    urbanizaciones: frm.doc.urbanizaciones || ''
                }
            };
        });
        frm.set_query('centro_costo', function() {
            return {
                filters: {
                    is_group: 0
                }
            };
        });
    },

    onload: function(frm)
    {
		// Calculate capital_financiado on load if fields already have values
        calculate_capital_financiero(frm);
        calculate_cuota_estimada(frm);
        calculate_proxima_fecha(frm);
        calculate_saldo_actual(frm);
    },

    refresh: function(frm) {
        const hasCuotas = Array.isArray(frm.doc.cuotas) && frm.doc.cuotas.length > 0;
        const isDraft = frm.doc.docstatus === 0;

        // Mostrar botón 'Generar cuotas' mientras el documento esté en Borrador (docstatus == 0)
        if (isDraft) {
            let btn = frm.add_custom_button(__('Generar cuotas'), function() {
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

                if (!allFilled) {
                    frappe.show_alert({ message: __('Complete todos los campos requeridos para generar las cuotas'), indicator: 'red' });
                    return;
                }

                const call_generate = () => {
                    btn.prop('disabled', true);
                    frappe.call({
                        method: 'erpnext.urbanizaciones.doctype.financiamientos.financiamientos.generar_cuotas',
                        args: { docname: frm.doc.name },
                        freeze: true,
                        freeze_message: __('Generando cuotas de financiamiento...'),
                    }).then(() => {
                        frm.reload_doc();
                        frappe.show_alert({ message: __('Cuotas generadas exitosamente'), indicator: 'green' });
                    }).catch((err) => {
                        console.error(err);
                        btn.prop('disabled', false);
                    });
                };

                const execute = () => {
                    if (hasCuotas) {
                        frappe.confirm(
                            __('Ya existen cuotas generadas. ¿Desea regenerar el plan de pagos con los datos actuales?'),
                            function() {
                                if (frm.is_dirty()) {
                                    frm.save().then(() => call_generate()).catch(() => btn.prop('disabled', false));
                                } else {
                                    call_generate();
                                }
                            }
                        );
                    } else {
                        if (frm.is_new() || frm.is_dirty()) {
                            frm.save().then(() => call_generate()).catch(() => btn.prop('disabled', false));
                        } else {
                            call_generate();
                        }
                    }
                };

                execute();
            });

            if (!frm.is_new()) {
                btn.addClass('btn-primary');
            }
        }

        // lock 'es_refinanciamiento' if user selected "Si" or if cuotas already exist
        const lockField = (frm.doc.es_refinanciamiento === 'Si') || hasCuotas;
        frm.set_df_property('es_refinanciamiento', 'read_only', lockField ? 1 : 0);

        // Botón para abrir "Generar Factura" en una NUEVA pestaña del navegador
        if (!frm.is_new() && hasCuotas) {
            frm.add_custom_button(__('Generar Factura'), function() {
                if (frm.is_dirty()) {
                    frappe.show_alert({ message: __('Guarde los cambios antes de abrir Generar Factura'), indicator: 'warning' });
                    return;
                }
                let url = frappe.urllib.get_full_url(
                    `/app/generar-factura/new-generar-factura-1?customer=${encodeURIComponent(frm.doc.customer || '')}&financiamiento=${encodeURIComponent(frm.doc.name || '')}`
                );
                window.open(url, '_blank');
            });

            frm.add_custom_button(__('Actualizar Políticas de Cobro'), function() {
                frappe.confirm(
                    __('¿Desea actualizar las políticas financieras de este contrato a la versión vigente en su Configuración de Urbanización?'),
                    function() {
                        frappe.call({
                            method: 'erpnext.urbanizaciones.doctype.financiamientos.financiamientos.adoptar_nuevas_politicas',
                            args: { financiamiento_name: frm.doc.name },
                            callback: function(r) {
                                if (r.message && r.message.success) {
                                    frm.reload_doc();
                                }
                            }
                        });
                    }
                );
            }, __('Acciones'));
        }
    },

    es_refinanciamiento: function(frm) {
        // if user sets it to "Si" lock it immediately; if "No" only unlock when no cuotas
        const hasCuotas = Array.isArray(frm.doc.cuotas) && frm.doc.cuotas.length > 0;
        if (frm.doc.es_refinanciamiento === 'Si') {
            frm.set_df_property('es_refinanciamiento', 'read_only', 1);
        } else {
            frm.set_df_property('es_refinanciamiento', 'read_only', hasCuotas ? 1 : 0);
        }
    },

    urbanizaciones: function(frm) {
        if (frm.doc.activos) {
            frappe.db.get_value('Activos', frm.doc.activos, 'urbanizaciones', function(r) {
                if (r && r.urbanizaciones !== frm.doc.urbanizaciones) {
                    frm.set_value('activos', '');
                }
            });
        }
    },

    activos: function(frm) {
        if (frm.doc.activos) {
            frappe.db.get_value('Activos', frm.doc.activos, 'centro_de_costo', function(r) {
                if (r && r.centro_de_costo) {
                    frm.set_value('centro_costo', r.centro_de_costo);
                }
            });
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
    let monto = parseFloat(frm.doc.monto_contrato) || 0;
    let prima = parseFloat(frm.doc.prima) || 0;    

    const hasCuotas = Array.isArray(frm.doc.cuotas) && frm.doc.cuotas.length > 0;
    if (frm.is_new() || !hasCuotas) {
        frm.set_value('capital_financiado', monto - prima);    
    }
}

// Function to calculate cuota_estimada
function calculate_cuota_estimada(frm)
{
    let interes_anual = parseFloat(frm.doc.interes_anual) || 0;
    let capital = parseFloat(frm.doc.capital_financiado) || 0;
    let cuotas = parseInt(frm.doc.plazo_meses) || 0;

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
    calculate_saldo_actual(frm);
}

function calculate_proxima_fecha(frm)
{
    if (frm.is_new()){
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
}

function calculate_saldo_actual(frm)
{
    const hasCuotas = Array.isArray(frm.doc.cuotas) && frm.doc.cuotas.length > 0;
    if (frm.is_new() || !hasCuotas) {
        let cuota = parseFloat(frm.doc.cuota_estimada) || 0;
        let plazo = parseInt(frm.doc.plazo_meses) || 0;
        let prima = parseFloat(frm.doc.prima) || 0;

        let saldo_actual = cuota * plazo;
        let total_financiado = saldo_actual + prima;

        frm.set_value('saldo_actual', Math.round(saldo_actual * 100) / 100);
        frm.set_value('total_financiado', Math.round(total_financiado * 100) / 100);
    }
}