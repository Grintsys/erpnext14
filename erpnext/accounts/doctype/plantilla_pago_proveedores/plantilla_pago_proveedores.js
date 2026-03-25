// Copyright (c) 2026, Grintsys and contributors
// For license information, please see license.txt

frappe.ui.form.on('Plantilla Pago Proveedores', {
    setup: function (frm) {
        // Filtrar inteligentemente la Cuenta Puente
        frm.set_query("bridge_account", function () {
            return {
                filters: {
                    'is_group': 0,
                    'report_type': 'Balance Sheet',
                    'account_type': ['not in', ['Receivable', 'Payable', 'Expense', 'Income']]
                }
            };
        });

        // Auto-establecer compañía default
        if (frm.is_new() && !frm.doc.company) {
            let default_company = frappe.defaults.get_user_default("Company");
            if (default_company) {
                frm.set_value("company", default_company);
            }
        }
    },

    onload: function (frm) {
        if (frm.doc.company && !frm.doc.currency) {
            frm.trigger('company');
        }
    },

    company: function (frm) {
        if (frm.doc.company) {
            frappe.db.get_value('Company', frm.doc.company, 'default_currency', (r) => {
                if (r && r.default_currency) {
                    frm.set_value('currency', r.default_currency);
                }
            });
        }
    },

    refresh: function (frm) {
        frm.trigger('render_summary');
        
        frm.add_custom_button(__('Múltiples Facturas'), function() {
            show_multiselect_invoices_dialog(frm);
        }, __('Obtener de'));

        if (frm.fields_dict.payment_details && frm.fields_dict.payment_details.grid) {
            frm.fields_dict.payment_details.grid.add_custom_button(__('Añadir múltiples'), function() {
                show_multiselect_invoices_dialog(frm);
            });
        }
    },

    render_summary: function (frm) {
        if (frm.doc.payment_details && frm.doc.payment_details.length > 0) {
            let summary = {};
            frm.doc.payment_details.forEach(row => {
                if (row.supplier && row.allocated_amount) {
                    summary[row.supplier] = (summary[row.supplier] || 0) + flt(row.allocated_amount);
                }
            });

            let html = `
                <div class="row">
                    <div class="col-md-6">
                        <table class="table table-bordered table-condensed">
                            <thead class="bg-light">
                                <tr><th>${__("Proveedor")}</th><th class="text-right">${__("Total Asignado a Pagar")}</th></tr>
                            </thead>
                            <tbody>
            `;

            Object.keys(summary).forEach(sup => {
                html += `<tr><td>${sup}</td><td class="text-right text-bold">${format_currency(summary[sup], frm.doc.currency)}</td></tr>`;
            });

            html += "</tbody></table></div></div>";
            frm.get_field("summary_html").$wrapper.html(html);
        } else {
            frm.get_field("summary_html").$wrapper.html("");
        }
    }
});

frappe.ui.form.on('Detalle Plantilla Pago Proveedores', {
    supplier: function (frm, cdt, cdn) {
        let row = locals[cdt][cdn];
        if (row.supplier && frm.doc.company) {
            frappe.call({
                method: "erpnext.accounts.party.get_party_account",
                args: {
                    party_type: "Supplier",
                    party: row.supplier,
                    company: frm.doc.company
                },
                callback: function (r) {
                    if (r.message) {
                        frappe.model.set_value(cdt, cdn, 'payable_account', r.message);
                    }
                }
            });
        }
    },

    reference_doctype: function (frm, cdt, cdn) {
        let row = locals[cdt][cdn];

        frm.fields_dict['payment_details'].grid.get_field('reference_name').get_query = function (doc, c_dt, c_dn) {
            let grid_row = locals[c_dt][c_dn];

            if (!doc.company || !doc.currency || !grid_row.supplier) {
                frappe.msgprint(__("Por favor defina la Entidad, Moneda y Proveedor antes de buscar facturas."));
                return {};
            }

            let excluded = doc.payment_details.map(d => d.reference_name).filter(n => n && n !== grid_row.reference_name);

            return {
                query: "erpnext.accounts.doctype.plantilla_pago_proveedores.plantilla_pago_proveedores.get_invoices_for_payment_details",
                filters: {
                    "company": doc.company,
                    "supplier": grid_row.supplier,
                    "currency": doc.currency,
                    "excluded_invoices": excluded
                }
            };
        };
    },

    reference_name: function (frm, cdt, cdn) {
        let row = locals[cdt][cdn];
        if (row.reference_doctype && row.reference_name) {
            frappe.db.get_value(row.reference_doctype, row.reference_name, 'outstanding_amount', (r) => {
                if (r && r.outstanding_amount !== undefined) {
                    frappe.model.set_value(cdt, cdn, 'document_outstanding', flt(r.outstanding_amount));

                    if (!row.allocated_amount || row.allocated_amount === 0) {
                        frappe.model.set_value(cdt, cdn, 'allocated_amount', flt(r.outstanding_amount));
                    }
                }
            });
        }
    },

    allocated_amount: function (frm, cdt, cdn) {
        frm.trigger('render_summary');
    }
});

