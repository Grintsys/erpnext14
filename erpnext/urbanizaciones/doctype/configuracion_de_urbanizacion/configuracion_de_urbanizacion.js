// Copyright (c) 2025, Frappe Technologies Pvt. Ltd. and contributors
// For license information, please see license.txt

frappe.ui.form.on('Configuracion de Urbanizacion', {
	refresh: function(frm) {
		toggle_policy_fields(frm);
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

function toggle_policy_fields(frm) {
	frm.toggle_display(['permitir_vuelto_efectivo', 'politica_excedentes'], !!frm.doc.permitir_monto_mayor);
	frm.toggle_display('regla_monto_siguiente_cuota', !!frm.doc.permitir_anticipo_siguiente_cuota);
	frm.toggle_display('politica_recalculo_capital', !!frm.doc.permitir_abono_capital);
	frm.toggle_display('politica_recalculo_interes', !!frm.doc.permitir_abono_interes);
}

