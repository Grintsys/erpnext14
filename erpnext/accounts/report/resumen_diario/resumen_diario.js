// Copyright (c) 2025, Frappe Technologies Pvt. Ltd. and contributors
// For license information, please see license.txt

frappe.query_reports["Resumen diario"] = {
  "filters": [
    {
      "fieldname": "company",
      "label": __("Empresa"),
      "fieldtype": "Link",
      "options": "Company",
      "reqd": 1,
      "default": frappe.defaults.get_user_default("Company")
    },
    {
      "fieldname": "from_date",
      "label": __("Fecha desde"),
      "fieldtype": "Date",
      "reqd": 1,
      "default": frappe.datetime.month_start()
    },
    {
      "fieldname": "to_date",
      "label": __("Fecha hasta"),
      "fieldtype": "Date",
      "reqd": 1,
      "default": frappe.datetime.month_end()
    },
    // Serie opcional: si la dejas en blanco, incluye todas
    {
      "fieldname": "prefix",
      "label": __("Serie de facturación"),
      "fieldtype": "Link",
      "options": "Prefix sales for days",
      "reqd": 0
    }
  ]
};
