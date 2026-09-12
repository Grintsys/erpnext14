frappe.pages['tablero-facturas-venta'].on_page_load = function(wrapper) {
    let page = frappe.ui.make_app_page({
        parent: wrapper,
        title: __('Tablero de Facturas de Venta'),
        single_column: true
    });

    wrapper.tablero_app = new TableroFacturasVentaApp(page, wrapper);
};

class TableroFacturasVentaApp {
    constructor(page, wrapper) {
        this.page = page;
        this.wrapper = wrapper;
        this.charts = {};

        this.setup_header_actions();
        this.setup_ui_layout();
        this.setup_filter_controls();
        this.set_default_dates();
        this.bind_events();
        this.load_dashboard_data();
    }

    setup_header_actions() {
        let me = this;
        this.page.set_primary_action(__('Actualizar Dashboard'), function() {
            me.load_dashboard_data();
        }, 'refresh');

        this.page.add_button(__('Este Mes'), function() {
            me.set_date_range('this_month');
        });

        this.page.add_button(__('Mes Anterior'), function() {
            me.set_date_range('last_month');
        });

        this.page.add_button(__('Año Actual'), function() {
            me.set_date_range('this_year');
        });

        this.page.add_button(__('Últimos 30 Días'), function() {
            me.set_date_range('last_30');
        });
    }

