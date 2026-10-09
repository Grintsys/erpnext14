# Copyright (c) 2026, Frappe Technologies Pvt. Ltd. and contributors
# For license information, please see license.txt

import json
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

	conversion_rate = flt(getattr(generar_factura, "conversion_rate", 1.0)) or 1.0
	fin_currency = getattr(financiamiento, "currency", None) or "USD"
	invoice_currency = getattr(doc, "currency", None) or getattr(generar_factura, "currency", None) or "HNL"

	cuota_encontrada = False

	for index, cuota in enumerate(financiamiento.cuotas):
		if getdate(cuota.fecha_vencimiento_cuota) == fecha_cuota and cuota.status == "Pendiente":
			# Montos en moneda de financiamiento (ej. USD)
			net_cuota_pendiente_finan = flt(cuota.total_cuota) - flt(getattr(cuota, "monto_adelantado", 0.0))
			if net_cuota_pendiente_finan < 0:
				net_cuota_pendiente_finan = 0.0

			mora_finan = flt(cuota.mora)
			total_a_pagar_finan = net_cuota_pendiente_finan + mora_finan

			# Montos convertidos a la moneda de la factura (ej. HNL)
			net_cuota_factura = round(net_cuota_pendiente_finan * conversion_rate, 2)
			mora_factura = round(mora_finan * conversion_rate, 2)
			total_a_pagar_esperado_factura = round(net_cuota_factura + mora_factura, 2)

			monto_recibido_gf = flt(getattr(generar_factura, "monto_recibido", 0.0))
			monto_adelanto_gf = flt(getattr(generar_factura, "monto_adelanto", 0.0))
			modo_aplicar = getattr(generar_factura, "aplicar", None)

			es_pago_parcial = (monto_recibido_gf > 0) and (monto_recibido_gf < total_a_pagar_esperado_factura)

			monto_adelanto_sig_factura = 0.0
			if es_pago_parcial:
				total_esperado_factura = round(monto_recibido_gf, 2)
			else:
				if modo_aplicar == "Abona a siguiente cuota" and monto_recibido_gf > total_a_pagar_esperado_factura:
					monto_adelanto_sig_factura = monto_adelanto_gf or (monto_recibido_gf - total_a_pagar_esperado_factura)
					total_esperado_factura = round(monto_recibido_gf, 2)
				elif modo_aplicar in ("Abono a Capital", "Abono a Intereses") and monto_recibido_gf > total_a_pagar_esperado_factura:
					total_esperado_factura = round(monto_recibido_gf, 2)
				elif getattr(generar_factura, "abonar_siguiente_cuota", 0) and monto_adelanto_gf > 0:
					monto_adelanto_sig_factura = monto_adelanto_gf
					total_esperado_factura = round(total_a_pagar_esperado_factura + monto_adelanto_sig_factura, 2)
				elif monto_adelanto_gf > 0:
					monto_adelanto_sig_factura = monto_adelanto_gf
					total_esperado_factura = round(total_a_pagar_esperado_factura + monto_adelanto_sig_factura, 2)
				else:
					total_esperado_factura = round(total_a_pagar_esperado_factura, 2)

			# Comparar con los totales cobrados en la factura (en moneda de facturación)
			total_cobrado = round(flt(doc.paid_amount) + flt(doc.change_amount), 2)
			total_factura = round(flt(doc.grand_total) + flt(doc.change_amount), 2)
			direct_paid = round(flt(doc.paid_amount), 2)

			diff_cobrado = abs(total_cobrado - total_esperado_factura)
			diff_factura = abs(total_factura - total_esperado_factura)
			diff_direct = abs(direct_paid - total_esperado_factura)

			if diff_cobrado > 0.05 and diff_factura > 0.05 and diff_direct > 0.05:
				frappe.throw(
					_(
						"El total de la factura debe ser exactamente {0} {1}. "
						"Total cobrado en factura: {2} {1}"
					).format(
						total_esperado_factura,
						invoice_currency,
						total_cobrado if total_cobrado > 0 else direct_paid
					)
				)

			if es_pago_parcial:
				monto_recibido_finan = flt(monto_recibido_gf / conversion_rate, 4)
				prev_adelantado = flt(getattr(cuota, "monto_adelantado", 0.0))
				nuevo_adelantado = flt(prev_adelantado + monto_recibido_finan, 2)

				frappe.db.set_value(
					"Cuota de financiamiento",
					cuota.name,
					"monto_adelantado",
					nuevo_adelantado,
					update_modified=False
				)

				nota_adelanto = f"Se aplicó abono parcial de {invoice_currency} {monto_recibido_gf:.2f} (@ tasa {conversion_rate} = {fin_currency} {monto_recibido_finan:.2f}) desde factura {doc.name}."
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

				nuevo_saldo = max(0.0, flt(financiamiento.saldo_actual) - monto_recibido_finan)

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

				nota_pago = f"Pagado completamente en factura {doc.name} ({invoice_currency} {total_cobrado:.2f} @ tasa {conversion_rate})."
				nota_existente = cstr(cuota.notas).strip()
				nueva_nota = f"{nota_existente}\n{nota_pago}".strip() if nota_existente else nota_pago
				frappe.db.set_value(
					"Cuota de financiamiento",
					cuota.name,
					"notas",
					nueva_nota,
					update_modified=False
				)

				monto_adelanto_sig_finan = flt(monto_adelanto_sig_factura / conversion_rate, 4) if monto_adelanto_sig_factura > 0 else 0.0
				nuevo_saldo = max(0.0, flt(financiamiento.saldo_actual) - (net_cuota_pendiente_finan + mora_finan + monto_adelanto_sig_finan))

				frappe.db.set_value(
					"Financiamientos",
					financiamiento.name,
					"saldo_actual",
					nuevo_saldo,
					update_modified=False
				)

				if monto_adelanto_sig_finan > 0:
					monto_adelanto_restante = flt(monto_adelanto_sig_finan)
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

						nota_adelanto = f"Se aplicó abono adelantado de {fin_currency} {monto_a_aplicar_cuota:.2f} desde factura {doc.name}."
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
	Utiliza el snapshot pre-transaccional de Generar Factura si existe para
	restaurar de forma atómica y fidedigna las cuotas y saldos sin reamortizaciones destructivas.
	"""
	# 1. Obtener Generar Factura vinculada
	generar_factura = None
	financiamiento_name = None
	if doc.get("invoice_generate"):
		if frappe.db.exists("Generar Factura", doc.invoice_generate):
			generar_factura = frappe.get_doc("Generar Factura", doc.invoice_generate)
			financiamiento_name = generar_factura.financiamiento
			if hasattr(generar_factura, "validate_lifo_cancellation"):
				generar_factura.validate_lifo_cancellation()
			if generar_factura.docstatus == 1 and not getattr(generar_factura.flags, "in_cancel", False):
				generar_factura.flags.ignore_permissions = True
				generar_factura.flags.in_cancel = True
				generar_factura.cancel()

	# 2. Si existe un snapshot pre-transaccional en Generar Factura, restaurar desde snapshot
	snapshot_restaurado = False
	if generar_factura and getattr(generar_factura, "estado_previo_financiamiento", None):
		try:
			snap_data = json.loads(generar_factura.estado_previo_financiamiento)
			fin_name = snap_data.get("financiamiento") or financiamiento_name
			if fin_name and frappe.db.exists("Financiamientos", fin_name):
				fin_doc = frappe.get_doc("Financiamientos", fin_name)

				# Restaurar cada cuota guardada en el snapshot
				for c_snap in snap_data.get("cuotas", []):
					c_name = c_snap.get("name")
					if c_name and frappe.db.exists("Cuota de financiamiento", c_name):
						update_dict = {
							"status": c_snap.get("status", "Pendiente"),
							"saldo_anterior": flt(c_snap.get("saldo_anterior", 0.0)),
							"capital": flt(c_snap.get("capital", 0.0)),
							"intereses": flt(c_snap.get("intereses", 0.0)),
							"total_cuota": flt(c_snap.get("total_cuota", 0.0)),
							"saldo": flt(c_snap.get("saldo", 0.0)),
							"monto_adelantado": flt(c_snap.get("monto_adelantado", 0.0)),
							"sales_invoice": c_snap.get("sales_invoice"),
							"mora": flt(c_snap.get("mora", 0.0)),
							"notas": c_snap.get("notas")
						}
						if c_snap.get("fecha_vencimiento_cuota"):
							update_dict["fecha_vencimiento_cuota"] = c_snap.get("fecha_vencimiento_cuota")
						frappe.db.set_value("Cuota de financiamiento", c_name, update_dict, update_modified=False)

				# Restaurar cabecera del financiamiento
				fin_update = {
					"saldo_actual": flt(snap_data.get("saldo_actual", 0.0)),
					"status": snap_data.get("status", "Activo")
				}
				if snap_data.get("fecha_vencimiento_cuota"):
					fin_update["fecha_vencimiento_cuota"] = snap_data.get("fecha_vencimiento_cuota")

				# Asegurar que el status no sea 'Completado' o 'Cancelado' si debe estar activo
				if fin_update["status"] in ("Completado", "Cancelado") and fin_update["saldo_actual"] > 0:
					is_ref = str(fin_doc.es_refinanciamiento or "").strip().lower() in ('si', 'sí', 's', 'true', '1')
					fin_update["status"] = "Refinanciado" if is_ref else "Activo"

				frappe.db.set_value("Financiamientos", fin_name, fin_update, update_modified=False)

				# Restaurar estado de activos si estaban como Vendido
				is_ref = str(fin_doc.es_refinanciamiento or "").strip().lower() in ('si', 'sí', 's', 'true', '1')
				all_activos = fin_doc.get_all_linked_activos() if hasattr(fin_doc, "get_all_linked_activos") else ([fin_doc.activos] if getattr(fin_doc, "activos", None) else [])
				for act_name in all_activos:
					cur_act_status = frappe.db.get_value("Activos", act_name, "status")
					if cur_act_status == "Vendido":
						frappe.db.set_value(
							"Activos",
							act_name,
							"status",
							"Refinanciado" if is_ref else "Financiado",
							update_modified=False
						)

				snapshot_restaurado = True
		except Exception as e:
			frappe.log_error(frappe.get_traceback(), f"process_financing_on_cancel snapshot restore error: {str(e)}")
			snapshot_restaurado = False

	# 3. Fallback para documentos sin snapshot (legados)
	if not snapshot_restaurado:
		cuotas_directas = frappe.get_all(
			"Cuota de financiamiento",
			filters={"sales_invoice": doc.name},
			fields=["name", "parent", "status", "total_cuota", "monto_adelantado", "numero_cuota", "notas"]
		)
		financiamientos_afectados = set()
		if financiamiento_name:
			financiamientos_afectados.add(financiamiento_name)
		for c in cuotas_directas:
			if c.parent:
				financiamientos_afectados.add(c.parent)

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

		for fin_name in financiamientos_afectados:
			fin = frappe.get_doc("Financiamientos", fin_name)
			if hasattr(fin, "recalcular_amortizacion_completa"):
				fin.recalcular_amortizacion_completa()

			if fin.status == "Completado":
				is_ref = str(fin.es_refinanciamiento or "").strip().lower() in ('si', 'sí', 's', 'true', '1')
				new_status = "Refinanciado" if is_ref else "Activo"
				frappe.db.set_value("Financiamientos", fin.name, "status", new_status, update_modified=False)

				all_activos = fin.get_all_linked_activos() if hasattr(fin, "get_all_linked_activos") else ([fin.activos] if getattr(fin, "activos", None) else [])
				for act_name in all_activos:
					frappe.db.set_value(
						"Activos",
						act_name,
						"status",
						"Financiado" if not is_ref else "Refinanciado",
						update_modified=False
					)

	frappe.msgprint(
		_(
			"Se ha cancelado la factura <b>{0}</b>.<br>"
			"Las cuotas vinculadas han regresado a su estado previo y el saldo del financiamiento fue restaurado de forma íntegra."
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
