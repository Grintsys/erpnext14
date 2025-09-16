// Copyright (c) 2025, Frappe Technologies Pvt. Ltd. and contributors
// For license information, please see license.txt

frappe.ui.form.on('Financiamientos', {
	onload: function(frm)
	{
		// Get a single value from a doctype and set the value into the current doctype
		// frappe.db.get_single_value('Configuracion de Urbanizacion', 'interes_anual')
		// 	.then(value => {
		// 		frm.set_value('interes_anual', value)
		// 	});

		// Get multiple value from a doctype and set the values into the current doctype
		frappe.db.get_doc('Configuracion de Urbanizacion')
			.then(config => {
				frm.set_value('interes_anual', config.interes_anual);
				frm.set_value('mora_diaria', config.mora_diaria);
				frm.set_value('vencimiento_cuota', config.vencimiento_cuota);
			});

		// Calculate capital_financiado on load if fields already have values
		calculate_capital_financiero(frm);
		calculate_cuota_estimada(frm);
	},

	monto_contrato: function(frm)
	{
		calculate_capital_financiero(frm);
		calculate_cuota_estimada(frm);
	},

	prima: function(frm)
	{
		calculate_capital_financiero(frm);
		calculate_cuota_estimada(frm);
	},

	interes_anual: function(frm)
	{
		calculate_cuota_estimada(frm);
	},

	plazo_meses: function(frm)
	{
		calculate_cuota_estimada(frm);
	}
});

// Function to calculate capital_financiado
function calculate_capital_financiero(frm)
{
	let monto = frm.doc.monto_contrato || 0;
	let prima = frm.doc.prima || 0;

	frm.set_value('capital_financiado', monto - prima);
}

// Function to calculate cuota_estimada
function calculate_cuota_estimada(frm)
{
	console.log("Enter the method");
	
	let interes_anual = frm.doc.interes_anual || 0;
	let capital = frm.doc.capital_financiado || 0;
	let cuotas = frm.doc.plazo_meses || 0;

	if (interes_anual > 0 && capital > 0 && cuotas > 0)
	{
		let r = (interes_anual / 100) / 12;
		let n = cuotas;
		let pv = capital;

		let cuota = (r * pv) / (1 - Math.pow(1 + r, -n));

		console.log("Cuota: " + cuota);

		frm.set_value('cuota_estimada', Math.round(cuota * 100) / 100);
	}
	else
	{
		console.log("Enter else");
		frm.set_value('cuota_estimada', 0);
	}
}