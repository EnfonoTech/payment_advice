# Copyright (c) 2025, Enfono and contributors
# For license information, please see license.txt

import frappe
from frappe import _
from frappe.model.document import Document
from frappe.utils import flt, nowdate, money_in_words
from erpnext.accounts.doctype.payment_entry.payment_entry import get_payment_entry
from erpnext.accounts.utils import get_account_currency

class PaymentAdvice(Document):
    def validate(self):
        if self.amount_to_be_settled:
            self.amount_to_be_settled_in_words = money_in_words(self.amount_to_be_settled)
        if self.amount_to_be_settled_trans_curr:
            self.amount_words_trans_curr = money_in_words(self.amount_to_be_settled_trans_curr, self.transaction_currency)
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

def get_reference_party_account(row, party_type, party, company):
    """Party account the referenced document is booked against (same rule as HRMS / ERPNext)."""
    if row.reference_doctype == "Employee Advance":
        return frappe.db.get_value("Employee Advance", row.reference_record, "advance_account")
    if row.reference_doctype in ("Expense Claim", "Gratuity", "Leave Encashment"):
        return frappe.db.get_value(row.reference_doctype, row.reference_record, "payable_account")
    if row.reference_doctype == "Purchase Invoice":
        return frappe.db.get_value("Purchase Invoice", row.reference_record, "credit_to")
    if row.reference_doctype == "Sales Invoice":
        return frappe.db.get_value("Sales Invoice", row.reference_record, "debit_to")
    return get_party_account(party_type, party, company)


def get_reference_outstanding(row):
    """(outstanding in party account currency, document currency, document exchange rate)."""
    if row.reference_doctype in ("Purchase Invoice", "Sales Invoice"):
        ref = frappe.db.get_value(row.reference_doctype, row.reference_record,
                                  ["outstanding_amount", "currency", "conversion_rate"], as_dict=True)
        if ref:
            return flt(ref.outstanding_amount), ref.currency, flt(ref.conversion_rate)
    # net_payable_amount is empty on Expense Claim / Employee Advance rows; fall back to amount
    return flt(row.net_payable_amount) or flt(row.amount), None, 0


def add_exchange_gain_loss(pe, party_amount, pay_in_trans, unsettled_trans, advice_rate):
    """Book the SAR difference between the advice rate and the invoice rate to Exchange Gain/Loss."""
    allocated = sum(flt(r.allocated_amount) for r in pe.references)
    if unsettled_trans <= 0.005:
        paid_for_refs = party_amount
    else:
        paid_for_refs = flt((pay_in_trans - unsettled_trans) * advice_rate, 2)
    diff = flt(paid_for_refs - allocated, 2)
    if not diff:
        return

    account, cost_center, round_off_cc = frappe.get_cached_value(
        "Company", pe.company, ["exchange_gain_loss_account", "cost_center", "round_off_cost_center"])
    if not account:
        frappe.throw(_("Please set the Exchange Gain / Loss Account in Company {0}").format(pe.company))

    pe.append("deductions", {
        "account": account,
        "cost_center": round_off_cc or cost_center,
        # Pay: extra SAR paid is a loss (debit); Receive: extra SAR received is a gain (credit)
        "amount": diff if pe.payment_type == "Pay" else -diff,
        "description": _("Exchange rate difference: Payment Advice rate {0}").format(advice_rate),
    })


