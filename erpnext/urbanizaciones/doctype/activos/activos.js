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
    }
});
