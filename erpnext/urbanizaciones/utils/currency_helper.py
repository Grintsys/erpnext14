# Copyright (c) 2026, Frappe Technologies Pvt. Ltd. and contributors
# For license information, please see license.txt

import requests
import frappe
from frappe import _
from frappe.utils import today, flt, getdate, nowdate


@frappe.whitelist()
def get_daily_exchange_rate(
	from_currency=None,
	to_currency=None,
	transaction_date=None,
	company=None,
):
	"""
	Obtiene la tasa de cambio oficial vigente entre from_currency y to_currency.
	Respeta la arquitectura estándar de ERPNext utilizando el DocType 'Currency Exchange'.
	
	Jerarquía de resolución:
	1. Si from_currency == to_currency -> 1.0
	2. Registro en 'Currency Exchange' (ERPNext nativo) para la fecha o más reciente.
	3. 'erpnext.setup.utils.get_exchange_rate' estándar de ERPNext.
	4. Consulta a API de tasas de cambio con auto-registro en 'Currency Exchange'.
	5. Fallback seguro.
	"""
	if not company:
		company = frappe.defaults.get_user_default("Company") or frappe.defaults.get_global_default("company")

	company_currency = None
	if company:
		company_currency = frappe.get_cached_value("Company", company, "default_currency")
	if not company_currency:
		company_currency = frappe.db.get_single_value("Global Defaults", "default_currency") or "HNL"

	if not to_currency:
		to_currency = company_currency

	if not from_currency:
		from_currency = company_currency

	if from_currency == to_currency:
		return 1.0

	if not transaction_date:
		transaction_date = today()

	# 1. Buscar en Currency Exchange estándar de ERPNext (para la fecha o anterior más cercana)
	entries = frappe.get_all(
		"Currency Exchange",
		filters={
			"from_currency": from_currency,
			"to_currency": to_currency,
			"for_selling": 1,
			"date": ["<=", transaction_date],
		},
		fields=["exchange_rate"],
		order_by="date desc",
		limit=1,
	)
	if entries and flt(entries[0].exchange_rate) > 0:
		return flt(entries[0].exchange_rate, 4)

	# 2. Utilidad estándar de ERPNext
	try:
		from erpnext.setup.utils import get_exchange_rate
		rate = get_exchange_rate(from_currency, to_currency, transaction_date, "for_selling")
		if flt(rate) > 0:
			return flt(rate, 4)
	except Exception:
		pass

	# 3. Consulta externa de respaldo y auto-guardado en Currency Exchange
	external_rate = fetch_official_exchange_rate(from_currency, to_currency)
	if external_rate and flt(external_rate) > 0:
		try:
			save_currency_exchange_entry(from_currency, to_currency, transaction_date, external_rate)
		except Exception:
			pass
		return flt(external_rate, 4)

	return 1.0


def fetch_official_exchange_rate(from_currency, to_currency):
	"""
	Consulta el tipo de cambio oficial de mercado entre dos divisas.
	"""
	if from_currency == to_currency:
		return 1.0

	urls = [
		f"https://open.er-api.com/v6/latest/{from_currency}",
		f"https://api.exchangerate-api.com/v4/latest/{from_currency}",
	]

	for url in urls:
		try:
			resp = requests.get(url, timeout=5)
			if resp.status_code == 200:
				data = resp.json()
				rates = data.get("rates", {})
				if to_currency in rates:
					rate = flt(rates[to_currency], 4)
					if rate > 0:
						return rate
		except Exception:
			continue

	return None


def save_currency_exchange_entry(from_currency, to_currency, date_str, rate):
	"""
	Inserta o actualiza un registro en el DocType estándar 'Currency Exchange' de ERPNext.
	"""
	existing = frappe.db.get_value(
		"Currency Exchange",
		{"from_currency": from_currency, "to_currency": to_currency, "date": date_str, "for_selling": 1},
		"name",
	)
	if existing:
		frappe.db.set_value(
			"Currency Exchange",
			existing,
			{"exchange_rate": rate, "for_buying": 1, "for_selling": 1},
			update_modified=False,
		)
	else:
		ce_doc = frappe.get_doc({
			"doctype": "Currency Exchange",
			"from_currency": from_currency,
			"to_currency": to_currency,
			"date": date_str,
			"exchange_rate": rate,
			"for_buying": 1,
			"for_selling": 1,
		})
		ce_doc.flags.ignore_permissions = True
		ce_doc.insert()