    setup_ui_layout() {
        let body_html = `
            <div class="tablero-sales-invoice-container p-3" style="background: #f8f9fa; min-height: 100vh;">
                <!-- SECCIÓN DE FILTROS PRINCIPALES -->
                <div class="card mb-4" style="border-radius: 10px; border: 1px solid #e2e8f0; box-shadow: 0 2px 4px rgba(0,0,0,0.02); background: #ffffff; padding: 16px;">
                    <div class="d-flex flex-wrap align-items-center" style="gap: 12px;">
                        <div style="min-width: 180px;" id="fc-dash-company"></div>
                        <div style="min-width: 140px;" id="fc-dash-from-date"></div>
                        <div style="min-width: 140px;" id="fc-dash-to-date"></div>
                        <div style="min-width: 160px;" id="fc-dash-customer"></div>
                        <div style="min-width: 160px;" id="fc-dash-customer-group"></div>
                        <div style="min-width: 160px;" id="fc-dash-territory"></div>
                        <div style="min-width: 160px;" id="fc-dash-pos-profile"></div>
                        <div style="min-width: 130px;" id="fc-dash-periodicity"></div>
                    </div>
                </div>

                <!-- SECCIÓN DE KPIS (METRIC CARDS) -->
                <div class="row mb-4">
                    <div class="col-md-2 col-sm-6 mb-3">
                        <div class="card p-3 border-0" style="border-radius: 10px; background: linear-gradient(135deg, #1e3c72 0%, #2a5298 100%); color: #fff; box-shadow: 0 4px 6px rgba(0,0,0,0.1);">
                            <div class="d-flex justify-content-between align-items-center mb-2">
                                <span class="small font-weight-bold text-uppercase">${__('Total Facturado')}</span>
                                <i class="fa fa-line-chart fa-lg" style="opacity: 0.7;"></i>
                            </div>
                            <h3 class="mb-0 font-weight-bold" id="kpi-grand-total">L 0.00</h3>
                            <small class="text-white-50 mt-1" id="kpi-net-total">${__('Neto')}: L 0.00</small>
                        </div>
                    </div>
                    <div class="col-md-2 col-sm-6 mb-3">
                        <div class="card p-3 border-0" style="border-radius: 10px; background: linear-gradient(135deg, #11998e 0%, #38ef7d 100%); color: #fff; box-shadow: 0 4px 6px rgba(0,0,0,0.1);">
                            <div class="d-flex justify-content-between align-items-center mb-2">
                                <span class="small font-weight-bold text-uppercase">${__('Total Cobrado')}</span>
                                <i class="fa fa-check-circle fa-lg" style="opacity: 0.7;"></i>
                            </div>
                            <h3 class="mb-0 font-weight-bold" id="kpi-paid-amount">L 0.00</h3>
                            <small class="text-white-50 mt-1">${__('Ingresos Ingresados')}</small>
                        </div>
                    </div>
                    <div class="col-md-2 col-sm-6 mb-3">
                        <div class="card p-3 border-0" style="border-radius: 10px; background: linear-gradient(135deg, #ff416c 0%, #ff4b2b 100%); color: #fff; box-shadow: 0 4px 6px rgba(0,0,0,0.1);">
                            <div class="d-flex justify-content-between align-items-center mb-2">
                                <span class="small font-weight-bold text-uppercase">${__('Pendiente Cobro')}</span>
                                <i class="fa fa-clock-o fa-lg" style="opacity: 0.7;"></i>
                            </div>
                            <h3 class="mb-0 font-weight-bold" id="kpi-outstanding-amount">L 0.00</h3>
                            <small class="text-white-50 mt-1">${__('Cuentas por Cobrar')}</small>
                        </div>
                    </div>
                    <div class="col-md-2 col-sm-6 mb-3">
                        <div class="card p-3 border-0" style="border-radius: 10px; background: linear-gradient(135deg, #8e2de2 0%, #4a00e0 100%); color: #fff; box-shadow: 0 4px 6px rgba(0,0,0,0.1);">
                            <div class="d-flex justify-content-between align-items-center mb-2">
                                <span class="small font-weight-bold text-uppercase">${__('ISV / Impuestos')}</span>
                                <i class="fa fa-university fa-lg" style="opacity: 0.7;"></i>
                            </div>
                            <h3 class="mb-0 font-weight-bold" id="kpi-total-taxes">L 0.00</h3>
                            <small class="text-white-50 mt-1">${__('Impuestos Generados')}</small>
                        </div>
                    </div>
                    <div class="col-md-2 col-sm-6 mb-3">
                        <div class="card p-3 border-0" style="border-radius: 10px; background: linear-gradient(135deg, #2193b0 0%, #6dd5ed 100%); color: #fff; box-shadow: 0 4px 6px rgba(0,0,0,0.1);">
                            <div class="d-flex justify-content-between align-items-center mb-2">
                                <span class="small font-weight-bold text-uppercase">${__('Facturas Emitidas')}</span>
                                <i class="fa fa-file-text-o fa-lg" style="opacity: 0.7;"></i>
                            </div>
                            <h3 class="mb-0 font-weight-bold" id="kpi-invoice-count">0</h3>
                            <small class="text-white-50 mt-1">${__('Documentos Validados')}</small>
                        </div>
                    </div>
                    <div class="col-md-2 col-sm-6 mb-3">
                        <div class="card p-3 border-0" style="border-radius: 10px; background: linear-gradient(135deg, #3a1c71 0%, #d76d77 50%, #ffaf7b 100%); color: #fff; box-shadow: 0 4px 6px rgba(0,0,0,0.1);">
                            <div class="d-flex justify-content-between align-items-center mb-2">
                                <span class="small font-weight-bold text-uppercase">${__('Ticket Promedio')}</span>
                                <i class="fa fa-calculator fa-lg" style="opacity: 0.7;"></i>
                            </div>
                            <h3 class="mb-0 font-weight-bold" id="kpi-avg-ticket">L 0.00</h3>
                            <small class="text-white-50 mt-1">${__('Promedio por Venta')}</small>
                        </div>
                    </div>
                </div>

                <!-- SECCIÓN DE GRÁFICOS INTERACTIVOS (FILA 1) -->
                <div class="row mb-4">
                    <div class="col-lg-8 mb-3">
                        <div class="card border-0" style="border-radius: 10px; box-shadow: 0 2px 4px rgba(0,0,0,0.03); background: #fff; padding: 20px;">
                            <h5 class="card-title font-weight-bold text-dark mb-3"><i class="fa fa-area-chart text-primary mr-2"></i>${__('Tendencia de Facturación vs. Cobros')}</h5>
                            <div id="chart-sales-trend" style="min-height: 320px;"></div>
                        </div>
                    </div>
                    <div class="col-lg-4 mb-3">
                        <div class="card border-0" style="border-radius: 10px; box-shadow: 0 2px 4px rgba(0,0,0,0.03); background: #fff; padding: 20px;">
                            <h5 class="card-title font-weight-bold text-dark mb-3"><i class="fa fa-pie-chart text-success mr-2"></i>${__('Distribución por Forma de Pago')}</h5>
                            <div id="chart-payment-modes" style="min-height: 320px;"></div>
                        </div>
                    </div>
                </div>

                <!-- SECCIÓN DE GRÁFICOS INTERACTIVOS (FILA 2) -->
                <div class="row mb-4">
                    <div class="col-lg-6 mb-3">
                        <div class="card border-0" style="border-radius: 10px; box-shadow: 0 2px 4px rgba(0,0,0,0.03); background: #fff; padding: 20px;">
                            <h5 class="card-title font-weight-bold text-dark mb-3"><i class="fa fa-users text-info mr-2"></i>${__('Top 10 Clientes con Mayor Facturación')}</h5>
                            <div id="chart-top-customers" style="min-height: 300px;"></div>
                        </div>
                    </div>
                    <div class="col-lg-6 mb-3">
                        <div class="card border-0" style="border-radius: 10px; box-shadow: 0 2px 4px rgba(0,0,0,0.03); background: #fff; padding: 20px;">
                            <h5 class="card-title font-weight-bold text-dark mb-3"><i class="fa fa-tags text-warning mr-2"></i>${__('Top 10 Productos Más Facturados')}</h5>
                            <div class="table-responsive" style="max-height: 300px; overflow-y: auto;">
                                <table class="table table-sm table-hover table-striped mb-0" id="table-top-products">
                                    <thead class="thead-light">
                                        <tr>
                                            <th>${__('Código')}</th>
                                            <th>${__('Producto')}</th>
                                            <th class="text-right">${__('Cantidad')}</th>
                                            <th class="text-right">${__('Monto Facturado')}</th>
                                        </tr>
                                    </thead>
                                    <tbody></tbody>
                                </table>
                            </div>
                        </div>
                    </div>
                </div>

                <!-- TABLA DE FACTURAS DESTACADAS Y RECIENTES -->
                <div class="card border-0 mb-4" style="border-radius: 10px; box-shadow: 0 2px 4px rgba(0,0,0,0.03); background: #fff; padding: 20px;">
                    <div class="d-flex justify-content-between align-items-center mb-3">
                        <h5 class="card-title font-weight-bold text-dark m-0"><i class="fa fa-list-alt text-secondary mr-2"></i>${__('Facturas Destacadas Recientes')}</h5>
                        <span class="text-muted small">${__('Mostrando las últimas 15 facturas del período')}</span>
                    </div>
                    <div class="table-responsive">
                        <table class="table table-bordered table-hover table-sm align-middle" id="table-recent-invoices" style="font-size: 13px;">
                            <thead style="background-color: #f8f9fa;">
                                <tr>
                                    <th>${__('Factura')}</th>
                                    <th>${__('Fecha')}</th>
                                    <th>${__('Cliente')}</th>
                                    <th class="text-right">${__('Monto Total')}</th>
                                    <th class="text-right">${__('Saldo Pendiente')}</th>
                                    <th class="text-center">${__('Estado')}</th>
                                </tr>
                            </thead>
                            <tbody></tbody>
                        </table>
                    </div>
                </div>
            </div>
        `;

        $(this.page.body).html(body_html);
    }

