frappe.pages['precio-y-utilidades'].on_page_load = function(wrapper) {
    let page = frappe.ui.make_app_page({
        parent: wrapper,
        title: __('Precio y Utilidades'),
        single_column: true
    });

    wrapper.precio_app = new PrecioYUtilidadesApp(page, wrapper);
};

class PrecioYUtilidadesApp {
    constructor(page, wrapper) {
        this.page = page;
        this.wrapper = wrapper;
        this.current_page = 1;
        this.page_length = 100;
        this.total_records = 0;
        this.items_data = [];
        this.filtered_items_data = [];
        this.selected_items = new Set();
        this.sort_by = 'item_code';
        this.sort_order = 'ASC';
        this.column_filters = {};
        
        this.setup_header_actions();
        this.setup_ui_layout();
        this.setup_filter_controls();
        this.bind_events();
        this.load_data();
    }

    setup_header_actions() {
        let me = this;
        this.page.set_primary_action(__('Consultar / Simular'), function() {
            me.current_page = 1;
            me.load_data();
        }, 'search');

        this.page.add_button(__('Copiar Sugeridos a Nuevos'), function() {
            me.copy_suggested_to_new_prices();
        }, 'copy').addClass('mr-2');

        this.page.add_button(__('Aplicar Precios Seleccionados'), function() {
            me.apply_selected_prices();
        }, 'check').addClass('btn-primary');
    }

    setup_ui_layout() {
        let body_html = `
            <div class="frappe-card mb-3" style="border-radius: 8px; box-shadow: 0 1px 3px rgba(0,0,0,0.05); background: #fff; padding: 16px;">
                <!-- SECCIÓN DE FILTROS PRINCIPALES (Nativos Frappe Desk) -->
                <div class="d-flex flex-wrap align-items-center mb-3 pb-3 border-bottom" style="gap: 12px;">
                    <div style="min-width: 180px;" id="fc-company"></div>
                    <div style="min-width: 180px;" id="fc-price-list"></div>
                    <div style="min-width: 180px;" id="fc-warehouse"></div>
                    <div style="min-width: 180px;" id="fc-item-group"></div>
                    <div style="min-width: 180px;" id="fc-brand"></div>
                    <div style="min-width: 180px;" id="fc-item-code"></div>
                    <div style="min-width: 140px;" id="fc-target-margin"></div>
                    <div style="min-width: 160px;" id="fc-rounding"></div>
                    <div style="min-width: 150px;" id="fc-status"></div>
                    <div class="ml-auto d-flex align-items-center pt-3">
                        <button class="btn btn-sm btn-default" id="btn-reset-filters"><i class="fa fa-refresh"></i> ${__('Limpiar Filtros')}</button>
                    </div>
                </div>

                <!-- Resumen de Métricas, Paginación y Contador -->
                <div class="d-flex justify-content-between align-items-center mb-3">
                    <div class="d-flex align-items-center">
                        <span class="text-muted mr-4">${__('Total Registros')}: <strong id="metric-total" class="text-dark">0</strong></span>
                        <span class="text-muted mr-4">${__('Visibles')}: <strong id="metric-visible" class="text-info">0</strong></span>
                        <span class="text-muted mr-4">${__('Seleccionados')}: <strong id="metric-selected" class="text-primary">0</strong></span>
                    </div>
                    <div class="pagination-controls d-flex align-items-center">
                        <button class="btn btn-xs btn-default mr-2" id="btn-prev-page">&laquo; ${__('Anterior')}</button>
                        <span class="text-muted small mr-2" id="label-page-info">${__('Página 1 de 1')}</span>
                        <button class="btn btn-xs btn-default" id="btn-next-page">${__('Siguiente')} &raquo;</button>
                    </div>
                </div>

                <!-- Tabla de Datos con Filtros Rápidos de Columna -->
                <div id="datatable-wrapper" class="table-responsive" style="min-height: 380px;">
                    <div id="datatable-container"></div>
                </div>
            </div>
        `;

        $(this.page.body).html(body_html);
    }

