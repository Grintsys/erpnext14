# Copyright (c) 2019, Frappe Technologies Pvt. Ltd. and contributors
# For license information, please see license.txt

import frappe
from frappe.model.docstatus import DocStatus
from frappe.utils import flt

from erpnext.controllers.status_updater import StatusUpdater


class BankTransaction(StatusUpdater):
	def after_insert(self):
		self.unallocated_amount = abs(flt(self.withdrawal) - flt(self.deposit))

	def on_submit(self):
		self.clear_linked_payment_entries()
		self.set_status()

		if frappe.db.get_single_value("Accounts Settings", "enable_party_matching"):
			self.auto_set_party()

	_saving_flag = False

	def on_update(self):
		self.sync_transit_balances()

	# nosemgrep: frappe-semgrep-rules.rules.frappe-modifying-but-not-comitting
	def on_update_after_submit(self):
		"Run on save(). Avoid recursion caused by multiple saves"
		if not self._saving_flag:
			self._saving_flag = True
			self.clear_linked_payment_entries()
			self.update_allocations()
			self._saving_flag = False

	def on_cancel(self):
		if self.ref_journal_entry:
			frappe.throw(frappe._("Please delete the linked Journal Entry before cancelling this transaction."))
			
		self.clear_linked_payment_entries(for_cancel=True)
		self.set_status(update=True)
		self.sync_transit_balances(is_cancelled=True)

	def sync_transit_balances(self, is_cancelled=False):
		if not self.bank_account: 
			return
		
		try:
			old_doc = self.get_doc_before_save()
		except Exception:
			old_doc = None

		old_status = old_doc.custom_estado_bancario if old_doc else None
		new_status = self.custom_estado_bancario

		old_is_valid = old_doc.docstatus != 2 if old_doc else True
		new_is_valid = self.docstatus != 2 and not is_cancelled

		# Comprobamos un estado de "tránsito" (cualquier estado diferente a Conciliado y válido)
		old_in_transit = old_status in ["Tránsito", "Pre-conciliado"] and old_is_valid
		new_in_transit = new_status in ["Tránsito", "Pre-conciliado"] and new_is_valid

		if old_in_transit == new_in_transit:
			if old_in_transit:
				old_dep = flt(old_doc.deposit) if old_doc else 0.0
				new_dep = flt(self.deposit)
				old_with = flt(old_doc.withdrawal) if old_doc else 0.0
				new_with = flt(self.withdrawal)
				
				diff_dep = new_dep - old_dep
				diff_with = new_with - old_with
				
				if diff_dep != 0 or diff_with != 0:
					self._update_bank_account(self.bank_account, diff_dep, diff_with)
			return

		if new_in_transit and not old_in_transit:
			# Sumar nuevo monto completo
			self._update_bank_account(self.bank_account, flt(self.deposit), flt(self.withdrawal))
		elif old_in_transit and not new_in_transit:
			# Revertir viejo monto completo
			old_dep = flt(old_doc.deposit) if old_doc else flt(self.deposit)
			old_with = flt(old_doc.withdrawal) if old_doc else flt(self.withdrawal)
			self._update_bank_account(self.bank_account, -old_dep, -old_with)

	def _update_bank_account(self, bank_account_name, delta_deposit, delta_withdrawal):
		acc = frappe.get_doc("Bank Account", bank_account_name)
		acc.deposits_in_transit = flt(acc.deposits_in_transit) + delta_deposit
		acc.deferred_debits = flt(acc.deferred_debits) + delta_withdrawal
		acc.current_balance = flt(acc.last_reconciliation_balance) + flt(acc.deposits_in_transit) - flt(acc.deferred_debits)
		
		# set de base de datos sin disparar hooks costosos save
		acc.db_set('deposits_in_transit', acc.deposits_in_transit)
		acc.db_set('deferred_debits', acc.deferred_debits)
		acc.db_set('current_balance', acc.current_balance)

	@frappe.whitelist()
	def make_journal_entry(self):
		if not self.custom_journal_entries:
			frappe.throw(frappe._("Please add an Account in 'Asiento Contable' table before creating Journal Entry"))

		if self.ref_journal_entry:
			frappe.throw(frappe._("Journal Entry already exists for this transaction"))

		# 1. Corrección en la Creación (Account)
		# "Account: Debe ser exactamente el valor del campo bank_account del doctype padre."
		# Nota: Si el campo bank_account apunta a un DocType 'Bank Account', debemos sacar la cuenta contable de ahí.
		# Si el usuario insiste en que USE el valor directo, asumimos que bank_account YA es la cuenta contable (Link: Account).
		# PERO el JSON dice que es Link: Bank Account. Así que usamos get_value.
		# Si falla, lanzamos error claro.
		
		bank_gl_account = frappe.db.get_value("Bank Account", self.bank_account, "account")
		if not bank_gl_account:
			# Fallback: Si no tiene cuenta vinculada, quizás el campo bank_account mismo es la cuenta? 
			# Intentamos validar si self.bank_account es un Account válido.
			if frappe.db.exists("Account", self.bank_account):
				bank_gl_account = self.bank_account
			else:
				frappe.throw(frappe._("Bank Account {0} does not have a linked GL Account").format(self.bank_account))

		je = frappe.new_doc("Journal Entry")
		je.voucher_type = "Bank Entry"
		je.posting_date = self.date
		je.company = self.company
		je.cheque_no = self.reference_number
		je.cheque_date = self.date
		je.user_remark = self.description
		je.reference_type = "Bank Transaction"
		je.reference_name = self.name
		je.multi_currency = 1 # Force multi-currency to handle different currencies if needed

		# 2. Lógica de Montos
		deposit = flt(self.deposit)
		withdrawal = flt(self.withdrawal)

		# Row 1: Bank Account
		bank_row = {
			"account": bank_gl_account,
			"cost_center": self.custom_journal_entries[0].cost_center if self.custom_journal_entries else None,
			"reference_type": "Bank Transaction",
			"reference_name": self.name
		}
		
		# Si deposit > 0: Asignar a debit_in_account_currency
		if deposit > 0:
			bank_row["debit_in_account_currency"] = deposit
			bank_row["debit"] = deposit # Base currency assumption or handled by JE
			bank_row["credit_in_account_currency"] = 0
			bank_row["credit"] = 0
		
		# Si withdrawal > 0: Asignar a credit_in_account_currency
		elif withdrawal > 0:
			bank_row["credit_in_account_currency"] = withdrawal
			bank_row["credit"] = withdrawal
			bank_row["debit_in_account_currency"] = 0
			bank_row["debit"] = 0

		je.append("accounts", bank_row)

		# Row 2: Contra Account (from first row of custom_journal_entries)
		contra_row_data = self.custom_journal_entries[0]
		
		contra_row = {
			"account": contra_row_data.account,
			"party_type": contra_row_data.party_type,
			"party": contra_row_data.party,
			"cost_center": contra_row_data.cost_center,
			"project": contra_row_data.project,
			"reference_type": "Bank Transaction",
			"reference_name": self.name
		}

		# Balancing logic (Opposite of Bank Row)
		if deposit > 0:
			contra_row["credit_in_account_currency"] = deposit
			contra_row["credit"] = deposit
			contra_row["debit_in_account_currency"] = 0
			contra_row["debit"] = 0
		elif withdrawal > 0:
			contra_row["debit_in_account_currency"] = withdrawal
			contra_row["debit"] = withdrawal
			contra_row["credit_in_account_currency"] = 0
			contra_row["credit"] = 0

		je.append("accounts", contra_row)

		je.save()
		je.submit()

		frappe.db.set_value(self.doctype, self.name, "ref_journal_entry", je.name)
		
		return je.name

	@frappe.whitelist()
	def delete_journal_entry(self):
		# 1. Identificar y Desvincular Bank Transaction
		if not self.ref_journal_entry:
			frappe.throw(frappe._("No Journal Entry linked to this transaction"))

		journal_id = self.ref_journal_entry
		
		# Paso 1: Romper Vínculo en Bank Transaction (DB directo y Commit)
		# "Antes de cualquier otra acción, usa frappe.db.set_value... y ejecuta commit"
		frappe.db.set_value("Bank Transaction", self.name, "ref_journal_entry", None)
		frappe.db.commit()

		# Validar existencia antes de proceder con limpieza
		if not frappe.db.exists("Journal Entry", journal_id):
			self.reload()
			return

		try:
			# Paso 2: Limpieza de Referencias en Journal Entry (Accounts)
			# "Asegúrate de que el campo reference_name (que apunta a la Bank Transaction) se establezca en None"
			frappe.db.sql("""
				UPDATE `tabJournal Entry Account`
				SET reference_type=NULL, reference_name=NULL
				WHERE parent=%s AND reference_type='Bank Transaction'
			""", journal_id)
			frappe.db.commit() # Asegurar cambios

			# Paso 3: Cancelación y Borrado "Silencioso"
			# "Forzar la cancelación de los GL Entries vinculados primero"
			frappe.db.sql("""DELETE FROM `tabGL Entry` WHERE voucher_type='Journal Entry' AND voucher_no=%s""", journal_id)

			# "Cancelar y borrar el Journal Entry ignorando los enlaces (links)"
			journal_doc = frappe.get_doc("Journal Entry", journal_id)
			journal_doc.db_set("docstatus", 2) # Forzar estado cancelado en DB
			
			# Eliminar Journal Entry forzosamente
			frappe.delete_doc("Journal Entry", journal_id, ignore_permissions=True, force=True)
		
		except Exception as e:
			frappe.log_error(title="Force Delete Journal Entry Failed", message=str(e))
			# No lanzamos error para no bloquear la UI, ya que el vínculo principal se rompió en el Paso 1
			frappe.msgprint(__("Warning: Could not fully delete linked Journal Entry, but it has been unlinked. Error: {0}").format(str(e)))

		# Finalización
		self.reload()

	def get_indicator(self):
		if self.docstatus == 0:
			return frappe._("Draft"), "blue"
		elif self.docstatus == 1:
			return frappe._("Submitted"), "green"
		elif self.docstatus == 2:
			return frappe._("Cancelled"), "red"

	def update_allocations(self):
		"The doctype does not allow modifications after submission, so write to the db direct"
		if self.payment_entries:
			allocated_amount = sum(p.allocated_amount for p in self.payment_entries)
		else:
			allocated_amount = 0.0

		unallocated_amount = abs(flt(self.withdrawal) - flt(self.deposit)) - allocated_amount

		self.db_set("allocated_amount", flt(allocated_amount, self.precision("allocated_amount")))
		self.db_set("unallocated_amount", flt(unallocated_amount, self.precision("unallocated_amount")))
		self.reload()
		self.set_status(update=True)

	def add_payment_entries(self, vouchers):
		"Add the vouchers with zero allocation. Save() will perform the allocations and clearance"
		if 0.0 >= self.unallocated_amount:
			frappe.throw(frappe._("Bank Transaction {0} is already fully reconciled").format(self.name))

		added = False
		for voucher in vouchers:
			# Can't add same voucher twice
			found = False
			for pe in self.payment_entries:
				if (
					pe.payment_document == voucher["payment_doctype"]
					and pe.payment_entry == voucher["payment_name"]
				):
					found = True

			if not found:
				pe = {
					"payment_document": voucher["payment_doctype"],
					"payment_entry": voucher["payment_name"],
					"allocated_amount": 0.0,  # Temporary
				}
				self.append("payment_entries", pe)
				added = True

		# runs on_update_after_submit
		if added:
			self.save()

	def allocate_payment_entries(self):
		"""Refactored from bank reconciliation tool.
		Non-zero allocations must be amended/cleared manually
		Get the bank transaction amount (b) and remove as we allocate
		For each payment_entry if allocated_amount == 0:
		- get the amount already allocated against all transactions (t), need latest date
		- get the voucher amount (from gl) (v)
		- allocate (a = v - t)
		    - a = 0: should already be cleared, so clear & remove payment_entry
		    - 0 < a <= u: allocate a & clear
		    - 0 < a, a > u: allocate u
		    - 0 > a: Error: already over-allocated
		- clear means: set the latest transaction date as clearance date
		"""
		remaining_amount = self.unallocated_amount
		for payment_entry in self.payment_entries:
			if payment_entry.allocated_amount == 0.0:
				unallocated_amount, should_clear, latest_transaction = get_clearance_details(
					self, payment_entry
				)

				if 0.0 == unallocated_amount:
					if should_clear:
						latest_transaction.clear_linked_payment_entry(payment_entry)
					self.db_delete_payment_entry(payment_entry)

				elif remaining_amount <= 0.0:
					self.db_delete_payment_entry(payment_entry)

				elif 0.0 < unallocated_amount and unallocated_amount <= remaining_amount:
					payment_entry.db_set("allocated_amount", unallocated_amount)
					remaining_amount -= unallocated_amount
					if should_clear:
						latest_transaction.clear_linked_payment_entry(payment_entry)

				elif 0.0 < unallocated_amount and unallocated_amount > remaining_amount:
					payment_entry.db_set("allocated_amount", remaining_amount)
					remaining_amount = 0.0

				elif 0.0 > unallocated_amount:
					self.db_delete_payment_entry(payment_entry)
					frappe.throw(frappe._("Voucher {0} is over-allocated by {1}").format(unallocated_amount))

		self.reload()

	def db_delete_payment_entry(self, payment_entry):
		frappe.db.delete("Bank Transaction Payments", {"name": payment_entry.name})

	@frappe.whitelist()
	def remove_payment_entries(self):
		for payment_entry in self.payment_entries:
			self.remove_payment_entry(payment_entry)
		# runs on_update_after_submit
		self.save()

	def remove_payment_entry(self, payment_entry):
		"Clear payment entry and clearance"
		self.clear_linked_payment_entry(payment_entry, for_cancel=True)
		self.remove(payment_entry)

	def clear_linked_payment_entries(self, for_cancel=False):
		if for_cancel:
			for payment_entry in self.payment_entries:
				self.clear_linked_payment_entry(payment_entry, for_cancel)
		else:
			self.allocate_payment_entries()

	def clear_linked_payment_entry(self, payment_entry, for_cancel=False):
		clearance_date = None if for_cancel else self.date
		set_voucher_clearance(
			payment_entry.payment_document, payment_entry.payment_entry, clearance_date, self
		)

	def auto_set_party(self):
		from erpnext.accounts.doctype.bank_transaction.auto_match_party import AutoMatchParty

		if self.party_type and self.party:
			return

		result = AutoMatchParty(
			bank_party_account_number=self.bank_party_account_number,
			bank_party_iban=self.bank_party_iban,
			bank_party_name=self.bank_party_name,
			description=self.description,
			deposit=self.deposit,
		).match()


		if result:
			party_type, party = result
			frappe.db.set_value(
				"Bank Transaction", self.name, field={"party_type": party_type, "party": party}
			)