    setup_filter_controls() {
        let me = this;

        this.f_company = frappe.ui.form.make_control({
            df: { fieldtype: 'Link', options: 'Company', fieldname: 'company', label: __('Empresa'), default: frappe.defaults.get_user_default("Company"), reqd: 1 },
            parent: $('#fc-dash-company'),
            only_input: false
        });
        this.f_company.refresh();

        this.f_from_date = frappe.ui.form.make_control({
            df: { fieldtype: 'Date', fieldname: 'from_date', label: __('Desde') },
            parent: $('#fc-dash-from-date'),
            only_input: false
        });
        this.f_from_date.refresh();

        this.f_to_date = frappe.ui.form.make_control({
            df: { fieldtype: 'Date', fieldname: 'to_date', label: __('Hasta') },
            parent: $('#fc-dash-to-date'),
            only_input: false
        });
        this.f_to_date.refresh();

        this.f_customer = frappe.ui.form.make_control({
            df: { fieldtype: 'Link', options: 'Customer', fieldname: 'customer', label: __('Cliente') },
            parent: $('#fc-dash-customer'),
            only_input: false
        });
        this.f_customer.refresh();

        this.f_customer_group = frappe.ui.form.make_control({
            df: { fieldtype: 'Link', options: 'Customer Group', fieldname: 'customer_group', label: __('Grupo Clientes') },
            parent: $('#fc-dash-customer-group'),
            only_input: false
        });
        this.f_customer_group.refresh();

        this.f_territory = frappe.ui.form.make_control({
            df: { fieldtype: 'Link', options: 'Territory', fieldname: 'territory', label: __('Territorio') },
            parent: $('#fc-dash-territory'),
            only_input: false
        });
        this.f_territory.refresh();

        this.f_pos_profile = frappe.ui.form.make_control({
            df: { fieldtype: 'Link', options: 'POS Profile', fieldname: 'pos_profile', label: __('Perfil POS') },
            parent: $('#fc-dash-pos-profile'),
            only_input: false
        });
        this.f_pos_profile.refresh();

        this.f_periodicity = frappe.ui.form.make_control({
            df: {
                fieldtype: 'Select',
                fieldname: 'periodicity',
                label: __('Frecuencia'),
                options: [
                    { label: __('Mensual'), value: 'Monthly' },
                    { label: __('Diario'), value: 'Daily' }
                ],
                default: 'Monthly'
            },
            parent: $('#fc-dash-periodicity'),
            only_input: false
        });
        this.f_periodicity.refresh();
    }