    setup_filter_controls() {
        let me = this;

        this.f_company = frappe.ui.form.make_control({
            df: { fieldtype: 'Link', options: 'Company', fieldname: 'company', label: __('Empresa'), default: frappe.defaults.get_user_default("Company"), reqd: 1 },
            parent: $('#fc-company'),
            only_input: false
        });
        this.f_company.refresh();

        this.f_price_list = frappe.ui.form.make_control({
            df: { fieldtype: 'Link', options: 'Price List', fieldname: 'price_list', label: __('Lista de Precios'), default: 'Venta estándar' },
            parent: $('#fc-price-list'),
            only_input: false
        });
        this.f_price_list.refresh();

        this.f_warehouse = frappe.ui.form.make_control({
            df: { fieldtype: 'Link', options: 'Warehouse', fieldname: 'warehouse', label: __('Bodega (Costo)'), placeholder: __('Todas (Costo Global)') },
            parent: $('#fc-warehouse'),
            only_input: false
        });
        this.f_warehouse.refresh();

        this.f_item_group = frappe.ui.form.make_control({
            df: { fieldtype: 'Link', options: 'Item Group', fieldname: 'item_group', label: __('Grupo de Productos') },
            parent: $('#fc-item-group'),
            only_input: false
        });
        this.f_item_group.refresh();

        this.f_brand = frappe.ui.form.make_control({
            df: { fieldtype: 'Link', options: 'Brand', fieldname: 'brand', label: __('Marca') },
            parent: $('#fc-brand'),
            only_input: false
        });
        this.f_brand.refresh();

        this.f_item_code = frappe.ui.form.make_control({
            df: { fieldtype: 'Link', options: 'Item', fieldname: 'item_code', label: __('Producto') },
            parent: $('#fc-item-code'),
            only_input: false
        });
        this.f_item_code.refresh();

        this.f_target_margin = frappe.ui.form.make_control({
            df: { fieldtype: 'Float', fieldname: 'target_margin', label: __('Margen Meta Global %'), placeholder: 'Ej. 35' },
            parent: $('#fc-target-margin'),
            only_input: false
        });
        this.f_target_margin.refresh();

        this.f_rounding = frappe.ui.form.make_control({
            df: { 
                fieldtype: 'Select', 
                fieldname: 'rounding', 
                label: __('Redondeo'),
                options: [
                    { label: __('Sin Redondeo'), value: 'none' },
                    { label: __('Entero Más Cercano'), value: 'round' },
                    { label: __('Redondear Hacia Arriba'), value: 'ceil' },
                    { label: __('Redondear Hacia Abajo'), value: 'floor' }
                ],
                default: 'none'
            },
            parent: $('#fc-rounding'),
            only_input: false
        });
        this.f_rounding.refresh();

        this.f_status = frappe.ui.form.make_control({
            df: { 
                fieldtype: 'Select', 
                fieldname: 'status', 
                label: __('Filtrar Estado'),
                options: [
                    { label: __('Todos'), value: '' },
                    { label: __('Margen Negativo'), value: 'margen_negativo' },
                    { label: __('Bajo Margen Meta'), value: 'bajo_meta' },
                    { label: __('Sin Costo'), value: 'sin_costo' },
                    { label: __('Sin Precio'), value: 'sin_precio' }
                ],
                default: ''
            },
            parent: $('#fc-status'),
            only_input: false
        });
        this.f_status.refresh();
    }

    bind_events() {
        let me = this;

        $('#btn-prev-page').on('click', function() {
            if (me.current_page > 1) {
                me.current_page--;
                me.load_data();
            }
        });

        $('#btn-next-page').on('click', function() {
            let total_pages = Math.ceil(me.total_records / me.page_length);
            if (me.current_page < total_pages) {
                me.current_page++;
                me.load_data();
            }
        });

        $('#btn-reset-filters').on('click', function() {
            me.f_warehouse.set_value('');
            me.f_item_group.set_value('');
            me.f_brand.set_value('');
            me.f_item_code.set_value('');
            me.f_target_margin.set_value('');
            me.f_rounding.set_value('none');
            me.f_status.set_value('');
            me.column_filters = {};
            me.current_page = 1;
            me.load_data();
        });

        frappe.realtime.on('bulk_price_update_completed', function(data) {
            frappe.hide_progress();
            me.handle_bulk_update_completed(data);
        });
    }

