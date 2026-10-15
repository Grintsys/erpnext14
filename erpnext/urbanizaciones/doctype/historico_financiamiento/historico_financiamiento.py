import calendar
import json
from decimal import Decimal, getcontext, ROUND_HALF_UP

import frappe
from frappe import _
from frappe.model.document import Document
from frappe.utils import add_months, flt, getdate


class HistoricoFinanciamiento(Document):
	def validate(self):
		if not self.company:
			self.company = (
				frappe.defaults.get_user_default("Company")
				or frappe.db.get_single_value("Global Defaults", "default_company")
			)
		if not self.currency and self.company:
			self.currency = frappe.get_cached_value("Company", self.company, "default_currency") or "HNL"

		if self.monto_contrato and self.prima is not None:
			# Si el usuario no especificó manualmente capital_financiado, calcularlo
			if not self.capital_financiado or self.capital_financiado == 0:
				self.capital_financiado = flt(flt(self.monto_contrato) - flt(self.prima), 2)

		self.recalcular_totales_internos()

	def recalcular_totales_internos(self):
		cuotas = self.get("cuotas") or []
		total_cap = 0.0
		total_saldo_pend = 0.0
		pagadas = 0

		for c in cuotas:
			total_cap += flt(c.capital)
			is_paid = c.status in ("Pagado", "Anticipada", "Abono a capital") or getattr(c, "abono_capital", 0)
			if is_paid:
				pagadas += 1
			elif c.status == "Pendiente":
				total_saldo_pend += flt(c.total_cuota)

		self.total_capital_cuotas = flt(total_cap, 2)
		self.cuotas_pagadas_count = pagadas
		self.saldo_actual = flt(total_saldo_pend, 2)

		if cuotas:
			self.total_financiado = flt(sum(flt(c.total_cuota) for c in cuotas) + flt(self.prima), 2)


@frappe.whitelist()
def generar_cuotas(docname):
	"""
	Genera la tabla base de amortización (método francés estándar con Decimal)
	en el Historico Financiamiento para que el usuario pueda ver y modificar
	cualquier celda (capital, saldo, abonos o estado) idéntico a su archivo Excel.
	"""
	doc = frappe.get_doc("Historico Financiamiento", docname)

	if doc.status == "Migrado":
		frappe.throw(_("Este histórico ya fue migrado al financiamiento {0} y está bloqueado.").format(doc.financiamiento_creado))

	plazo = int(doc.plazo_meses or 0)
	if plazo <= 0:
		frappe.throw(_("Debe especificar un plazo en meses mayor a 0."))

	capital_total = Decimal(str(doc.capital_financiado or 0))
	if capital_total <= 0:
		frappe.throw(_("El capital financiado debe ser mayor a 0."))

	doc.set("cuotas", [])

	fecha_inicio = doc.fecha_inicio
	dia_venc = int(doc.dia_vencimiento_cuota or 5)
	annual_interest = Decimal(str(doc.interes_anual or 0))

	getcontext().prec = 28
	CENT = Decimal("0.01")

	r = (annual_interest / Decimal("100")) / Decimal("12") if annual_interest != 0 else Decimal("0")

	if r == 0:
		monthly_payment = (capital_total / plazo).quantize(CENT, rounding=ROUND_HALF_UP)
	else:
		monthly_payment = (
			r * capital_total / (Decimal("1") - (Decimal("1") + r) ** (Decimal(-plazo)))
		).quantize(CENT, rounding=ROUND_HALF_UP)

	doc.cuota_estimada = float(monthly_payment)

	balance = capital_total

	for i in range(1, plazo + 1):
		interest = (balance * r).quantize(CENT, rounding=ROUND_HALF_UP)
		principal = (monthly_payment - interest).quantize(CENT, rounding=ROUND_HALF_UP)

		if i == plazo:
			principal = balance
			this_payment = (principal + interest).quantize(CENT, rounding=ROUND_HALF_UP)
		else:
			this_payment = monthly_payment

		prev_balance = balance
		balance = (balance - principal).quantize(CENT, rounding=ROUND_HALF_UP)

		if fecha_inicio:
			base = getdate(fecha_inicio)
			venc = add_months(base, i)
			last_day = calendar.monthrange(venc.year, venc.month)[1]
			venc = venc.replace(day=min(dia_venc, last_day))
			fecha_venc = venc
		else:
			fecha_venc = None

		doc.append(
			"cuotas",
			{
				"doctype": "Historico Cuota Financiamiento",
				"numero_cuota": i,
				"fecha_vencimiento_cuota": fecha_venc,
				"saldo_anterior": float(prev_balance),
				"capital": float(principal),
				"intereses": float(interest),
				"total_cuota": float(this_payment),
				"saldo": float(balance),
				"status": "Pendiente",
				"mora": 0.0,
			},
		)

	doc.save(ignore_permissions=True)

	return {
		"success": True,
		"rows_created": plazo,
		"cuota_estimada": doc.cuota_estimada,
		"saldo_actual": doc.saldo_actual,
	}