@frappe.whitelist()
def create_payment_entry(payment_advice):
    doc = frappe.get_doc("Payment Advice", payment_advice)

    rows = [r for r in (doc.payment_advice_reference or []) if r.reference_doctype and r.reference_record]
    if not rows:
        frappe.throw("No references found to create Payment Entry")

    pe = frappe.new_doc("Payment Entry")
    pe.payment_type = get_payment_type(doc.party_type)
    pe.party_type = doc.party_type
    pe.party = doc.party
    pe.posting_date = nowdate()
    # ENFA-91: use the Payment Advice's own company, not the user's default company
    pe.company = doc.company or frappe.defaults.get_user_default("Company") or frappe.db.get_single_value("Global Defaults", "default_company")
    pe.mode_of_payment = doc.mode_of_payment or "Cash"
    pe.custom_payment_advice = doc.name

    if doc.mode_of_payment and doc.mode_of_payment != "Cash":
        pe.reference_no = doc.reference_no or "TEMP"
        pe.reference_date = doc.reference_date or nowdate()

    # Party account: the account the referenced documents are booked against
    # (e.g. Employee Advance -> its advance account, Purchase Invoice -> credit_to)
    accounts = {get_reference_party_account(r, doc.party_type, doc.party, pe.company) for r in rows}
    accounts.discard(None)
    if len(accounts) > 1:
        frappe.throw(
            "The references in this Payment Advice are booked against different party accounts ({0}). "
            "Please make one Payment Advice per account.".format(", ".join(sorted(accounts)))
        )
    party_account = accounts.pop() if accounts else get_party_account(doc.party_type, doc.party, pe.company)
    company_account = get_default_company_account(pe.company, pe.mode_of_payment)

    if not party_account:
        frappe.throw(f"No default account found for {doc.party_type}: {doc.party}")

    if not company_account:
        frappe.throw(f"No default cash account found for company: {pe.company}")

    pe.paid_from, pe.paid_to = get_payment_accounts(doc.party_type, party_account, company_account)

    # ENFA-124: amounts and exchange rates.
    # The advice is paid in its transaction currency at the advice's Exchange Rate (the rate the bank used).
    # Invoices keep their own rate; the SAR difference goes to the company's Exchange Gain/Loss account.
    company_currency = frappe.get_cached_value("Company", pe.company, "default_currency")
    trans_currency = doc.transaction_currency or company_currency
    advice_rate = 1.0 if trans_currency == company_currency else flt(doc.exchange_rate)
    if not advice_rate:
        frappe.throw(_("Please enter the Exchange Rate on Payment Advice {0}").format(doc.name))

    party_currency = get_account_currency(party_account)
    company_account_currency = get_account_currency(company_account)
    pay_in_trans = flt(doc.payment_amount)
    base_amount = flt(pay_in_trans * advice_rate, 2)

    if party_currency == company_currency:
        party_amount, party_rate = base_amount, 1.0
    elif party_currency == trans_currency:
        # multi-currency party account (e.g. Debtors - USD): ERPNext books the gain/loss itself
        party_amount, party_rate = pay_in_trans, advice_rate
    else:
        frappe.throw(_("Party account {0} is in {1} but the Payment Advice is in {2}").format(
            party_account, party_currency, trans_currency))

    if company_account_currency == party_currency:
        bank_amount, bank_rate = party_amount, party_rate
    elif company_account_currency == company_currency:
        bank_amount, bank_rate = base_amount, 1.0
    else:
        frappe.throw(_("Bank/Cash account {0} is in {1}; it must be in {2} or {3}").format(
            company_account, company_account_currency, company_currency, party_currency))

    pe.paid_from_account_currency = get_account_currency(pe.paid_from)
    pe.paid_to_account_currency = get_account_currency(pe.paid_to)
    if pe.payment_type == "Receive":
        pe.paid_amount, pe.source_exchange_rate = party_amount, party_rate
        pe.received_amount, pe.target_exchange_rate = bank_amount, bank_rate
    else:
        pe.paid_amount, pe.source_exchange_rate = bank_amount, bank_rate
        pe.received_amount, pe.target_exchange_rate = party_amount, party_rate

    # Invoices in the advice's foreign currency booked on a SAR party account: settle them in that
    # currency at the invoice rate, so the rate difference becomes exchange gain/loss, not an advance
    settle_in_trans = party_currency == company_currency and trans_currency != company_currency
    balance = party_amount            # in party account currency
    balance_trans = pay_in_trans      # in advice currency (only used when settle_in_trans)

    for row in rows:
        outstanding, ref_currency, ref_rate = get_reference_outstanding(row)
        if settle_in_trans and ref_currency == trans_currency and ref_rate:
            outstanding_trans = outstanding / ref_rate
            settle_trans = min(outstanding_trans, balance_trans)
            balance_trans -= settle_trans
            allocated = outstanding if settle_trans >= outstanding_trans - 0.005 else flt(settle_trans * ref_rate, 2)
        else:
            allocated = min(outstanding, balance)
            if settle_in_trans:
                balance_trans -= allocated / advice_rate
        balance -= allocated

        pe.append("references", {
            "reference_doctype": row.reference_doctype,
            "reference_name": row.reference_record,
            "allocated_amount": max(allocated, 0)
        })

    # Fill totals/outstanding from the referenced documents and never allocate more than is outstanding
    # (e.g. a USD invoice whose rounded SAR total is 0.01 above its outstanding)
    pe.setup_party_account_field()
    pe.set_missing_values()
    pe.set_missing_ref_details()
    for ref in pe.references:
        if flt(ref.outstanding_amount) and flt(ref.allocated_amount) > flt(ref.outstanding_amount):
            ref.allocated_amount = flt(ref.outstanding_amount)

    if settle_in_trans:
        add_exchange_gain_loss(pe, party_amount, pay_in_trans, max(balance_trans, 0), advice_rate)

    try:
        pe.insert(ignore_permissions=True)
        frappe.msgprint(f"Payment Entry {pe.name} created successfully")
        return pe.name
    except Exception as e:
        frappe.log_error(f"Error creating payment entry: {str(e)}")
        frappe.throw(f"Error creating payment entry: {str(e)}")
