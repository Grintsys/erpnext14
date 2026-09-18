// Copyright (c) 2025, Frappe Technologies Pvt. Ltd. and contributors
// For license information, please see license.txt

frappe.ui.form.on('Financiamientos', {
    setup: function(frm) {
        // Filtrar activos disponibles o reservados para la urbanización seleccionada en cabecera
        frm.set_query('activos', function() {
            return {
                query: 'erpnext.urbanizaciones.doctype.financiamientos.financiamientos.activo_disponible_query',
                filters: {
                    urbanizaciones: frm.doc.urbanizaciones || '__NONE__',
                    current_doc: frm.doc.name || ''
                }
            };
        });

        // Filtrar en la tabla de múltiples activos
        frm.set_query('activo', 'activos_detalle', function(doc, cdt, cdn) {
            let row = locals[cdt] && locals[cdt][cdn];
            let urb = '';
            if (frm.doc.multiples_urbanizaciones) {
                urb = (row && row.urbanizacion) ? row.urbanizacion : '';
            } else {
                urb = frm.doc.urbanizaciones || '__NONE__';
            }

            return {
                query: 'erpnext.urbanizaciones.doctype.financiamientos.financiamientos.activo_disponible_query',
                filters: {
                    urbanizaciones: urb,
                    current_doc: frm.doc.name || ''
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

    onload: function(frm) {
        calculate_capital_financiero(frm);
        calculate_cuota_estimada(frm);
        calculate_proxima_fecha(frm);
        calculate_saldo_actual(frm);
    },

    refresh: function(frm) {
        const hasCuotas = Array.isArray(frm.doc.cuotas) && frm.doc.cuotas.length > 0;
        const isDraft = frm.doc.docstatus === 0;

        // Indicador de estado del financiamiento y mora
        if (!frm.is_new() && frm.doc.status) {
            let hasOverdue = false;
            let totalMora = 0;
            let cuotasPagadas = 0;
            let totalPagado = 0;
            let cuotasPendientes = 0;

            if (hasCuotas) {
                const today = frappe.datetime.get_today();
                frm.doc.cuotas.forEach(c => {
                    if (c.status === 'Pagado' || c.status === 'Anticipada') {
                        cuotasPagadas += 1;
                        totalPagado += flt(c.total_cuota);
                    } else if (c.status === 'Pendiente') {
                        cuotasPendientes += 1;
                        if (c.fecha_vencimiento_cuota && c.fecha_vencimiento_cuota < today) {
                            hasOverdue = true;
                            totalMora += flt(c.mora);
                        }
                    }
                });
            }

            if (frm.doc.status === 'Completado') {
                frm.page.set_indicator(__('Completado'), 'blue');
            } else if (frm.doc.status === 'Cancelado') {
                frm.page.set_indicator(__('Cancelado'), 'red');
            } else if (hasOverdue) {
                frm.page.set_indicator(__('En Mora (L %s)', [format_currency(totalMora)]), 'red');
            } else if (frm.doc.status === 'Activo') {
                frm.page.set_indicator(__('Al Día (Activo)'), 'green');
            } else if (frm.doc.status === 'Refinanciado') {
                frm.page.set_indicator(__('Refinanciado'), 'purple');
            } else {
                frm.page.set_indicator(__(frm.doc.status), 'orange');
            }

            // Resumen estadístico
            if (hasCuotas && frm.dashboard) {
                frm.dashboard.clear_headline();
                let hist_info = (frm.doc.es_saldo_inicial && frm.doc.cuotas_pagadas_historicas)
                    ? `<span style="color: var(--primary-color, #171717);"><b>Migradas/Iniciales:</b> ${frm.doc.cuotas_pagadas_historicas}</span>`
                    : '';
                let summary_html = `
                    <div style="display: flex; gap: 20px; font-size: 13px; padding: 5px 0; flex-wrap: wrap;">
                        <span><b>Cuotas Pagadas:</b> ${cuotasPagadas} / ${frm.doc.cuotas.length}</span>
                        ${hist_info}
                        <span><b>Total Pagado:</b> ${format_currency(totalPagado)}</span>
                        <span><b>Saldo Pendiente:</b> ${format_currency(frm.doc.saldo_actual || 0)}</span>
                        ${totalMora > 0 ? `<span style="color: var(--text-color-danger, #e24c4c);"><b>Mora Acumulada:</b> ${format_currency(totalMora)}</span>` : ''}
                    </div>
                `;
                frm.dashboard.set_headline(summary_html);
            }
        }

        // Mostrar botón 'Generar cuotas' mientras el documento esté en Borrador (docstatus == 0)
        if (isDraft) {
            let btn = frm.add_custom_button(__('Generar cuotas'), function() {
                const required_fields = [
                    'customer',
                    'urbanizaciones',
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

                const hasAsset = frm.doc.activos || (Array.isArray(frm.doc.activos_detalle) && frm.doc.activos_detalle.length > 0);

                if (!allFilled || !hasAsset) {
                    frappe.show_alert({ message: __('Complete todos los campos requeridos y seleccione al menos un Activo'), indicator: 'red' });
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

        // Lock 'es_refinanciamiento' si ya existen cuotas
        const lockField = (frm.doc.es_refinanciamiento === 'Si') || hasCuotas;
        frm.set_df_property('es_refinanciamiento', 'read_only', lockField ? 1 : 0);

        // Botón para abrir "Generar Factura"
        if (!frm.is_new() && hasCuotas && frm.doc.status !== 'Completado' && frm.doc.status !== 'Cancelado') {
            frm.add_custom_button(__('Generar Factura'), function() {
                if (frm.is_dirty()) {
                    frappe.show_alert({ message: __('Guarde los cambios antes de abrir Generar Factura'), indicator: 'warning' });
                    return;
                }
                let url = frappe.urllib.get_full_url(
                    `/app/generar-factura/new-generar-factura-1?customer=${encodeURIComponent(frm.doc.customer || '')}&financiamiento=${encodeURIComponent(frm.doc.name || '')}`
                );
                window.open(url, '_blank');
            }).addClass('btn-primary');

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

            frm.add_custom_button(__('Cargar Pagos Históricos'), function() {
                let d = new frappe.ui.Dialog({
                    title: __('Configurar Saldo Inicial / Pagos Históricos'),
                    fields: [
                        {
                            label: __('Número de Cuotas Pagadas'),
                            fieldname: 'cuotas_pagadas',
                            fieldtype: 'Int',
                            reqd: 1,
                            default: frm.doc.cuotas_pagadas_historicas || 0,
                            description: __('Total de cuotas ya pagadas en el sistema anterior (1 a ' + frm.doc.cuotas.length + ')')
                        },
                        {
                            label: __('No. Recibo / Referencia Histórica'),
                            fieldname: 'referencia',
                            fieldtype: 'Data',
                            default: frm.doc.referencia_migracion || '',
                            description: __('Número de recibo, contrato o referencia del sistema heredado')
                        },
                        {
                            label: __('Fecha Último Pago Histórico'),
                            fieldname: 'fecha_corte',
                            fieldtype: 'Date',
                            default: frm.doc.fecha_corte_migracion || frappe.datetime.get_today()
                        }
                    ],
                    primary_action_label: __('Aplicar Pagos Históricos'),
                    primary_action: function(values) {
                        if (values.cuotas_pagadas < 0 || values.cuotas_pagadas > frm.doc.cuotas.length) {
                            frappe.msgprint(__('El número de cuotas debe estar entre 0 y ' + frm.doc.cuotas.length));
                            return;
                        }
                        d.hide();
                        frappe.call({
                            method: 'erpnext.urbanizaciones.doctype.financiamientos.financiamientos.aplicar_pagos_historicos',
                            args: {
                                docname: frm.doc.name,
                                cuotas_pagadas: values.cuotas_pagadas,
                                referencia: values.referencia,
                                fecha_corte: values.fecha_corte
                            },
                            freeze: true,
                            freeze_message: __('Aplicando pagos históricos...'),
                            callback: function(r) {
                                if (r.message && r.message.success) {
                                    frappe.show_alert({
                                        message: __('Se aplicaron {0} cuotas históricas correctamente.', [r.message.cuotas_pagadas]),
                                        indicator: 'green'
                                    });
                                    frm.reload_doc();
                                }
                            }
                        });
                    }
                });
                d.show();
            }, __('Acciones'));
        }
    },

    es_refinanciamiento: function(frm) {
        const hasCuotas = Array.isArray(frm.doc.cuotas) && frm.doc.cuotas.length > 0;
        if (frm.doc.es_refinanciamiento === 'Si') {
            frm.set_df_property('es_refinanciamiento', 'read_only', 1);
        } else {
            frm.set_df_property('es_refinanciamiento', 'read_only', hasCuotas ? 1 : 0);
        }
    },

    multiples_urbanizaciones: function(frm) {
        if (!frm.doc.multiples_urbanizaciones && frm.doc.urbanizaciones) {
            (frm.doc.activos_detalle || []).forEach(row => {
                if (row.urbanizacion !== frm.doc.urbanizaciones) {
                    frappe.model.set_value(row.doctype, row.name, 'urbanizacion', frm.doc.urbanizaciones);
                }
            });
        }
        if (frm.fields_dict['activos_detalle'] && frm.fields_dict['activos_detalle'].grid) {
            frm.fields_dict['activos_detalle'].grid.refresh();
        }
    },

    urbanizaciones: function(frm) {
        if (frm.doc.urbanizaciones) {
            if (!frm.doc.centro_costo) {
                frappe.db.get_value('Urbanizaciones', frm.doc.urbanizaciones, 'cost_center', function(r) {
                    if (r && r.cost_center) {
                        frm.set_value('centro_costo', r.cost_center);
                    }
                });
            }
        }
        if (frm.doc.activos) {
            frappe.db.get_value('Activos', frm.doc.activos, 'urbanizaciones', function(r) {
                if (r && r.urbanizaciones !== frm.doc.urbanizaciones) {
                    frm.set_value('activos', '');
                }
            });
        }
        if (!frm.doc.multiples_urbanizaciones && frm.doc.urbanizaciones) {
            (frm.doc.activos_detalle || []).forEach(row => {
                frappe.model.set_value(row.doctype, row.name, 'urbanizacion', frm.doc.urbanizaciones);
                if (row.activo) {
                    frappe.db.get_value('Activos', row.activo, 'urbanizaciones', function(r) {
                        if (r && r.urbanizaciones !== frm.doc.urbanizaciones) {
                            frappe.model.set_value(row.doctype, row.name, 'activo', '');
                        }
                    });
                }
            });
        }
    },

    activos: function(frm) {
        if (frm.doc.activos) {
            frappe.db.get_value('Activos', frm.doc.activos, ['centro_de_costo', 'precio', 'status', 'descripcion_lote', 'urbanizaciones'], function(r) {
                if (r) {
                    if (r.urbanizaciones && !frm.doc.urbanizaciones) {
                        frm.set_value('urbanizaciones', r.urbanizaciones);
                    }
                    if (r.centro_de_costo) {
                        frm.set_value('centro_costo', r.centro_de_costo);
                    }
                    if (r.precio && (!frm.doc.monto_contrato || frm.doc.monto_contrato === 0)) {
                        frm.set_value('monto_contrato', r.precio);
                    }
                    // Validar estado
                    if (r.status && r.status !== 'Disponible' && r.status !== 'Reservado' && frm.is_new()) {
                        frappe.msgprint({
                            title: __('Activo no Disponible'),
                            indicator: 'orange',
                            message: __('Advertencia: El activo <b>{0}</b> tiene estado <b>{1}</b>. Asegúrese de que esté disponible para venta.', [frm.doc.activos, r.status])
                        });
                    }
                }
            });
        }
    },

    monto_contrato: function(frm) {
        calculate_capital_financiero(frm);
        calculate_cuota_estimada(frm);        
    },

    prima: function(frm) {
        calculate_capital_financiero(frm);
        calculate_cuota_estimada(frm);
    },

    interes_anual: function(frm) {
        calculate_cuota_estimada(frm);
    },

    plazo_meses: function(frm) {
        calculate_cuota_estimada(frm);
    },

    fecha_inicio: function(frm) {
        calculate_proxima_fecha(frm);
    },

    dia_vencimiento_cuota: function(frm) {
        calculate_proxima_fecha(frm);
    },

    capital_financiado: function(frm) {
        calculate_saldo_actual(frm);        
    }
});

// Eventos de la tabla de múltiples activos
frappe.ui.form.on('Financiamiento Activo Detalle', {
    activos_detalle_add: function(frm, cdt, cdn) {
        if (!frm.doc.multiples_urbanizaciones && frm.doc.urbanizaciones) {
            frappe.model.set_value(cdt, cdn, 'urbanizacion', frm.doc.urbanizaciones);
        }
    },

    urbanizacion: function(frm, cdt, cdn) {
        let row = locals[cdt][cdn];
        if (row.activo) {
            frappe.db.get_value('Activos', row.activo, 'urbanizaciones', function(r) {
                if (r && r.urbanizaciones && r.urbanizaciones !== row.urbanizacion) {
                    frappe.model.set_value(cdt, cdn, 'activo', '');
                }
            });
        }
    },

    activo: function(frm, cdt, cdn) {
        let row = locals[cdt][cdn];
        if (row.activo) {
            frappe.db.get_value('Activos', row.activo, ['descripcion_lote', 'precio', 'centro_de_costo', 'status', 'urbanizaciones'], function(r) {
                if (r) {
                    frappe.model.set_value(cdt, cdn, 'descripcion_lote', r.descripcion_lote || '');
                    frappe.model.set_value(cdt, cdn, 'precio', r.precio || 0);
                    frappe.model.set_value(cdt, cdn, 'centro_de_costo', r.centro_de_costo || '');
                    
                    if (r.urbanizaciones) {
                        frappe.model.set_value(cdt, cdn, 'urbanizacion', r.urbanizaciones);
                    }

                    if (r.status && r.status !== 'Disponible' && r.status !== 'Reservado' && frm.is_new()) {
                        frappe.show_alert({
                            message: __('El activo {0} tiene estado {1}', [row.activo, r.status]),
                            indicator: 'orange'
                        });
                    }

                    // Sincronizar activo principal si está vacío y coincide la urbanización
                    if (!frm.doc.activos && (!frm.doc.urbanizaciones || frm.doc.urbanizaciones === r.urbanizaciones)) {
                        if (!frm.doc.urbanizaciones && r.urbanizaciones) {
                            frm.set_value('urbanizaciones', r.urbanizaciones);
                        }
                        frm.set_value('activos', row.activo);
                    }

                    recalculate_multi_assets_total(frm);
                }
            });
        }
    },

    precio: function(frm) {
        recalculate_multi_assets_total(frm);
    },

    activos_detalle_remove: function(frm) {
        recalculate_multi_assets_total(frm);
    }
});

function recalculate_multi_assets_total(frm) {
    if (frm.doc.docstatus === 0 && Array.isArray(frm.doc.activos_detalle) && frm.doc.activos_detalle.length > 0) {
        let total = 0;
        frm.doc.activos_detalle.forEach(r => {
            total += flt(r.precio);
        });
        if (total > 0) {
            frm.set_value('monto_contrato', flt(total, 2));
        }
    }
}

function calculate_capital_financiero(frm) {
    let monto = flt(frm.doc.monto_contrato);
    let prima = flt(frm.doc.prima);    

    const hasCuotas = Array.isArray(frm.doc.cuotas) && frm.doc.cuotas.length > 0;
    if (frm.is_new() || !hasCuotas) {
        frm.set_value('capital_financiado', flt(monto - prima, 2));    
    }
}

function calculate_cuota_estimada(frm) {
    let interes_anual = flt(frm.doc.interes_anual);
    let capital = flt(frm.doc.capital_financiado);
    let cuotas = parseInt(frm.doc.plazo_meses) || 0;

    if (capital > 0 && cuotas > 0) {
        if (interes_anual > 0) {
            let r = (interes_anual / 100.0) / 12.0;
            let n = cuotas;
            let pv = capital;
            let cuota = (r * pv) / (1.0 - Math.pow(1.0 + r, -n));
            frm.set_value('cuota_estimada', flt(cuota, 2));
        } else {
            frm.set_value('cuota_estimada', flt(capital / cuotas, 2));
        }
    } else {
        frm.set_value('cuota_estimada', 0);
    }
    calculate_saldo_actual(frm);
}

function calculate_proxima_fecha(frm) {
    if (frm.is_new()){
        const fecha_inicio = frm.doc.fecha_inicio;
        const dia_vencimiento = frm.doc.dia_vencimiento_cuota;

        if (fecha_inicio && dia_vencimiento) {
            let fecha = frappe.datetime.str_to_obj(fecha_inicio);
            fecha.setMonth(fecha.getMonth() + 1);
            fecha.setDate(dia_vencimiento);
            frm.set_value('fecha_vencimiento_cuota', frappe.datetime.obj_to_str(fecha));
        } else {
            frm.set_value('fecha_vencimiento_cuota', null);
        }
    }    
}

function calculate_saldo_actual(frm) {
    const hasCuotas = Array.isArray(frm.doc.cuotas) && frm.doc.cuotas.length > 0;
    if (frm.is_new() || !hasCuotas) {
        let cuota = flt(frm.doc.cuota_estimada);
        let plazo = parseInt(frm.doc.plazo_meses) || 0;
        let prima = flt(frm.doc.prima);

        let saldo_actual = flt(cuota * plazo, 2);
        let total_financiado = flt(saldo_actual + prima, 2);

        frm.set_value('saldo_actual', saldo_actual);
        frm.set_value('total_financiado', total_financiado);
    }
}