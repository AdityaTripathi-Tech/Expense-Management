/** @odoo-module **/

import { Component, useState, onMounted } from "@odoo/owl";
import { registry } from "@web/core/registry";
import { useService } from "@web/core/utils/hooks";

export class ApprovalGraphWidget extends Component {
    setup() {
        this.rpc = useService("rpc");
        this.state = useState({
            approvals: [],
            loading: true,
            error: null
        });
        
        onMounted(() => {
            this.loadApprovalData();
        });
    }

    async loadApprovalData() {
        try {
            this.state.loading = true;
            const result = await this.rpc("/web/dataset/call_kw", {
                model: "approval.request",
                method: "search_read",
                args: [
                    [["expense_claim_id", "=", this.props.record.resId]],
                    ["approver_id", "sequence", "state", "request_date", "response_date"]
                ],
                kwargs: {}
            });
            
            this.state.approvals = result;
            this.renderApprovalFlow();
        } catch (error) {
            this.state.error = error.message;
        } finally {
            this.state.loading = false;
        }
    }

    renderApprovalFlow() {
        const container = this.el.querySelector('.approval-flow-container');
        if (!container) return;

        container.innerHTML = '';
        
        this.state.approvals.forEach((approval, index) => {
            const stepEl = document.createElement('div');
            stepEl.className = `approval-step ${approval.state}`;
            
            stepEl.innerHTML = `
                <div class="step-number">${index + 1}</div>
                <div class="step-content">
                    <div class="approver-name">${approval.approver_id[1]}</div>
                    <div class="step-status">${approval.state}</div>
                    ${approval.response_date ? `<div class="response-date">${approval.response_date}</div>` : ''}
                </div>
            `;
            
            container.appendChild(stepEl);
            
            // Add connector line if not last step
            if (index < this.state.approvals.length - 1) {
                const connector = document.createElement('div');
                connector.className = 'approval-connector';
                container.appendChild(connector);
            }
        });
    }
}

ApprovalGraphWidget.template = "smart_expense_management.ApprovalGraphWidget";

registry.category("fields").add("approval_graph", ApprovalGraphWidget);
