// Copyright (c) 2026, Frappe Technologies Pvt. Ltd. and contributors
// For license information, please see license.txt

frappe.ui.form.on('Pago de cuota', {
	onload: function(frm) {
		// incluir financiamientos con status 'Activo' o 'Refinanciado'
		frm.set_query('financiamiento', function() {
			return {
				filters: [
					['status', 'in', ['Activo', 'Refinanciado']]
				]
			};
		});
	},

	refresh: function(frm) {
		frm.set_query('financiamiento', function() {
			return {
				filters: [
					['status', 'in', ['Activo', 'Refinanciado']]
				]
			};
		});
	},
});
