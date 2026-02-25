import frappe

def run():
    # Bank Account modifications
    ba = frappe.get_doc("DocType", "Bank Account")
    if not any(f.fieldname == "check_correlative" for f in ba.fields):
        ba.append("fields", {
            "fieldname": "check_correlative",
            "fieldtype": "Int",
            "label": "Correlativo de Cheques",
            "default": "0",
            "insert_after": "bank_account_no"
        })
        ba.save()
        print("Bank Account saved.")

    # Bank Transaction modifications
    bt = frappe.get_doc("DocType", "Bank Transaction")
    
    # entity_type
    if not any(f.fieldname == "entity_type" for f in bt.fields):
        bt.append("fields", {
            "fieldname": "entity_type",
            "fieldtype": "Select",
            "label": "Tipo de Entidad",
            "options": "Cliente\nProveedor\nEmpleado\nTercero",
            "insert_after": "date"
        })
    
    # beneficiary_type (hidden, to drive Dynamic Link)
    if not any(f.fieldname == "beneficiary_type" for f in bt.fields):
        bt.append("fields", {
            "fieldname": "beneficiary_type",
            "fieldtype": "Data",
            "label": "Beneficiary Type",
            "hidden": 1,
            "insert_after": "entity_type"
        })
    
    # beneficiary
    if not any(f.fieldname == "beneficiary" for f in bt.fields):
        bt.append("fields", {
            "fieldname": "beneficiary",
            "fieldtype": "Dynamic Link",
            "label": "Beneficiario",
            "options": "beneficiary_type",
            "insert_after": "beneficiary_type"
        })
        
    # transaction_type -> transform to Select
    for f in bt.fields:
        if f.fieldname == "transaction_type":
            f.fieldtype = "Select"
            f.options = "Cheque\nTransferencia\nDébito\nDepósito\nCrédito"
            break
            
    # Totals Section
    if not any(f.fieldname == "totals_section" for f in bt.fields):
        bt.append("fields", {
            "fieldname": "totals_section",
            "fieldtype": "Section Break",
            "label": "Totales",
            "insert_after": "custom_journal_entries"
        })
        
    # total_debit, total_credit, difference
    if not any(f.fieldname == "total_debit" for f in bt.fields):
        bt.append("fields", {
            "fieldname": "total_debit",
            "fieldtype": "Currency",
            "label": "Total Debe",
            "options": "currency",
            "read_only": 1,
            "insert_after": "totals_section"
        })
        
    if not any(f.fieldname == "total_credit" for f in bt.fields):
        bt.append("fields", {
            "fieldname": "total_credit",
            "fieldtype": "Currency",
            "label": "Total Haber",
            "options": "currency",
            "read_only": 1,
            "insert_after": "total_debit"
        })
        
    if not any(f.fieldname == "difference" for f in bt.fields):
        bt.append("fields", {
            "fieldname": "difference",
            "fieldtype": "Currency",
            "label": "Diferencia",
            "options": "currency",
            "read_only": 1,
            "insert_after": "total_credit"
        })
        
    bt.save()
    frappe.db.commit()
    print("Bank Transaction saved.")
