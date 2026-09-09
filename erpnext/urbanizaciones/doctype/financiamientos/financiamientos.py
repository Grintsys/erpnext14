# Copyright (c) 2025, Frappe Technologies Pvt. Ltd. and contributors
# For license information, please see license.txt

import json
import frappe
from frappe import _
from frappe.model.document import Document
from frappe.utils import getdate, add_months, nowdate, flt
import calendar
import math
from decimal import Decimal, getcontext, ROUND_HALF_UP

STATUS_CUOTA = [
    "Pendiente",
    "Refinanciado",
    "Pagado",
    "Cancelado",
    "Abono a capital",
]

# Mapea fieldname -> etiqueta para mensajes amigables (ajusta si quieres otros labels)
REQUIRED_FIELDS = {
    "naming_series": "Series",
    "customer": "Cliente",
    "urbanizaciones": "Urbanización",
    "activos": "Activo",
    "fecha_inicio": "Fecha de inicio",
    "monto_contrato": "Monto del contrato",
    "configuracion_financiamiento": "Configuración de financiamiento",
    "prima": "Prima",
    "capital_financiado": "Capital financiado",
    "plazo_meses": "Plazo en meses",
    "interes_anual": "Interés anual",
    "mora_diaria": "Mora diaria",
    "dia_vencimiento_cuota": "Día de vencimiento",
}

def _is_filled(value):
    """Consider 0 valid. Only None, empty string or NaN are treated as empty."""
    if value is None:
        return False
    if isinstance(value, str) and value.strip() == "":
        return False
    if isinstance(value, float) and math.isnan(value):
        return False
    return True

def validate_required_fields(doc):
    """
    Valida en servidor que los campos marcados como 'reqd' en financiamientos.json
    estén presentes. Lanza frappe.ValidationError (frappe.throw) con la lista de faltantes.
    """
    missing = []
    for fieldname, label in REQUIRED_FIELDS.items():
        val = doc.get(fieldname)
        if not _is_filled(val):
            missing.append(label)
    if missing:
        frappe.throw(_("Faltan campos requeridos: {0}").format(", ".join(missing)))