@frappe.whitelist()
def get_doctypes_for_bank_reconciliation():
	"""Get Bank Reconciliation doctypes from all the apps"""
	return frappe.get_hooks("bank_reconciliation_doctypes")


def get_clearance_details(transaction, payment_entry):
	"""
	There should only be one bank gle for a voucher.
	Could be none for a Bank Transaction.
	But if a JE, could affect two banks.
	Should only clear the voucher if all bank gles are allocated.
	"""
	gl_bank_account = frappe.db.get_value("Bank Account", transaction.bank_account, "account")
	gles = get_related_bank_gl_entries(payment_entry.payment_document, payment_entry.payment_entry)
	bt_allocations = get_total_allocated_amount(payment_entry.payment_document, payment_entry.payment_entry)

	unallocated_amount = min(
		transaction.unallocated_amount,
		get_paid_amount(payment_entry, transaction.currency, gl_bank_account),
	)
	unmatched_gles = len(gles)
	latest_transaction = transaction
	for gle in gles:
		if gle["gl_account"] == gl_bank_account:
			if gle["amount"] <= 0.0:
				frappe.throw(
					frappe._("Voucher {0} value is broken: {1}").format(
						payment_entry.payment_entry, gle["amount"]
					)
				)

			unmatched_gles -= 1
			unallocated_amount = gle["amount"]
			for a in bt_allocations:
				if a["gl_account"] == gle["gl_account"]:
					unallocated_amount = gle["amount"] - a["total"]
					if frappe.utils.getdate(transaction.date) < a["latest_date"]:
						latest_transaction = frappe.get_doc("Bank Transaction", a["latest_name"])
		else:
			# Must be a Journal Entry affecting more than one bank
			for a in bt_allocations:
				if a["gl_account"] == gle["gl_account"] and a["total"] == gle["amount"]:
					unmatched_gles -= 1

	return unallocated_amount, unmatched_gles == 0, latest_transaction


