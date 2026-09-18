# Copyright (c) 2026, Frappe Technologies Pvt. Ltd. and contributors
# For license information, please see license.txt

import frappe
from frappe import _
from frappe.utils import getdate, flt, cstr


def on_submit(doc, method=None):
	"""
	Hook doc_events on_submit para Sales Invoice.
	Procesa pagos de cuotas de financiamiento, actualiza saldos y completa contratos si aplica.
	"""
	process_financing_on_submit(doc)


def on_cancel(doc, method=None):
	"""
	Hook doc_events on_cancel para Sales Invoice.
	Revierte el estado de las cuotas a 'Pendiente', desvincula la factura,
	restaura los saldos y reabre contratos/activos si estaban completados.
	"""
	process_financing_on_cancel(doc)


def on_trash(doc, method=None):
	"""
	Hook doc_events on_trash para Sales Invoice.
	Limpia enlaces directos y elimina entradas contables (GL Entry / Payment Ledger)
	de facturas canceladas para permitir su eliminación sin bloqueo de integridad.
	"""
	process_financing_on_trash(doc)


def process_financing_on_submit(doc):
	if not doc.get("invoice_generate"):
		return

	if not frappe.db.exists("Generar Factura", doc.invoice_generate):
		return

	generar_factura = frappe.get_doc("Generar Factura", doc.invoice_generate)
	if not generar_factura.financiamiento:
		return

	financiamiento = frappe.get_doc("Financiamientos", generar_factura.financiamiento)
	fecha_cuota = getdate(generar_factura.date_quote_financing)

	cuota_encontrada = False

	for index, cuota in enumerate(financiamiento.cuotas):
		if getdate(cuota.fecha_vencimiento_cuota) == fecha_cuota and cuota.status == "Pendiente":
			net_cuota_pendiente = flt(cuota.total_cuota) - flt(getattr(cuota, "monto_adelantado", 0.0))
			if net_cuota_pendiente < 0:
				net_cuota_pendiente = 0.0

			monto_recibido_gf = flt(getattr(generar_factura, "monto_recibido", 0.0))
			total_a_pagar_esperado = net_cuota_pendiente + flt(cuota.mora)

			es_pago_parcial = (monto_recibido_gf > 0) and (monto_recibido_gf < total_a_pagar_esperado)

			monto_adelanto_sig = 0.0
			modo_aplicar = getattr(generar_factura, "aplicar", None)
			if es_pago_parcial:
				total_esperado = round(monto_recibido_gf, 2)
			else:
				if modo_aplicar == "Abona a siguiente cuota" and monto_recibido_gf > total_a_pagar_esperado:
					monto_adelanto_sig = flt(getattr(generar_factura, "monto_adelanto", 0.0)) or (monto_recibido_gf - total_a_pagar_esperado)
					total_esperado = round(monto_recibido_gf, 2)
				elif modo_aplicar in ("Abono a Capital", "Abono a Intereses") and monto_recibido_gf > total_a_pagar_esperado:
					total_esperado = round(monto_recibido_gf, 2)
				elif getattr(generar_factura, "abonar_siguiente_cuota", 0) and flt(getattr(generar_factura, "monto_adelanto", 0.0)) > 0:
					monto_adelanto_sig = flt(generar_factura.monto_adelanto)
					total_esperado = round(net_cuota_pendiente + flt(cuota.mora) + monto_adelanto_sig, 2)
				else:
					total_esperado = round(total_a_pagar_esperado, 2)

			total_cobrado = round(flt(doc.paid_amount) + flt(doc.change_amount), 2)
			total_factura = round(flt(doc.grand_total) + flt(doc.change_amount), 2)
			direct_paid = round(flt(doc.paid_amount), 2)

			diff_cobrado = abs(total_cobrado - total_esperado)
			diff_factura = abs(total_factura - total_esperado)
			diff_direct = abs(direct_paid - total_esperado)

			if diff_cobrado > 0.05 and diff_factura > 0.05 and diff_direct > 0.05:
				frappe.throw(
					_(
						"El total de la factura debe ser exactamente {0}. "
						"Total cobrado en factura: {1}"
					).format(
						total_esperado,
						total_cobrado if total_cobrado > 0 else direct_paid
					)
				)

			if es_pago_parcial:
				prev_adelantado = flt(getattr(cuota, "monto_adelantado", 0.0))
				nuevo_adelantado = prev_adelantado + monto_recibido_gf
				frappe.db.set_value(
					"Cuota de financiamiento",
					cuota.name,
					"monto_adelantado",
					nuevo_adelantado,
					update_modified=False
				)

				nota_adelanto = f"Se aplicó abono parcial/adelantado de L {monto_recibido_gf} desde factura {doc.name}."
				nota_existente = cstr(cuota.notas).strip()
				nueva_nota = f"{nota_existente}\n{nota_adelanto}".strip() if nota_existente else nota_adelanto
				frappe.db.set_value(
					"Cuota de financiamiento",
					cuota.name,
					"notas",
					nueva_nota,
					update_modified=False
				)

				if nuevo_adelantado >= flt(cuota.total_cuota) - 0.001:
					frappe.db.set_value(
						"Cuota de financiamiento",
						cuota.name,
						{
							"status": "Pagado",
							"sales_invoice": doc.name
						},
						update_modified=False
					)

				nuevo_saldo = flt(financiamiento.saldo_actual) - monto_recibido_gf
				if nuevo_saldo < 0:
					nuevo_saldo = 0

				frappe.db.set_value(
					"Financiamientos",
					financiamiento.name,
					"saldo_actual",
					nuevo_saldo,
					update_modified=False
				)
			else:
				frappe.db.set_value(
					"Cuota de financiamiento",
					cuota.name,
					{
						"status": "Pagado",
						"sales_invoice": doc.name
					},
					update_modified=False
				)

				nota_pago = f"Pagado completamente en factura {doc.name}."
				nota_existente = cstr(cuota.notas).strip()
				nueva_nota = f"{nota_existente}\n{nota_pago}".strip() if nota_existente else nota_pago
				frappe.db.set_value(
					"Cuota de financiamiento",
					cuota.name,
					"notas",
					nueva_nota,
					update_modified=False
				)

				nuevo_saldo = flt(financiamiento.saldo_actual) - (net_cuota_pendiente + flt(cuota.mora) + monto_adelanto_sig)
				if nuevo_saldo < 0:
					nuevo_saldo = 0

				frappe.db.set_value(
					"Financiamientos",
					financiamiento.name,
					"saldo_actual",
					nuevo_saldo,
					update_modified=False
				)

				if monto_adelanto_sig > 0:
					monto_adelanto_restante = flt(monto_adelanto_sig)
					for sig in financiamiento.cuotas[index + 1:]:
						if monto_adelanto_restante <= 0:
							break
						if sig.status != "Pendiente":
							continue

						total_cuota_sig = flt(sig.total_cuota)
						prev_adelantado = flt(getattr(sig, "monto_adelantado", 0.0))
						saldo_neto_sig = total_cuota_sig - prev_adelantado
						if saldo_neto_sig <= 0:
							continue

						monto_a_aplicar_cuota = min(monto_adelanto_restante, saldo_neto_sig)
						nuevo_adelantado = prev_adelantado + monto_a_aplicar_cuota

						update_dict = {
							"monto_adelantado": nuevo_adelantado,
							"sales_invoice": doc.name
						}

						nota_adelanto = f"Se aplicó abono adelantado de L {monto_a_aplicar_cuota} desde factura {doc.name}."
						nota_existente = cstr(sig.notas).strip()
						nueva_nota = f"{nota_existente}\n{nota_adelanto}".strip() if nota_existente else nota_adelanto
						update_dict["notas"] = nueva_nota

						if nuevo_adelantado >= total_cuota_sig - 0.001:
							update_dict["status"] = "Pagado"

						frappe.db.set_value("Cuota de financiamiento", sig.name, update_dict, update_modified=False)
						monto_adelanto_restante -= monto_a_aplicar_cuota

			# Actualizar próxima fecha de vencimiento y verificar si el contrato se completó
			pendientes = frappe.db.sql(
				"""
				SELECT name, fecha_vencimiento_cuota
				FROM `tabCuota de financiamiento`
				WHERE parent = %s AND status = 'Pendiente'
				ORDER BY numero_cuota ASC
				""",
				financiamiento.name,
				as_dict=True
			)
			pendientes_count = len(pendientes)
			siguiente_fecha = pendientes[0].fecha_vencimiento_cuota if pendientes else None

			update_fin_vals = {
				"fecha_vencimiento_cuota": siguiente_fecha
			}

			if pendientes_count == 0:
				update_fin_vals["status"] = "Completado"
				all_activos = financiamiento.get_all_linked_activos() if hasattr(financiamiento, "get_all_linked_activos") else ([financiamiento.activos] if getattr(financiamiento, "activos", None) else [])
				for act_name in all_activos:
					frappe.db.set_value("Activos", act_name, "status", "Vendido", update_modified=False)
				frappe.msgprint(
					_(
						"<b>¡Felicidades!</b> Todas las cuotas han sido canceladas.<br>"
						"El financiamiento <b>{0}</b> ha pasado a estado <b>Completado</b> y los activos asociados a <b>Vendido</b>."
					).format(financiamiento.name),
					title=_("Financiamiento Liquidado")
				)

			frappe.db.set_value("Financiamientos", financiamiento.name, update_fin_vals, update_modified=False)

			cuota_encontrada = True
			break

	if not cuota_encontrada:
		frappe.throw(
			f"No se encontró una cuota pendiente con fecha {fecha_cuota}"
		)