    load_data() {
        let me = this;
        let company = this.f_company.get_value();
        if (!company) {
            frappe.msgprint(__('Por favor seleccione una Empresa.'));
            return;
        }

        frappe.call({
            method: 'erpnext.selling.page.precio_y_utilidades.precio_y_utilidades.get_pricing_analysis',
            args: {
                company: company,
                price_list: this.f_price_list.get_value(),
                warehouse: this.f_warehouse.get_value(),
                item_group: this.f_item_group.get_value(),
                brand: this.f_brand.get_value(),
                item_code: this.f_item_code.get_value(),
                target_margin: this.f_target_margin.get_value(),
                rounding_strategy: this.f_rounding.get_value(),
                status_filter: this.f_status.get_value(),
                sort_by: this.sort_by,
                sort_order: this.sort_order,
                page: this.current_page,
                page_length: this.page_length
            },
            freeze: true,
            freeze_message: __('Cargando análisis de precios...'),
            callback: function(r) {
                if (r.message) {
                    me.items_data = r.message.items || [];
                    me.total_records = r.message.total_records || 0;
                    me.apply_in_grid_column_filters();
                    me.update_pagination_ui(r.message.total_pages);
                }
            }
        });
    }

    apply_in_grid_column_filters() {
        let me = this;
        let filters = this.column_filters;

        this.filtered_items_data = this.items_data.filter(row => {
            if (filters.code && !row.item_code.toLowerCase().includes(filters.code.toLowerCase())) {
                return false;
            }
            if (filters.name && !row.item_name.toLowerCase().includes(filters.name.toLowerCase())) {
                return false;
            }
            if (filters.tax && filters.tax !== "" && String(row.tax_rate) !== String(filters.tax)) {
                return false;
            }
            if (filters.status && filters.status !== "" && row.row_status !== filters.status) {
                return false;
            }
            return true;
        });

        this.render_grid();
    }