class Financiamientos(Document):
    def validate(self):
        self.validate_activo_urbanizacion()
        self.ensure_politicas_snapshot()
        self.calculate_financial_totals()

    def ensure_politicas_snapshot(self):
        if not self.politicas_financieras_snapshot and self.configuracion_financiamiento:
            config_doc = frappe.get_doc("Configuracion de Urbanizacion", self.configuracion_financiamiento)
            self.politicas_financieras_snapshot = json.dumps(config_doc.get_politicas_dict(), indent=2, ensure_ascii=False)

    def get_politicas_snapshot(self):
        if self.politicas_financieras_snapshot:
            try:
                return json.loads(self.politicas_financieras_snapshot)
            except Exception:
                pass
        if self.configuracion_financiamiento:
            try:
                config_doc = frappe.get_doc("Configuracion de Urbanizacion", self.configuracion_financiamiento)
                return config_doc.get_politicas_dict()
            except Exception:
                pass
        return {
            "exigir_cobertura_mora": 1,
            "permitir_pagos_parciales_sin_mora": 1,
            "permitir_monto_mayor": 1,
            "permitir_vuelto_efectivo": 1,
            "politica_excedentes": "Selección por Usuario en Caja",
            "permitir_anticipo_siguiente_cuota": 1,
            "regla_monto_siguiente_cuota": "Coincidencia Exacta",
            "permitir_abono_capital": 1,
            "politica_recalculo_capital": "Reducir Plazo (Cuota Fija)",
            "permitir_abono_interes": 1,
            "politica_recalculo_interes": "Crédito Directo Cuota Posterior",
            "version_politica": "Fallback",
        }

    def reamortizar_por_abono_capital(self, monto_abono, politica=None):
        """
        Recalcula la tabla de amortización tras un abono extraordinario a capital.
        - Las cuotas 'Pagado' se mantienen intactas.
        - Reduce el saldo de capital por `monto_abono`.
        - Si politica == 'Reducir Plazo (Cuota Fija)' (default):
            Mantiene el valor de la cuota mensual fija (PMT) y cancela las cuotas finales sobrantes.
        - Si politica == 'Reducir Valor de Cuota (Plazo Fijo)':
            Recalcula un nuevo PMT menor manteniendo el número de cuotas pendientes.
        """
        import json
        from decimal import Decimal, getcontext, ROUND_HALF_UP

        getcontext().prec = 28
        CENT = Decimal('0.01')

        abono = Decimal(str(monto_abono or 0)).quantize(CENT, rounding=ROUND_HALF_UP)
        if abono <= 0:
            return

        politicas = self.get_politicas_snapshot()
        politica = politica or politicas.get("politica_recalculo_capital", "Reducir Plazo (Cuota Fija)")

        cuotas_pendientes = [c for c in self.cuotas if c.status == "Pendiente"]
        if not cuotas_pendientes:
            return

        first_pending = cuotas_pendientes[0]
        saldo_anterior_base = Decimal(str(first_pending.saldo_anterior))
        nuevo_saldo_base = (saldo_anterior_base - abono).quantize(CENT, rounding=ROUND_HALF_UP)
        if nuevo_saldo_base < Decimal('0.00'):
            nuevo_saldo_base = Decimal('0.00')

        annual_interest = Decimal(str(self.interes_anual or 0))
        r = (annual_interest / Decimal('100')) / Decimal('12') if annual_interest != 0 else Decimal('0')
        n_rem = len(cuotas_pendientes)

        if politica == "Reducir Valor de Cuota (Plazo Fijo)":
            if n_rem > 0 and nuevo_saldo_base > 0:
                if r == 0:
                    new_pmt = (nuevo_saldo_base / n_rem).quantize(CENT, rounding=ROUND_HALF_UP)
                else:
                    new_pmt = (r * nuevo_saldo_base / (Decimal('1') - (Decimal('1') + r) ** (Decimal(-n_rem)))).quantize(CENT, rounding=ROUND_HALF_UP)
            else:
                new_pmt = Decimal('0.00')

            curr_balance = nuevo_saldo_base
            for idx, c in enumerate(cuotas_pendientes):
                i = idx + 1
                interest = (curr_balance * r).quantize(CENT, rounding=ROUND_HALF_UP)
                if i == n_rem:
                    principal = curr_balance
                    this_payment = (principal + interest).quantize(CENT, rounding=ROUND_HALF_UP)
                else:
                    principal = (new_pmt - interest).quantize(CENT, rounding=ROUND_HALF_UP)
                    this_payment = new_pmt

                prev_b = curr_balance
                curr_balance = (curr_balance - principal).quantize(CENT, rounding=ROUND_HALF_UP)
                if curr_balance < 0:
                    curr_balance = Decimal('0.00')

                c.saldo_anterior = float(prev_b)
                c.capital = float(principal)
                c.intereses = float(interest)
                c.total_cuota = float(this_payment)
                c.saldo = float(curr_balance)

        else: # "Reducir Plazo (Cuota Fija)"
            fixed_pmt = Decimal(str(first_pending.total_cuota))
            curr_balance = nuevo_saldo_base

            for c in cuotas_pendientes:
                if curr_balance <= 0:
                    c.capital = 0.0
                    c.intereses = 0.0
                    c.total_cuota = 0.0
                    c.saldo = 0.0
                    c.saldo_anterior = 0.0
                    c.status = "Cancelado"
                    continue

                interest = (curr_balance * r).quantize(CENT, rounding=ROUND_HALF_UP)
                principal = (fixed_pmt - interest).quantize(CENT, rounding=ROUND_HALF_UP)

                if principal >= curr_balance:
                    principal = curr_balance
                    this_payment = (principal + interest).quantize(CENT, rounding=ROUND_HALF_UP)
                    prev_b = curr_balance
                    curr_balance = Decimal('0.00')
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

        # Persistir cambios en cada fila de cuota en DB
        for c in cuotas_pendientes:
            if getattr(c, "name", None):
                frappe.db.set_value("Cuota de financiamiento", c.name, {
                    "saldo_anterior": c.saldo_anterior,
                    "capital": c.capital,
                    "intereses": c.intereses,
                    "total_cuota": c.total_cuota,
                    "saldo": c.saldo,
                    "status": c.status
                }, update_modified=False)

        # Actualizar saldo_actual del financiamiento
        ultimas_activas = [c for c in self.cuotas if c.status == "Pendiente"]
        if ultimas_activas:
            total_futuro = sum(flt(c.total_cuota) for c in ultimas_activas)
            self.saldo_actual = flt(total_futuro, 2)
        else:
            self.saldo_actual = 0.0

        if not self.is_new():
            frappe.db.set_value("Financiamientos", self.name, "saldo_actual", self.saldo_actual, update_modified=False)
            if self.docstatus == 0:
                self.save(ignore_permissions=True)

    def reamortizar_por_abono_interes(self, monto_abono, politica=None):
        """
        Aplica un abono extraordinario destinado exclusivamente a reducir intereses futuros.
        - Las cuotas 'Pagado' no se alteran.
        - Mantiene el número de cuotas restantes (mismo plazo).
        - Disminuye el valor total a pagar de cuotas futuras.
        """
        from decimal import Decimal, getcontext, ROUND_HALF_UP

        getcontext().prec = 28
        CENT = Decimal('0.01')

        abono = Decimal(str(monto_abono or 0)).quantize(CENT, rounding=ROUND_HALF_UP)
        if abono <= 0:
            return

        politicas = self.get_politicas_snapshot()
        politica = politica or politicas.get("politica_recalculo_interes", "Crédito Directo Cuota Posterior")

        cuotas_pendientes = [c for c in self.cuotas if c.status == "Pendiente"]
        if not cuotas_pendientes:
            return

        if politica == "Descuento Prorrateado Futuro":
            n_rem = len(cuotas_pendientes)
            descuento_por_cuota = (abono / Decimal(str(n_rem))).quantize(CENT, rounding=ROUND_HALF_UP)

            rem_abono = abono
            for idx, c in enumerate(cuotas_pendientes):
                cur_int = Decimal(str(c.intereses))
                if idx == n_rem - 1:
                    disc = rem_abono
                else:
                    disc = min(descuento_por_cuota, cur_int)

                rem_abono -= disc
                nuevo_int = (cur_int - disc).quantize(CENT, rounding=ROUND_HALF_UP)
                if nuevo_int < 0:
                    nuevo_int = Decimal('0.00')

                c.intereses = float(nuevo_int)
                c.total_cuota = float(Decimal(str(c.capital)) + nuevo_int)

        else: # "Crédito Directo Cuota Posterior"
            rem_abono = abono
            for c in cuotas_pendientes:
                if rem_abono <= 0:
                    break
                cur_int = Decimal(str(c.intereses))
                disc = min(rem_abono, cur_int)
                rem_abono -= disc
                nuevo_int = (cur_int - disc).quantize(CENT, rounding=ROUND_HALF_UP)

                c.intereses = float(nuevo_int)
                c.total_cuota = float(Decimal(str(c.capital)) + nuevo_int)

        # Persistir cambios en cada fila de cuota en DB
        for c in cuotas_pendientes:
            if getattr(c, "name", None):
                frappe.db.set_value("Cuota de financiamiento", c.name, {
                    "intereses": c.intereses,
                    "total_cuota": c.total_cuota
                }, update_modified=False)

        # Actualizar saldo_actual del financiamiento
        total_futuro = sum(flt(c.total_cuota) for c in cuotas_pendientes)
        self.saldo_actual = flt(total_futuro, 2)
        if not self.is_new():
            frappe.db.set_value("Financiamientos", self.name, "saldo_actual", self.saldo_actual, update_modified=False)
            if self.docstatus == 0:
                self.save(ignore_permissions=True)


    def calculate_financial_totals(self):
        if self.is_new() or not self.get("cuotas"):
            cuota = flt(self.cuota_estimada)
            plazo = flt(self.plazo_meses)
            prima = flt(self.prima)

            self.saldo_actual = flt(cuota * plazo, 2)
            self.total_financiado = flt((cuota * plazo) + prima, 2)

    def validate_activo_urbanizacion(self):
        if self.activos and self.urbanizaciones:
            activo_urbanizacion = frappe.db.get_value('Activos', self.activos, 'urbanizaciones')
            if activo_urbanizacion != self.urbanizaciones:
                frappe.throw(
                    _("El Activo seleccionado ({0}) no pertenece a la Urbanización seleccionada ({1}).").format(
                        self.activos, self.urbanizaciones
                    )
                )

