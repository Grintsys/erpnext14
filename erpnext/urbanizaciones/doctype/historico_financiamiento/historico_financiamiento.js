frappe.ui.form.on("Historico Financiamiento", {
	setup: function(frm) {
		// Filtrar activos disponibles o reservados para la urbanización seleccionada en cabecera
		frm.set_query('activos', function () {
			return {
				query: 'erpnext.urbanizaciones.doctype.financiamientos.financiamientos.activo_disponible_query',
				filters: {
					urbanizaciones: frm.doc.urbanizaciones || '__NONE__',
					current_doc: frm.doc.name || ''
				}
			};
		});

		frm.set_query('centro_costo', function () {
			let filters = {
				is_group: 0
			};
			if (frm.doc.company) {
				filters.company = frm.doc.company;
			}
			return {
				filters: filters
			};
		});
	},

	onload: function(frm) {
		if (frm.is_new() && !frm.doc.company) {
			let default_company = frappe.defaults.get_user_default('Company') || frappe.defaults.get_global_default('company');
			if (default_company) {
				frm.set_value('company', default_company);
			}
		}
	},

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
				let recalcular_fn = function() {
					frappe.call({
						method: "erpnext.urbanizaciones.doctype.historico_financiamiento.historico_financiamiento.recalcular_cadena_saldos",
						args: {
							docname: frm.doc.name,
							auto_ajustar_residuo: 1
						},
						freeze: true,
						freeze_message: __("Recalculando saldos y conciliando residuo final..."),
						callback: function(r) {
							if (r.message && r.message.success) {
								let msg = __("Saldos recalculados en cadena correctamente.");
								if (r.message.residuo_absorbido) {
									msg += __(" Se absorbió residuo de L {0} en la última cuota.", [r.message.residuo_absorbido]);
								}
								frappe.show_alert({ message: msg, indicator: "green" });
								frm.reload_doc();
							}
						}
					});
				};

				frm.add_custom_button(__("Recalcular Saldos y Conciliar"), recalcular_fn);
				frm.add_custom_button(__("Recalcular Saldos en Cadena"), recalcular_fn, __("Acciones"));

				frm.add_custom_button(__("Marcar Cuotas 1 a N Pagadas"), function() {
					frappe.prompt(
						[
							{
								label: __("Marcar como Pagadas hasta la cuota número"),
								fieldname: "hasta_cuota",
								fieldtype: "Int",
								reqd: 1,
								default: frm.doc.cuotas_pagadas_count || 11
							}
						],
						function(vals) {
							let max_c = vals.hasta_cuota;
							(frm.doc.cuotas || []).forEach(function(row) {
								if (row.numero_cuota <= max_c) {
									if (row.status === "Pendiente") {
										row.status = "Pagado";
									}
								} else {
									if (row.status === "Pagado") {
										row.status = "Pendiente";
									}
								}
							});
							recalcular_saldos_cliente(frm);
							frm.save();
						},
						__("Marcar Cuotas Históricas Pagadas"),
						__("Aplicar")
					);
				}, __("Acciones"));

				frm.add_custom_button(__("Reamortizar Cuotas Pendientes"), function() {
					frappe.confirm(
						__("¿Desea reamortizar automáticamente las cuotas pendientes con la cuota fija a partir del saldo actual post-abonos?"),
						function() {
							frappe.call({
								method: "erpnext.urbanizaciones.doctype.historico_financiamiento.historico_financiamiento.reamortizar_cuotas_pendientes",
								args: { docname: frm.doc.name },
								freeze: true,
								freeze_message: __("Reamortizando cuotas pendientes..."),
								callback: function(r) {
									if (r.message && r.message.success) {
										frappe.show_alert({
											message: __("Cuotas pendientes reamortizadas correctamente."),
											indicator: "green"
										});
										frm.reload_doc();
									}
								}
							});
						}
					);
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

	company: function(frm) {
		if (frm.doc.centro_costo && frm.doc.company) {
			frappe.db.get_value('Cost Center', frm.doc.centro_costo, 'company', function(r) {
				if (r && r.company && r.company !== frm.doc.company) {
					frm.set_value('centro_costo', '');
				}
			});
		}
	},

	urbanizaciones: function(frm) {
		if (frm.doc.urbanizaciones) {
			if (!frm.doc.centro_costo) {
				frappe.db.get_value('Urbanizaciones', frm.doc.urbanizaciones, 'cost_center', function(r) {
					if (r && r.cost_center) {
						frm.set_value('centro_costo', r.cost_center);
					}
				});
			}
		}
		if (frm.doc.activos) {
			frappe.db.get_value('Activos', frm.doc.activos, 'urbanizaciones', function(r) {
				if (r && r.urbanizaciones !== frm.doc.urbanizaciones) {
					frm.set_value('activos', '');
				}
			});
		}
	},

	activos: function(frm) {
		if (frm.doc.activos) {
			frappe.db.get_value('Activos', frm.doc.activos, ['centro_de_costo', 'precio', 'status', 'descripcion_lote', 'urbanizaciones'], function(r) {
				if (r) {
					if (r.urbanizaciones && !frm.doc.urbanizaciones) {
						frm.set_value('urbanizaciones', r.urbanizaciones);
					}
					if (r.centro_de_costo) {
						frm.set_value('centro_costo', r.centro_de_costo);
					}
					if (r.precio && (!frm.doc.monto_contrato || frm.doc.monto_contrato === 0)) {
						frm.set_value('monto_contrato', r.precio);
					}
					// Validar estado
					if (r.status && r.status !== 'Disponible' && r.status !== 'Reservado' && frm.is_new()) {
						frappe.msgprint({
							title: __('Activo no Disponible'),
							indicator: 'orange',
							message: __('Advertencia: El activo <b>{0}</b> tiene estado <b>{1}</b>. Asegúrese de que esté disponible para venta.', [frm.doc.activos, r.status])
						});
					}
				}
			});
		}
	},

	configuracion_financiamiento: function(frm) {
		if (frm.doc.configuracion_financiamiento) {
			frappe.db.get_value('Configuracion de Urbanizacion', frm.doc.configuracion_financiamiento,
				['moneda_financiamiento', 'interes_anual', 'vencimiento_cuota', 'mora_diaria'],
				function(r) {
					if (r) {
						if (r.moneda_financiamiento) {
							frm.set_value('currency', r.moneda_financiamiento);
						}
						if (!frm.doc.company) {
							let default_company = frappe.defaults.get_user_default('Company') || frappe.defaults.get_global_default('company');
							if (default_company) {
								frm.set_value('company', default_company);
							}
						}
						if (r.interes_anual !== undefined && (!frm.doc.interes_anual || frm.doc.interes_anual === 0)) {
							frm.set_value('interes_anual', r.interes_anual);
						}
						if (r.vencimiento_cuota && (!frm.doc.dia_vencimiento_cuota || frm.doc.dia_vencimiento_cuota === 0)) {
							frm.set_value('dia_vencimiento_cuota', r.vencimiento_cuota);
						}
						if (r.mora_diaria !== undefined && (!frm.doc.mora_diaria || frm.doc.mora_diaria === 0)) {
							frm.set_value('mora_diaria', r.mora_diaria);
						}
					}
				}
			);
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
		recalcular_saldos_cliente(frm);
	},

	intereses: function(frm, cdt, cdn) {
		let row = locals[cdt][cdn];
		frappe.model.set_value(cdt, cdn, "total_cuota", flt(flt(row.capital) + flt(row.intereses), 2));
		recalcular_saldos_cliente(frm);
	},

	total_cuota: function(frm, cdt, cdn) {
		let row = locals[cdt][cdn];
		let int_val = flt(row.intereses);
		let cuota_val = flt(row.total_cuota);
		let nuevo_cap = flt(cuota_val - int_val, 2);
		if (nuevo_cap >= 0 && Math.abs(nuevo_cap - flt(row.capital)) > 0.009) {
			frappe.model.set_value(cdt, cdn, "capital", nuevo_cap);
		} else {
			recalcular_saldos_cliente(frm);
		}
	},

	status: function(frm, cdt, cdn) {
		actualizar_resumen(frm);
	},

	abono_capital: function(frm, cdt, cdn) {
		actualizar_resumen(frm);
	}
});

function recalcular_saldos_cliente(frm) {
	let prev_balance = flt(frm.doc.capital_financiado);
	(frm.doc.cuotas || []).forEach(function(row) {
		row.saldo_anterior = prev_balance;
		let cap = flt(row.capital);
		let nuevo_saldo = prev_balance - cap;
		if (nuevo_saldo < 0) nuevo_saldo = 0.0;
		row.saldo = flt(nuevo_saldo, 2);
		prev_balance = row.saldo;
	});
	if (frm.doc.cuotas && frm.doc.cuotas.length > 0) {
		frm.doc.cuotas[frm.doc.cuotas.length - 1].saldo = 0.0;
	}
	frm.refresh_field("cuotas");
	actualizar_resumen(frm);
}

function actualizar_resumen(frm) {
	let total_cap = 0.0;
	let pagadas = 0;
	let pendiente = 0.0;

	(frm.doc.cuotas || []).forEach(function(row) {
		total_cap += flt(row.capital);
		let is_paid = row.status === "Pagado" || row.status === "Anticipada" || row.status === "Abono a capital" || row.abono_capital;
		if (is_paid) {
			pagadas++;
		} else if (row.status === "Pendiente") {
			pendiente += flt(row.total_cuota);
		}
	});

	frm.set_value("total_capital_cuotas", flt(total_cap, 2));
	frm.set_value("cuotas_pagadas_count", pagadas);
	frm.set_value("saldo_actual", flt(pendiente, 2));
}
