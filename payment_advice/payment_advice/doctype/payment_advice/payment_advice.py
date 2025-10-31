# Copyright (c) 2025, Enfono and contributors
# For license information, please see license.txt

import frappe
from frappe.model.document import Document
from frappe.utils import nowdate, money_in_words
from erpnext.accounts.doctype.payment_entry.payment_entry import get_payment_entry
from erpnext.accounts.utils import get_account_currency
from erpnext.setup.utils import get_exchange_rate

class PaymentAdvice(Document):
    def validate(self):
        if self.amount_to_be_settled:
            self.amount_to_be_settled_in_words = money_in_words(self.amount_to_be_settled)
        if self.payment_amount:
            pending = self.amount_to_be_settled - self.payment_amount
            self.pending_amount = pending if pending > 0 else 0

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

def get_party_account(party_type, party, company):
    if party_type == "Customer":
        return frappe.get_cached_value("Customer", party, "default_receivable_account") or \
               frappe.db.get_value("Company", company, "default_receivable_account")
    elif party_type == "Supplier":
        return frappe.get_cached_value("Supplier", party, "default_payable_account") or \
               frappe.db.get_value("Company", company, "default_payable_account")
    elif party_type == "Employee":
        return frappe.get_cached_value("Employee", party, "payable_account") or \
               frappe.db.get_value("Company", company, "default_payable_account")
    else:
        frappe.throw(f"Unsupported party type: {party_type}")

def get_default_company_account(company, mode_of_payment="Cash"):
    company_account = frappe.db.get_value(
        "Mode of Payment Account",
        {"parent": mode_of_payment, "company": company},
        "default_account"
    )
    
    if company_account:
        return company_account
    
    # Fallback to company's default accounts
    if mode_of_payment == "Cash":
        return frappe.db.get_value("Company", company, "default_cash_account")
    return frappe.db.get_value("Company", company, "default_bank_account")

def get_payment_type(party_type):
    if party_type == "Customer":
        return "Receive"
    elif party_type in ["Supplier", "Employee"]:
        return "Pay"
    else:
        frappe.throw(f"Unsupported party type for payment: {party_type}")

def get_payment_accounts(party_type, party_account, company_account):
    if party_type == "Customer":
        return party_account, company_account
    elif party_type in ["Supplier", "Employee"]:
        return company_account, party_account
    else:
        frappe.throw(f"Unsupported party type for payment accounts: {party_type}")

@frappe.whitelist()
def create_payment_entry(payment_advice):
    doc = frappe.get_doc("Payment Advice", payment_advice)
 
    if not doc.payment_advice_reference:
        frappe.throw("No references found to create Payment Entry")
 
    pe = frappe.new_doc("Payment Entry")
    pe.payment_type = get_payment_type(doc.party_type)
    pe.party_type = doc.party_type
    pe.party = doc.party
    pe.posting_date = nowdate()
    pe.company = frappe.defaults.get_user_default("Company") or frappe.db.get_single_value("Global Defaults", "default_company")
    pe.mode_of_payment = doc.mode_of_payment or "Cash"
    pe.custom_payment_advice = doc.name

    if doc.mode_of_payment and doc.mode_of_payment != "Cash":
        pe.reference_no = doc.reference_no or "TEMP"
        pe.reference_date = doc.reference_date or nowdate()

    # Get accounts
    party_account = get_party_account(doc.party_type, doc.party, pe.company)
    company_account = get_default_company_account(pe.company, pe.mode_of_payment)
    
    if not party_account:
        frappe.throw(f"No default account found for {doc.party_type}: {doc.party}")
    
    if not company_account:
        frappe.throw(f"No default cash account found for company: {pe.company}")
    
    pe.paid_from, pe.paid_to = get_payment_accounts(doc.party_type, party_account, company_account)
    
    pe.paid_amount = doc.payment_amount
    pe.received_amount = doc.payment_amount
    
    balance = doc.payment_amount

    for row in doc.payment_advice_reference:
        if not row.reference_doctype or not row.reference_record:
            continue

        if row.net_payable_amount > balance:
            allocated = balance
            balance = 0
        else:
            allocated = row.net_payable_amount
            balance -= row.net_payable_amount
 
        pe.append("references", {
            "reference_doctype": row.reference_doctype,
            "reference_name": row.reference_record,
            "allocated_amount": allocated
        })
 
    #     pe.paid_amount += row.amount
    #     pe.received_amount += row.amount
 
    # pe.custom_payment_advice = doc.name // added for tracing back
    
    if not pe.paid_from_account_currency:
        pe.paid_from_account_currency = get_account_currency(pe.paid_from)
    if not pe.paid_to_account_currency:
        pe.paid_to_account_currency = get_account_currency(pe.paid_to)
    
    # Set exchange rate if needed
    if pe.paid_from_account_currency != pe.paid_to_account_currency:
        pe.source_exchange_rate = get_exchange_rate(pe.paid_from_account_currency, pe.company, pe.posting_date)
        pe.target_exchange_rate = get_exchange_rate(pe.paid_to_account_currency, pe.company, pe.posting_date)
 
    try:
        pe.insert(ignore_permissions=True)
        # pe.submit()
        frappe.msgprint(f"Payment Entry {pe.name} created successfully")
        return pe.name
    except Exception as e:
        frappe.log_error(f"Error creating payment entry: {str(e)}")
        frappe.throw(f"Error creating payment entry: {str(e)}")