function show_multiselect_invoices_dialog(frm) {
    if (!frm.doc.company || !frm.doc.currency) {
        frappe.msgprint(__("Debe seleccionar la Empresa y Moneda antes de buscar facturas."));
        return;
    }

    let dialog = new frappe.ui.Dialog({
        title: __('Seleccionar Facturas por Pagar'),
        fields: [
            { fieldtype: 'Link', fieldname: 'supplier', options: 'Supplier', label: __('Proveedor') },
            { fieldtype: 'Data', fieldname: 'bill_no', label: __('Número de Factura (Bill No)') },
            { fieldtype: 'Button', fieldname: 'search', label: __('Buscar'), cssClass: 'btn-primary' },
            { fieldtype: 'Section Break' },
            { fieldtype: 'HTML', fieldname: 'results_html' }
        ]
    });

    dialog.fields_dict.search.$input.on('click', function() {
        let supplier = dialog.get_value('supplier');
        let bill_no = dialog.get_value('bill_no');
        
        let excluded_invoices = frm.doc.payment_details ? frm.doc.payment_details.map(d => d.reference_name).filter(Boolean) : [];

        dialog.get_field('results_html').$wrapper.html('<p class="text-muted">' + __('Buscando facturas...') + '</p>');

        frappe.call({
            method: 'erpnext.accounts.doctype.plantilla_pago_proveedores.plantilla_pago_proveedores.get_pending_invoices',
            args: {
                company: frm.doc.company,
                currency: frm.doc.currency,
                supplier: supplier,
                bill_no: bill_no,
                excluded_invoices: excluded_invoices
            },
            callback: function(r) {
                if (r.message && r.message.length > 0) {
                    let thead = `<tr>
                        <th width="5%" class="text-center"><input type="checkbox" id="select_all_invoices"></th>
                        <th width="25%">${__("Proveedor")}</th>
                        <th width="20%">${__("Factura")}</th>
                        <th width="15%">${__("Ref/Bill")}</th>
                        <th width="15%">${__("Fecha")}</th>
                        <th width="20%" class="text-right">${__("Saldo")}</th>
                    </tr>`;
                    let tbody = '';
                    r.message.forEach(inv => {
                        tbody += `<tr>
                            <td class="text-center"><input type="checkbox" class="invoice-checkbox" data-invoice='${JSON.stringify(inv)}'></td>
                            <td>${inv.supplier}</td>
                            <td>${inv.name}</td>
                            <td>${inv.bill_no || ''}</td>
                            <td>${frappe.datetime.str_to_user(inv.posting_date)}</td>
                            <td class="text-right">${format_currency(inv.outstanding_amount, frm.doc.currency)}</td>
                        </tr>`;
                    });
                    
                    let table = `<table class="table table-bordered table-hover invoice-result-table"><thead class="bg-light">${thead}</thead><tbody>${tbody}</tbody></table>`;
                    dialog.get_field('results_html').$wrapper.html(table);
                    
                    dialog.get_field('results_html').$wrapper.find('#select_all_invoices').on('change', function() {
                        let checked = $(this).prop('checked');
                        dialog.get_field('results_html').$wrapper.find('.invoice-checkbox').prop('checked', checked);
                    });
                } else {
                    dialog.get_field('results_html').$wrapper.html('<p class="text-muted">' + __('No se encontraron facturas pendientes y válidas para los filtros indicados.') + '</p>');
                }
            }
        });
    });

    dialog.set_primary_action(__('Añadir Seleccionadas'), function() {
        let selected_invoices = [];
        dialog.get_field('results_html').$wrapper.find('.invoice-checkbox:checked').each(function() {
            selected_invoices.push(JSON.parse($(this).attr('data-invoice')));
        });

        if (selected_invoices.length > 0) {
            frappe.dom.freeze(__('Agregando facturas...'));
            setTimeout(() => {
                selected_invoices.forEach(inv => {
                    let row = frm.add_child('payment_details');
                    row.supplier = inv.supplier;
                    row.reference_doctype = 'Purchase Invoice';
                    row.reference_name = inv.name;
                    row.payable_account = inv.credit_to; 
                    row.document_outstanding = flt(inv.outstanding_amount);
                    row.allocated_amount = flt(inv.outstanding_amount);
                });
                frm.refresh_field('payment_details');
                frm.trigger('render_summary');
                frappe.dom.unfreeze();
                dialog.hide();
                frappe.show_alert({message: __('Se agregaron {0} facturas exitosamente', [selected_invoices.length]), indicator: 'green'});
            }, 100);
        } else {
            frappe.msgprint(__("Debe seleccionar al menos una factura."));
        }
    });

    dialog.show();
}
