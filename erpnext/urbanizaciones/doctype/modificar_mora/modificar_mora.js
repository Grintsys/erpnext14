// Copyright (c) 2025, Frappe Technologies Pvt. Ltd. and contributors
// For license information, please see license.txt

frappe.ui.form.on('Modificar Mora', {
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

	// handler al cambiar el link 'financiamiento'
    financiamiento: function(frm) {
        if (!frm.doc.financiamiento) return;

        // traer el documento relacionado
        frappe.db.get_doc('Financiamientos', frm.doc.financiamiento)
            .then(fin => {
                // ejemplo: si quieres copiar campos simples del financiamiento al form
                // (ajusta los nombres de campo según existan en tu doctype Modificar Mora)
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
                    const mora = parseFloat(c.mora || 0);
                    return (status === 'pendiente' || status === 'refinanciado' || status === 'refinanciado'.toLowerCase() || status === 'pendiente'.toLowerCase()) && (total_cuota > 0);
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

                // si tu doctype Modificar Mora tiene campos para guardar la cuota encontrada, setéalos
                // Ejemplo: campos 'numero_cuota', 'fecha_vencimiento', 'saldo_cuota'
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
