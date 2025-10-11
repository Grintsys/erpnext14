# Copyright (c) 2025, Frappe Technologies Pvt. Ltd. and contributors
# For license information, please see license.txt

import frappe
from frappe import _
from frappe.model.document import Document
from frappe.utils import getdate, add_months
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
    pass

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
            'status': STATUS_CUOTA[0],  # Pendiente
        }
        doc.append(child_fieldname, row)

    
    # actualizar estado del financiamiento
    if estado_financiamiento == 'Borrador':
        doc.status = 'Activo'

    # guardar y devolver
    doc.save(ignore_permissions=True)
    return {'success': True, 'rows_created': int(plazo)}
