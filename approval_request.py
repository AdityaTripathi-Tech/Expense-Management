# type: ignore
import logging
from datetime import datetime, timedelta
from odoo import models, fields, api, _
from odoo.exceptions import ValidationError, UserError

_logger = logging.getLogger(__name__)


class ApprovalRequest(models.Model):
    _name = 'approval.request'
    _description = 'Expense Approval Request'
    _inherit = ['mail.thread', 'mail.activity.mixin']
    _order = 'sequence, create_date'
    _rec_name = 'display_name'

    # Basic Information
    expense_claim_id = fields.Many2one(
        'expense.claim',
        string='Expense Claim',
        required=True,
        ondelete='cascade',
        index=True
    )
    
    approval_rule_id = fields.Many2one(
        'approval.rule',
        string='Approval Rule',
        required=True,
        ondelete='restrict'
    )
    
    approver_id = fields.Many2one(
        'hr.employee',
        string='Approver',
        required=True,
        tracking=True
    )
    
    sequence = fields.Integer(
        string='Sequence',
        default=1,
        help='Order of approval in sequential workflows'
    )
    
    # Status and Workflow
    state = fields.Selection([
        ('waiting', 'Waiting'),
        ('pending', 'Pending Approval'),
        ('approved', 'Approved'),
        ('rejected', 'Rejected'),
        ('cancelled', 'Cancelled'),
        ('escalated', 'Escalated')
    ], string='Status', default='waiting', required=True, tracking=True)
    
    # Request Information
    request_date = fields.Datetime(
        string='Request Date',
        default=fields.Datetime.now,
        required=True
    )
    
    required_amount = fields.Monetary(
        string='Amount to Approve',
        currency_field='currency_id',
        help='Amount that needs approval'
    )
    
    currency_id = fields.Many2one(
        'res.currency',
        string='Currency',
        related='expense_claim_id.company_currency_id',
        store=True,
        readonly=True
    )
    
    # Approval Information
    approval_date = fields.Datetime(
        string='Approval Date',
        readonly=True,
        tracking=True
    )
    
    approved_by_id = fields.Many2one(
        'res.users',
        string='Approved By',
        readonly=True,
        tracking=True
    )
    
    rejection_date = fields.Datetime(
        string='Rejection Date',
        readonly=True,
        tracking=True
    )
    
    rejected_by_id = fields.Many2one(
        'res.users',
        string='Rejected By',
        readonly=True,
        tracking=True
    )
    
    # Comments and Feedback
    comments = fields.Text(
        string='Comments',
        help='Approver comments or feedback'
    )
    
    rejection_reason = fields.Text(
        string='Rejection Reason',
        readonly=True
    )
    
    # Escalation
    escalation_date = fields.Datetime(
        string='Escalation Date',
        compute='_compute_escalation_date',
        store=True,
        help='When this request will be escalated if not approved'
    )
    
    is_escalated = fields.Boolean(
        string='Is Escalated',
        default=False,
        help='Whether this request has been escalated'
    )
    
    escalated_from_id = fields.Many2one(
        'approval.request',
        string='Escalated From',
        help='Original request that was escalated'
    )
    
    escalated_to_ids = fields.One2many(
        'approval.request',
        'escalated_from_id',
        string='Escalated To',
        help='Escalated requests created from this one'
    )
    
    # Computed Fields
    display_name = fields.Char(
        string='Display Name',
        compute='_compute_display_name',
        store=True
    )
    
    is_overdue = fields.Boolean(
        string='Is Overdue',
        compute='_compute_is_overdue',
        help='Whether this approval is overdue for escalation'
    )
    
    days_pending = fields.Integer(
        string='Days Pending',
        compute='_compute_days_pending',
        help='Number of days this request has been pending'
    )
    
    can_approve = fields.Boolean(
        string='Can Approve',
        compute='_compute_can_approve',
        help='Whether current user can approve this request'
    )
    
    can_reject = fields.Boolean(
        string='Can Reject',
        compute='_compute_can_reject',
        help='Whether current user can reject this request'
    )

    @api.depends('expense_claim_id', 'approver_id', 'required_amount')
    def _compute_display_name(self):
        for request in self:
            claim_name = request.expense_claim_id.name or 'Draft'
            approver_name = request.approver_id.name or 'Unknown'
            request.display_name = f"{claim_name} - {approver_name}"

    @api.depends('request_date', 'approval_rule_id')
    def _compute_escalation_date(self):
        for request in self:
            if (request.approval_rule_id.escalation_enabled and 
                request.approval_rule_id.escalation_hours > 0 and
                request.request_date):
                
                hours = request.approval_rule_id.escalation_hours
                request.escalation_date = request.request_date + timedelta(hours=hours)
            else:
                request.escalation_date = False

    @api.depends('escalation_date', 'state')
    def _compute_is_overdue(self):
        now = fields.Datetime.now()
        for request in self:
            request.is_overdue = (
                request.state == 'pending' and
                request.escalation_date and
                request.escalation_date < now
            )

    @api.depends('request_date', 'state')
    def _compute_days_pending(self):
        now = fields.Datetime.now()
        for request in self:
            if request.state == 'pending' and request.request_date:
                delta = now - request.request_date
                request.days_pending = delta.days
            else:
                request.days_pending = 0

    @api.depends('approver_id', 'state')
    def _compute_can_approve(self):
        current_user = self.env.user
        current_employee = current_user.employee_id
        
        for request in self:
            request.can_approve = (
                request.state == 'pending' and
                current_employee and
                current_employee == request.approver_id
            )

    @api.depends('approver_id', 'state')
    def _compute_can_reject(self):
        current_user = self.env.user
        current_employee = current_user.employee_id
        
        for request in self:
            request.can_reject = (
                request.state == 'pending' and
                current_employee and
                current_employee == request.approver_id
            )

    # Actions
    def action_approve(self, comments=None):
        """Approve the request"""
        for request in self:
            if request.state != 'pending':
                raise UserError(_('Only pending requests can be approved.'))
            
            current_user = self.env.user
            current_employee = current_user.employee_id
            
            if not current_employee or current_employee != request.approver_id:
                raise UserError(_('You are not authorized to approve this request.'))
            
            # Update request
            request.write({
                'state': 'approved',
                'approval_date': fields.Datetime.now(),
                'approved_by_id': current_user.id,
                'comments': comments or request.comments,
            })
            
            # Log approval
            request.message_post(
                body=_('Approval request approved by %s') % current_employee.name,
                message_type='notification'
            )
            
            # Check if this enables next approval in sequence
            request._activate_next_approval()

    def action_reject(self, reason=None):
        """Reject the request"""
        for request in self:
            if request.state != 'pending':
                raise UserError(_('Only pending requests can be rejected.'))
            
            current_user = self.env.user
            current_employee = current_user.employee_id
            
            if not current_employee or current_employee != request.approver_id:
                raise UserError(_('You are not authorized to reject this request.'))
            
            # Update request
            request.write({
                'state': 'rejected',
                'rejection_date': fields.Datetime.now(),
                'rejected_by_id': current_user.id,
                'rejection_reason': reason or _('No reason provided'),
            })
            
            # Log rejection
            request.message_post(
                body=_('Approval request rejected by %s. Reason: %s') % 
                     (current_employee.name, reason or _('No reason provided')),
                message_type='notification'
            )

    def action_escalate(self):
        """Escalate the request to next level"""
        for request in self:
            if request.state != 'pending':
                raise UserError(_('Only pending requests can be escalated.'))
            
            if not request.approval_rule_id.escalation_enabled:
                raise UserError(_('Escalation is not enabled for this approval rule.'))
            
            escalation_approvers = request.approval_rule_id.escalation_approver_ids
            if not escalation_approvers:
                raise UserError(_('No escalation approvers configured.'))
            
            # Create escalated requests
            for approver in escalation_approvers:
                escalated_request = self.create({
                    'expense_claim_id': request.expense_claim_id.id,
                    'approval_rule_id': request.approval_rule_id.id,
                    'approver_id': approver.id,
                    'sequence': request.sequence + 1000,  # Higher sequence for escalated
                    'state': 'pending',
                    'required_amount': request.required_amount,
                    'escalated_from_id': request.id,
                    'comments': _('Escalated from %s') % request.approver_id.name,
                })
                
                escalated_request.message_post(
                    body=_('Request escalated from %s') % request.approver_id.name,
                    message_type='notification'
                )
            
            # Update original request
            request.write({
                'state': 'escalated',
                'is_escalated': True,
            })
            
            request.message_post(
                body=_('Request escalated due to timeout'),
                message_type='notification'
            )

    def action_cancel(self):
        """Cancel the request"""
        for request in self:
            if request.state in ['approved', 'rejected']:
                raise UserError(_('Cannot cancel approved or rejected requests.'))
            
            request.write({'state': 'cancelled'})
            
            request.message_post(
                body=_('Approval request cancelled'),
                message_type='notification'
            )

    def _activate_next_approval(self):
        """Activate next approval in sequence if current is approved"""
        self.ensure_one()
        
        if self.state != 'approved':
            return
        
        # Find next pending approval in same claim
        next_approval = self.search([
            ('expense_claim_id', '=', self.expense_claim_id.id),
            ('sequence', '>', self.sequence),
            ('state', '=', 'waiting')
        ], order='sequence', limit=1)
        
        if next_approval:
            next_approval.write({'state': 'pending'})
            
            next_approval.message_post(
                body=_('Approval request activated (previous level approved)'),
                message_type='notification'
            )
            
            # Send notification to next approver
            if next_approval.approval_rule_id.notify_approvers:
                next_approval._send_approval_notification()

    def _send_approval_notification(self):
        """Send notification to approver"""
        self.ensure_one()
        
        if not self.approver_id.user_id:
            _logger.warning(f"Approver {self.approver_id.name} has no linked user account")
            return
        
        # Create activity for approver
        self.activity_schedule(
            'smart_expense_management.mail_activity_expense_approval',
            user_id=self.approver_id.user_id.id,
            summary=_('Expense Approval Required'),
            note=_(
                'Please review and approve expense claim %s for %s (Amount: %s %s)'
            ) % (
                self.expense_claim_id.name,
                self.expense_claim_id.employee_id.name,
                self.required_amount,
                self.currency_id.name
            )
        )

    # Automated Actions
    @api.model
    def _cron_check_escalations(self):
        """Cron job to check for overdue approvals and escalate them"""
        overdue_requests = self.search([
            ('state', '=', 'pending'),
            ('is_overdue', '=', True),
            ('approval_rule_id.escalation_enabled', '=', True)
        ])
        
        escalated_count = 0
        
        for request in overdue_requests:
            try:
                request.action_escalate()
                escalated_count += 1
            except Exception as e:
                _logger.error(f"Failed to escalate request {request.id}: {e}")
        
        if escalated_count > 0:
            _logger.info(f"Escalated {escalated_count} overdue approval requests")
        
        return escalated_count

    @api.model
    def _cron_send_pending_reminders(self):
        """Send reminders for pending approvals"""
        # Find requests pending for more than 1 day
        reminder_date = fields.Datetime.now() - timedelta(days=1)
        
        pending_requests = self.search([
            ('state', '=', 'pending'),
            ('request_date', '<', reminder_date)
        ])
        
        reminded_count = 0
        
        for request in pending_requests:
            try:
                if request.approver_id.user_id:
                    # Send reminder email or create activity
                    request.activity_schedule(
                        'mail.mail_activity_data_todo',
                        user_id=request.approver_id.user_id.id,
                        summary=_('Expense Approval Reminder'),
                        note=_(
                            'Reminder: Please review expense claim %s (Pending for %d days)'
                        ) % (request.expense_claim_id.name, request.days_pending)
                    )
                    reminded_count += 1
            except Exception as e:
                _logger.error(f"Failed to send reminder for request {request.id}: {e}")
        
        if reminded_count > 0:
            _logger.info(f"Sent {reminded_count} approval reminders")
        
        return reminded_count

    # Utility Methods
    def action_view_expense_claim(self):
        """Action to view related expense claim"""
        self.ensure_one()
        return {
            'type': 'ir.actions.act_window',
            'name': _('Expense Claim'),
            'res_model': 'expense.claim',
            'res_id': self.expense_claim_id.id,
            'view_mode': 'form',
            'target': 'current',
        }

    def action_open_approval_wizard(self):
        """Open approval wizard for detailed approval"""
        self.ensure_one()
        return {
            'type': 'ir.actions.act_window',
            'name': _('Approve Expense'),
            'res_model': 'expense.approval.wizard',
            'view_mode': 'form',
            'target': 'new',
            'context': {
                'default_approval_request_id': self.id,
                'default_comments': self.comments,
            }
        }

    # Constraints
    @api.constrains('sequence')
    def _check_sequence(self):
        for request in self:
            if request.sequence < 1:
                raise ValidationError(_('Sequence must be greater than 0'))

    @api.constrains('required_amount')
    def _check_required_amount(self):
        for request in self:
            if request.required_amount < 0:
                raise ValidationError(_('Required amount cannot be negative'))

    # Onchange Methods
    @api.onchange('approver_id')
    def _onchange_approver_id(self):
        if self.approver_id and self.state == 'waiting':
            # Auto-activate if this is the first approver
            if not self.search([
                ('expense_claim_id', '=', self.expense_claim_id.id),
                ('sequence', '<', self.sequence),
                ('state', 'in', ['pending', 'approved'])
            ]):
                self.state = 'pending'
