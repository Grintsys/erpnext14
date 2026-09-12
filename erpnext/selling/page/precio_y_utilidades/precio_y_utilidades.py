import math
import frappe
from frappe import _
from frappe.utils import flt, cint

@frappe.whitelist()
def get_pricing_analysis(
    company,
    price_list=None,
    warehouse=None,
    item_group=None,
    brand=None,
    item_code=None,
    search_term=None,
    status_filter=None,
    target_margin=None,
    rounding_strategy=None,
    page=1,
    page_length=100,
    sort_by="item_code",
    sort_order="ASC"
):
    """
    Backend API de consulta y análisis de precios.
    Soporta ordenamiento dinámico por cualquier columna principal.
    """
    if not frappe.has_permission("Item Price", "read"):
        frappe.throw(_("No tiene permisos para consultar Precios de Artículos"), frappe.PermissionError)

    page = max(1, cint(page))
    page_length = min(500, max(10, cint(page_length)))
    offset = (page - 1) * page_length

    target_margin_val = flt(target_margin) if target_margin is not None and str(target_margin).strip() != "" else None
    rounding_strategy = (rounding_strategy or "none").lower()

    where_conditions = ["i.disabled = 0", "i.is_sales_item = 1"]
    params = {"company": company}

    if item_group:
        ig_bounds = frappe.db.get_value("Item Group", item_group, ["lft", "rgt"], as_dict=True)
        if ig_bounds:
            where_conditions.append("""i.item_group IN (
                SELECT name FROM `tabItem Group` WHERE lft >= %(ig_lft)s AND rgt <= %(ig_rgt)s
            )""")
            params["ig_lft"] = ig_bounds.lft
            params["ig_rgt"] = ig_bounds.rgt
        else:
            where_conditions.append("i.item_group = %(item_group)s")
            params["item_group"] = item_group

    if brand:
        where_conditions.append("i.brand = %(brand)s")
        params["brand"] = brand

    if item_code:
        where_conditions.append("i.name = %(item_code)s")
        params["item_code"] = item_code

    if search_term and search_term.strip():
        where_conditions.append("(i.name LIKE %(search)s OR i.item_name LIKE %(search)s)")
        params["search"] = f"%{search_term.strip()}%"

    price_list_condition = ""
    if price_list and price_list.strip():
        price_list_condition = "AND ip.price_list = %(price_list)s"
        params["price_list"] = price_list.strip()

    allowed_sort_fields = {
        "item_code": "i.name",
        "item_name": "i.item_name",
        "item_group": "i.item_group",
        "price_list": "ip.price_list",
        "cost": "i.valuation_rate",
        "current_price": "ip.price_list_rate"
    }
    sort_column = allowed_sort_fields.get(sort_by, "i.name")
    order_direction = "DESC" if str(sort_order).upper() == "DESC" else "ASC"

    sql_query = f"""
        SELECT 
            i.name AS item_code,
            i.item_name,
            i.item_group,
            i.brand,
            i.stock_uom AS uom,
            i.valuation_rate AS item_std_valuation_rate,
            ip.name AS item_price_name,
            ip.price_list,
            ip.price_list_rate AS current_price,
            ip.currency,
            ip.modified AS item_price_modified
        FROM `tabItem` i
        LEFT JOIN `tabItem Price` ip 
            ON ip.item_code = i.name 
            AND ip.selling = 1 
            {price_list_condition}
        WHERE {" AND ".join(where_conditions)}
        ORDER BY {sort_column} {order_direction}
    """

    raw_items = frappe.db.sql(sql_query, params, as_dict=True)

    item_codes = list({r["item_code"] for r in raw_items})
    costs_map = get_batch_costs(item_codes, company, warehouse)
    taxes_map = get_batch_taxes(item_codes)

    analyzed_rows = []

    for r in raw_items:
        code = r["item_code"]
        cost_info = costs_map.get(code, {"cost": 0.0, "has_cost": False, "cost_source": "Sin Inventario"})
        cost = flt(cost_info["cost"])
        has_cost = cost_info["has_cost"]
        cost_source = cost_info["cost_source"]

        current_price = flt(r["current_price"]) if r.get("current_price") is not None else None
        tax_rate = flt(taxes_map.get(code, 15.0))

        current_calc = calculate_pricing_metrics(cost, current_price, tax_rate, has_cost)

        row_target_margin = target_margin_val if target_margin_val is not None else (current_calc["margin"] if current_calc["margin"] is not None else 35.0)

        suggested_calc = None
        if has_cost and row_target_margin is not None:
            suggested_calc = calculate_target_price_and_margin(
                cost=cost,
                target_margin=row_target_margin,
                tax_rate=tax_rate,
                rounding_strategy=rounding_strategy
            )

        row_status = determine_row_status(has_cost, current_price, current_calc, target_margin_val)

        if status_filter and not matches_status_filter(row_status, current_calc, status_filter):
            continue

        analyzed_rows.append({
            "item_code": code,
            "item_name": r["item_name"],
            "item_group": r["item_group"],
            "brand": r.get("brand"),
            "uom": r["uom"],
            "price_list": r.get("price_list") or price_list or "",
            "currency": r.get("currency") or "HNL",
            "cost": cost if has_cost else None,
            "has_cost": has_cost,
            "cost_source": cost_source,
            "current_price": current_price,
            "has_price": current_price is not None,
            "tax_rate": tax_rate,
            "current_net_price": current_calc["net_price"],
            "current_isv_amount": current_calc["isv_amount"],
            "current_utility": current_calc["utility"],
            "current_margin": current_calc["margin"],
            
            "target_margin": flt(row_target_margin, 2),
            
            "suggested_price": suggested_calc["final_price"] if suggested_calc else current_price,
            "suggested_net_price": suggested_calc["net_price"] if suggested_calc else current_calc["net_price"],
            "suggested_utility": suggested_calc["utility"] if suggested_calc else current_calc["utility"],
            "suggested_margin": suggested_calc["margin"] if suggested_calc else current_calc["margin"],
            
            "new_price": suggested_calc["final_price"] if suggested_calc else (current_price or 0.0),
            "new_net_price": suggested_calc["net_price"] if suggested_calc else current_calc["net_price"],
            "new_utility": suggested_calc["utility"] if suggested_calc else current_calc["utility"],
            "new_margin": suggested_calc["margin"] if suggested_calc else current_calc["margin"],
            "variation": flt((suggested_calc["final_price"] if suggested_calc else (current_price or 0.0)) - (current_price or 0.0), 2),
            
            "item_price_name": r.get("item_price_name"),
            "item_price_modified": str(r.get("item_price_modified") or ""),
            "cost_at_analysis": cost if has_cost else None,
            "price_at_analysis": current_price,
            "row_status": row_status
        })

    # Ordenamiento secundario en memoria si se requiere ordenar por columnas calculadas (margen, variación)
    if sort_by in ["current_margin", "variation", "new_margin"]:
        reverse = (sort_order.upper() == "DESC")
        analyzed_rows.sort(key=lambda x: (x.get(sort_by) is not None, x.get(sort_by) or 0), reverse=reverse)

    total_records = len(analyzed_rows)
    paginated_rows = analyzed_rows[offset:offset + page_length]

    return {
        "items": paginated_rows,
        "total_records": total_records,
        "page": page,
        "page_length": page_length,
        "total_pages": math.ceil(total_records / page_length) if total_records > 0 else 1
    }


