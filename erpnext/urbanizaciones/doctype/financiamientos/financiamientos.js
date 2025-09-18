// Copyright (c) 2025, Frappe Technologies Pvt. Ltd. and contributors
// For license information, please see license.txt

frappe.ui.form.on('Financiamientos', {
	//refresh: function(frm) {
	onload: function(frm)
	{
		// Get a single value from a doctype and set the value into the current doctype
		// frappe.db.get_single_value('Configuracion de Urbanizacion', 'interes_anual')
		// 	.then(value => {
		// 		frm.set_value('interes_anual', value)
		// 	});

		// Get multiple value from a doctype and set the values into the current doctype
		// frappe.db.get_doc('Configuracion de Urbanizacion')
		// 	.then(config => {
		// 		frm.set_value('interes_anual', config.interes_anual);
		// 		frm.set_value('mora_diaria', config.mora_diaria);
		// 		frm.set_value('vencimiento_cuota', config.vencimiento_cuota);
		// 	});

		// Calculate capital_financiado on load if fields already have values
		calculate_capital_financiero(frm);
		calculate_cuota_estimada(frm);
		calculate_proxima_fecha(frm);
		calculate_saldo_actual(frm);
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
	},

	fecha_inicio: function(frm)
	{
		calculate_proxima_fecha(frm);
	},

	dia_vencimiento_cuota: function(frm)
	{
		calculate_proxima_fecha(frm);
	},

	capital_financiado: function(frm)
	{
		calculate_saldo_actual(frm);
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

function calculate_proxima_fecha(frm)
{
	//Todo: si ya existe el plan de pago, mostrar la fecha de vencimiento de la cuota correspondiente
	
	const fecha_inicio = frm.doc.fecha_inicio;
	const dia_vencimiento = frm.doc.dia_vencimiento_cuota;

	if (fecha_inicio && dia_vencimiento)
	{
		let fecha = frappe.datetime.str_to_obj(fecha_inicio);
		
		fecha.setMonth(fecha.getMonth() + 1);
		fecha.setDate(dia_vencimiento);

		frm.set_value('fecha_vencimiento_cuota', frappe.datetime.obj_to_str(fecha));
	}
	else
	{
		frm.set_value('fecha_vencimiento_cuota', null);
	}
}

function calculate_saldo_actual(frm)
{
	// Todo: Hacer el calculo correspondiente al capital a medida se pagan las cuotas
	frm.set_value('saldo_actual', frm.doc.capital_financiado);
}