frappe.query_reports["Resumen de Ventas"] = {
  "filters": [
    {
      "fieldname": "company",
      "label": __("Empresa"),
      "fieldtype": "Link",
      "options": "Company",
      "reqd": 1
    },
    {
      "fieldname": "from_date",
      "label": __("Fecha desde"),
      "fieldtype": "Date",
      "default": frappe.datetime.month_start(),
      "reqd": 1
    },
    {
      "fieldname": "to_date",
      "label": __("Fecha hasta"),
      "fieldtype": "Date",
      "default": frappe.datetime.month_end(),
      "reqd": 1
    },
    // Serie de facturación opcional: si se deja en blanco, incluye todas.
    {
      "fieldname": "prefix",
      "label": __("Serie de facturación"),
      "fieldtype": "Link",
      "options": "Prefix sales for days",
      "reqd": 0
    }
  ]
};
