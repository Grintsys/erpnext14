// Copyright (c) 2025, Frappe Technologies Pvt. Ltd. and contributors
// For license information, please see license.txt

frappe.ui.form.on('Urbanizaciones', {
    setup: function(frm) {
        frm.set_query('cost_center', function() {
            return {
                filters: {
                    is_group: 0
                }
            };
        });
    }
});