def calculate_pricing_metrics(cost, final_price, tax_rate, has_cost=True):
    if final_price is None or final_price <= 0:
        return {
            "net_price": None,
            "isv_amount": None,
            "utility": None,
            "margin": None
        }

    final_price = flt(final_price, 2)
    tax_rate = flt(tax_rate)
    
    tax_factor = 1.0 + (tax_rate / 100.0)
    net_price = flt(final_price / tax_factor, 4)
    isv_amount = flt(final_price - net_price, 4)

    if not has_cost or cost is None:
        return {
            "net_price": flt(net_price, 2),
            "isv_amount": flt(isv_amount, 2),
            "utility": None,
            "margin": None
        }

    cost = flt(cost, 4)
    utility = flt(net_price - cost, 4)
    margin = flt((utility / net_price * 100.0), 2) if net_price > 0 else 0.0

    return {
        "net_price": flt(net_price, 2),
        "isv_amount": flt(isv_amount, 2),
        "utility": flt(utility, 2),
        "margin": flt(margin, 2)
    }


def calculate_target_price_and_margin(cost, target_margin, tax_rate, rounding_strategy="none"):
    if not cost or cost <= 0 or target_margin >= 100.0:
        return None

    cost = flt(cost, 4)
    target_margin = flt(target_margin)
    tax_rate = flt(tax_rate)

    margin_factor = 1.0 - (target_margin / 100.0)
    raw_net_price = cost / margin_factor
    tax_factor = 1.0 + (tax_rate / 100.0)
    raw_final_price = raw_net_price * tax_factor

    rounded_final_price = apply_rounding(raw_final_price, rounding_strategy)

    real_net_price = flt(rounded_final_price / tax_factor, 4)
    real_utility = flt(real_net_price - cost, 4)
    real_margin = flt((real_utility / real_net_price * 100.0), 2) if real_net_price > 0 else 0.0

    return {
        "final_price": flt(rounded_final_price, 2),
        "net_price": flt(real_net_price, 2),
        "utility": flt(real_utility, 2),
        "margin": flt(real_margin, 2)
    }


