// Copyright (c) 2025, Frappe Technologies Pvt. Ltd. and contributors
// For license information, please see license.txt

frappe.ui.form.on('Cancelar Financiamiento', {
	onload: function(frm) {
		// incluir financiamientos con status 'Activo' o 'Refinanciado'
		frm.set_query('financiamientos', function() {
			return {
				filters: [
					['status', 'in', ['Activo', 'Refinanciado']]
				]
			};
		});
	}, 

	refresh: function(frm) {
		frm.set_query('financiamientos', function() {
			return {
				filters: [
					['status', 'in', ['Activo', 'Refinanciado']]
				]
			};
		});
	}
});