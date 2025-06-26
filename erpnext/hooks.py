# Copyright (c) 2015, Frappe Technologies Pvt. Ltd. and Contributors
# License: GNU General Public License v3. See license.txt

from __future__ import unicode_literals
from frappe import _

app_name = "erpnext"
app_title = "ERPNext"
app_publisher = "Frappe Technologies Pvt. Ltd."
app_description = "ERP made simple"
app_icon = "octicon octicon-briefcase"
app_color = "grey"
app_email = "info@erpnext.com"
app_license = "GNU General Public License v3"

# Fixtures to include Workspace configuration
fixtures = [
    {
        "dt": "Workspace",
        "filters": [["name", "in", ["Accounting"]]]
    }
]

# Run function to rebuild Accounting workspace after migrations
after_migrate = [
    "erpnext.accounts.report.utils.rebuild_accounting_workspace"
]
