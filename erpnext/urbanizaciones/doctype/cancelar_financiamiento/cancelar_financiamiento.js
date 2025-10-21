// Copyright (c) 2025, Frappe Technologies Pvt. Ltd. and contributors
// For license information, please see license.txt

frappe.ui.form.on('Cancelar Financiamiento', {
	onload: function(frm) {
		frm.set_query('financiamientos', function() {
			return {
				filters: {
					status: 'Activo'
				}
			};
		});
	}, 

	refresh: function(frm) {
		frm.set_query('financiamientos', function() {
			return {
				filters: {
					status: 'Activo'
				}
			};
		});
	}
});