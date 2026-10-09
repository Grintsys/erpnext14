// Copyright (c) 2025, Frappe Technologies Pvt. Ltd. and contributors
// For license information, please see license.txt

frappe.ui.form.on('Configuracion de Urbanizacion', {
	onload: function(frm) {
		if (frm.is_new() && !frm.doc.moneda_financiamiento) {
			set_default_currency_from_company(frm);
		}
	},
	refresh: function(frm) {
		toggle_policy_fields(frm);
		if (!frm.is_new()) {
			// Acciones de gestión de divisas
			frm.add_custom_button(__('Actualizar Tasa de Hoy'), function() {
				open_exchange_rate_dialog(frm);
			}, __('Acciones'));

			frm.add_custom_button(__('Ver Historial de Tasas'), function() {
				frappe.set_route('List', 'Currency Exchange');
			}, __('Acciones'));
		}
	},
	company: function(frm) {
		if (frm.doc.company && (!frm.doc.moneda_financiamiento || frm.is_new())) {
			set_default_currency_from_company(frm);
		}
	},
	permitir_monto_mayor: function(frm) {
		toggle_policy_fields(frm);
	},
	permitir_anticipo_siguiente_cuota: function(frm) {
		toggle_policy_fields(frm);
	},
	permitir_abono_capital: function(frm) {
		toggle_policy_fields(frm);
	},
	permitir_abono_interes: function(frm) {
		toggle_policy_fields(frm);
	}
});

function set_default_currency_from_company(frm) {
	let company = frm.doc.company || frappe.defaults.get_user_default('Company') || frappe.defaults.get_global_default('company');
	if (company) {
		frappe.db.get_value('Company', company, 'default_currency', function(r) {
			if (r && r.default_currency) {
				frm.set_value('moneda_financiamiento', r.default_currency);
			}
		});
	}
}

function open_exchange_rate_dialog(frm) {
	let from_curr = frm.doc.moneda_financiamiento || 'USD';
	let company = frm.doc.company || frappe.defaults.get_user_default('Company');
	
	frappe.db.get_value('Company', company, 'default_currency', function(r) {
		let to_curr = (r && r.default_currency) ? r.default_currency : 'HNL';

		let d = new frappe.ui.Dialog({
			title: __('Gestión de Tasa de Cambio ({0} -> {1})', [from_curr, to_curr]),
			fields: [
				{
					fieldname: 'help_html',
					fieldtype: 'HTML',
					options: `<div class="text-muted" style="margin-bottom: 15px;">
						Puede ingresar manualmente la tasa del día o consultar en vivo la tasa oficial de mercado para guardarla directamente en <b>Currency Exchange</b>.
					</div>`
				},
				{
					label: __('Moneda Origen'),
					fieldname: 'from_currency',
					fieldtype: 'Link',
					options: 'Currency',
					default: from_curr,
					read_only: 1
				},
				{
					label: __('Moneda Destino (Local)'),
					fieldname: 'to_currency',
					fieldtype: 'Link',
					options: 'Currency',
					default: to_curr,
					read_only: 1
				},
				{
					label: __('Tasa de Cambio Manual'),
					fieldname: 'manual_rate',
					fieldtype: 'Float',
					precision: 4,
					description: __('Deje en blanco para sincronizar automáticamente en línea')
				}
			],
			primary_action_label: __('Guardar Tasa en Currency Exchange'),
			primary_action: function(values) {
				d.hide();
				frappe.call({
					method: 'erpnext.urbanizaciones.utils.currency_helper.update_today_exchange_rate',
					args: {
						from_currency: values.from_currency,
						to_currency: values.to_currency,
						rate: values.manual_rate || 0
					},
					freeze: true,
					freeze_message: __('Guardando tasa de cambio oficial...'),
					callback: function(res) {
						if (res.message) {
							frappe.show_alert({
								message: res.message.message || __('Tasa de cambio actualizada correctamente.'),
								indicator: 'green'
							});
						}
					}
				});
			}
		});

		d.show();
	});
}

function toggle_policy_fields(frm) {
	frm.toggle_display(['permitir_vuelto_efectivo', 'politica_excedentes'], !!frm.doc.permitir_monto_mayor);
	frm.toggle_display('regla_monto_siguiente_cuota', !!frm.doc.permitir_anticipo_siguiente_cuota);
	frm.toggle_display('politica_recalculo_capital', !!frm.doc.permitir_abono_capital);
	frm.toggle_display('politica_recalculo_interes', !!frm.doc.permitir_abono_interes);
}