    set_default_dates() {
        let today_date = frappe.datetime.get_today();
        let thirty_days_ago = frappe.datetime.add_days(today_date, -30);
        this.f_from_date.set_value(thirty_days_ago);
        this.f_to_date.set_value(today_date);
    }

    set_date_range(range_type) {
        let today_date = frappe.datetime.get_today();
        if (range_type === 'this_month') {
            this.f_from_date.set_value(frappe.datetime.month_start());
            this.f_to_date.set_value(frappe.datetime.month_end());
        } else if (range_type === 'last_month') {
            let prev_month_end = frappe.datetime.add_days(frappe.datetime.month_start(), -1);
            let prev_month_start = frappe.datetime.month_start(prev_month_end);
            this.f_from_date.set_value(prev_month_start);
            this.f_to_date.set_value(prev_month_end);
        } else if (range_type === 'this_year') {
            this.f_from_date.set_value(frappe.datetime.year_start());
            this.f_to_date.set_value(today_date);
        } else if (range_type === 'last_30') {
            this.f_from_date.set_value(frappe.datetime.add_days(today_date, -30));
            this.f_to_date.set_value(today_date);
        }
        this.load_dashboard_data();
    }

    bind_events() {
        let me = this;
        $(this.page.body).find('input, select').on('change', function() {
            // Auto refresh al cambiar un filtro si tiene valor
        });
    }

    load_dashboard_data() {
        let me = this;
        let company = this.f_company.get_value();

        frappe.call({
            method: 'erpnext.selling.page.tablero_facturas_venta.tablero_facturas_venta.get_dashboard_data',
            args: {
                company: company,
                from_date: this.f_from_date.get_value(),
                to_date: this.f_to_date.get_value(),
                customer: this.f_customer.get_value(),
                customer_group: this.f_customer_group.get_value(),
                territory: this.f_territory.get_value(),
                pos_profile: this.f_pos_profile.get_value(),
                periodicity: this.f_periodicity.get_value()
            },
            freeze: true,
            freeze_message: __('Cargando métricas de facturación...'),
            callback: function(r) {
                if (r.message) {
                    me.render_kpis(r.message.kpis);
                    me.render_sales_trend_chart(r.message.trend_chart);
                    me.render_payment_modes_chart(r.message.payment_chart);
                    me.render_top_customers_chart(r.message.top_customers);
                    me.render_top_products_table(r.message.top_products);
                    me.render_recent_invoices_table(r.message.recent_invoices);
                }
            }
        });
    }

    render_kpis(kpis) {
        if (!kpis) return;
        $('#kpi-grand-total').text(format_currency(kpis.grand_total, 'HNL'));
        $('#kpi-net-total').text(`${__('Neto')}: ${format_currency(kpis.net_total, 'HNL')}`);
        $('#kpi-paid-amount').text(format_currency(kpis.paid_amount, 'HNL'));
        $('#kpi-outstanding-amount').text(format_currency(kpis.outstanding_amount, 'HNL'));
        $('#kpi-total-taxes').text(format_currency(kpis.total_taxes, 'HNL'));
        $('#kpi-invoice-count').text(kpis.invoice_count);
        $('#kpi-avg-ticket').text(format_currency(kpis.avg_ticket, 'HNL'));
    }

