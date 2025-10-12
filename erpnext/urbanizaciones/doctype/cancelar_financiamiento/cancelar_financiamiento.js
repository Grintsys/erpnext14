// Copyright (c) 2025, Frappe Technologies Pvt. Ltd. and contributors
// For license information, please see license.txt

frappe.ui.form.on('Cancelar Financiamiento', {

	// When the linked Financiamientos is selected, load its cuotas into this form
	financiamientos: function(frm) {
		if (!frm.doc.financiamientos) {
			// nothing selected, clear cuotas
			frm.clear_table('cuotas');
			frm.refresh_field('cuotas');
			return;
		}

		const load = () => {
			// show overlay/spinner while loading cuotas
			frappe.dom.freeze(__('Cargando cuotas...'));

			frappe.call({
				method: 'frappe.client.get',
				args: {
					doctype: 'Financiamientos',
					name: frm.doc.financiamientos
				},
				callback: function(r) {
					// always unfreeze when callback executes
					frappe.dom.unfreeze();

					if (!r.message) return;

					const source_cuotas = r.message.cuotas || [];

					// transform rows: remove internal keys that shouldn't be copied
					const rows = source_cuotas.map(c => {
						const obj = {};
						for (const k in c) {
							if (Object.prototype.hasOwnProperty.call(c, k)) {
								if (k === 'name' || k === 'idx' || k === 'owner' || k === 'creation' || k === 'modified' || k === 'modified_by') continue;
								obj[k] = c[k];
							}
						}
						return obj;
					});

					// set the table
					frm.set_value('cuotas', rows);
					frm.refresh_field('cuotas');
				},
				error: function() {
					// ensure spinner removed on error
					frappe.dom.unfreeze();
				}
			});
		};

		// always overwrite the cuotas table (table is read-only in this doctype)
		load();
	},

	// also load on refresh if a financiamiento is already selected
	refresh: function(frm) {
		if (frm.doc.financiamientos) {
			// always reload cuotas from the selected financiamiento (table is read-only)
			frappe.ui.form.trigger('Cancelar Financiamiento', 'financiamientos', frm);
		}
	}
});