@frappe.whitelist()
def generar_cuotas(docname):
    """
    Crea filas en la child table según el campo `plazo_meses`.
    Convierte correctamente la fecha de vencimiento desde string a fecha (YYYY-MM-DD).
    """
    doc = frappe.get_doc('Financiamientos', docname)

    # Validación server-side de campos requeridos (según financiamientos.json)
    validate_required_fields(doc)

    plazo = doc.get('plazo_meses') or doc.get('plazo')
    estado_financiamiento = doc.get('status')
    
    if not plazo or int(plazo) <= 0:
        frappe.throw(_("El campo 'plazo_meses' debe estar definido y ser mayor que 0"))

    # Cambia esto al fieldname real de la child table en Financiamientos
    child_fieldname = 'cuotas'

    # Nombre del doctype de cada fila de la child table (ajusta si es necesario)
    child_doctype = 'Cuota de financiamiento'

    # limpiar filas existentes (opcional)
    doc.set(child_fieldname, [])

    # datos base para calcular vencimientos y montos
    fecha_inicio = doc.get('fecha_inicio')  # string o date
    dia_venc = doc.get('dia_vencimiento_cuota')  # número de día preferido (1-31)
    is_refinancing = doc.get('es_refinanciamiento')  # booleano

    try:
        dia_venc = int(dia_venc) if dia_venc is not None else None
    except (ValueError, TypeError):
        dia_venc = None

    # Use Decimal for monetary calculations to avoid floating point rounding issues
    getcontext().prec = 28
    CENT = Decimal('0.01')

    capital_total = Decimal(str(doc.get('capital_financiado') or 0))
    annual_interest = Decimal(str(doc.get('interes_anual') or 0))
    n = int(plazo)

    # mensual interest rate as Decimal (e.g., 12% -> 0.01 per month)
    r = (annual_interest / Decimal('100')) / Decimal('12') if annual_interest != 0 else Decimal('0')

    # Calculate monthly payment (annuity) with Decimal and keep it fixed
    if n > 0:
        if r == 0:
            monthly_payment = (capital_total / n).quantize(CENT, rounding=ROUND_HALF_UP)
        else:
            # monthly_payment = r * pv / (1 - (1 + r) ** -n)
            monthly_payment = (r * capital_total / (Decimal('1') - (Decimal('1') + r) ** (Decimal(-n)))).quantize(CENT, rounding=ROUND_HALF_UP)
    else:
        monthly_payment = Decimal('0.00')

    balance = capital_total

    estado_cuota = STATUS_CUOTA[0]
    
    if is_refinancing == 'Sí':
        estado_cuota = STATUS_CUOTA[1]  # Refinanciado

    for i in range(1, n + 1):
        # calculate interest for this period
        interest = (balance * r).quantize(CENT, rounding=ROUND_HALF_UP)

        # provisional principal is payment - interest
        principal = (monthly_payment - interest).quantize(CENT, rounding=ROUND_HALF_UP)

        # On the last installment, adjust principal/payment to clear the remaining balance
        if i == n:
            principal = balance
            last_payment = (principal + interest).quantize(CENT, rounding=ROUND_HALF_UP)
            this_payment = last_payment
        else:
            this_payment = monthly_payment

        prev_balance = balance
        balance = (balance - principal).quantize(CENT, rounding=ROUND_HALF_UP)

        # calcular fecha de vencimiento: partir de fecha_inicio y sumar i meses
        if fecha_inicio:
            base = getdate(fecha_inicio)
            venc = add_months(base, i)
            if dia_venc:
                last_day = calendar.monthrange(venc.year, venc.month)[1]
                day = min(dia_venc, last_day)
                venc = venc.replace(day=day)
            fecha_venc = venc
        else:
            fecha_venc = None

        row = {
            'doctype': child_doctype,
            'numero_cuota': i,
            # store as date object (Frappe will format as YYYY-MM-DD)
            'fecha_vencimiento_cuota': fecha_venc,
            'capital': float(principal),
            'intereses': float(interest),
            'total_cuota': float(this_payment),
            'saldo_anterior': float(prev_balance),
            'saldo': float(balance),
            'mora': 0.0,
            'status': estado_cuota,
        }
        doc.append(child_fieldname, row)

    
    # actualizar estado del financiamiento y del Activo asociado
    if estado_financiamiento == 'Borrador':
        # normalizar valor de es_refinanciamiento (acepta "Si", "Sí", "si", etc.)
        is_ref = False
        try:
            val = doc.get('es_refinanciamiento')
            if val is not None and str(val).strip().lower() in ('si', 'sí', 's', 'yes', 'y', 'true', '1'):
                is_ref = True
        except Exception:
            is_ref = False

        if is_ref:
            doc.status = 'Refinanciado'
            activo_status = 'Refinanciado'
        else:
            doc.status = 'Activo'
            activo_status = 'Financiado'

        # actualizar estado del Activo ligado (si existe)
        activo_name = doc.get('activos')
        if activo_name:
            try:
                # actualizar directamente en DB para evitar problemas con docstatus del Activo
                frappe.db.set_value('Activos', activo_name, 'status', activo_status)
            except Exception:
                frappe.log_error(frappe.get_traceback(), 'Financiamientos.generar_cuotas - actualizar Activo')

    # guardar y devolver
    doc.save(ignore_permissions=True)
    return {'success': True, 'rows_created': int(plazo)}