@frappe.whitelist()
def recalcular_cadena_saldos(docname, auto_ajustar_residuo=1):
	"""
	Recalcula la corrida completa de saldos (saldo_anterior y saldo) a lo largo
	de toda la tabla a partir del capital financiado y los capitales ingresados.
	- Si una cuota fue modificada con abonos o capitales atípicos, recalcula
	  la cascada hacia abajo.
	- Si auto_ajustar_residuo=1 y existe un descuadre menor (<= L 100), ajusta
	  la última cuota para absorber el residuo y garantizar saldo final exacto en 0.00.
	- Persiste los cambios en la base de datos y recalcula los totales.
	"""
	doc = frappe.get_doc("Historico Financiamiento", docname)

	if doc.status == "Migrado":
		frappe.throw(_("Este histórico ya fue migrado a {0} y no puede modificarse.").format(doc.financiamiento_creado))

	if not doc.cuotas:
		frappe.throw(_("No hay cuotas para recalcular."))

	getcontext().prec = 28
	CENT = Decimal("0.01")

	prev_balance = Decimal(str(doc.capital_financiado or 0)).quantize(CENT, rounding=ROUND_HALF_UP)

	for c in doc.cuotas:
		c.saldo_anterior = float(prev_balance)
		cap = Decimal(str(c.capital or 0)).quantize(CENT, rounding=ROUND_HALF_UP)
		nuevo_saldo = (prev_balance - cap).quantize(CENT, rounding=ROUND_HALF_UP)
		if nuevo_saldo < Decimal("0.00"):
			nuevo_saldo = Decimal("0.00")
		c.saldo = float(nuevo_saldo)
		prev_balance = nuevo_saldo

	# Validar diferencia con el capital financiado
	capital_esperado = Decimal(str(doc.capital_financiado or 0)).quantize(CENT, rounding=ROUND_HALF_UP)
	total_cap_cuotas = sum(Decimal(str(c.capital or 0)) for c in doc.cuotas).quantize(CENT, rounding=ROUND_HALF_UP)
	diff_capital = (total_cap_cuotas - capital_esperado).quantize(CENT, rounding=ROUND_HALF_UP)

	residuo_absorbido = 0.0
	if abs(diff_capital) > Decimal("0.00"):
		if int(auto_ajustar_residuo) and abs(diff_capital) <= Decimal("100.00"):
			last_row = doc.cuotas[-1]
			nuevo_cap_last = (Decimal(str(last_row.capital or 0)) - diff_capital).quantize(CENT, rounding=ROUND_HALF_UP)
			last_row.capital = float(nuevo_cap_last)
			last_row.total_cuota = float((nuevo_cap_last + Decimal(str(last_row.intereses or 0))).quantize(CENT, rounding=ROUND_HALF_UP))
			last_row.saldo = 0.0
			residuo_absorbido = float(diff_capital)
		else:
			frappe.msgprint(
				_(
					"Aviso: La suma de capitales de las cuotas ({0}) difiere del capital financiado ({1}) por {2}."
				).format(float(total_cap_cuotas), float(capital_esperado), float(diff_capital)),
				indicator="orange"
			)

	if doc.cuotas:
		doc.cuotas[-1].saldo = 0.0

	doc.recalcular_totales_internos()
	doc.save(ignore_permissions=True)

	return {
		"success": True,
		"cuotas_pagadas": doc.cuotas_pagadas_count,
		"saldo_actual": doc.saldo_actual,
		"total_capital_cuotas": doc.total_capital_cuotas,
		"residuo_absorbido": residuo_absorbido,
		"diff_capital": float(diff_capital),
	}