@frappe.whitelist()
def update_today_exchange_rate(from_currency="USD", to_currency=None, rate=None):
	"""
	Permite a Tesorería / Administrador registrar o sincronizar inmediatamente la tasa para hoy.
	Si rate es None o <= 0, consulta la API oficial en vivo.
	"""
	frappe.only_for(["Accounts Manager", "System Manager", "Accounts User"])
	today_str = today()

	if not to_currency:
		company = frappe.defaults.get_user_default("Company") or frappe.defaults.get_global_default("company")
		to_currency = frappe.get_cached_value("Company", company, "default_currency") or "HNL"

	rate = flt(rate)
	if rate <= 0:
		rate = fetch_official_exchange_rate(from_currency, to_currency)
		if not rate or rate <= 0:
			frappe.throw(_("No se pudo obtener la tasa oficial en línea para {0} -> {1}. Ingrese el valor manualmente.").format(from_currency, to_currency))

	save_currency_exchange_entry(from_currency, to_currency, today_str, rate)
	frappe.db.commit()

	return {
		"from_currency": from_currency,
		"to_currency": to_currency,
		"date": today_str,
		"exchange_rate": rate,
		"message": _("Tasa de cambio para {0} -> {1} actualizada exitosamente a {2}").format(from_currency, to_currency, rate)
	}


def sync_daily_exchange_rate():
	"""
	Cron Job Diario (00:00 / 12:00 AM).
	Sincroniza automáticamente las tasas de cambio de las monedas utilizadas en Urbanizaciones
	directamente en el DocType estándar 'Currency Exchange' si el modo automático está habilitado.
	"""
	today_str = today()

	# Identificar configuraciones que tienen la sincronización automática habilitada
	auto_configs = frappe.get_all(
		"Configuracion de Urbanizacion",
		filters={"sincronizacion_automatica_tasa": 1},
		fields=["name", "moneda_financiamiento"],
	)

	if not auto_configs:
		frappe.logger("urbanizaciones").info(
			"Sincronización automática de tasas omitida: ninguna configuración tiene el modo automático activo."
		)
		return

	distinct_currencies = list(set([c.moneda_financiamiento for c in auto_configs if c.moneda_financiamiento]))
	company_currencies = frappe.db.sql_list(
		"SELECT DISTINCT default_currency FROM `tabCompany` WHERE default_currency IS NOT NULL AND default_currency != ''"
	)

	if not distinct_currencies:
		distinct_currencies = ["USD"]
	if not company_currencies:
		company_currencies = ["HNL"]

	for from_curr in distinct_currencies:
		for to_curr in company_currencies:
			if from_curr == to_curr:
				continue
			rate = fetch_official_exchange_rate(from_curr, to_curr)
			if rate and rate > 0:
				save_currency_exchange_entry(from_curr, to_curr, today_str, rate)
				frappe.logger("urbanizaciones").info(
					f"Currency Exchange actualizado automáticamente para {from_curr}->{to_curr} ({today_str}): {rate}"
				)
			else:
				frappe.logger("urbanizaciones").warning(
					f"No se pudo obtener tasa oficial automática para {from_curr}->{to_curr} en {today_str}"
				)

	frappe.db.commit()


@frappe.whitelist()
def populate_urbanizaciones_currency_data():
	"""
	Puebla valores por defecto de moneda en registros de Urbanizaciones.
	Idempotente y seguro para ejecutarse bajo demanda en sitios que usan el módulo.
	"""
	today_str = today()

	if frappe.db.table_exists("Configuracion de Urbanizacion"):
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

	if frappe.db.table_exists("Financiamientos"):
		frappe.db.sql(
			"""
			UPDATE `tabFinanciamientos`
			SET currency = COALESCE(NULLIF(currency, ''), 'USD')
			WHERE currency IS NULL OR currency = ''
		"""
		)

	if frappe.db.table_exists("Cancelar Financiamiento") and frappe.db.table_exists("Financiamientos"):
		frappe.db.sql(
			"""
			UPDATE `tabCancelar Financiamiento` cf
			LEFT JOIN `tabFinanciamientos` f ON cf.financiamientos = f.name
			SET cf.currency = COALESCE(NULLIF(f.currency, ''), 'USD')
			WHERE cf.currency IS NULL OR cf.currency = ''
		"""
		)

	if frappe.db.table_exists("Modificar Mora") and frappe.db.table_exists("Financiamientos"):
		frappe.db.sql(
			"""
			UPDATE `tabModificar Mora` mm
			LEFT JOIN `tabFinanciamientos` f ON mm.financiamiento = f.name
			SET mm.currency = COALESCE(NULLIF(f.currency, ''), 'USD')
			WHERE mm.currency IS NULL OR mm.currency = ''
		"""
		)

	if frappe.db.table_exists("Generar Factura") and frappe.db.table_exists("Financiamientos"):
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

	frappe.db.commit()
	return {"status": "success", "message": "Datos de moneda de Urbanizaciones actualizados correctamente."}