    render_sales_trend_chart(data) {
        if (!data || !data.labels) return;

        let chart_data = {
            labels: data.labels,
            datasets: data.datasets
        };

        if (this.charts.sales_trend) {
            this.charts.sales_trend.update(chart_data);
        } else {
            this.charts.sales_trend = new frappe.Chart("#chart-sales-trend", {
                title: "",
                data: chart_data,
                type: 'bar',
                height: 300,
                colors: ['#2a5298', '#38ef7d'],
                axisOptions: {
                    xIsSeries: true
                },
                barOptions: {
                    spaceRatio: 0.3
                }
            });
        }
    }

    render_payment_modes_chart(data) {
        if (!data || !data.labels || data.labels.length === 0) {
            $('#chart-payment-modes').html(`<div class="text-center text-muted p-4">${__('Sin datos de pago')}</div>`);
            return;
        }

        let chart_data = {
            labels: data.labels,
            datasets: [
                { values: data.values }
            ]
        };

        if (this.charts.payment_modes) {
            this.charts.payment_modes.update(chart_data);
        } else {
            this.charts.payment_modes = new frappe.Chart("#chart-payment-modes", {
                title: "",
                data: chart_data,
                type: 'percentage',
                height: 300,
                colors: ['#36a2eb', '#ff6384', '#4bc0c0', '#ffcd56', '#9966ff']
            });
        }
    }

    render_top_customers_chart(data) {
        if (!data || !data.labels || data.labels.length === 0) {
            $('#chart-top-customers').html(`<div class="text-center text-muted p-4">${__('Sin datos de clientes')}</div>`);
            return;
        }

        let chart_data = {
            labels: data.labels,
            datasets: [
                { name: __('Facturado'), values: data.values }
            ]
        };

        if (this.charts.top_customers) {
            this.charts.top_customers.update(chart_data);
        } else {
            this.charts.top_customers = new frappe.Chart("#chart-top-customers", {
                title: "",
                data: chart_data,
                type: 'bar',
                height: 280,
                colors: ['#2193b0']
            });
        }
    }

    render_top_products_table(items) {
        let $tbody = $('#table-top-products tbody');
        $tbody.empty();

        if (!items || items.length === 0) {
            $tbody.append(`<tr><td colspan="4" class="text-center text-muted py-3">${__('Sin ventas de productos')}</td></tr>`);
            return;
        }

        items.forEach(p => {
            let row_html = `
                <tr>
                    <td><strong>${p.item_code}</strong></td>
                    <td>${p.item_name}</td>
                    <td class="text-right font-weight-bold">${p.qty}</td>
                    <td class="text-right text-primary font-weight-bold">${format_currency(p.amount, 'HNL')}</td>
                </tr>
            `;
            $tbody.append(row_html);
        });
    }

    render_recent_invoices_table(invoices) {
        let $tbody = $('#table-recent-invoices tbody');
        $tbody.empty();

        if (!invoices || invoices.length === 0) {
            $tbody.append(`<tr><td colspan="6" class="text-center text-muted py-4">${__('No se encontraron facturas de venta en el período seleccionado.')}</td></tr>`);
            return;
        }

        invoices.forEach(inv => {
            let badge_class = 'badge-success';
            if (inv.status === 'Draft') badge_class = 'badge-secondary';
            else if (inv.status === 'Unpaid' || inv.status === 'Overdue') badge_class = 'badge-danger';
            else if (inv.status === 'Partially Paid') badge_class = 'badge-warning';

            let row_html = `
                <tr>
                    <td><a href="/app/sales-invoice/${inv.name}" target="_blank" class="font-weight-bold text-primary">${inv.name}</a></td>
                    <td>${inv.posting_date}</td>
                    <td>${inv.customer}</td>
                    <td class="text-right font-weight-bold">${format_currency(inv.grand_total, inv.currency)}</td>
                    <td class="text-right ${inv.outstanding_amount > 0 ? 'text-danger font-weight-bold' : 'text-muted'}">${format_currency(inv.outstanding_amount, inv.currency)}</td>
                    <td class="text-center"><span class="badge ${badge_class}">${inv.status}</span></td>
                </tr>
            `;
            $tbody.append(row_html);
        });
    }
}
