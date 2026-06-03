# -*- coding: utf-8 -*-
# Copyright (c) 2026, Grintsys and contributors
# For license information, please see license.txt

import frappe
from frappe import _
from frappe.utils import flt
from erpnext.controllers.accounts_controller import AccountsController

class PlantillaPagoProveedores(AccountsController):
    def validate(self):
        self.validate_company_currency()
        self.validate_bridge_account()
        self.calculate_total()
        self.validate_strict_allocations()

    def validate_company_currency(self):
        company_currency = frappe.get_cached_value("Company", self.company, "default_currency")
        if self.currency != company_currency:
            frappe.throw(_("En esta versión, la plantilla obliga a trabajar en moneda local ({0}).").format(company_currency))

    def validate_bridge_account(self):
        if not self.bridge_account:
            return
            
        acc = frappe.get_cached_value("Account", self.bridge_account, ["report_type", "account_type"], as_dict=1)
        if not acc:
            frappe.throw(_("Cuenta {0} no encontrada.").format(self.bridge_account))
            
        if acc.report_type == "Profit and Loss":
            frappe.throw(_("La cuenta puente ({0}) es de Gastos/Ingresos (P&L). Debe ser una cuenta transitoria del Balance General.").format(self.bridge_account))
        if acc.account_type in ["Payable", "Receivable"]:
            frappe.throw(_("La cuenta puente ({0}) no puede tener tipo Payable o Receivable. Use cuentas Pasivas Transitorias o Banco.").format(self.bridge_account))

    def calculate_total(self):
        total = 0.0
        for row in self.payment_details:
            total += flt(row.allocated_amount)
        self.total_allocated_amount = total

    def validate_strict_allocations(self):
        if not self.payment_details:
            frappe.throw(_("La tabla de detalles de pago no puede estar vacía."))

        seen_references = set()

        for row in self.payment_details:
            if flt(row.allocated_amount) <= 0:
                frappe.throw(_("Fila {0}: El monto a pagar de la referencia {1} debe ser mayor a cero.").format(row.idx, row.reference_name))
            
            key = (row.reference_doctype, row.reference_name)
            if key in seen_references:
                frappe.throw(_("Fila {0}: La factura {1} está duplicada dentro de la misma plantilla.").format(row.idx, row.reference_name))
            seen_references.add(key)

            invoice = frappe.db.get_value(
                row.reference_doctype, 
                row.reference_name, 
                ["docstatus", "outstanding_amount", "supplier", "company", "currency", "credit_to"], 
                as_dict=1
            )

            if not invoice:
                frappe.throw(_("Fila {0}: El documento {1} no existe o no pudo ser leído.").format(row.idx, row.reference_name))
                
            if invoice.docstatus != 1:
                frappe.throw(_("Fila {0}: El documento {1} no tiene estado 'Validado'.").format(row.idx, row.reference_name))
            if flt(invoice.outstanding_amount) <= 0.009:
                frappe.throw(_("Fila {0}: El documento {1} ya no tiene saldo pendiente válido para pago.").format(row.idx, row.reference_name))
            if invoice.supplier != row.supplier:
                frappe.throw(_("Inconsistencia en Fila {0}: La factura pertenece a {1}, no al proveedor {2} de la línea.").format(row.idx, invoice.supplier, row.supplier))
            if invoice.company != self.company:
                frappe.throw(_("Inconsistencia en Fila {0}: La factura y la plantilla son de empresas diferentes ({1}).").format(row.idx, invoice.company))
            if invoice.currency != self.currency:
                frappe.throw(_("Inconsistencia en Fila {0}: La factura usa moneda {1}, no {2}.").format(row.idx, invoice.currency, self.currency))
            if invoice.credit_to != row.payable_account:
                frappe.throw(_("Fila {0}: Cuenta de pasivo informada no coincide con cuenta nativa contabilizada de la Factura ({1}).").format(row.idx, invoice.credit_to))

            if flt(row.allocated_amount) - flt(invoice.outstanding_amount) > 0.009:
                frappe.throw(_("Fila {0}: Intento de sobrepago. El monto ({1}) supera saldo pendiente ({2}) de {3}.").format(
                    row.idx, row.allocated_amount, invoice.outstanding_amount, row.reference_name
                ))

    def before_cancel(self):
        if self.clearance_date:
            frappe.throw(_("Cancelación denegada. La Plantilla ya fue conciliada bancariamente el {0}. Anule la conciliación para proceder.").format(self.clearance_date))

    def on_submit(self):
        self.make_gl_entries()

    def on_cancel(self):
        self.make_gl_entries(cancel=1)

    def make_gl_entries(self, cancel=0):
        from erpnext.accounts.general_ledger import make_gl_entries

        gl_entries = []

        # 1. Total descargado vía Cuenta Puente Transitoria (Crédito)
        gl_entries.append(
            self.get_gl_dict({
                "account": self.bridge_account,
                "against": "Múltiples Proveedores",
                "credit": self.total_allocated_amount,
                "credit_in_account_currency": self.total_allocated_amount,
                "remarks": _("Total Planilla Masiva. Ref: {0}").format(self.bank_reference),
                "voucher_type": self.doctype,
                "voucher_no": self.name
            }, account_currency=self.currency, item=self)
        )

        # 2. Descargo iterativo CxP y Generación de Payment Ledger (Débito)
        for row in self.payment_details:
            gl_entries.append(
                self.get_gl_dict({
                    "account": row.payable_account,
                    "party_type": "Supplier",
                    "party": row.supplier,
                    "against": self.bridge_account,
                    "debit": flt(row.allocated_amount),
                    "debit_in_account_currency": flt(row.allocated_amount),
                    "against_voucher_type": row.reference_doctype,
                    "against_voucher": row.reference_name,
                    "remarks": _("Abono s/Factura {0} (Planilla Lote: {1})").format(row.reference_name, self.bank_reference),
                    "voucher_type": self.doctype,
                    "voucher_no": self.name
                }, account_currency=self.currency, item=self)
            )

        make_gl_entries(gl_entries, cancel=cancel, update_outstanding="Yes")