def get_related_bank_gl_entries(doctype, docname):
	# nosemgrep: frappe-semgrep-rules.rules.frappe-using-db-sql
	result = frappe.db.sql(
		"""
		SELECT
			ABS(gle.credit_in_account_currency - gle.debit_in_account_currency) AS amount,
			gle.account AS gl_account
		FROM
			`tabGL Entry` gle
		LEFT JOIN
			`tabAccount` ac ON ac.name=gle.account
		WHERE
			ac.account_type = 'Bank'
			AND gle.voucher_type = %(doctype)s
			AND gle.voucher_no = %(docname)s
			AND is_cancelled = 0
		""",
		dict(doctype=doctype, docname=docname),
		as_dict=True,
	)
	return result


def get_total_allocated_amount(doctype, docname):
	"""
	Gets the sum of allocations for a voucher on each bank GL account
	along with the latest bank transaction name & date
	NOTE: query may also include just saved vouchers/payments but with zero allocated_amount
	"""
	# nosemgrep: frappe-semgrep-rules.rules.frappe-using-db-sql
	result = frappe.db.sql(
		"""
		SELECT total, latest_name, latest_date, gl_account FROM (
			SELECT
				ROW_NUMBER() OVER w AS rownum,
				SUM(btp.allocated_amount) OVER(PARTITION BY ba.account) AS total,
				FIRST_VALUE(bt.name) OVER w AS latest_name,
				FIRST_VALUE(bt.date) OVER w AS latest_date,
				ba.account AS gl_account
			FROM
				`tabBank Transaction Payments` btp
			LEFT JOIN `tabBank Transaction` bt ON bt.name=btp.parent
			LEFT JOIN `tabBank Account` ba ON ba.name=bt.bank_account
			WHERE
				btp.payment_document = %(doctype)s
				AND btp.payment_entry = %(docname)s
				AND bt.docstatus = 1
			WINDOW w AS (PARTITION BY ba.account ORDER BY bt.date desc)
		) temp
		WHERE
			rownum = 1
		""",
		dict(doctype=doctype, docname=docname),
		as_dict=True,
	)
	for row in result:
		# Why is this *sometimes* a byte string?
		if isinstance(row["latest_name"], bytes):
			row["latest_name"] = row["latest_name"].decode()
		row["latest_date"] = frappe.utils.getdate(row["latest_date"])
	return result


