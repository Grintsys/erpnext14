frappe.ui.form.on("Historico Financiamiento", {
	refresh: function(frm) {
		if (!frm.is_new() && frm.doc.status === "Borrador") {
			frm.add_custom_button(__("Generar Cuotas Base"), function() {
				frappe.confirm(
					__("¿Desea generar el plan de cuotas base según el plazo y capital? (Si ya ingresó datos, se reemplazarán)"),
					function() {
						frappe.call({
							method: "erpnext.urbanizaciones.doctype.historico_financiamiento.historico_financiamiento.generar_cuotas",
							args: { docname: frm.doc.name },
							freeze: true,
							freeze_message: __("Generando tabla de amortización base..."),
							callback: function(r) {
								if (r.message && r.message.success) {
									frappe.show_alert({
										message: __("Se generaron {0} cuotas base correctamente. Ahora puede ajustar los valores idéntico a su Excel.", [r.message.rows_created]),
										indicator: "green"
									});
									frm.reload_doc();
								}
							}
						});
					}
				);
			}, __("Acciones"));

			if (frm.doc.cuotas && frm.doc.cuotas.length > 0) {
				frm.add_custom_button(__("Recalcular Saldos en Cadena"), function() {
					let prev_balance = flt(frm.doc.capital_financiado);
					(frm.doc.cuotas || []).forEach(function(row) {
						frappe.model.set_value(row.doctype, row.name, "saldo_anterior", prev_balance);
						let cap = flt(row.capital);
						let nuevo_saldo = prev_balance - cap;
						if (nuevo_saldo < 0) nuevo_saldo = 0.0;
						frappe.model.set_value(row.doctype, row.name, "saldo", nuevo_saldo);
						prev_balance = nuevo_saldo;
					});
					frm.refresh_field("cuotas");
					frappe.show_alert({ message: __("Saldos recalculados en cadena."), indicator: "blue" });
				}, __("Acciones"));

				frm.add_custom_button(__("Validar y Crear Financiamiento"), function() {
					frappe.confirm(
						__("¿Está seguro de validar este histórico y crear el Financiamiento real activo en el sistema?"),
						function() {
							frappe.call({
								method: "erpnext.urbanizaciones.doctype.historico_financiamiento.historico_financiamiento.validar_y_crear_financiamiento",
								args: {
									docname: frm.doc.name,
									auto_ajustar_residuo: 1
								},
								freeze: true,
								freeze_message: __("Validando y creando Financiamiento oficial..."),
								callback: function(r) {
									if (r.message && r.message.success) {
										frappe.msgprint({
											title: __("Migración Exitosa"),
											message: __(
												"Se ha creado exitosamente el financiamiento oficial: <br><br>" +
												"<b><a href='/app/financiamientos/{0}' target='_blank'>{0}</a></b><br><br>" +
												"- Cuotas Pagadas Históricas: <b>{1}</b><br>" +
												"- Saldo Pendiente Actual: <b>L {2}</b><br>" +
												"- Próximo Vencimiento: <b>{3}</b>",
												[r.message.financiamiento, r.message.cuotas_pagadas, r.message.saldo_actual, r.message.proximo_vencimiento || "N/A"]
											),
											indicator: "green"
										});
										frm.reload_doc();
									}
								}
							});
						}
					);
				}).addClass("btn-primary");
			}
		}

		if (frm.doc.status === "Migrado" && frm.doc.financiamiento_creado) {
			frm.add_custom_button(__("Ver Financiamiento Creado"), function() {
				frappe.set_route("Form", "Financiamientos", frm.doc.financiamiento_creado);
			}).addClass("btn-primary");
		}
	},

	monto_contrato: function(frm) {
		calcular_capital_financiado(frm);
	},

	prima: function(frm) {
		calcular_capital_financiado(frm);
	}
});

function calcular_capital_financiado(frm) {
	let total = flt(frm.doc.monto_contrato);
	let prima = flt(frm.doc.prima);
	if (total > 0 && prima >= 0) {
		frm.set_value("capital_financiado", flt(total - prima, 2));
	}
}

frappe.ui.form.on("Historico Cuota Financiamiento", {
	capital: function(frm, cdt, cdn) {
		let row = locals[cdt][cdn];
		frappe.model.set_value(cdt, cdn, "total_cuota", flt(flt(row.capital) + flt(row.intereses), 2));
		actualizar_resumen(frm);
	},

	intereses: function(frm, cdt, cdn) {
		let row = locals[cdt][cdn];
		frappe.model.set_value(cdt, cdn, "total_cuota", flt(flt(row.capital) + flt(row.intereses), 2));
		actualizar_resumen(frm);
	},

	status: function(frm, cdt, cdn) {
		actualizar_resumen(frm);
	}
});

function actualizar_resumen(frm) {
	let total_cap = 0.0;
	let pagadas = 0;
	let pendiente = 0.0;

	(frm.doc.cuotas || []).forEach(function(row) {
		total_cap += flt(row.capital);
		if (row.status === "Pagado" || row.status === "Anticipada") {
			pagadas++;
		} else if (row.status === "Pendiente") {
			pendiente += flt(row.total_cuota);
		}
	});

	frm.set_value("total_capital_cuotas", flt(total_cap, 2));
	frm.set_value("cuotas_pagadas_count", pagadas);
	frm.set_value("saldo_actual", flt(pendiente, 2));
}
