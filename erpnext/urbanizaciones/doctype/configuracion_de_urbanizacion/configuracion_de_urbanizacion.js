// Copyright (c) 2025, Frappe Technologies Pvt. Ltd. and contributors
// For license information, please see license.txt

frappe.ui.form.on('Configuracion de Urbanizacion', {
	// refresh: function(frm) {

	// }
	onload: function(frm) {
        frappe.call({
            method: "get_prefix",
            doc: frm.doc,
            callback: function(r) {
                if (r.message) {
                    frm.set_df_property("prefix", "options", r.message.prefix);
                }
            }
        });
    }
});
