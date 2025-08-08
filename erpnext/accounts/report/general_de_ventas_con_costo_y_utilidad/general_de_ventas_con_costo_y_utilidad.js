// Copyright (c) 2025, Frappe Technologies Pvt. Ltd. and contributors
// For license information, please see license.txt
/* eslint-disable */

frappe.query_reports["General de ventas con costo y utilidad"] = {
	"filters": [
		{
			fieldname:"company",
			label: __("Compañia"),
			fieldtype: "Link",
			options: "Company",
			reqd: 1
		},
		{
			fieldname: "from_date",
			label: __("Desde"),
			fieldtype: "Date",
			default: frappe.datetime.add_months(frappe.datetime.get_today(), -1),
			reqd: 1
		},
		{
			fieldname:"to_date",
			label: __("Hasta"),
			fieldtype: "Date",
			default: frappe.datetime.get_today(),
			reqd: 1
		},
		{
			fieldname: "from_time",
			label: __("Hora inicial"),
			fieldtype: "Time",
			default: "00:00:00"
		},
		{
			fieldname: "to_time",
			label: __("Hora final"),
			fieldtype: "Time",
			default: "23:59:59"
		}
	]
};