def apply_rounding(value, strategy):
    val = flt(value)
    strategy = str(strategy).lower()

    if strategy == "ceil":
        return math.ceil(val)
    elif strategy == "floor":
        return math.floor(val)
    elif strategy == "round":
        return round(val)
    return flt(val, 2)


def get_batch_costs(item_codes, company, warehouse=None):
    if not item_codes:
        return {}

    result = {}

    if warehouse and warehouse.strip():
        bin_data = frappe.db.sql("""
            SELECT bin.item_code, bin.valuation_rate, bin.actual_qty
            FROM `tabBin` bin
            INNER JOIN `tabWarehouse` wh ON wh.name = bin.warehouse
            WHERE bin.item_code IN %(items)s
              AND bin.warehouse = %(warehouse)s
              AND wh.company = %(company)s
              AND wh.disabled = 0
              AND wh.is_group = 0
        """, {"items": item_codes, "warehouse": warehouse.strip(), "company": company}, as_dict=True)

        for b in bin_data:
            val_rate = flt(b["valuation_rate"])
            result[b["item_code"]] = {
                "cost": val_rate,
                "has_cost": val_rate > 0,
                "cost_source": f"Bodega {warehouse}"
            }
    else:
        weighted_data = frappe.db.sql("""
            SELECT 
                bin.item_code,
                SUM(bin.stock_value) AS total_stock_value,
                SUM(bin.actual_qty) AS total_actual_qty
            FROM `tabBin` bin
            INNER JOIN `tabWarehouse` wh ON wh.name = bin.warehouse
            LEFT JOIN `tabWarehouse Type` wt ON wt.name = wh.warehouse_type
            WHERE bin.item_code IN %(items)s
              AND wh.company = %(company)s
              AND wh.disabled = 0
              AND wh.is_group = 0
              AND wh.is_rejected_warehouse = 0
              AND (wh.warehouse_type IS NULL OR wh.warehouse_type != 'Transit')
              AND bin.actual_qty > 0
            GROUP BY bin.item_code
        """, {"items": item_codes, "company": company}, as_dict=True)

        for w in weighted_data:
            tot_val = flt(w["total_stock_value"])
            tot_qty = flt(w["total_actual_qty"])
            if tot_qty > 0 and tot_val > 0:
                weighted_cost = flt(tot_val / tot_qty, 4)
                result[w["item_code"]] = {
                    "cost": weighted_cost,
                    "has_cost": True,
                    "cost_source": "Ponderado Global"
                }

    std_costs = frappe.db.sql("""
        SELECT name AS item_code, valuation_rate
        FROM `tabItem`
        WHERE name IN %(items)s
    """, {"items": item_codes}, as_dict=True)

    for item in std_costs:
        code = item["item_code"]
        if code not in result or not result[code]["has_cost"]:
            std_val = flt(item["valuation_rate"])
            if std_val > 0:
                result[code] = {
                    "cost": std_val,
                    "has_cost": True,
                    "cost_source": "Valuación Ítem"
                }
            else:
                result[code] = {
                    "cost": 0.0,
                    "has_cost": False,
                    "cost_source": "Sin Costo"
                }

    return result


def get_batch_taxes(item_codes):
    if not item_codes:
        return {}

    taxes_map = {}
    item_taxes = frappe.db.sql("""
        SELECT it.parent AS item_code, itd.tax_rate
        FROM `tabItem` i
        INNER JOIN `tabItem Tax` it ON it.parent = i.name
        INNER JOIN `tabItem Tax Template Detail` itd ON itd.parent = it.item_tax_template
        WHERE it.parent IN %(items)s
    """, {"items": item_codes}, as_dict=True)

    for t in item_taxes:
        taxes_map[t["item_code"]] = flt(t["tax_rate"])

    for code in item_codes:
        if code not in taxes_map:
            taxes_map[code] = 15.0

    return taxes_map


