// Copyright (c) 2026, Frappe Technologies Pvt. Ltd. and contributors
// For license information, please see license.txt

frappe.query_reports["Reporte de Ventas Exoneradas SAR"] = {
    "filters": [
        {
            "fieldname": "company",
            "label": __("Empresa"),
            "fieldtype": "Link",
            "options": "Company",
            "default": frappe.defaults.get_user_default("Company"),
            "reqd": 1
        },
        {
            "fieldname": "from_date",
            "label": __("Desde Fecha"),
            "fieldtype": "Date",
            "default": frappe.datetime.month_start(),
            "reqd": 1
        },
        {
            "fieldname": "to_date",
            "label": __("Hasta Fecha"),
            "fieldtype": "Date",
            "default": frappe.datetime.now_date(),
            "reqd": 1
        },
        {
            "fieldname": "customer",
            "label": __("Cliente"),
            "fieldtype": "Link",
            "options": "Customer"
        },
        {
            "fieldname": "custom_subtipo_exonerado",
            "label": __("Subtipo de Exoneración"),
            "fieldtype": "Select",
            "options": "\nConstancia SAR / SAG / SEFIN\nDiplomático / Misión Internacional\nDecreto / Ley Especial"
        }
    ]
};
