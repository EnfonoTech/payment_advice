# Copyright (c) 2025, Enfono and contributors
# For license information, please see license.txt

import frappe
from frappe.model.document import Document


class PaymentAdvice(Document):
    def before_submit(self):
        self.validate_approver_permission()

    def validate_approver_permission(self):
        if not self.approver:
            frappe.throw("Please select an Approver before submitting")

        # Get user linked to the employee
        approver_user = frappe.db.get_value("Employee", self.approver, "user_id")
        
        if not approver_user:
            frappe.throw("No user account is linked to the selected Approver (Employee)")
        
        if frappe.session.user != approver_user:
            frappe.throw("Only the user associated with the selected Approver can submit this document")