def determine_row_status(has_cost, current_price, current_calc, target_margin):
    if not has_cost:
        return "sin_costo"
    if current_price is None or current_price <= 0:
        return "sin_precio"
    
    margin = current_calc.get("margin")
    if margin is not None and margin < 0:
        return "margen_negativo"
    if target_margin is not None and margin is not None and margin < target_margin:
        return "bajo_meta"
    
    return "ok"


def matches_status_filter(row_status, current_calc, status_filter):
    status_filter = str(status_filter).lower()
    if status_filter == "sin_costo":
        return row_status == "sin_costo"
    elif status_filter == "sin_precio":
        return row_status == "sin_precio"
    elif status_filter == "margen_negativo":
        return row_status == "margen_negativo"
    elif status_filter == "bajo_meta":
        return row_status in ["bajo_meta", "margen_negativo"]
    return True


@frappe.whitelist()
def apply_bulk_prices(company, price_list, items_payload, warehouse=None):
    if not frappe.has_permission("Item Price", "write"):
        frappe.throw(_("No tiene permisos para modificar Precios de Artículos"), frappe.PermissionError)

    items = frappe.parse_json(items_payload)
    if not items:
        frappe.throw(_("No se enviaron artículos para actualizar."))

    current_user = getattr(frappe.session, "user", "Administrator")

    if len(items) > 200:
        frappe.enqueue(
            "erpnext.selling.page.precio_y_utilidades.precio_y_utilidades.process_bulk_price_updates_worker",
            queue="long",
            timeout=1500,
            company=company,
            price_list=price_list,
            items=items,
            warehouse=warehouse,
            user=current_user
        )
        return {
            "status": "enqueued",
            "message": _("Los precios se están actualizando en segundo plano para {0} artículos.").format(len(items))
        }
    else:
        return process_bulk_price_updates_worker(company, price_list, items, warehouse, user=current_user)


def process_bulk_price_updates_worker(company, price_list, items, warehouse=None, user=None):
    item_codes = [r["item_code"] for r in items]
    
    current_costs = get_batch_costs(item_codes, company, warehouse)
    
    current_prices_sql = frappe.db.sql("""
        SELECT name, item_code, price_list_rate, modified
        FROM `tabItem Price`
        WHERE item_code IN %(items)s 
          AND price_list = %(price_list)s
          AND selling = 1
    """, {"items": item_codes, "price_list": price_list}, as_dict=True)
    
    current_prices = {p["item_code"]: p for p in current_prices_sql}

    updated_count = 0
    skipped_stale_count = 0
    error_count = 0
    stale_items = []
    errors = []

    for idx, row in enumerate(items):
        code = row["item_code"]
        new_price = flt(row.get("new_price"))
        
        if new_price <= 0:
            continue

        cost_info = current_costs.get(code, {"cost": 0.0, "has_cost": False})
        current_cost = flt(cost_info["cost"])
        analysis_cost = flt(row.get("cost_at_analysis")) if row.get("cost_at_analysis") is not None else None
        
        db_price_rec = current_prices.get(code)
        db_price = flt(db_price_rec["price_list_rate"]) if db_price_rec else None
        analysis_price = flt(row.get("price_at_analysis")) if row.get("price_at_analysis") is not None else None

        cost_changed = (abs(current_cost - analysis_cost) > 0.0001) if (cost_info["has_cost"] and analysis_cost is not None) else False
        price_changed = (db_price != analysis_price) if (db_price is not None and analysis_price is not None) else False

        if cost_changed or price_changed:
            skipped_stale_count += 1
            reason = "Costo de inventario se actualizó" if cost_changed else "Precio fue modificado por otro usuario"
            stale_items.append({
                "item_code": code,
                "reason": reason,
                "analysis_cost": analysis_cost,
                "current_cost": current_cost
            })
            continue

        try:
            if db_price_rec:
                frappe.db.set_value("Item Price", db_price_rec["name"], "price_list_rate", new_price, update_modified=True)
            else:
                new_doc = frappe.get_doc({
                    "doctype": "Item Price",
                    "item_code": code,
                    "price_list": price_list,
                    "price_list_rate": new_price,
                    "selling": 1
                })
                new_doc.insert(ignore_permissions=True)

            updated_count += 1
        except Exception as e:
            error_count += 1
            errors.append({"item_code": code, "error": str(e)})

    frappe.db.commit()

    result = {
        "status": "completed",
        "processed": len(items),
        "updated": updated_count,
        "stale_skipped": skipped_stale_count,
        "errors_count": error_count,
        "stale_items": stale_items,
        "errors": errors
    }

    if user and user != "Guest":
        frappe.publish_realtime("bulk_price_update_completed", result, user=user)

    return result
