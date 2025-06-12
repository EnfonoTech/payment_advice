import frappe

def validate_reference_no(doc, method):
    """Validate reference number before submitting Payment Entry"""
    if doc.reference_no and doc.reference_no.upper() == "TEMP":
        frappe.throw(
            "Payment Entry cannot be submitted with reference number 'TEMP'. Please update the reference number and date",
            title="Invalid Reference Number"
        )