    render_grid() {
        let me = this;
        let $container = $('#datatable-container');
        $container.empty();

        if (this.filtered_items_data.length === 0) {
            $container.html(`<div class="text-center text-muted p-5">${__('No se encontraron artículos con los filtros aplicados.')}</div>`);
            return;
        }

        let get_sort_icon = (field) => {
            if (me.sort_by === field) {
                return me.sort_order === 'ASC' ? ' <i class="fa fa-sort-asc text-primary"></i>' : ' <i class="fa fa-sort-desc text-primary"></i>';
            }
            return ' <i class="fa fa-sort text-muted" style="opacity: 0.3;"></i>';
        };

        let table_html = `
            <table class="table table-bordered table-hover table-sm m-0 align-middle" style="font-size: 13px;">
                <thead style="background-color: #f8f9fa;">
                    <!-- FILA 1: Encabezados con Ordenamiento Interactivo -->
                    <tr>
                        <th style="width: 38px;" class="text-center"><input type="checkbox" id="select-all-rows"></th>
                        <th class="th-sortable" data-field="item_code" style="cursor:pointer;">${__('Código')}${get_sort_icon('item_code')}</th>
                        <th class="th-sortable" data-field="item_name" style="cursor:pointer;">${__('Nombre del Artículo')}${get_sort_icon('item_name')}</th>
                        <th class="text-right th-sortable" data-field="cost" style="cursor:pointer;">${__('Costo')}${get_sort_icon('cost')}</th>
                        <th class="text-right th-sortable" data-field="current_price" style="cursor:pointer;">${__('Precio Actual')}${get_sort_icon('current_price')}</th>
                        <th class="text-center">${__('ISV %')}</th>
                        <th class="text-right">${__('Precio Neto')}</th>
                        <th class="text-right th-sortable" data-field="current_margin" style="cursor:pointer;">${__('Margen Actual')}${get_sort_icon('current_margin')}</th>
                        <th class="text-right" style="width: 130px; background-color: #eef6ff;">${__('Margen Meta % (Editable)')}</th>
                        <th class="text-right">${__('Precio Sugerido')}</th>
                        <th class="text-right" style="width: 140px; background-color: #fff8dc;">${__('Nuevo Precio (Editable)')}</th>
                        <th class="text-right th-sortable" data-field="new_margin" style="cursor:pointer;">${__('Margen Proyectado')}${get_sort_icon('new_margin')}</th>
                        <th class="text-right th-sortable" data-field="variation" style="cursor:pointer;">${__('Variación')}${get_sort_icon('variation')}</th>
                        <th class="text-center">${__('Estado')}</th>
                    </tr>
                    <!-- FILA 2: Filtros Rápidos de Columna (In-Grid Column Search) -->
                    <tr style="background-color: #f1f3f5;">
                        <th></th>
                        <th><input type="text" class="form-control form-control-sm in-grid-filter" data-col="code" placeholder="${__('Filtrar código...')}" value="${me.column_filters.code || ''}"></th>
                        <th><input type="text" class="form-control form-control-sm in-grid-filter" data-col="name" placeholder="${__('Filtrar nombre...')}" value="${me.column_filters.name || ''}"></th>
                        <th></th>
                        <th></th>
                        <th>
                            <select class="form-control form-control-sm in-grid-filter" data-col="tax">
                                <option value="">${__('Todos')}</option>
                                <option value="15" ${me.column_filters.tax === '15' ? 'selected' : ''}>15%</option>
                                <option value="18" ${me.column_filters.tax === '18' ? 'selected' : ''}>18%</option>
                                <option value="0" ${me.column_filters.tax === '0' ? 'selected' : ''}>0%</option>
                            </select>
                        </th>
                        <th></th>
                        <th></th>
                        <th></th>
                        <th></th>
                        <th></th>
                        <th></th>
                        <th></th>
                        <th>
                            <select class="form-control form-control-sm in-grid-filter" data-col="status">
                                <option value="">${__('Todos')}</option>
                                <option value="ok" ${me.column_filters.status === 'ok' ? 'selected' : ''}>OK</option>
                                <option value="bajo_meta" ${me.column_filters.status === 'bajo_meta' ? 'selected' : ''}>Bajo Meta</option>
                                <option value="margen_negativo" ${me.column_filters.status === 'margen_negativo' ? 'selected' : ''}>Margen < 0%</option>
                                <option value="sin_costo" ${me.column_filters.status === 'sin_costo' ? 'selected' : ''}>Sin Costo</option>
                                <option value="sin_precio" ${me.column_filters.status === 'sin_precio' ? 'selected' : ''}>Sin Precio</option>
                            </select>
                        </th>
                    </tr>
                </thead>
                <tbody>
                    ${this.filtered_items_data.map(row => me.render_row_html(row)).join('')}
                </tbody>
            </table>
        `;

        $container.html(table_html);
        this.bind_grid_cell_events();
    }

