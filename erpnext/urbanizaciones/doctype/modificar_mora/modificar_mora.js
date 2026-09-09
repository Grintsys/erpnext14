// Copyright (c) 2025, Frappe Technologies Pvt. Ltd. and contributors
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

frappe.ui.form.on('Modificar Mora', {
	onload: function(frm) {
		setup_financiamiento_query(frm);
	},

	refresh: function(frm) {
		setup_financiamiento_query(frm);
	},

	customer: function(frm) {
		// Al cambiar el cliente, si hay un financiamiento ya seleccionado,
		// verificar si corresponde al cliente seleccionado; si no, limpiarlo.
		if (frm.doc.financiamiento) {
			frappe.db.get_value('Financiamientos', frm.doc.financiamiento, 'customer')
				.then(r => {
					if (r && r.message && r.message.customer !== frm.doc.customer) {
						frm.set_value('financiamiento', null);
						frm.set_value('numero_cuota', null);
						frm.set_value('fecha_vencimiento_cuota', null);
						frm.set_value('total_cuota', 0);
						frm.set_value('mora', 0);
						frm.set_value('mora_negociada', 0);
					}
				});
		}
	},

	// handler al cambiar el link 'financiamiento'
	financiamiento: function(frm) {
		if (!frm.doc.financiamiento) {
			frm.set_value('numero_cuota', null);
			frm.set_value('fecha_vencimiento_cuota', null);
			frm.set_value('total_cuota', 0);
			frm.set_value('mora', 0);
			frm.set_value('mora_negociada', 0);
			return;
		}

		// traer el documento relacionado
		frappe.db.get_doc('Financiamientos', frm.doc.financiamiento)
			.then(fin => {
				if (fin && fin.customer && frm.doc.customer !== fin.customer) {
					frm.set_value('customer', fin.customer).catch(() => {});
				}

				if (fin && fin.tipo_financiamiento) {
					frm.set_value('tipo_financiamiento', fin.tipo_financiamiento).catch(() => {});
				}
				if (fin && fin.valor_total) {
					frm.set_value('monto_financiamiento', fin.valor_total).catch(() => {});
				}

				// buscar cuota pendiente más antigua en la tabla 'cuotas' del financiamiento
				const cuotas = fin.cuotas || [];
				const pendientes = cuotas.filter(c => {
					const status = (c.status || '').toString().toLowerCase();
					const total_cuota = parseFloat(c.total_cuota || 0);
					return (status === 'pendiente' || status === 'refinanciado') && (total_cuota > 0);
				});

				if (!pendientes.length) {
					frappe.msgprint(__('No se encontraron cuotas pendientes para este financiamiento.'));
					return;
				}

				pendientes.sort((a, b) => {
					const da = a.fecha_vencimiento_cuota ? new Date(a.fecha_vencimiento_cuota) : new Date(0);
					const dbt = b.fecha_vencimiento_cuota ? new Date(b.fecha_vencimiento_cuota) : new Date(0);
					return da - dbt;
				});

				const cuota = pendientes[0];

				frm.set_value('numero_cuota', cuota.numero_cuota).catch(() => {});
				frm.set_value('fecha_vencimiento_cuota', cuota.fecha_vencimiento_cuota).catch(() => {});
				frm.set_value('total_cuota', cuota.total_cuota).catch(() => {});
				frm.set_value('mora', cuota.mora).catch(() => {});
				frm.set_value('mora_negociada', cuota.mora).catch(() => {});

			})
			.catch(err => {
				frappe.msgprint({ title: __('Error'), message: __('No se pudo obtener el financiamiento:') + (err && err.message ? '<br>' + err.message : '') });
			});
	}
});
