import frappe

def validate_reference_no(doc, method):
    """Validate reference number before submitting Payment Entry"""
    if doc.reference_no and doc.reference_no.upper() == "TEMP":
        frappe.throw(
            "Payment Entry cannot be submitted with reference number 'TEMP'. Please update the reference number and date",
            title="Invalid Reference Number"
        )

    set_payment_entry_reference_in_payment_advice(doc, method)
    

def set_payment_entry_reference_in_payment_advice(doc, method):
    """Set Payment Entry reference in Payment Advice"""
    if doc.custom_payment_advice:
        payment_advice = frappe.get_doc("Payment Advice", doc.custom_payment_advice)
        payment_advice.payment_entry_reference = doc.name
        payment_advice.payment_entry_date = doc.posting_date
        payment_advice.save(ignore_permissions=True)