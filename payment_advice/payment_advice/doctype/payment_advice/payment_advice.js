// Copyright (c) 2025, Enfono and contributors
// For license information, please see license.txt

// frappe.ui.form.on("Payment Advice", {
// 	refresh(frm) {

// 	},
// });

frappe.ui.form.on('Payment Advice', {
    refresh: function (frm) {

        if (frm.doc.__islocal && !frm.doc.transaction_date) {
         frm.set_value('transaction_date', frappe.datetime.get_today());   
        }

        if (frm.doc.docstatus === 1) {
            frm.add_custom_button('Payment Entry', () => {
                frappe.call({
                    method: 'payment_advice.payment_advice.doctype.payment_advice.payment_advice.create_payment_entry',
                    args: {
                        payment_advice: frm.doc.name
                    },
                    callback: function(r) {
                        if (!r.exc && r.message) {
                            frappe.set_route('Form', 'Payment Entry', r.message);
                        }
                    }
                });
            }, __('Create'));
        }

        frm.fields_dict.party_type.get_query = function() {
            return {
                filters: {
                    "name": ["in", ["Customer", "Supplier", "Employee"]]
                }
            };
        };

        frm.fields_dict.payment_advice_reference.grid.get_field('reference_doctype').get_query = function() {
            return {
                filters: {
                    name: ['in', ['Sales Invoice', 'Sales Order', 'Purchase Invoice', 'Purchase Order', 'Expense Claim', 'Employee Advance']]
                }
            };
        };

        update_reference_filters(frm);
        
        // Update filters when party_type or party changes
        frm.get_field('party_type').df.onchange = () => update_reference_filters(frm);

        frm.get_field('party').df.onchange = () => update_reference_filters(frm);
        
        // Initialize event handlers
        setup_amount_calculation(frm);
    },

    onload: function(frm) {
        // Calculate initial sum when form loads
        calculate_total_amount(frm);
    },

    party: function(frm) {
        if (frm.doc.party_type && frm.doc.party) {
            let doctype = frm.doc.party_type;
            let docname = frm.doc.party;

            const name_field_map = {
                'Customer': 'customer_name',
                'Supplier': 'supplier_name',
                'Employee': 'employee_name'
            };

            if (name_field_map[doctype]) {
                frappe.db.get_value(doctype, docname, name_field_map[doctype])
                    .then(r => {
                        frm.set_value('party_name', r.message[name_field_map[doctype]]);
                    });
            } else {
                frm.set_value('party_name', '');
            }
        } else {
            frm.set_value('party_name', '');
        }
    },

    party_type: function(frm) {
        frm.set_value('party', null);
        frm.set_value('party_name', '');
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
    let total_paid = 0;
    let total_payable = 0;
    
    // Sum amounts from all rows
    frm.doc.payment_advice_reference.forEach(row => {
        if (row.amount) {
            total += flt(row.amount);
        }
        if (row.net_payable_amount) {
            total_payable += flt(row.net_payable_amount);
        }
        if (row.settled_amount) {
            total_paid += flt(row.settled_amount)
        }
    });
    
    // Update the main amount field
    frm.set_value('amount', total);
    frm.set_value('amount_in_words', total_paid);
    frm.set_value('amount_to_be_settled', total_payable);
}

function update_reference_filters(frm) {
    // Update filters for all existing rows
    (frm.doc.payment_advice_reference || []).forEach(function(row, i) {
        update_row_filter(frm, 'Payment Advice Reference', row.name);
    });
}

function update_row_filter(frm, cdt, cdn) {
    var row = frappe.get_doc(cdt, cdn);
    if (!row || !row.reference_doctype) return;
    
    // Set dynamic filter based on party_type and party
    frappe.meta.get_docfield(cdt, 'reference_record', row.name).get_query = function() {
        var filters = {
            'docstatus': 1  // Only show submitted documents
        };
        
        if (frm.doc.party_type && frm.doc.party) {
            if (frm.doc.party_type === 'Customer') {
                if (['Sales Order', 'Sales Invoice', 'Delivery Note'].includes(row.reference_doctype)) {
                    filters['customer'] = frm.doc.party;
                    filters['status'] = ['!=', 'Paid'];
                }
            } 
            else if (frm.doc.party_type === 'Supplier') {
                if (['Purchase Order', 'Purchase Invoice', 'Purchase Receipt'].includes(row.reference_doctype)) {
                    filters['supplier'] = frm.doc.party;
                    filters['status'] = ['!=', 'Paid'];
                }
            }
            else if (frm.doc.party_type === 'Employee') {
                if (['Expense Claim'].includes(row.reference_doctype)) {
                    filters['employee'] = frm.doc.party;
                    filters['approval_status'] = "Approved";
                    filters['status'] = ['!=', 'Paid'];
                }
                else if(['Employee Advance'].includes(row.reference_doctype)) {
                    filters['employee'] = frm.doc.party;
                    filters['status'] = ['!=', 'Paid'];
                }
            }
        }
        
        return { filters: filters };
    };
    
    // Refresh the field if it exists
    var grid = frm.fields_dict.payment_advice_reference.grid;
    var grid_row = grid.grid_rows_by_docname[row.name];
    if (grid_row && grid_row.reference_record) {
        grid_row.reference_record.refresh();
    }
}

frappe.ui.form.on('Payment Advice Reference', {

    amount: function(frm, cdt, cdn) {
        calculate_total_amount(frm);
    },

    reference_doctype: function(frm, cdt, cdn) {
        update_row_filter(frm, cdt, cdn);
    },

    reference_record: function(frm, cdt, cdn) {
        let row = frappe.get_doc(cdt, cdn);
        if (row.reference_doctype && row.reference_record) {
            let date_field = '';
            if (['Sales Invoice', 'Employee Advance'].includes(row.reference_doctype)) {
                date_field = 'posting_date';
            } else if (['Purchase Invoice'].includes(row.reference_doctype)) {
                date_field = 'bill_date';
            } else if (['Sales Order', 'Purchase Order'].includes(row.reference_doctype)) {
                date_field = 'transaction_date';
            }
            
            if (row.reference_doctype == "Expense Claim") {
                filter = ['grand_total']
            } else if (row.reference_doctype == "Employee Advance") {
                filter = ['advance_amount', date_field]
            } else if (row.reference_doctype == "Purchase Invoice") {
                if (frappe.meta.has_field("Purchase Invoice", "custom_job_record")) {
                    filter = ['grand_total', date_field, 'custom_job_record', 'outstanding_amount'];
                } else {
                    filter = ['grand_total', date_field, 'outstanding_amount'];
                }
            } else {
                filter = ['grand_total', date_field]
            }

            frappe.db.get_value(
                row.reference_doctype,
                row.reference_record,
                filter,
                (r) => {
                    if (r) {

                        if (r.grand_total != null) {
                            frappe.model.set_value(cdt, cdn, 'amount', r.grand_total);
                            
                            if (r.outstanding_amount && r.outstanding_amount != null) {
                                frappe.model.set_value(cdt, cdn, 'net_payable_amount', r.outstanding_amount);
                                frappe.model.set_value(cdt, cdn, 'settled_amount', r.grand_total - r.outstanding_amount);
                            }
                        }

                        if (r.advance_amount != null) {
                            frappe.model.set_value(cdt, cdn, 'amount', r.advance_amount);
                        }

                        if (r[date_field] != null) {
                            frappe.model.set_value(cdt, cdn, 'date', r[date_field]);

                            const record_date = new Date(r[date_field]);
                            const today = new Date();

                            record_date.setHours(0, 0, 0, 0);
                            today.setHours(0, 0, 0, 0);

                            const diffTime = today - record_date;
                            const diffDays = Math.floor(diffTime / (1000 * 60 * 60 * 24));

                            frappe.model.set_value(cdt, cdn, 'aeging', diffDays);
                        }

                        if (r.custom_job_record && r.custom_job_record != null) {
                            frappe.model.set_value(cdt, cdn, 'job_number', r.custom_job_record);
                        }

                        calculate_total_amount(frm);
                    }
                }
            );
        } else {
            frappe.model.set_value(cdt, cdn, 'amount', 0);
            frappe.model.set_value(cdt, cdn, 'date', null);
            calculate_total_amount(frm);
        }
    }

});