TWOPLACES = Decimal('0.01')

def update_overdue_mora():
    """
    Scheduler: actualizar el campo `mora` en Cuota de financiamiento para filas
    con status 'Pendiente' y fecha_vencimiento_cuota < hoy.

    Cálculo: mora = saldo * (mora_diaria / 100) * dias_vencidos
    Redondeo a 2 decimales con ROUND_HALF_UP.
    """
    today = nowdate()
    try:
        rows = frappe.db.sql("""
            SELECT name, total_cuota, fecha_vencimiento_cuota, parent
            FROM `tabCuota de financiamiento`
            WHERE status = %s
              AND fecha_vencimiento_cuota < %s
        """, ('Pendiente', today), as_dict=True)

        for r in rows:
            try:
                if not r.get('fecha_vencimiento_cuota'):
                    continue
                days = (getdate(today) - getdate(r.fecha_vencimiento_cuota)).days
                if days <= 0:
                    continue

                mora_pct = frappe.db.get_value('Financiamientos', r.parent, 'mora_diaria') or 0
                # Use total_cuota for mora calculation per requirements
                total_cuota = Decimal(str(r.get('total_cuota') or 0))

                # mora = total_cuota * (mora_diaria/100) * days
                mora_amount = (total_cuota * (Decimal(str(mora_pct)) / Decimal('100')) * Decimal(days))
                mora_amount = mora_amount.quantize(TWOPLACES, rounding=ROUND_HALF_UP)

                # set_value acepta float/Decimal; guardamos como string/float
                frappe.db.set_value('Cuota de financiamiento', r.name, 'mora', float(mora_amount))
            except Exception:
                frappe.log_error(frappe.get_traceback(), 'update_overdue_mora_row')
        frappe.db.commit()
    except Exception:
        frappe.log_error(frappe.get_traceback(), 'update_overdue_mora')


