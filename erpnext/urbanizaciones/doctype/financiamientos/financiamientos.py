# Copyright (c) 2025, Frappe Technologies Pvt. Ltd. and contributors
# For license information, please see license.txt

import frappe
from frappe import _
from frappe.model.document import Document
from frappe.utils import getdate, add_months
import calendar

STATUS_CUOTA = [
    "Pendiente",
    "Pagada",
    "Abono a capital"
    "Vencida",
    "Anulada",
    "Refinanciada",
]

class Financiamientos(Document):
    pass

@frappe.whitelist()
def generar_cuotas(docname):
    """
    Crea filas en la child table según el campo `plazo_meses`.
    Convierte correctamente la fecha de vencimiento desde string a fecha (YYYY-MM-DD).
    """
    doc = frappe.get_doc('Financiamientos', docname)
    plazo = doc.get('plazo_meses') or doc.get('plazo')
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

    cuota_mensual = float(doc.get('cuota_estimada') or 0.0)
    capital_total = float(doc.get('capital_financiado') or 0.0)
    interes_mensual = float(doc.get('interes_anual') or 0.0) / 12 / 100  # convertir a decimal mensual
    intereses = capital_total * interes_mensual
    capital = cuota_mensual - intereses

    for i in range(1, int(plazo) + 1):
        # calcular fecha de vencimiento: partir de fecha_inicio y sumar i meses
        if fecha_inicio:
            base = getdate(fecha_inicio)
            # primera cuota = +1 mes, segunda = +2, ... (ajusta si quieres incluir mes 0)
            venc = add_months(base, i)
            if dia_venc:
                # asegurar día válido para el mes
                last_day = calendar.monthrange(venc.year, venc.month)[1]
                day = min(dia_venc, last_day)
                venc = venc.replace(day=day)
            fecha_venc_str = venc.strftime('%Y-%m-%d')
        else:
            fecha_venc_str = None

        row = {
            'doctype': child_doctype,
            'numero_cuota': i,
            'fecha_vencimiento_cuota': fecha_venc_str,
            'capital': capital,
            'intereses': intereses,
            'total_cuota': cuota_mensual,
            'saldo_anterior': capital_total,
            'saldo': capital_total - capital,
            'status': STATUS_CUOTA[0],  # Pendiente
        }
        doc.append(child_fieldname, row)

        capital_total -= capital
        intereses = capital_total * interes_mensual
        capital = cuota_mensual - intereses

    # guardar y devolver
    doc.save(ignore_permissions=True)
    return {'success': True, 'rows_created': int(plazo)}