@frappe.whitelist()
def get_pending_invoices(company, currency, supplier=None, bill_no=None, excluded_invoices=None):
    import json
    
    if isinstance(excluded_invoices, str):
        excluded_invoices = json.loads(excluded_invoices)
        
    filters = {
        "docstatus": 1,
        "company": company,
        "currency": currency,
        "outstanding_amount": (">", 0.009)
    }
    
    if supplier:
        filters["supplier"] = supplier
        
    if bill_no:
        filters["bill_no"] = ("like", f"%{bill_no}%")
        
    if excluded_invoices:
        filters["name"] = ("not in", excluded_invoices)

    invoices = frappe.get_all("Purchase Invoice", 
        filters=filters,
        fields=["name", "supplier", "bill_no", "posting_date", "due_date", "outstanding_amount", "credit_to"],
        order_by="posting_date asc, name asc"
    )
    
    return invoices

@frappe.whitelist()
@frappe.validate_and_sanitize_search_inputs
def get_invoices_for_payment_details(doctype, txt, searchfield, start, page_len, filters):
    # This explicit SQL query ensures exact behavior bypassing standard query parser limits
    from erpnext.controllers.queries import get_match_cond
    
    company = filters.get("company")
    supplier = filters.get("supplier")
    currency = filters.get("currency")
    excluded = filters.get("excluded_invoices")
    
    if isinstance(excluded, str):
        import json
        excluded = json.loads(excluded)
        
    conditions = "docstatus = 1 and outstanding_amount > 0.009"
    
    if company:
        conditions += f" and company = {frappe.db.escape(company)}"
    if supplier:
        conditions += f" and supplier = {frappe.db.escape(supplier)}"
    if currency:
        conditions += f" and currency = {frappe.db.escape(currency)}"
        
    if excluded:
        excluded_str = ", ".join([frappe.db.escape(n) for n in excluded])
        conditions += f" and name not in ({excluded_str})"

    if txt:
        conditions += f" and (name like {frappe.db.escape('%'+txt+'%')} or bill_no like {frappe.db.escape('%'+txt+'%')})"

    match_cond = get_match_cond(doctype)
    if match_cond:
        conditions += f" and {match_cond}"

    return frappe.db.sql(f"""
        select name, supplier, bill_no, base_grand_total, outstanding_amount
        from `tabPurchase Invoice`
        where {conditions}
        order by posting_date asc, name asc
        limit {start}, {page_len}
    """)