@frappe.whitelist()
def adoptar_nuevas_politicas(financiamiento_name):
    """
    Actualiza el snapshot de políticas del financiamiento con las políticas
    vigentes en su Configuración de Urbanización.
    """
    doc = frappe.get_doc("Financiamientos", financiamiento_name)
    if not doc.configuracion_financiamiento:
        frappe.throw(_("El financiamiento no tiene una configuración asignada."))

    config_doc = frappe.get_doc("Configuracion de Urbanizacion", doc.configuracion_financiamiento)
    snap_json = json.dumps(config_doc.get_politicas_dict(), indent=2, ensure_ascii=False)
    frappe.db.set_value("Financiamientos", doc.name, "politicas_financieras_snapshot", snap_json, update_modified=False)
    if doc.docstatus == 0:
        doc.save(ignore_permissions=True)
    frappe.msgprint(_("Políticas de cobro actualizadas a la versión vigente de {0}.").format(doc.configuracion_financiamiento))
    return {"success": True}


@frappe.whitelist()
@frappe.validate_and_sanitize_search_inputs
def financiamiento_query(doctype, txt, searchfield, start, page_len, filters):
    if isinstance(filters, str):
        import json
        filters = json.loads(filters)
    filters = filters or {}

    conditions = []
    values = {}

    # Filtro por estado
    if filters.get("status"):
        status_val = filters.get("status")
        if isinstance(status_val, (list, tuple)):
            conditions.append("f.status IN %(status)s")
            values["status"] = tuple(status_val)
        else:
            conditions.append("f.status = %(status)s")
            values["status"] = status_val
    else:
        conditions.append("f.status IN ('Activo', 'Refinanciado')")

    # Filtro por cliente
    if filters.get("customer"):
        conditions.append("f.customer = %(customer)s")
        values["customer"] = filters.get("customer")

    # Búsqueda por texto (txt)
    if txt:
        conditions.append("""(
            f.name LIKE %(txt)s
            OR f.customer LIKE %(txt)s
            OR u.nombre_proyecto LIKE %(txt)s
            OR a.descripcion_lote LIKE %(txt)s
        )""")
        values["txt"] = f"%{txt}%"
        values["txt_start"] = f"{txt}%"
    else:
        values["txt_start"] = "%"

    where_clause = " AND ".join(conditions) if conditions else "1=1"

    query = f"""
        SELECT
            f.name,
            COALESCE(NULLIF(f.customer, ''), ''),
            COALESCE(NULLIF(u.nombre_proyecto, ''), f.urbanizaciones),
            COALESCE(NULLIF(a.descripcion_lote, ''), f.activos)
        FROM `tabFinanciamientos` f
        LEFT JOIN `tabUrbanizaciones` u ON u.name = f.urbanizaciones
        LEFT JOIN `tabActivos` a ON a.name = f.activos
        WHERE {where_clause}
        ORDER BY
            (CASE WHEN f.name LIKE %(txt_start)s THEN 0 ELSE 1 END),
            f.modified DESC
        LIMIT %(start)s, %(page_len)s
    """
    values["start"] = int(start or 0)
    values["page_len"] = int(page_len or 20)

    return frappe.db.sql(query, values)