def get_paid_amount(payment_entry, currency, gl_bank_account):
	if payment_entry.payment_document in ["Payment Entry", "Sales Invoice", "Purchase Invoice"]:
		paid_amount_field = "paid_amount"
		if payment_entry.payment_document == "Payment Entry":
			doc = frappe.get_doc("Payment Entry", payment_entry.payment_entry)

			if doc.payment_type == "Receive":
				paid_amount_field = (
					"received_amount" if doc.paid_to_account_currency == currency else "base_received_amount"
				)
			elif doc.payment_type == "Pay":
				paid_amount_field = (
					"paid_amount" if doc.paid_from_account_currency == currency else "base_paid_amount"
				)

		return frappe.db.get_value(
			payment_entry.payment_document, payment_entry.payment_entry, paid_amount_field
		)

	elif payment_entry.payment_document == "Journal Entry":
		return abs(
			frappe.db.get_value(
				"Journal Entry Account",
				{"parent": payment_entry.payment_entry, "account": gl_bank_account},
				"sum(debit_in_account_currency-credit_in_account_currency)",
			)
			or 0
		)

	elif payment_entry.payment_document == "Expense Claim":
		return frappe.db.get_value(
			payment_entry.payment_document, payment_entry.payment_entry, "total_amount_reimbursed"
		)

	elif payment_entry.payment_document == "Loan Disbursement":
		return frappe.db.get_value(
			payment_entry.payment_document, payment_entry.payment_entry, "disbursed_amount"
		)

	elif payment_entry.payment_document == "Loan Repayment":
		return frappe.db.get_value(payment_entry.payment_document, payment_entry.payment_entry, "amount_paid")

	elif payment_entry.payment_document == "Bank Transaction":
		dep, wth = frappe.db.get_value(
			"Bank Transaction", payment_entry.payment_entry, ("deposit", "withdrawal")
		)
		return abs(flt(wth) - flt(dep))

	else:
		frappe.throw(
			f"Please reconcile {payment_entry.payment_document}: {payment_entry.payment_entry} manually"
		)


