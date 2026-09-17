// Copyright (c) 2026, Frappe Technologies Pvt. Ltd. and contributors
// For license information, please see license.txt

function setup_financiamiento_query(frm) {
	frm.set_query('financiamiento', function() {
		let filters = {
			status: ['Activo', 'Refinanciado']
		};
		if (frm.doc.customer) {
			filters.customer = frm.doc.customer;
		}
		return {
			query: 'erpnext.urbanizaciones.doctype.financiamientos.financiamientos.financiamiento_query',
			filters: filters
		};
	});
}

function recalculate_totals(frm) {
	let total_actual = 0;
	let total_negociada = 0;

	(frm.doc.cuotas_detalle || []).forEach(row => {
		const act = flt(row.mora_actual || 0);
		const neg = flt(row.mora_negociada || 0);
		row.descuento = flt(act - neg, 2);

		total_actual += act;
		total_negociada += neg;
	});

	frm.set_value('total_mora_actual', flt(total_actual, 2));
	frm.set_value('total_mora_negociada', flt(total_negociada, 2));
	frm.set_value('total_descuento', flt(total_actual - total_negociada, 2));
	frm.refresh_field('cuotas_detalle');
}

frappe.ui.form.on('Modificar Mora', {
	onload: function(frm) {
		setup_financiamiento_query(frm);
		if (frm.is_new() && !frm.doc.fecha_limite_acuerdo) {
			frm.set_value('fecha_limite_acuerdo', frappe.datetime.add_days(frappe.datetime.nowdate(), 3));
		}
	},

	refresh: function(frm) {
		setup_financiamiento_query(frm);
	},

	customer: function(frm) {
		if (frm.doc.financiamiento) {
			frappe.db.get_value('Financiamientos', frm.doc.financiamiento, 'customer')
				.then(r => {
					if (r && r.message && r.message.customer !== frm.doc.customer) {
						frm.set_value('financiamiento', null);
						frm.clear_table('cuotas_detalle');
						frm.refresh_field('cuotas_detalle');
						recalculate_totals(frm);
					}
				});
		}
	},

	financiamiento: function(frm) {
		if (!frm.doc.financiamiento) {
			frm.clear_table('cuotas_detalle');
			frm.refresh_field('cuotas_detalle');
			recalculate_totals(frm);
			return;
		}

		frappe.call({
			method: 'erpnext.urbanizaciones.doctype.modificar_mora.modificar_mora.get_vencidas_cuotas',
			args: {
				financiamiento: frm.doc.financiamiento
			},
			freeze: true,
			freeze_message: __('Buscando cuotas vencidas...'),
			callback: function(r) {
				frm.clear_table('cuotas_detalle');
				if (r.message && r.message.length > 0) {
					r.message.forEach(item => {
						let row = frm.add_child('cuotas_detalle');
						row.cuota_name = item.cuota_name;
						row.numero_cuota = item.numero_cuota;
						row.fecha_vencimiento_cuota = item.fecha_vencimiento_cuota;
						row.total_cuota = item.total_cuota;
						row.dias_mora = item.dias_mora;
						row.mora_actual = item.mora_actual;
						row.mora_negociada = item.mora_negociada;
						row.descuento = 0;
					});
					frm.refresh_field('cuotas_detalle');
					recalculate_totals(frm);
				} else {
					frm.refresh_field('cuotas_detalle');
					recalculate_totals(frm);
					frappe.msgprint(__('Este financiamiento no tiene cuotas vencidas pendientes con mora.'));
				}

				// Sincronizar cliente del financiamiento
				frappe.db.get_value('Financiamientos', frm.doc.financiamiento, 'customer')
					.then(res => {
						if (res && res.message && res.message.customer) {
							frm.set_value('customer', res.message.customer);
						}
					});
			}
		});
	}
});

frappe.ui.form.on('Modificar Mora Cuota', {
	mora_negociada: function(frm, cdt, cdn) {
		let row = locals[cdt][cdn];
		if (flt(row.mora_negociada) < 0) {
			frappe.msgprint(__('La mora negociada no puede ser menor a 0.'));
			frappe.model.set_value(cdt, cdn, 'mora_negociada', 0);
		}
		recalculate_totals(frm);
	},

	cuotas_detalle_remove: function(frm) {
		recalculate_totals(frm);
	}
});
