// Copyright (c) 2018, Frappe Technologies Pvt. Ltd. and contributors
// For license information, please see license.txt

frappe.ui.form.on("Bank Transaction", {
	onload(frm) {
		frm.set_query("payment_document", "payment_entries", function () {
			const payment_doctypes = frm.events.get_payment_doctypes(frm);
			return {
				filters: {
					name: ["in", payment_doctypes],
				},
			};
		});
	},
	refresh(frm) {
		frm.events.setup_party_ui(frm);
		frm.events.calculate_totals(frm);
		if (!frm.is_dirty() && frm.doc.payment_entries.length > 0) {
			frm.add_custom_button(__("Unreconcile Transaction"), () => {
				frm.call("remove_payment_entries").then(() => frm.refresh());
			});
		}

		if (frm.doc.docstatus === 1) {

			// Estado Bancario Dropdown Logic
			frm.add_custom_button(__("Tránsito"), function () {
				frm.set_value("custom_estado_bancario", "Tránsito");
				frm.save();
			}, __("Estado Bancario"));

			frm.add_custom_button(__("Pre-conciliado"), function () {
				frm.set_value("custom_estado_bancario", "Pre-conciliado");
				frm.save();
			}, __("Estado Bancario"));

			frm.add_custom_button(__("Conciliado"), function () {
				frm.set_value("custom_estado_bancario", "Conciliado");
				frm.save();
			}, __("Estado Bancario"));

			// Manual Journal Entry Deletion only (creation is auto)
			if (frm.doc.ref_journal_entry) {
				frm.add_custom_button(__("Eliminar Asiento Contable"), function () {
					frappe.confirm(__("¿Está seguro de eliminar el Asiento Contable vinculado?"), () => {
						frappe.call({
							method: "delete_journal_entry",
							doc: frm.doc,
							freeze: true,
							callback: function (r) {
								if (!r.exc) {
									frappe.msgprint(__("Asiento Contable Eliminado"));
									frm.reload_doc();
								}
							}
						});
					});
				}).addClass("btn-danger");
			}
		}
	},
	bank_account: function (frm) {
		set_bank_statement_filter(frm);
		frm.events.sync_bank_account(frm);
		frm.trigger('transaction_type');
	},

	transaction_type: function (frm) {
		if (frm.doc.transaction_type === 'Cheque' && frm.doc.bank_account && !frm.doc.check_number) {
			frappe.db.get_value('Bank Account', frm.doc.bank_account, 'check_correlative', function (r) {
				if (r) {
					let correlative = r.check_correlative || 0;
					frm.set_value('check_number', parseInt(correlative) + 1);
				}
			});
		}
	},

	setup_party_ui: function (frm) {
		if (frm.doc.party_type === 'Tercero') {
			frm.set_df_property('party', 'hidden', 1);
			frm.set_df_property('custom_beneficiary_name', 'hidden', 0);
		} else {
			frm.set_df_property('party', 'hidden', 0);
			frm.set_df_property('custom_beneficiary_name', 'hidden', 1);
		}
	},

	party_type: function (frm) {
		frm.events.setup_party_ui(frm);

		// Limpiar campos residuales solo si es cambio explícito (UI)
		frm.set_value('party', '');
		frm.set_value('custom_beneficiary_name', '');
	},

	deposit: function (frm) {
		frm.events.update_first_row_amounts(frm);
	},

	withdrawal: function (frm) {
		frm.events.update_first_row_amounts(frm);
	},

	sync_bank_account: function (frm) {
		if (frm.doc.bank_account) {
			frappe.db.get_value('Bank Account', frm.doc.bank_account, 'account', function (r) {
				if (r && r.account) {
					if (!frm.doc.custom_journal_entries || frm.doc.custom_journal_entries.length === 0) {
						frm.add_child('custom_journal_entries');
					}
					let first_row = frm.doc.custom_journal_entries[0];
					frappe.model.set_value(first_row.doctype, first_row.name, 'account', r.account).then(() => {
						frm.events.update_first_row_amounts(frm);
					});
				}
			});
		}
	},

	update_first_row_amounts: function (frm) {
		if (frm.doc.custom_journal_entries && frm.doc.custom_journal_entries.length > 0) {
			let first_row = frm.doc.custom_journal_entries[0];
			let deposit = flt(frm.doc.deposit);
			let withdrawal = flt(frm.doc.withdrawal);

			if (deposit > 0) {
				frappe.model.set_value(first_row.doctype, first_row.name, 'debit_in_account_currency', deposit);
				frappe.model.set_value(first_row.doctype, first_row.name, 'credit_in_account_currency', 0);
			} else if (withdrawal > 0) {
				frappe.model.set_value(first_row.doctype, first_row.name, 'credit_in_account_currency', withdrawal);
				frappe.model.set_value(first_row.doctype, first_row.name, 'debit_in_account_currency', 0);
			} else {
				frappe.model.set_value(first_row.doctype, first_row.name, 'debit_in_account_currency', 0);
				frappe.model.set_value(first_row.doctype, first_row.name, 'credit_in_account_currency', 0);
			}
			frm.events.calculate_totals(frm);
		}
	},

	calculate_totals: function (frm) {
		if (!frm.doc.custom_journal_entries || frm.doc.custom_journal_entries.length === 0) {
			frm.set_value('total_debit', 0);
			frm.set_value('total_credit', 0);
			frm.set_value('difference', 0);
			frm.set_intro("");
			return;
		}

		let total_debit = 0;
		let total_credit = 0;

		frm.doc.custom_journal_entries.forEach(row => {
			total_debit += flt(row.debit_in_account_currency);
			total_credit += flt(row.credit_in_account_currency);
		});

		let diff = Math.abs(total_debit - total_credit);
		let indicator = diff === 0 ? "green" : "red";

		frm.set_value('total_debit', total_debit);
		frm.set_value('total_credit', total_credit);
		frm.set_value('difference', diff);

		let msg = `<b>Asiento Contable</b> - Total Debe: ${format_currency(total_debit)} | Total Haber: ${format_currency(total_credit)} | Diferencia: ${format_currency(diff)}`;

		frm.set_intro(msg, indicator);
	},

	before_submit: function (frm) {
		if (['Cheque', 'Transferencia'].includes(frm.doc.transaction_type)) {
			if (!frm.doc.party && !frm.doc.custom_beneficiary_name) {
				frappe.throw(__('El campo Beneficiario es obligatorio para Cheques o Transferencias.'));
			}
		}

		if (!frm.doc.custom_journal_entries || frm.doc.custom_journal_entries.length === 0) {
			frappe.throw(__('La tabla de Asientos Contables debe tener al menos una fila.'));
		}

		let first_row = frm.doc.custom_journal_entries[0];
		let total_debit = 0;
		let total_credit = 0;

		frm.doc.custom_journal_entries.forEach(row => {
			total_debit += flt(row.debit_in_account_currency);
			total_credit += flt(row.credit_in_account_currency);
		});

		if (flt(total_debit) !== flt(total_credit)) {
			frappe.throw(__('No se puede someter: Los totales del Asiento Contable en la tabla no están cuadrados. Diferencia: {0}', [format_currency(Math.abs(total_debit - total_credit))]));
		}

		if (flt(frm.doc.deposit) > 0 && flt(total_debit) !== flt(frm.doc.deposit)) {
			frappe.throw(__('No se puede someter: El Total Debe ({0}) debe coincidir con el monto del Depósito ({1}).',
				[format_currency(total_debit), format_currency(frm.doc.deposit)]));
		}
		if (flt(frm.doc.withdrawal) > 0 && flt(total_credit) !== flt(frm.doc.withdrawal)) {
			frappe.throw(__('No se puede someter: El Total Haber ({0}) debe coincidir con el monto del Retiro ({1}).',
				[format_currency(total_credit), format_currency(frm.doc.withdrawal)]));
		}

		if (!frm.doc.bank_account) {
			frappe.throw(__('Seleccione una Cuenta Bancaria.'));
		}

		return new Promise((resolve, reject) => {
			frappe.db.get_value('Bank Account', frm.doc.bank_account, 'account', function (r) {
				if (r && r.account) {
					if (first_row.account !== r.account) {
						frappe.msgprint({
							message: __('No se puede someter: La primera línea debe corresponder a la cuenta contable del banco ({0}).', [r.account]),
							indicator: 'red'
						});
						reject();
					} else {
						resolve();
					}
				} else {
					frappe.msgprint({
						message: __('No se encontró cuenta contable para el Banco seleccionado.'),
						indicator: 'red'
					});
					reject();
				}
			});
		});
	},

	custom_journal_entries_add: function (frm) {
		frm.events.calculate_totals(frm);
	},

	custom_journal_entries_remove: function (frm) {
		frm.events.calculate_totals(frm);
	},

	setup: function (frm) {
		frm.set_query("party_type", function () {
			return {
				filters: {
					name: ["in", Object.keys(frappe.boot.party_account_types)],
				},
			};
		});
	},

	get_payment_doctypes: function () {
		// get payment doctypes from all the apps
		return ["Payment Entry", "Journal Entry", "Sales Invoice", "Purchase Invoice", "Bank Transaction"];
	},
});

frappe.ui.form.on("Bank Transaction Payments", {
	payment_entries_remove: function (frm, cdt, cdn) {
		update_clearance_date(frm, cdt, cdn);
	},
});

frappe.ui.form.on("Journal Entry Account", {
	debit_in_account_currency: function (frm, cdt, cdn) {
		frm.events.calculate_totals(frm);
	},
	credit_in_account_currency: function (frm, cdt, cdn) {
		frm.events.calculate_totals(frm);
	},
	account: function (frm, cdt, cdn) {
		frm.events.calculate_totals(frm);
	}
});

const update_clearance_date = (frm, cdt, cdn) => {
	if (frm.doc.docstatus === 1) {
		frappe
			.xcall("erpnext.accounts.doctype.bank_transaction.bank_transaction.unclear_reference_payment", {
				doctype: cdt,
				docname: cdn,
				bt_name: frm.doc.name,
			})
			.then((e) => {
				if (e == "success") {
					frappe.show_alert({
						message: __("Document {0} successfully uncleared", [e]),
						indicator: "green",
					});
				}
			});
	}
};

function set_bank_statement_filter(frm) {
	frm.set_query("bank_statement", function () {
		return {
			filters: {
				bank_account: frm.doc.bank_account,
			},
		};
	});
}