def set_voucher_clearance(doctype, docname, clearance_date, self):
	if doctype in [
		"Payment Entry",
		"Journal Entry",
		"Purchase Invoice",
		"Expense Claim",
		"Loan Repayment",
		"Loan Disbursement",
	]:
		if (
			doctype == "Payment Entry"
			and frappe.db.get_value("Payment Entry", docname, "payment_type") == "Internal Transfer"
			and len(get_reconciled_bank_transactions(doctype, docname)) < 2
		):
			return
		frappe.db.set_value(doctype, docname, "clearance_date", clearance_date)

	elif doctype == "Sales Invoice":
		frappe.db.set_value(
			"Sales Invoice Payment",
			dict(parenttype=doctype, parent=docname),
			"clearance_date",
			clearance_date,
		)

	elif doctype == "Bank Transaction":
		# For when a second bank transaction has fixed another, e.g. refund
		bt = frappe.get_doc(doctype, docname)
		if clearance_date:
			vouchers = [{"payment_doctype": "Bank Transaction", "payment_name": self.name}]
			bt.add_payment_entries(vouchers)
		else:
			for pe in bt.payment_entries:
				if pe.payment_document == self.doctype and pe.payment_entry == self.name:
					bt.remove(pe)
					bt.save()
					break


def get_reconciled_bank_transactions(doctype, docname):
	return frappe.get_all(
		"Bank Transaction Payments",
		filters={"payment_document": doctype, "payment_entry": docname},
		pluck="parent",
	)


@frappe.whitelist()
def unclear_reference_payment(doctype, docname, bt_name):
	bt = frappe.get_doc("Bank Transaction", bt_name)
	set_voucher_clearance(doctype, docname, None, bt)
	return docname


def remove_from_bank_transaction(doctype, docname):
	"""Remove a (cancelled) voucher from all Bank Transactions."""
	for bt_name in get_reconciled_bank_transactions(doctype, docname):
		bt = frappe.get_doc("Bank Transaction", bt_name)
		if bt.docstatus == DocStatus.cancelled():
			continue

		modified = False

		for pe in bt.payment_entries:
			if pe.payment_document == doctype and pe.payment_entry == docname:
				bt.remove(pe)
				modified = True

		if modified:
			bt.save()