@frappe.whitelist()
def reamortizar_cuotas_pendientes(docname):
	"""
	Reamortiza únicamente las cuotas que están en estado 'Pendiente' utilizando
	el saldo real tras los abonos y cuotas pagadas/históricas, manteniendo
	el valor de la cuota mensual fija (método reducir plazo).
	"""
	doc = frappe.get_doc("Historico Financiamiento", docname)

	if doc.status == "Migrado":
		frappe.throw(_("Este histórico ya fue migrado a {0}.").format(doc.financiamiento_creado))

	cuotas_pend = [c for c in doc.cuotas if c.status == "Pendiente" and not getattr(c, "abono_capital", 0)]
	if not cuotas_pend:
		frappe.throw(_("No hay cuotas pendientes para reamortizar."))

	first_idx = cuotas_pend[0].idx - 1
	if first_idx > 0:
		base_balance = Decimal(str(doc.cuotas[first_idx - 1].saldo or 0))
	else:
		base_balance = Decimal(str(doc.capital_financiado or 0))

	if base_balance <= 0:
		frappe.throw(_("El saldo restante ya es 0."))

	getcontext().prec = 28
	CENT = Decimal("0.01")

	annual_interest = Decimal(str(doc.interes_anual or 0))
	r = (annual_interest / Decimal("100")) / Decimal("12") if annual_interest != 0 else Decimal("0")
	fixed_pmt = Decimal(str(doc.cuota_estimada or cuotas_pend[0].total_cuota or 0))

	curr_balance = base_balance

	for c in cuotas_pend:
		if curr_balance <= Decimal("0.00"):
			c.saldo_anterior = 0.0
			c.capital = 0.0
			c.intereses = 0.0
			c.total_cuota = 0.0
			c.saldo = 0.0
			c.status = "Anticipada"
			c.notas = "Cancelada anticipadamente por abonos a capital históricos."
			continue

		interest = (curr_balance * r).quantize(CENT, rounding=ROUND_HALF_UP)
		principal = (fixed_pmt - interest).quantize(CENT, rounding=ROUND_HALF_UP)

		if principal >= curr_balance:
			principal = curr_balance
			this_payment = (principal + interest).quantize(CENT, rounding=ROUND_HALF_UP)
			prev_b = curr_balance
			curr_balance = Decimal("0.00")
			c.saldo_anterior = float(prev_b)
			c.capital = float(principal)
			c.intereses = float(interest)
			c.total_cuota = float(this_payment)
			c.saldo = 0.0
		else:
			this_payment = fixed_pmt
			prev_b = curr_balance
			curr_balance = (curr_balance - principal).quantize(CENT, rounding=ROUND_HALF_UP)
			c.saldo_anterior = float(prev_b)
			c.capital = float(principal)
			c.intereses = float(interest)
			c.total_cuota = float(this_payment)
			c.saldo = float(curr_balance)

	doc.recalcular_totales_internos()
	doc.save(ignore_permissions=True)

	return {
		"success": True,
		"cuotas_pagadas": doc.cuotas_pagadas_count,
		"saldo_actual": doc.saldo_actual,
	}