    render_row_html(row) {
        let is_checked = this.selected_items.has(row.item_code) ? 'checked' : '';
        let cost_str = row.has_cost ? format_currency(row.cost, row.currency) : `<span class="text-muted font-italic">${__('No disponible')}</span>`;
        let curr_price_str = row.current_price ? format_currency(row.current_price, row.currency) : `<span class="text-muted">${__('Sin precio')}</span>`;
        let net_price_str = row.current_net_price ? format_currency(row.current_net_price, row.currency) : '-';
        let margin_str = row.current_margin !== null ? `<span class="${row.current_margin < 0 ? 'text-danger font-weight-bold' : 'text-success'}">${row.current_margin}%</span>` : '-';
        
        let sug_price_str = row.suggested_price ? `<strong class="text-primary cell-sug-price" data-code="${row.item_code}">${format_currency(row.suggested_price, row.currency)}</strong>` : '-';
        let new_margin_str = row.new_margin !== null ? `<span class="${row.new_margin < 0 ? 'text-danger font-weight-bold' : 'text-success font-weight-bold'} cell-new-margin" data-code="${row.item_code}">${row.new_margin}%</span>` : '-';
        let variation_str = `<span class="${row.variation > 0 ? 'text-success' : (row.variation < 0 ? 'text-danger' : 'text-muted')} cell-variation" data-code="${row.item_code}">${format_currency(row.variation, row.currency)}</span>`;

        return `
            <tr data-code="${row.item_code}">
                <td class="text-center"><input type="checkbox" class="row-select" data-code="${row.item_code}" ${is_checked}></td>
                <td><strong>${row.item_code}</strong></td>
                <td>${row.item_name}</td>
                <td class="text-right">${cost_str}</td>
                <td class="text-right font-weight-bold">${curr_price_str}</td>
                <td class="text-center">${row.tax_rate}%</td>
                <td class="text-right">${net_price_str}</td>
                <td class="text-right">${margin_str}</td>
                <td>
                    <input type="number" class="form-control form-control-sm cell-target-margin text-right font-weight-bold" style="background-color: #eef6ff; border-color: #b8daff;" data-code="${row.item_code}" value="${row.target_margin || 35}" step="0.5">
                </td>
                <td class="text-right">${sug_price_str}</td>
                <td>
                    <input type="number" class="form-control form-control-sm cell-new-price text-right font-weight-bold" style="background-color: #fff8dc; border-color: #ffeba8;" data-code="${row.item_code}" value="${row.new_price || 0}" step="0.5">
                </td>
                <td class="text-right">${new_margin_str}</td>
                <td class="text-right">${variation_str}</td>
                <td class="text-center cell-status" data-code="${row.item_code}">${this.get_badge_html(row.row_status)}</td>
            </tr>
        `;
    }

