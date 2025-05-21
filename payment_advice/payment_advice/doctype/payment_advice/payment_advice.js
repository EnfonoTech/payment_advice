// Copyright (c) 2025, Enfono and contributors
// For license information, please see license.txt

// frappe.ui.form.on("Payment Advice", {
// 	refresh(frm) {

// 	},
// });

frappe.ui.form.on('Payment Advice', {
    refresh: function (frm) {
        frm.fields_dict.party_type.get_query = function() {
            return {
                filters: {
                    "name": ["in", ["Customer", "Supplier"]]
                }
            };
        };
        
        // Initialize event handlers
        setup_amount_calculation(frm);
    },
    onload: function(frm) {
        // Calculate initial sum when form loads
        calculate_total_amount(frm);
    }
});

// Set up event handlers for the table
function setup_amount_calculation(frm) {
    // Calculate sum when table rows change
    frm.fields_dict.payment_advice_reference.grid.wrapper.on('change', () => {
        calculate_total_amount(frm);
    });
    
    // Calculate sum when amount in any row changes
    frm.fields_dict.payment_advice_reference.grid.wrapper.on('row-change', () => {
        calculate_total_amount(frm);
    });
    
    // Calculate sum when row is removed
    frm.fields_dict.payment_advice_reference.grid.wrapper.on('remove-row', () => {
        calculate_total_amount(frm);
    });
}

// Calculate the total amount from all rows
function calculate_total_amount(frm) {
    let total = 0;
    
    // Sum amounts from all rows
    frm.doc.payment_advice_reference.forEach(row => {
        if (row.amount) {
            total += flt(row.amount);
        }
    });
    
    // Update the main amount field
    frm.set_value('amount', total);
}

// Handle amount updates in table rows
frappe.ui.form.on('Payment Advice Reference', {
    amount: function(frm, cdt, cdn) {
        calculate_total_amount(frm);
    },
    reference_record: function(frm, cdt, cdn) {
        // Keep your existing reference_record logic here
        let row = frappe.get_doc(cdt, cdn);
        if (row.reference_doctype && row.reference_record) {
            frappe.db.get_value(
                row.reference_doctype,
                row.reference_record,
                'grand_total',
                (r) => {
                    if (r && r.grand_total) {
                        frappe.model.set_value(cdt, cdn, 'amount', r.grand_total);
                        calculate_total_amount(frm);  // Update total after setting row amount
                    }
                }
            );
        } else {
            frappe.model.set_value(cdt, cdn, 'amount', 0);
            calculate_total_amount(frm);  // Update total after clearing row amount
        }
    }
});