@frappe.whitelist()
def validar_y_crear_financiamiento(docname, auto_ajustar_residuo=1):
	"""
	Valida las cuotas cargadas/modificadas y crea el DocType Financiamientos oficial.
	- No re-amortiza ni regenera cuotas: copia exactamente las cifras aprobadas del Excel.
	- Si existe un residuo menor (como los -47.44 del Excel), lo absorbe en la última cuota a saldo 0.
	- Marca las cuotas 'Pagado' como saldo inicial histórico sin emitir facturas en SAR.
	- Actualiza el estado del Activo a 'Financiado'.
	"""
	doc = frappe.get_doc("Historico Financiamiento", docname)

	if doc.status == "Migrado":
		frappe.throw(_("Este histórico ya fue migrado a {0}.").format(doc.financiamiento_creado))

	if not doc.cuotas:
		frappe.throw(_("El plan de cuotas está vacío. Primero genere o pegue las cuotas."))

	capital_esperado = flt(doc.capital_financiado, 2)
	total_cap_cuotas = flt(sum(flt(c.capital) for c in doc.cuotas), 2)
	diff_capital = flt(total_cap_cuotas - capital_esperado, 2)

	# Absorción automática de residuo de centavos o ajuste de última cuota
	if abs(diff_capital) > 0:
		if int(auto_ajustar_residuo) and abs(diff_capital) <= 100.0:
			last_row = doc.cuotas[-1]
			nuevo_capital_last = flt(flt(last_row.capital) - diff_capital, 2)
			last_row.capital = nuevo_capital_last
			last_row.total_cuota = flt(nuevo_capital_last + flt(last_row.intereses), 2)
			last_row.saldo = 0.0
			doc.recalcular_totales_internos()
			doc.save(ignore_permissions=True)
		else:
			frappe.throw(
				_(
					"La suma del capital de las cuotas ({0}) difiere del capital financiado ({1}) por {2}.<br>"
					"Por favor revise las celdas de capital o active el ajuste automático de residuo."
				).format(total_cap_cuotas, capital_esperado, diff_capital)
			)

	# Asegurar que la última cuota termine exactamente en 0
	if doc.cuotas:
		doc.cuotas[-1].saldo = 0.0

	# 1. Crear el DocType Financiamientos real
	fin_doc = frappe.new_doc("Financiamientos")
	fin_doc.company = doc.company
	fin_doc.currency = doc.currency
	fin_doc.customer = doc.customer
	fin_doc.urbanizaciones = doc.urbanizaciones
	fin_doc.centro_costo = doc.centro_costo
	fin_doc.activos = doc.activos
	fin_doc.fecha_inicio = doc.fecha_inicio
	fin_doc.configuracion_financiamiento = doc.configuracion_financiamiento
	fin_doc.monto_contrato = doc.monto_contrato
	fin_doc.prima = doc.prima
	fin_doc.capital_financiado = doc.capital_financiado
	fin_doc.plazo_meses = doc.plazo_meses
	fin_doc.interes_anual = doc.interes_anual
	fin_doc.dia_vencimiento_cuota = doc.dia_vencimiento_cuota
	fin_doc.mora_diaria = doc.mora_diaria
	fin_doc.cuota_estimada = doc.cuota_estimada
	fin_doc.total_financiado = doc.total_financiado

	# Marcar saldo inicial histórico
	fin_doc.es_saldo_inicial = 1
	fin_doc.referencia_migracion = f"Migración Histórica Excel - {doc.name}"
	fin_doc.fecha_corte_migracion = doc.fecha_inicio

	# Copiar snapshot de políticas si existe
	if doc.configuracion_financiamiento:
		try:
			config_doc = frappe.get_doc("Configuracion de Urbanizacion", doc.configuracion_financiamiento)
			fin_doc.politicas_financieras_snapshot = json.dumps(config_doc.get_politicas_dict(), indent=2, ensure_ascii=False)
		except Exception:
			pass

	cuotas_pagadas = 0
	saldo_pendiente = 0.0
	primera_fecha_pendiente = None

	for c in doc.cuotas:
		st = c.status or "Pendiente"
		is_paid = st in ("Pagado", "Anticipada", "Abono a capital") or getattr(c, "abono_capital", 0)
		if is_paid:
			cuotas_pagadas += 1
			extra_tag = " - Abono a capital" if (st == "Abono a capital" or getattr(c, "abono_capital", 0)) else ""
			nota_row = c.notas or f"Pago histórico migrado de Excel (Cuota #{c.numero_cuota}{extra_tag})."
			status_real = st if st in ("Pagado", "Anticipada") else "Pagado"
		else:
			saldo_pendiente += flt(c.total_cuota)
			if not primera_fecha_pendiente:
				primera_fecha_pendiente = c.fecha_vencimiento_cuota
			nota_row = c.notas
			status_real = "Pendiente"

		fin_doc.append(
			"cuotas",
			{
				"doctype": "Cuota de financiamiento",
				"numero_cuota": c.numero_cuota,
				"fecha_vencimiento_cuota": c.fecha_vencimiento_cuota,
				"saldo_anterior": c.saldo_anterior,
				"capital": c.capital,
				"intereses": c.intereses,
				"total_cuota": c.total_cuota,
				"saldo": c.saldo,
				"status": status_real,
				"mora": flt(c.mora or 0),
				"notas": nota_row,
				"monto_adelantado": 0.0,
			},
		)

	fin_doc.cuotas_pagadas_historicas = cuotas_pagadas
	fin_doc.saldo_actual = flt(saldo_pendiente, 2)
	fin_doc.fecha_vencimiento_cuota = primera_fecha_pendiente

	if saldo_pendiente > 0:
		fin_doc.status = "Activo"
		activo_status = "Financiado"
	else:
		fin_doc.status = "Completado"
		activo_status = "Vendido"

	# Insertar y Someter (docstatus=1) directamente para que quede operativo
	fin_doc.flags.ignore_permissions = True
	fin_doc.insert()
	fin_doc.submit()

	# Actualizar Activo
	if doc.activos:
		frappe.db.set_value("Activos", doc.activos, "status", activo_status, update_modified=False)

	# Actualizar este Historico Financiamiento
	doc.db_set("status", "Migrado")
	doc.db_set("financiamiento_creado", fin_doc.name)
	doc.status = "Migrado"
	doc.financiamiento_creado = fin_doc.name

	frappe.db.commit()

	return {
		"success": True,
		"financiamiento": fin_doc.name,
		"cuotas_pagadas": cuotas_pagadas,
		"saldo_actual": fin_doc.saldo_actual,
		"proximo_vencimiento": fin_doc.fecha_vencimiento_cuota,
	}
