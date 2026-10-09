import frappe
from frappe.utils import today


def execute():
	today_str = today()

	# 1. Configuracion de Urbanizacion
	frappe.db.sql(
		"""
		UPDATE `tabConfiguracion de Urbanizacion`
		SET
			moneda_financiamiento = COALESCE(NULLIF(moneda_financiamiento, ''), 'USD'),
			tasa_cambio_manual = CASE WHEN tasa_cambio_manual IS NULL OR tasa_cambio_manual = 0 THEN 25.0 ELSE tasa_cambio_manual END,
			tasa_cambio_actual = CASE WHEN tasa_cambio_actual IS NULL OR tasa_cambio_actual = 0 THEN 25.0 ELSE tasa_cambio_actual END,
			fecha_ultima_tasa = COALESCE(fecha_ultima_tasa, %s)
	""",
		(today_str,),
	)

	# 2. Financiamientos
	frappe.db.sql(
		"""
		UPDATE `tabFinanciamientos`
		SET currency = COALESCE(NULLIF(currency, ''), 'USD')
		WHERE currency IS NULL OR currency = ''
	"""
	)

	# 3. Cancelar Financiamiento
	frappe.db.sql(
		"""
		UPDATE `tabCancelar Financiamiento` cf
		LEFT JOIN `tabFinanciamientos` f ON cf.financiamientos = f.name
		SET cf.currency = COALESCE(NULLIF(f.currency, ''), 'USD')
		WHERE cf.currency IS NULL OR cf.currency = ''
	"""
	)

	# 4. Modificar Mora
	frappe.db.sql(
		"""
		UPDATE `tabModificar Mora` mm
		LEFT JOIN `tabFinanciamientos` f ON mm.financiamiento = f.name
		SET mm.currency = COALESCE(NULLIF(f.currency, ''), 'USD')
		WHERE mm.currency IS NULL OR mm.currency = ''
	"""
	)

	# 5. Generar Factura
	frappe.db.sql(
		"""
		UPDATE `tabGenerar Factura` gf
		LEFT JOIN `tabFinanciamientos` f ON gf.financiamiento = f.name
		LEFT JOIN `tabPOS Profile` pos ON gf.pos_profile = pos.name
		SET
			gf.currency_financiamiento = COALESCE(NULLIF(f.currency, ''), 'USD'),
			gf.currency = COALESCE(NULLIF(pos.currency, ''), 'HNL'),
			gf.conversion_rate = CASE WHEN gf.conversion_rate IS NULL OR gf.conversion_rate = 0 THEN 1.0 ELSE gf.conversion_rate END
		WHERE gf.currency IS NULL OR gf.currency = ''
	"""
	)