def process_financing_on_cancel(doc):
	"""
	Reversión automática al anular una Sales Invoice.
	"""
	# 1. Buscar todas las cuotas asociadas directamente a esta factura
	cuotas_directas = frappe.get_all(
		"Cuota de financiamiento",
		filters={"sales_invoice": doc.name},
		fields=["name", "parent", "status", "total_cuota", "monto_adelantado", "numero_cuota", "notas"]
	)

	# 2. Si tiene doc.invoice_generate
	generar_factura = None
	financiamiento_name = None
	if doc.get("invoice_generate"):
		if frappe.db.exists("Generar Factura", doc.invoice_generate):
			generar_factura = frappe.get_doc("Generar Factura", doc.invoice_generate)
			financiamiento_name = generar_factura.financiamiento

	# Identificar financiamientos afectados
	financiamientos_afectados = set()
	if financiamiento_name:
		financiamientos_afectados.add(financiamiento_name)
	for c in cuotas_directas:
		if c.parent:
			financiamientos_afectados.add(c.parent)

	# Revertir cuotas directas
	for c in cuotas_directas:
		nota_cancel = f"[Factura {doc.name} CANCELADA] Pago revertido."
		nota_existente = cstr(c.notas).strip()
		nueva_nota = f"{nota_existente}\n{nota_cancel}".strip() if nota_existente else nota_cancel

		frappe.db.set_value(
			"Cuota de financiamiento",
			c.name,
			{
				"status": "Pendiente",
				"sales_invoice": None,
				"notas": nueva_nota
			},
			update_modified=False
		)

	# Si hay Generar Factura, verificar abonos parciales o adelantos multi-cuota
	if generar_factura and financiamiento_name:
		fin_doc = frappe.get_doc("Financiamientos", financiamiento_name)
		monto_recibido_gf = flt(getattr(generar_factura, "monto_recibido", 0.0))
		net_cuota_pendiente = flt(generar_factura.total_cuota)
		total_a_pagar_esperado = net_cuota_pendiente + flt(generar_factura.total_mora)
		es_pago_parcial = (monto_recibido_gf > 0) and (monto_recibido_gf < total_a_pagar_esperado)

		for cuota in fin_doc.cuotas:
			if doc.name in (cuota.notas or ""):
				if es_pago_parcial and getdate(cuota.fecha_vencimiento_cuota) == getdate(generar_factura.date_quote_financing):
					prev_adelantado = flt(getattr(cuota, "monto_adelantado", 0.0))
					nuevo_adelantado = max(0.0, prev_adelantado - monto_recibido_gf)
					frappe.db.set_value(
						"Cuota de financiamiento",
						cuota.name,
						{
							"monto_adelantado": nuevo_adelantado,
							"status": "Pendiente",
							"sales_invoice": None
						},
						update_modified=False
					)
				elif not es_pago_parcial and cuota.numero_cuota > 1:
					if cuota.status in ("Pagado", "Pendiente") and (cuota.sales_invoice == doc.name or doc.name in (cuota.notas or "")):
						frappe.db.set_value(
							"Cuota de financiamiento",
							cuota.name,
							{
								"status": "Pendiente",
								"sales_invoice": None,
								"monto_adelantado": 0.0
							},
							update_modified=False
						)

	# Recalcular saldos, estados y fechas en los financiamientos afectados
	for fin_name in financiamientos_afectados:
		fin = frappe.get_doc("Financiamientos", fin_name)
		total_pendiente = sum(
			(flt(c.total_cuota) - flt(getattr(c, "monto_adelantado", 0.0)))
			for c in fin.cuotas
			if c.status == "Pendiente"
		)
		siguiente_fecha = None
		for c in fin.cuotas:
			if c.status == "Pendiente":
				siguiente_fecha = c.fecha_vencimiento_cuota
				break

		update_fin = {
			"saldo_actual": flt(total_pendiente, 2),
			"fecha_vencimiento_cuota": siguiente_fecha
		}

		if fin.status == "Completado":
			is_ref = str(fin.es_refinanciamiento or "").strip().lower() in ('si', 'sí', 's', 'true', '1')
			update_fin["status"] = "Refinanciado" if is_ref else "Activo"

			all_activos = fin.get_all_linked_activos() if hasattr(fin, "get_all_linked_activos") else ([fin.activos] if getattr(fin, "activos", None) else [])
			for act_name in all_activos:
				frappe.db.set_value(
					"Activos",
					act_name,
					"status",
					"Financiado" if not is_ref else "Refinanciado",
					update_modified=False
				)

		frappe.db.set_value("Financiamientos", fin.name, update_fin, update_modified=False)

	frappe.msgprint(
		_(
			"Se ha cancelado la factura <b>{0}</b>.<br>"
			"Las cuotas vinculadas han regresado a estado <b>Pendiente</b> y el saldo del financiamiento fue restaurado."
		).format(doc.name),
		title=_("Reversión de Facturación Exitosa")
	)


def process_financing_on_trash(doc):
	"""
	Limpia enlaces y entradas contables de facturas canceladas para permitir eliminación física limpia.
	"""
	# 1. Desvincular en Cuota de financiamiento
	frappe.db.sql(
		"""
		UPDATE `tabCuota de financiamiento`
		SET `sales_invoice` = NULL
		WHERE `sales_invoice` = %s
		""",
		doc.name
	)

	# 2. Si la factura está cancelada (docstatus == 2), eliminar asientos vinculados para evitar LinkExistsError
	if doc.docstatus == 2:
		frappe.db.sql(
			"DELETE FROM `tabGL Entry` WHERE voucher_type = 'Sales Invoice' AND voucher_no = %s",
			doc.name
		)
		frappe.db.sql(
			"""
			DELETE FROM `tabPayment Ledger Entry`
			WHERE (voucher_type = 'Sales Invoice' AND voucher_no = %s)
			   OR (against_voucher_type = 'Sales Invoice' AND against_voucher_no = %s)
			""",
			(doc.name, doc.name)
		)
		frappe.db.sql(
			"DELETE FROM `tabStock Ledger Entry` WHERE voucher_type = 'Sales Invoice' AND voucher_no = %s",
			doc.name
		)
