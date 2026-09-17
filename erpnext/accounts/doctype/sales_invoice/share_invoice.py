import os
import urllib.parse
import hashlib
import pdfkit
import frappe
from frappe import _


def get_document_share_key(doc):
	secret = frappe.local.conf.get("encryption_key") or "leaf_secret_share_key"
	raw = f"{doc.doctype}:{doc.name}:{doc.creation}:{secret}".encode("utf-8")
	return hashlib.sha256(raw).hexdigest()[:16]


@frappe.whitelist()
def get_share_details(doctype, name, format=None, host=None):
	"""
	Returns customer contact details, access key, and pre-composed message for sharing via WhatsApp.
	"""
	if not doctype or not name:
		frappe.throw(_("DocType and Name are required."))

	doc = frappe.get_doc(doctype, name)
	doc.check_permission("read")

	customer_mobile = getattr(doc, "contact_mobile", None) or getattr(doc, "contact_phone", None)
	customer_name = getattr(doc, "customer_name", None) or getattr(doc, "customer", "")

	if not customer_mobile and doc.get("customer"):
		customer_doc = frappe.db.get_value("Customer", doc.customer, ["mobile_no"], as_dict=True)
		if customer_doc:
			customer_mobile = customer_doc.get("mobile_no")

	if not customer_mobile and doc.get("contact_person"):
		contact_doc = frappe.db.get_value("Contact", doc.contact_person, ["mobile_no", "phone"], as_dict=True)
		if contact_doc:
			customer_mobile = contact_doc.get("mobile_no") or contact_doc.get("phone")

	currency = doc.get("currency") or "L"
	grand_total = frappe.utils.fmt_money(doc.get("grand_total") or 0, currency=currency)

	share_key = get_document_share_key(doc)
	base_host = (host or frappe.utils.get_url()).rstrip("/")

	# Ensure URL parameters are properly encoded to prevent WhatsApp link truncation on spaces
	encoded_doctype = urllib.parse.quote_plus(doctype)
	encoded_name = urllib.parse.quote_plus(name)
	encoded_format = urllib.parse.quote_plus(format or "Standard")

	pdf_url = (
		f"{base_host}/api/method/erpnext.accounts.doctype.sales_invoice.share_invoice.download_pdf?"
		f"doctype={encoded_doctype}&name={encoded_name}&format={encoded_format}&no_letterhead=0&key={share_key}"
	)

	default_message = (
		f"Estimado(a) {customer_name or 'Cliente'},\n"
		f"Le compartimos el comprobante de su Factura {name} por un monto de {grand_total}.\n"
		f"Puede consultar y descargar su factura en el siguiente enlace:\n{pdf_url}"
	)

	return {
		"customer_name": customer_name,
		"customer_mobile": customer_mobile or "",
		"grand_total": grand_total,
		"currency": currency,
		"share_key": share_key,
		"pdf_url": pdf_url,
		"default_message": default_message
	}


@frappe.whitelist()
def log_share_event(doctype, name, print_format=None, share_method=None):
	"""
	Logs adoption metrics when a user triggers the 'Compartir' action on a document.
	Does NOT store sensitive recipient data or message content.
	"""
	if not doctype or not name:
		return {"status": "error", "message": "doctype and name are required"}

	if not frappe.has_permission(doctype, "read", name):
		frappe.throw(_("No permission to read {0} {1}").format(doctype, name), frappe.PermissionError)

	try:
		log_msg = f"User={frappe.session.user} | DocType={doctype} | Name={name} | Format={print_format or 'Default'} | Method={share_method or 'unknown'}"
		frappe.logger("leaf_share").info(log_msg)
		return {"status": "success"}
	except Exception as e:
		frappe.log_error(title="Leaf Share Analytics Error", message=str(e))
		return {"status": "error", "message": str(e)}


@frappe.whitelist(allow_guest=True)
def download_pdf(doctype, name, format=None, no_letterhead=0, letterhead=None, key=None):
	"""
	Generates PDF for document sharing in LEAF ERP.
	Allows direct public access for recipients with a valid document signature key (no login required).
	Converts HTTP/relative asset links to local file:// paths to prevent network loop deadlocks.
	"""
	if not doctype or not name:
		frappe.throw(_("DocType and Name are required."))

	if frappe.session.user == "Guest":
		doc = frappe.get_doc(doctype, name)
		expected_key = get_document_share_key(doc)
		if not key or key != expected_key:
			frappe.throw(_("Enlace no válido o expirado para visualizar este documento."), frappe.PermissionError)
	else:
		doc = frappe.get_doc(doctype, name)
		doc.check_permission("read")

	if not getattr(frappe.local, "assets_json", None):
		try:
			assets_file = frappe.read_file("sites/assets/assets.json") or frappe.read_file("assets/assets.json")
			frappe.local.assets_json = frappe.parse_json(assets_file) if assets_file else {}
		except Exception:
			frappe.local.assets_json = {}

	frappe.flags.ignore_print_permissions = True
	try:
		html = frappe.get_print(
			doctype=doctype,
			name=name,
			print_format=format,
			doc=doc,
			no_letterhead=no_letterhead,
			letterhead=letterhead,
			as_pdf=False
		)
	finally:
		frappe.flags.ignore_print_permissions = False

	bench_path = frappe.utils.get_bench_path()
	site_path = frappe.get_site_path()
	host = frappe.utils.get_url()

	if host and host in html:
		html = html.replace(host + "/assets/", "file://" + bench_path + "/sites/assets/")
		html = html.replace(host + "/files/", "file://" + site_path + "/public/files/")
		html = html.replace(host, "file://" + site_path + "/public")

	html = html.replace("/assets/", "file://" + bench_path + "/sites/assets/")
	html = html.replace("/files/", "file://" + site_path + "/public/files/")

	options = {
		"enable-local-file-access": None,
		"load-error-handling": "ignore",
		"load-media-error-handling": "ignore",
		"quiet": None,
		"encoding": "UTF-8"
	}

	try:
		pdf_bytes = pdfkit.from_string(html, options=options)
	except Exception as e:
		frappe.log_error(title="Leaf PDF Generation Fallback", message=str(e))
		pdf_bytes = frappe.get_print(
			doctype=doctype,
			name=name,
			print_format=format,
			doc=doc,
			no_letterhead=no_letterhead,
			letterhead=letterhead,
			as_pdf=True
		)

	frappe.local.response.filename = f"{name.replace('/', '-')}.pdf"
	frappe.local.response.filecontent = pdf_bytes
	frappe.local.response.type = "pdf"

