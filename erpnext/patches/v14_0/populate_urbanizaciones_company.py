import frappe


def execute():
	default_company = frappe.defaults.get_user_default("Company") or frappe.db.get_single_value(
		"Global Defaults", "default_company"
	)
	if not default_company:
		companies = frappe.get_all("Company", limit=1, pluck="name")
		if companies:
			default_company = companies[0]

	# 1. Update Financiamientos from Cost Center or Urbanizacion or default
	frappe.db.sql(
		"""
		UPDATE `tabFinanciamientos` f
		LEFT JOIN `tabCost Center` cc ON f.centro_costo = cc.name
		LEFT JOIN `tabUrbanizaciones` u ON f.urbanizaciones = u.name
		LEFT JOIN `tabCost Center` ucc ON u.cost_center = ucc.name
		SET f.company = COALESCE(NULLIF(cc.company, ''), NULLIF(ucc.company, ''), %s)
		WHERE f.company IS NULL OR f.company = ''
	""",
		(default_company,),
	)

	# 2. Update Cancelar Financiamiento from Financiamientos or default
	frappe.db.sql(
		"""
		UPDATE `tabCancelar Financiamiento` cf
		LEFT JOIN `tabFinanciamientos` f ON cf.financiamientos = f.name
		SET cf.company = COALESCE(NULLIF(f.company, ''), %s)
		WHERE cf.company IS NULL OR cf.company = ''
	""",
		(default_company,),
	)

	# 3. Update Modificar Mora from Financiamientos or default
	frappe.db.sql(
		"""
		UPDATE `tabModificar Mora` mm
		LEFT JOIN `tabFinanciamientos` f ON mm.financiamiento = f.name
		SET mm.company = COALESCE(NULLIF(f.company, ''), %s)
		WHERE mm.company IS NULL OR mm.company = ''
	""",
		(default_company,),
	)

	# 4. Update Generar Factura from Financiamientos, POS Profile, Sales Invoice, or default
	frappe.db.sql(
		"""
		UPDATE `tabGenerar Factura` gf
		LEFT JOIN `tabFinanciamientos` f ON gf.financiamiento = f.name
		LEFT JOIN `tabPOS Profile` pos ON gf.pos_profile = pos.name
		LEFT JOIN `tabSales Invoice` si ON gf.sales_invoice = si.name
		SET gf.company = COALESCE(NULLIF(f.company, ''), NULLIF(pos.company, ''), NULLIF(si.company, ''), %s)
		WHERE gf.company IS NULL OR gf.company = ''
	""",
		(default_company,),
	)

	# 5. Update Pago de cuota from Financiamientos or default
	frappe.db.sql(
		"""
		UPDATE `tabPago de cuota` pc
		LEFT JOIN `tabFinanciamientos` f ON pc.financiamiento = f.name
		SET pc.company = COALESCE(NULLIF(f.company, ''), %s)
		WHERE pc.company IS NULL OR pc.company = ''
	""",
		(default_company,),
	)
