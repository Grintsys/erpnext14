// Copyright (c) 2025, Frappe Technologies Pvt. Ltd. and contributors
// For license information, please see license.txt

frappe.ui.form.on('Activos', {
    setup: function(frm) {
        frm.set_query('centro_de_costo', function() {
            return {
                filters: {
                    is_group: 0
                }
            };
        });
    },

    refresh: function(frm) {
        // Indicadores visuales de estado
        if (!frm.is_new() && frm.doc.status) {
            const status_colors = {
                'Disponible': 'green',
                'Reservado': 'orange',
                'Financiado': 'blue',
                'Refinanciado': 'purple',
                'Vendido': 'gray'
            };
            const color = status_colors[frm.doc.status] || 'blue';
            frm.page.set_indicator(__(frm.doc.status), color);
        }

        // Botón rápido para crear financiamiento si el activo está disponible
        if (!frm.is_new() && frm.doc.status === 'Disponible') {
            frm.add_custom_button(__('Crear Financiamiento'), function() {
                frappe.new_doc('Financiamientos', {
                    urbanizaciones: frm.doc.urbanizaciones,
                    activos: frm.doc.name,
                    monto_contrato: frm.doc.precio || 0,
                    centro_costo: frm.doc.centro_de_costo || ''
                });
            }).addClass('btn-primary');
        }
    },

    urbanizaciones: function(frm) {
        if (frm.doc.urbanizaciones && !frm.doc.centro_de_costo) {
            frappe.db.get_value('Urbanizaciones', frm.doc.urbanizaciones, 'cost_center', function(r) {
                if (r && r.cost_center) {
                    frm.set_value('centro_de_costo', r.cost_center);
                }
            });
        }
    }
});
