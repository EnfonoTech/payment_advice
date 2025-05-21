// Copyright (c) 2025, Enfono and contributors
// For license information, please see license.txt

// frappe.ui.form.on("Payment Advice", {
// 	refresh(frm) {

// 	},
// });

frappe.ui.form.on('Payment Advice', {
    refresh: function(frm) {
    },
});

frappe.ui.form.on('Payment Advice Reference', {
    reference_record: function(frm, cdt, cdn) {
        const row = frappe.get_doc(cdt, cdn);
        
        if (!row.reference_doctype || !row.reference_record) {
            frappe.model.set_value(cdt, cdn, 'amount', 0);
            return;
        }

        frappe.db.get_value(
            row.reference_doctype,
            row.reference_record,
            'grand_total',
            (r) => {
                if (r && r.grand_total) {
                    frappe.model.set_value(cdt, cdn, 'amount', r.grand_total);
                }
            }
        );
    }
});