    bind_grid_cell_events() {
        let me = this;

        // Ordenamiento al hacer clic en el Encabezado
        $('.th-sortable').on('click', function() {
            let field = $(this).data('field');
            if (me.sort_by === field) {
                me.sort_order = me.sort_order === 'ASC' ? 'DESC' : 'ASC';
            } else {
                me.sort_by = field;
                me.sort_order = 'ASC';
            }
            me.load_data();
        });

        // Filtros Rápidos por Columna (In-Grid Column Search)
        $('.in-grid-filter').on('input change', function() {
            let col = $(this).data('col');
            me.column_filters[col] = $(this).val();
            me.apply_in_grid_column_filters();
        });

        $('#select-all-rows').on('change', function() {
            let is_checked = $(this).is(':checked');
            $('.row-select').prop('checked', is_checked);
            me.filtered_items_data.forEach(r => {
                if (is_checked) me.selected_items.add(r.item_code);
                else me.selected_items.delete(r.item_code);
            });
            me.update_metrics_summary();
        });

        $('.row-select').on('change', function() {
            let code = $(this).data('code');
            if ($(this).is(':checked')) me.selected_items.add(code);
            else me.selected_items.delete(code);
            me.update_metrics_summary();
        });

        $('.cell-target-margin').on('input change', function() {
            let code = $(this).data('code');
            let target_margin = flt($(this).val());
            let row = me.items_data.find(r => r.item_code === code);

            if (row && row.has_cost && row.cost > 0 && target_margin < 100) {
                row.target_margin = target_margin;
                
                let margin_factor = 1.0 - (target_margin / 100.0);
                let raw_net_price = row.cost / margin_factor;
                let tax_factor = 1.0 + (flt(row.tax_rate) / 100.0);
                let raw_final_price = raw_net_price * tax_factor;
                
                let rounding_strategy = me.f_rounding.get_value() || 'none';
                let suggested_price = me.apply_rounding(raw_final_price, rounding_strategy);
                
                row.suggested_price = flt(suggested_price, 2);
                row.new_price = flt(suggested_price, 2);

                let real_net_price = suggested_price / tax_factor;
                let utility = real_net_price - row.cost;
                let margin = real_net_price > 0 ? (utility / real_net_price * 100.0) : 0.0;

                row.new_net_price = flt(real_net_price, 2);
                row.new_utility = flt(utility, 2);
                row.new_margin = flt(margin, 2);
                row.variation = flt(suggested_price - (row.current_price || 0), 2);

                $(`.cell-sug-price[data-code="${code}"]`).text(format_currency(row.suggested_price, row.currency));
                $(`.cell-new-price[data-code="${code}"]`).val(row.new_price);
                
                $(`.cell-new-margin[data-code="${code}"]`).text(`${row.new_margin}%`)
                    .attr('class', `cell-new-margin ${row.new_margin < 0 ? 'text-danger font-weight-bold' : 'text-success font-weight-bold'}`);
                
                $(`.cell-variation[data-code="${code}"]`).text(format_currency(row.variation, row.currency))
                    .attr('class', `cell-variation ${row.variation > 0 ? 'text-success' : (row.variation < 0 ? 'text-danger' : 'text-muted')}`);
            }
        });

        $('.cell-new-price').on('input change', function() {
            let code = $(this).data('code');
            let new_price = flt($(this).val());
            let row = me.items_data.find(r => r.item_code === code);
            
            if (row) {
                row.new_price = new_price;
                
                if (new_price > 0 && row.has_cost && row.cost > 0) {
                    let tax_factor = 1.0 + (flt(row.tax_rate) / 100.0);
                    let net_price = new_price / tax_factor;
                    let utility = net_price - row.cost;
                    let margin = net_price > 0 ? (utility / net_price * 100.0) : 0.0;
                    
                    row.new_net_price = flt(net_price, 2);
                    row.new_utility = flt(utility, 2);
                    row.new_margin = flt(margin, 2);
                    row.variation = flt(new_price - (row.current_price || 0), 2);

                    $(`.cell-new-margin[data-code="${code}"]`).text(`${row.new_margin}%`)
                        .attr('class', `cell-new-margin ${row.new_margin < 0 ? 'text-danger font-weight-bold' : 'text-success font-weight-bold'}`);
                    
                    $(`.cell-variation[data-code="${code}"]`).text(format_currency(row.variation, row.currency))
                        .attr('class', `cell-variation ${row.variation > 0 ? 'text-success' : (row.variation < 0 ? 'text-danger' : 'text-muted')}`);
                }
            }
        });
    }

    copy_suggested_to_new_prices() {
        let me = this;
        let count = 0;

        this.filtered_items_data.forEach(row => {
            if (me.selected_items.has(row.item_code) && row.suggested_price > 0) {
                row.new_price = row.suggested_price;
                $(`.cell-new-price[data-code="${row.item_code}"]`).val(row.new_price).trigger('change');
                count++;
            }
        });

        if (count > 0) {
            frappe.show_alert({
                message: __('Copiados {0} precios sugeridos a nuevos precios.', [count]),
                indicator: 'green'
            }, 3);
        } else {
            frappe.msgprint(__('Por favor seleccione al menos un artículo que tenga un precio sugerido válido.'));
        }
    }

    apply_rounding(value, strategy) {
        let val = flt(value);
        strategy = (strategy || 'none').toLowerCase();
        if (strategy === 'ceil') return Math.ceil(val);
        if (strategy === 'floor') return Math.floor(val);
        if (strategy === 'round') return Math.round(val);
        return flt(val, 2);
    }

