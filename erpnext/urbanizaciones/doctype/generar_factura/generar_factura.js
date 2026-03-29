// Copyright (c) 2026, Frappe Technologies Pvt. Ltd. and contributors
// For license information, please see license.txt

frappe.ui.form.on('Generar Factura', {
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
