import frappe
from frappe.utils import flt


def execute(filters=None):
    columns = get_columns()
    data = get_data(filters)
    return columns, data


def get_columns():
    return [
        {"fieldname": "posting_date", "label": "Fecha", "fieldtype": "Date", "width": 100},
        {"fieldname": "document_type", "label": "Tipo Doc", "fieldtype": "Data", "width": 80},
        {"fieldname": "invoice_number", "label": "Factura", "fieldtype": "Link", "options": "Sales Invoice", "width": 180},
        {"fieldname": "customer", "label": "Cliente", "fieldtype": "Data", "width": 140},
        {"fieldname": "tax_id", "label": "RTN", "fieldtype": "Data", "width": 130},
        {"fieldname": "exempt_amount", "label": "Exento", "fieldtype": "Currency", "width": 100},
        {"fieldname": "taxed_amount_15", "label": "Base 15%", "fieldtype": "Currency", "width": 100},
        {"fieldname": "isv_15", "label": "ISV 15%", "fieldtype": "Currency", "width": 100},
        {"fieldname": "taxed_amount_18", "label": "Base 18%", "fieldtype": "Currency", "width": 100},
        {"fieldname": "isv_18", "label": "ISV 18%", "fieldtype": "Currency", "width": 100},
        {"fieldname": "discount_amount", "label": "Descuento", "fieldtype": "Currency", "width": 100},
        {"fieldname": "monto_bruto", "label": "Monto Bruto", "fieldtype": "Currency", "width": 110},
        {"fieldname": "rounded_total", "label": "Total", "fieldtype": "Currency", "width": 100},
        {"fieldname": "grand_total", "label": "Total Final", "fieldtype": "Currency", "width": 100},
    ]


def get_data(filters):
    sales_invoice = frappe.get_all(
        "Sales Invoice",
        filters={"docstatus": 1},
        fields=[
            "posting_date",
            "customer",
            "name",
            "tax_id",
            "exempt_amount",
            "taxed_amount_15",
            "isv_15",
            "taxed_amount_18",
            "isv_18",
            "discount_amount",
            "rounded_total",
            "grand_total",
            "naming_series"
        ],
        order_by="posting_date asc"
    )
    
    data = []
    for sales in sales_invoice:
        type_document = "Devolucion" if sales.naming_series and "Devolucion" in sales.naming_series else "Factura"
        monto_bruto = (
            flt(sales.exempt_amount)
            + flt(sales.taxed_amount_15)
            + flt(sales.taxed_amount_18)
            - flt(sales.discount_amount)
        )

        row = [
            sales.posting_date,
            type_document,
            sales.name,
            sales.customer,
            sales.tax_id,
            sales.exempt_amount,
            sales.taxed_amount_15,
            sales.isv_15,
            sales.taxed_amount_18,
            sales.isv_18,
            sales.discount_amount,
            monto_bruto,
            sales.rounded_total,
            sales.grand_total
        ]
        data.append(row)

    return data