    apply_selected_prices() {
        let me = this;
        let selected_codes = Array.from(this.selected_items);
        
        if (selected_codes.length === 0) {
            frappe.msgprint(__('Por favor seleccione al menos un artículo para actualizar.'));
            return;
        }

        let selected_payload = this.items_data.filter(r => me.selected_items.has(r.item_code) && r.new_price > 0);

        if (selected_payload.length === 0) {
            frappe.msgprint(__('Ninguno de los artículos seleccionados tiene un Nuevo Precio válido (> 0).'));
            return;
        }

        frappe.confirm(
            __('¿Está seguro de aplicar la actualización de precios para los <strong>{0}</strong> artículos seleccionados en la Lista de Precios <strong>{1}</strong>?', [selected_payload.length, me.f_price_list.get_value()]),
            function() {
                frappe.call({
                    method: 'erpnext.selling.page.precio_y_utilidades.precio_y_utilidades.apply_bulk_prices',
                    args: {
                        company: me.f_company.get_value(),
                        price_list: me.f_price_list.get_value(),
                        warehouse: me.f_warehouse.get_value(),
                        items_payload: JSON.stringify(selected_payload)
                    },
                    freeze: true,
                    freeze_message: __('Aplicando cambios en Item Price...'),
                    callback: function(r) {
                        if (r.message) {
                            me.handle_bulk_update_completed(r.message);
                        }
                    }
                });
            }
        );
    }

    handle_bulk_update_completed(res) {
        let me = this;

        if (res.status === 'enqueued') {
            frappe.msgprint({
                title: __('Tarea en Segundo Plano'),
                indicator: 'blue',
                message: res.message
            });
            return;
        }

        let msg = `
            <div class="p-2">
                <p class="text-success font-weight-bold">${__('Artículos actualizados exitosamente en Item Price')}: ${res.updated}</p>
        `;

        if (res.stale_skipped > 0) {
            msg += `<p class="text-warning font-weight-bold">${__('Artículos omitidos por cambios de concurrencia')}: ${res.stale_skipped}</p>`;
        }

        if (res.errors_count > 0) {
            msg += `<p class="text-danger font-weight-bold">${__('Errores')}: ${res.errors_count}</p>`;
        }

        msg += `</div>`;

        frappe.show_alert({
            message: __('Precios actualizados exitosamente'),
            indicator: 'green'
        }, 5);

        frappe.msgprint({
            title: __('Resultado de Actualización'),
            indicator: res.stale_skipped > 0 ? 'orange' : 'green',
            message: msg
        });

        this.selected_items.clear();
        this.load_data();
    }

    update_metrics_summary() {
        $('#metric-total').text(this.total_records);
        $('#metric-visible').text(this.filtered_items_data.length);
        $('#metric-selected').text(this.selected_items.size);
    }

    update_pagination_ui(total_pages) {
        $('#metric-total').text(this.total_records);
        $('#metric-visible').text(this.filtered_items_data.length);
        $('#metric-selected').text(this.selected_items.size);
        $('#label-page-info').text(`Página ${this.current_page} de ${total_pages || 1}`);
        $('#btn-prev-page').prop('disabled', this.current_page <= 1);
        $('#btn-next-page').prop('disabled', this.current_page >= total_pages);
    }

    get_badge_html(status) {
        if (status === 'sin_costo') {
            return `<span class="indicator-pill gray">${__('Sin Costo')}</span>`;
        } else if (status === 'sin_precio') {
            return `<span class="indicator-pill orange">${__('Sin Precio')}</span>`;
        } else if (status === 'margen_negativo') {
            return `<span class="badge badge-danger" style="background-color:#e63946; color:#fff;">${__('Margen < 0%')}</span>`;
        } else if (status === 'bajo_meta') {
            return `<span class="indicator-pill orange">${__('Bajo Meta')}</span>`;
        } else if (status === 'requiere_recalculo') {
            return `<span class="badge badge-info" title="${__('Costo o precio cambió durante el análisis')}">${__('Requiere Recálculo')}</span>`;
        }
        return `<span class="indicator-pill green">${__('OK')}</span>`;
    }
}
