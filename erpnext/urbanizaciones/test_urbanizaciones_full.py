import frappe
from frappe.utils import flt, today

def test_full_reversal_and_lifecycle():
    print("=== INICIANDO PRUEBAS DE REVERSIÓN Y CICLO DE VIDA URBANIZACIONES ===")

    # 1. Verificar hooks
    from erpnext.urbanizaciones.sales_invoice_events import (
        process_financing_on_submit,
        process_financing_on_cancel,
        process_financing_on_trash
    )
    print("[1/5] Hooks y manejadores importados exitosamente.")

    # 2. Setup datos de prueba
    # Urbanización
    urb_name = "URB-TEST-VERIFY"
    if not frappe.db.exists("Urbanizaciones", urb_name):
        urb = frappe.get_doc({
            "doctype": "Urbanizaciones",
            "naming_series": "URB-.#####",
            "nombre_proyecto": "Proyecto Verificación",
            "direccion": "Tegucigalpa"
        }).insert(ignore_permissions=True)
        urb_name = urb.name
    print(f"[2/5] Urbanización creada: {urb_name}")

    # Activo
    act_name = "LOT-TEST-VERIFY"
    if not frappe.db.exists("Activos", act_name):
        act = frappe.get_doc({
            "doctype": "Activos",
            "naming_series": "LOT-.#####",
            "urbanizaciones": urb_name,
            "descripcion_lote": "Lote 99 Bloque Z",
            "precio": 100000.0,
            "status": "Disponible"
        }).insert(ignore_permissions=True)
        act_name = act.name
    print(f"      Activo creado: {act_name}, status={frappe.db.get_value('Activos', act_name, 'status')}")

    # Configuración
    conf_name = "CONF-TEST-VERIFY"
    if not frappe.db.exists("Configuracion de Urbanizacion", conf_name):
        conf = frappe.get_doc({
            "doctype": "Configuracion de Urbanizacion",
            "naming_series": "CONF-.#####",
            "interes_anual": 12.0,
            "mora_diaria": 0.05,
            "vencimiento_cuota": 15,
            "item_cuota": frappe.db.get_value("Item", {}, "name") or "Servicio Cuota",
            "item_mora": frappe.db.get_value("Item", {}, "name") or "Servicio Mora",
            "item_adelantos": frappe.db.get_value("Item", {}, "name") or "Servicio Adelanto"
        }).insert(ignore_permissions=True)
        conf_name = conf.name
    print(f"      Configuración creada: {conf_name}")

    # Cliente
    customer_name = frappe.db.get_value("Customer", {}, "name")
    if not customer_name:
        cust = frappe.get_doc({
            "doctype": "Customer",
            "customer_name": "Cliente Prueba Verificacion"
        }).insert(ignore_permissions=True)
        customer_name = cust.name

    # Financiamiento
    fin = frappe.get_doc({
        "doctype": "Financiamientos",
        "customer": customer_name,
        "urbanizaciones": urb_name,
        "activos": act_name,
        "fecha_inicio": today(),
        "configuracion_financiamiento": conf_name,
        "monto_contrato": 100000.0,
        "prima": 10000.0,
        "capital_financiado": 90000.0,
        "plazo_meses": 2,
        "interes_anual": 12.0,
        "mora_diaria": 0.05,
        "dia_vencimiento_cuota": 15,
        "centro_costo": frappe.db.get_value("Cost Center", {"is_group": 0}, "name")
    }).insert(ignore_permissions=True)

    from erpnext.urbanizaciones.doctype.financiamientos.financiamientos import generar_cuotas
    generar_cuotas(fin.name)

    fin.reload()
    assert len(fin.cuotas) == 2, "Deben generarse 2 cuotas"
    print(f"[3/5] Financiamiento generado: {fin.name}, Saldo Inicial = {fin.saldo_actual}, Activo status = {frappe.db.get_value('Activos', act_name, 'status')}")

    cuota1 = fin.cuotas[0]
    cuota2 = fin.cuotas[1]

    # Simular Generar Factura para Cuota 1 y Cuota 2
    dummy_gf1 = frappe._dict({
        "name": "GF-TEST-001",
        "financiamiento": fin.name,
        "date_quote_financing": cuota1.fecha_vencimiento_cuota,
        "monto_recibido": cuota1.total_cuota,
        "total_cuota": cuota1.total_cuota,
        "total_mora": 0,
        "aplicar": ""
    })
    dummy_gf2 = frappe._dict({
        "name": "GF-TEST-002",
        "financiamiento": fin.name,
        "date_quote_financing": cuota2.fecha_vencimiento_cuota,
        "monto_recibido": cuota2.total_cuota,
        "total_cuota": cuota2.total_cuota,
        "total_mora": 0,
        "aplicar": ""
    })

    gf_mock_dict = {
        "GF-TEST-001": dummy_gf1,
        "GF-TEST-002": dummy_gf2
    }
    frappe.db.exists = lambda dt, dn: True if dt == "Generar Factura" and dn in gf_mock_dict else frappe.db.__class__.exists(frappe.db, dt, dn)
    frappe.get_doc_orig = frappe.get_doc
    def mock_get_doc(dt, dn=None):
        if dt == "Generar Factura" and dn in gf_mock_dict:
            return gf_mock_dict[dn]
        return frappe.get_doc_orig(dt, dn)
    frappe.get_doc = mock_get_doc

    dummy_sinv1 = frappe._dict({
        "doctype": "Sales Invoice",
        "name": "ACC-SINV-TEST-001",
        "invoice_generate": "GF-TEST-001",
        "paid_amount": cuota1.total_cuota,
        "change_amount": 0,
        "grand_total": cuota1.total_cuota,
        "docstatus": 1
    })

    # PROBAR SUBMIT DE FACTURA 1
    process_financing_on_submit(dummy_sinv1)
    cuota1_status = frappe.db.get_value("Cuota de financiamiento", cuota1.name, "status")
    cuota1_sinv = frappe.db.get_value("Cuota de financiamiento", cuota1.name, "sales_invoice")
    fin.reload()
    print(f"      [Submit Factura 1] Cuota 1 status = {cuota1_status}, Factura vinculada = {cuota1_sinv}, Saldo financiamiento = {fin.saldo_actual}")
    assert cuota1_status == "Pagado", "La cuota 1 debe estar Pagado"
    assert cuota1_sinv == "ACC-SINV-TEST-001", "La cuota 1 debe tener la factura vinculada"

    # PROBAR CANCELACIÓN DE FACTURA (ON_CANCEL)
    dummy_sinv1.docstatus = 2
    process_financing_on_cancel(dummy_sinv1)
    cuota1_status_after_cancel = frappe.db.get_value("Cuota de financiamiento", cuota1.name, "status")
    cuota1_sinv_after_cancel = frappe.db.get_value("Cuota de financiamiento", cuota1.name, "sales_invoice")
    fin.reload()
    print(f"[4/5] [Cancel Factura 1] Cuota 1 status revertido = {cuota1_status_after_cancel}, Factura = {cuota1_sinv_after_cancel}, Saldo restaurado = {fin.saldo_actual}")
    assert cuota1_status_after_cancel == "Pendiente", "La cuota 1 debe regresar a Pendiente"
    assert cuota1_sinv_after_cancel is None or cuota1_sinv_after_cancel == "", "El enlace a la factura debe limpiarse"

    # PROBAR ON_TRASH
    process_financing_on_trash(dummy_sinv1)
    print("      [Trash Factura 1] Limpieza de asientos y enlaces ejecutada sin errores.")

    # PROBAR COMPLETADO DE FINANCIAMIENTO Y VENTA DE ACTIVO
    # Pagar Cuota 1
    dummy_sinv1.docstatus = 1
    process_financing_on_submit(dummy_sinv1)

    # Pagar Cuota 2
    dummy_sinv2 = frappe._dict({
        "doctype": "Sales Invoice",
        "name": "ACC-SINV-TEST-002",
        "invoice_generate": "GF-TEST-002",
        "paid_amount": cuota2.total_cuota,
        "change_amount": 0,
        "grand_total": cuota2.total_cuota,
        "docstatus": 1
    })
    process_financing_on_submit(dummy_sinv2)

    fin.reload()
    activo_status_final = frappe.db.get_value("Activos", act_name, "status")
    print(f"[5/5] [Liquidación Final] Financiamiento status = {fin.status}, Activo status = {activo_status_final}")
    assert fin.status == "Completado", "El financiamiento debe estar Completado"
    assert activo_status_final == "Vendido", "El activo debe estar Vendido"

    # Revertir Cuota 2 -> El financiamiento debe reabrir a Activo y el Activo a Financiado
    dummy_sinv2.docstatus = 2
    process_financing_on_cancel(dummy_sinv2)
    fin.reload()
    activo_status_reopened = frappe.db.get_value("Activos", act_name, "status")
    print(f"      [Reversión de Liquidación] Financiamiento status = {fin.status}, Activo status = {activo_status_reopened}")
    assert fin.status == "Activo", "El financiamiento debe reabrirse a Activo"
    assert activo_status_reopened == "Financiado", "El activo debe regresar a Financiado"

    # Restaurar mock
    frappe.get_doc = frappe.get_doc_orig

    # Limpiar datos de prueba
    frappe.db.sql("DELETE FROM `tabCuota de financiamiento` WHERE parent = %s", fin.name)
    frappe.db.sql("DELETE FROM `tabFinanciamientos` WHERE name = %s", fin.name)
    frappe.db.sql("DELETE FROM `tabActivos` WHERE name = %s", act_name)
    frappe.db.sql("DELETE FROM `tabUrbanizaciones` WHERE name = %s", urb_name)
    frappe.db.sql("DELETE FROM `tabConfiguracion de Urbanizacion` WHERE name = %s", conf_name)
    frappe.db.commit()

    print("\n✅ TODAS LAS PRUEBAS DE VERIFICACIÓN PASARON EXITOSAMENTE (100% OK).")
