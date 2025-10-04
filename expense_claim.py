# type: ignore
import logging
from datetime import datetime
from odoo import models, fields, api, _
from odoo.exceptions import ValidationError, UserError

_logger = logging.getLogger(__name__)


class ExpenseClaim(models.Model):
    _name = 'expense.claim'
    _description = 'Expense Claim'
    _inherit = ['mail.thread', 'mail.activity.mixin']
    _order = 'create_date desc'
    _rec_name = 'display_name'

    # Basic Information
    name = fields.Char(
        string='Claim Reference',
        required=True,
        copy=False,
        readonly=True,
        default=lambda self: _('New')
    )
    
    display_name = fields.Char(
        string='Display Name',
        compute='_compute_display_name',
        store=True
    )
    
    employee_id = fields.Many2one(
        'hr.employee',
        string='Employee',
        required=True,
        default=lambda self: self.env.user.employee_id,
        tracking=True
    )
    
    manager_id = fields.Many2one(
        'hr.employee',
        string='Manager',
        related='employee_id.parent_id',
        store=True,
        readonly=True
    )
    
    department_id = fields.Many2one(
        'hr.department',
        string='Department',
        related='employee_id.department_id',
        store=True,
        readonly=True
    )
    
    company_id = fields.Many2one(
        'res.company',
        string='Company',
        required=True,
        default=lambda self: self.env.company
    )
    
    # Dates
    claim_date = fields.Date(
        string='Claim Date',
        required=True,
        default=fields.Date.today,
        tracking=True
    )
    
    submission_date = fields.Datetime(
        string='Submission Date',
        readonly=True,
        tracking=True
    )
    
    # Status and Workflow
    state = fields.Selection([
        ('draft', 'Draft'),
        ('submitted', 'Submitted'),
        ('under_review', 'Under Review'),
        ('approved', 'Approved'),
        ('rejected', 'Rejected'),
        ('paid', 'Paid'),
        ('cancelled', 'Cancelled')
    ], string='Status', default='draft', required=True, tracking=True)
    
    # Financial Information
    currency_id = fields.Many2one(
        'res.currency',
        string='Currency',
        required=True,
        default=lambda self: self.env.company.expense_default_currency_id or self.env.company.currency_id
    )
    
    total_amount = fields.Monetary(
        string='Total Amount',
        currency_field='currency_id',
        compute='_compute_total_amount',
        store=True
    )
    
    company_currency_id = fields.Many2one(
        'res.currency',
        string='Company Currency',
        related='company_id.currency_id',
        readonly=True
    )
    
    total_amount_company_currency = fields.Monetary(
        string='Total (Company Currency)',
        currency_field='company_currency_id',
        compute='_compute_company_currency_amount',
        store=True
    )
    
    conversion_rate = fields.Float(
        string='Conversion Rate',
        digits=(12, 6),
        readonly=True,
        help='Exchange rate used for currency conversion'
    )
    
    conversion_date = fields.Date(
        string='Conversion Date',
        readonly=True,
        help='Date when currency conversion was performed'
    )
    
    conversion_pending = fields.Boolean(
        string='Conversion Pending',
        default=False,
        help='True if currency conversion failed and needs manual review'
    )
    
    # Expense Lines
    expense_line_ids = fields.One2many(
        'expense.line',
        'claim_id',
        string='Expense Lines'
    )
    
    expense_line_count = fields.Integer(
        string='Number of Expenses',
        compute='_compute_expense_line_count'
    )
    
    # Approval Information
    approval_request_ids = fields.One2many(
        'approval.request',
        'expense_claim_id',
        string='Approval Requests'
    )
    
    current_approver_id = fields.Many2one(
        'hr.employee',
        string='Current Approver',
        compute='_compute_current_approver',
        store=True
    )
    
    approval_level = fields.Integer(
        string='Current Approval Level',
        default=0,
        help='Current level in the approval hierarchy'
    )
    
    requires_cfo_approval = fields.Boolean(
        string='Requires CFO Approval',
        compute='_compute_requires_cfo_approval',
        store=True
    )
    
    # Notes and Attachments
    description = fields.Text(string='Description')
    
    notes = fields.Text(string='Internal Notes')
    
    rejection_reason = fields.Text(
        string='Rejection Reason',
        readonly=True
    )
    
    # Computed Fields
    @api.depends('name', 'employee_id', 'total_amount', 'currency_id')
    def _compute_display_name(self):
        for claim in self:
            if claim.name and claim.name != _('New'):
                claim.display_name = f"{claim.name} - {claim.employee_id.name or ''}"
            else:
                claim.display_name = f"Draft Claim - {claim.employee_id.name or ''}"

    @api.depends('expense_line_ids.total_amount')
    def _compute_total_amount(self):
        for claim in self:
            claim.total_amount = sum(claim.expense_line_ids.mapped('total_amount'))

    @api.depends('expense_line_ids')
    def _compute_expense_line_count(self):
        for claim in self:
            claim.expense_line_count = len(claim.expense_line_ids)

    @api.depends('total_amount_company_currency', 'company_id')
    def _compute_requires_cfo_approval(self):
        for claim in self:
            cfo_threshold = claim.company_id.expense_cfo_approval_required
            claim.requires_cfo_approval = claim.total_amount_company_currency >= cfo_threshold

    @api.depends('approval_request_ids', 'state')
    def _compute_current_approver(self):
        for claim in self:
            if claim.state in ['submitted', 'under_review']:
                pending_approval = claim.approval_request_ids.filtered(
                    lambda r: r.state == 'pending'
                ).sorted('sequence')
                
                claim.current_approver_id = pending_approval[0].approver_id if pending_approval else False
            else:
                claim.current_approver_id = False

    @api.depends('total_amount', 'currency_id', 'company_currency_id')
    def _compute_company_currency_amount(self):
        for claim in self:
            if claim.currency_id == claim.company_currency_id:
                claim.total_amount_company_currency = claim.total_amount
                claim.conversion_rate = 1.0
            elif claim.total_amount and claim.currency_id and claim.company_currency_id:
                # Convert using currency service
                try:
                    currency_service = self.env['currency.service']
                    conversion_result = currency_service.convert_amount(
                        amount=claim.total_amount,
                        from_currency=claim.currency_id.name,
                        to_currency=claim.company_currency_id.name,
                        rate_date=claim.claim_date
                    )
                    
                    claim.total_amount_company_currency = conversion_result['converted_amount']
                    claim.conversion_rate = conversion_result['exchange_rate']
                    claim.conversion_date = conversion_result['conversion_date']
                    claim.conversion_pending = False
                    
                except Exception as e:
                    _logger.error(f"Currency conversion failed for claim {claim.id}: {e}")
                    claim.total_amount_company_currency = 0.0
                    claim.conversion_rate = 0.0
                    claim.conversion_pending = True
            else:
                claim.total_amount_company_currency = 0.0
                claim.conversion_rate = 0.0

    # CRUD Operations
    @api.model
    def create(self, vals):
        if vals.get('name', _('New')) == _('New'):
            vals['name'] = self.env['ir.sequence'].next_by_code('expense.claim') or _('New')
        
        claim = super().create(vals)
        
        # Log creation
        claim.message_post(
            body=_('Expense claim created by %s') % claim.employee_id.name,
            message_type='notification'
        )
        
        return claim

    # Workflow Actions
    def action_submit(self):
        """Submit expense claim for approval"""
        for claim in self:
            if claim.state != 'draft':
                raise UserError(_('Only draft claims can be submitted.'))
            
            if not claim.expense_line_ids:
                raise UserError(_('Cannot submit a claim without expense lines.'))
            
            # Check for conversion pending
            if claim.conversion_pending:
                raise UserError(
                    _('Currency conversion is pending. Please contact administrator or try again later.')
                )
            
            # Update state and submission date
            claim.write({
                'state': 'submitted',
                'submission_date': fields.Datetime.now()
            })
            
            # Create approval requests
            claim._create_approval_requests()
            
            # Log submission
            claim.message_post(
                body=_('Expense claim submitted for approval'),
                message_type='notification'
            )

    def action_approve(self):
        """Approve current level of expense claim"""
        for claim in self:
            if claim.state not in ['submitted', 'under_review']:
                raise UserError(_('Only submitted or under review claims can be approved.'))
            
            current_user_employee = self.env.user.employee_id
            if not current_user_employee:
                raise UserError(_('You must be linked to an employee to approve expenses.'))
            
            # Find pending approval for current user
            pending_approval = claim.approval_request_ids.filtered(
                lambda r: r.approver_id == current_user_employee and r.state == 'pending'
            )
            
            if not pending_approval:
                raise UserError(_('You are not authorized to approve this claim at this level.'))
            
            # Approve the request
            pending_approval.action_approve()
            
            # Check if all approvals are complete
            if not claim.approval_request_ids.filtered(lambda r: r.state == 'pending'):
                claim.write({'state': 'approved'})
                claim.message_post(
                    body=_('Expense claim fully approved'),
                    message_type='notification'
                )
            else:
                claim.write({'state': 'under_review'})
                next_approver = claim.current_approver_id
                if next_approver:
                    claim.message_post(
                        body=_('Expense claim approved at level %d. Next approver: %s') % 
                             (claim.approval_level, next_approver.name),
                        message_type='notification'
                    )

    def action_reject(self, reason=None):
        """Reject expense claim"""
        for claim in self:
            if claim.state not in ['submitted', 'under_review']:
                raise UserError(_('Only submitted or under review claims can be rejected.'))
            
            current_user_employee = self.env.user.employee_id
            if not current_user_employee:
                raise UserError(_('You must be linked to an employee to reject expenses.'))
            
            # Find pending approval for current user
            pending_approval = claim.approval_request_ids.filtered(
                lambda r: r.approver_id == current_user_employee and r.state == 'pending'
            )
            
            if not pending_approval:
                raise UserError(_('You are not authorized to reject this claim.'))
            
            # Reject the request
            pending_approval.action_reject(reason)
            
            # Update claim state
            claim.write({
                'state': 'rejected',
                'rejection_reason': reason or _('No reason provided')
            })
            
            claim.message_post(
                body=_('Expense claim rejected by %s. Reason: %s') % 
                     (current_user_employee.name, reason or _('No reason provided')),
                message_type='notification'
            )

    def action_reset_to_draft(self):
        """Reset claim to draft state"""
        for claim in self:
            if claim.state not in ['rejected', 'cancelled']:
                raise UserError(_('Only rejected or cancelled claims can be reset to draft.'))
            
            # Cancel all approval requests
            claim.approval_request_ids.write({'state': 'cancelled'})
            
            claim.write({
                'state': 'draft',
                'submission_date': False,
                'rejection_reason': False,
                'approval_level': 0
            })
            
            claim.message_post(
                body=_('Expense claim reset to draft'),
                message_type='notification'
            )

    def action_cancel(self):
        """Cancel expense claim"""
        for claim in self:
            if claim.state in ['paid']:
                raise UserError(_('Paid claims cannot be cancelled.'))
            
            # Cancel all approval requests
            claim.approval_request_ids.write({'state': 'cancelled'})
            
            claim.write({'state': 'cancelled'})
            
            claim.message_post(
                body=_('Expense claim cancelled'),
                message_type='notification'
            )

    def action_mark_paid(self):
        """Mark claim as paid (for accounting integration)"""
        for claim in self:
            if claim.state != 'approved':
                raise UserError(_('Only approved claims can be marked as paid.'))
            
            claim.write({'state': 'paid'})
            
            claim.message_post(
                body=_('Expense claim marked as paid'),
                message_type='notification'
            )

    def _create_approval_requests(self):
        """Create approval requests based on company rules"""
        for claim in self:
            # Get applicable approval rules
            approval_rules = self.env['approval.rule'].get_applicable_rules(
                amount=claim.total_amount_company_currency,
                employee=claim.employee_id,
                department=claim.department_id,
                company=claim.company_id
            )
            
            if not approval_rules:
                # Auto-approve if no rules apply and below auto-approve limit
                auto_approve_limit = claim.company_id.expense_auto_approve_limit
                if claim.total_amount_company_currency <= auto_approve_limit:
                    claim.write({'state': 'approved'})
                    claim.message_post(
                        body=_('Expense claim auto-approved (below threshold)'),
                        message_type='notification'
                    )
                    return
                else:
                    raise UserError(
                        _('No approval rules found for this expense amount. Please contact administrator.')
                    )
            
            # Create approval requests
            sequence = 1
            for rule in approval_rules:
                approvers = rule.get_approvers(claim.employee_id, claim.department_id)
                
                for approver in approvers:
                    self.env['approval.request'].create({
                        'expense_claim_id': claim.id,
                        'approval_rule_id': rule.id,
                        'approver_id': approver.id,
                        'sequence': sequence,
                        'state': 'pending' if sequence == 1 else 'waiting',
                        'required_amount': claim.total_amount_company_currency,
                    })
                    sequence += 1
            
            # Update approval level
            claim.approval_level = 1

    # Utility Methods
    def action_view_expense_lines(self):
        """Action to view expense lines"""
        self.ensure_one()
        return {
            'type': 'ir.actions.act_window',
            'name': _('Expense Lines'),
            'res_model': 'expense.line',
            'view_mode': 'tree,form',
            'domain': [('claim_id', '=', self.id)],
            'context': {'default_claim_id': self.id},
        }

    def action_view_approvals(self):
        """Action to view approval requests"""
        self.ensure_one()
        return {
            'type': 'ir.actions.act_window',
            'name': _('Approval Requests'),
            'res_model': 'approval.request',
            'view_mode': 'tree,form',
            'domain': [('expense_claim_id', '=', self.id)],
            'context': {'default_expense_claim_id': self.id},
        }

    def action_refresh_currency_conversion(self):
        """Manually refresh currency conversion"""
        for claim in self:
            if claim.conversion_pending:
                # Trigger recomputation
                claim._compute_company_currency_amount()
                
                if not claim.conversion_pending:
                    claim.message_post(
                        body=_('Currency conversion refreshed successfully'),
                        message_type='notification'
                    )
                    return {
                        'type': 'ir.actions.client',
                        'tag': 'display_notification',
                        'params': {
                            'title': _('Conversion Updated'),
                            'message': _('Currency conversion refreshed successfully'),
                            'type': 'success',
                        }
                    }
                else:
                    return {
                        'type': 'ir.actions.client',
                        'tag': 'display_notification',
                        'params': {
                            'title': _('Conversion Failed'),
                            'message': _('Currency conversion still pending. Please try again later.'),
                            'type': 'warning',
                        }
                    }

    # Demo/Testing Methods
    def action_demo_approve_all(self):
        """Demo action to simulate all approvals (for testing only)"""
        if not self.env.context.get('demo_mode'):
            raise UserError(_('This action is only available in demo mode.'))
        
        for claim in self:
            if claim.state in ['submitted', 'under_review']:
                # Approve all pending requests
                pending_requests = claim.approval_request_ids.filtered(
                    lambda r: r.state in ['pending', 'waiting']
                )
                
                for request in pending_requests:
                    request.write({
                        'state': 'approved',
                        'approval_date': fields.Datetime.now(),
                        'comments': 'Demo auto-approval'
                    })
                
                claim.write({'state': 'approved'})
                claim.message_post(
                    body=_('Demo: All approvals simulated'),
                    message_type='notification'
                )

    # Constraints and Validations
    @api.constrains('expense_line_ids')
    def _check_expense_lines(self):
        for claim in self:
            if claim.state != 'draft' and not claim.expense_line_ids:
                raise ValidationError(_('Submitted claims must have at least one expense line.'))

    @api.constrains('total_amount')
    def _check_total_amount(self):
        for claim in self:
            if claim.total_amount < 0:
                raise ValidationError(_('Total amount cannot be negative.'))

    # Onchange Methods
    @api.onchange('employee_id')
    def _onchange_employee_id(self):
        if self.employee_id:
            # Set default currency based on employee's company
            if self.employee_id.company_id.expense_default_currency_id:
                self.currency_id = self.employee_id.company_id.expense_default_currency_id
