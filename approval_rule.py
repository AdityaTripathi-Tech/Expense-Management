# type: ignore
import logging
from odoo import models, fields, api, _
from odoo.exceptions import ValidationError

_logger = logging.getLogger(__name__)


class ApprovalRule(models.Model):
    _name = 'approval.rule'
    _description = 'Expense Approval Rule'
    _order = 'sequence, min_amount'

    name = fields.Char(
        string='Rule Name',
        required=True,
        help='Descriptive name for this approval rule'
    )
    
    active = fields.Boolean(
        string='Active',
        default=True,
        help='Whether this rule is currently active'
    )
    
    sequence = fields.Integer(
        string='Sequence',
        default=10,
        help='Order in which rules are evaluated'
    )
    
    company_id = fields.Many2one(
        'res.company',
        string='Company',
        required=True,
        default=lambda self: self.env.company
    )
    
    # Amount Criteria
    min_amount = fields.Monetary(
        string='Minimum Amount',
        currency_field='currency_id',
        default=0.0,
        help='Minimum expense amount for this rule to apply'
    )
    
    max_amount = fields.Monetary(
        string='Maximum Amount',
        currency_field='currency_id',
        help='Maximum expense amount for this rule (leave empty for no limit)'
    )
    
    currency_id = fields.Many2one(
        'res.currency',
        string='Currency',
        required=True,
        default=lambda self: self.env.company.currency_id
    )
    
    # Department Criteria
    department_ids = fields.Many2many(
        'hr.department',
        string='Departments',
        help='Departments this rule applies to (leave empty for all departments)'
    )
    
    # Employee Criteria
    employee_ids = fields.Many2many(
        'hr.employee',
        string='Specific Employees',
        help='Specific employees this rule applies to (leave empty for all employees)'
    )
    
    exclude_employee_ids = fields.Many2many(
        'hr.employee',
        'approval_rule_exclude_employee_rel',
        string='Exclude Employees',
        help='Employees excluded from this rule'
    )
    
    # Approval Type
    approval_type = fields.Selection([
        ('manager', 'Direct Manager'),
        ('department_head', 'Department Head'),
        ('specific_user', 'Specific User'),
        ('cfo', 'CFO'),
        ('sequential', 'Sequential Approval'),
        ('percentage', 'Percentage Based'),
        ('hybrid', 'Hybrid (Manager + Amount Based)')
    ], string='Approval Type', required=True, default='manager')
    
    # Specific Approvers
    approver_ids = fields.Many2many(
        'hr.employee',
        'approval_rule_approver_rel',
        string='Specific Approvers',
        help='Specific employees who can approve (for specific_user type)'
    )
    
    # Sequential Approval Settings
    require_all_approvers = fields.Boolean(
        string='Require All Approvers',
        default=True,
        help='If true, all approvers must approve. If false, any one approver is sufficient'
    )
    
    # Percentage Based Settings
    approval_percentage = fields.Float(
        string='Required Approval Percentage',
        default=50.0,
        help='Percentage of approvers required for approval (for percentage type)'
    )
    
    # Auto-approval Settings
    auto_approve_below_limit = fields.Boolean(
        string='Auto-approve Below Limit',
        default=False,
        help='Automatically approve expenses below minimum amount'
    )
    
    # Escalation Settings
    escalation_enabled = fields.Boolean(
        string='Enable Escalation',
        default=False,
        help='Enable automatic escalation if not approved within time limit'
    )
    
    escalation_hours = fields.Integer(
        string='Escalation Hours',
        default=24,
        help='Hours before escalation occurs'
    )
    
    escalation_approver_ids = fields.Many2many(
        'hr.employee',
        'approval_rule_escalation_rel',
        string='Escalation Approvers',
        help='Approvers for escalated requests'
    )
    
    # Notifications
    notify_submitter = fields.Boolean(
        string='Notify Submitter',
        default=True,
        help='Send notification to expense submitter'
    )
    
    notify_approvers = fields.Boolean(
        string='Notify Approvers',
        default=True,
        help='Send notification to approvers'
    )
    
    # Description and Notes
    description = fields.Text(
        string='Description',
        help='Detailed description of when this rule applies'
    )
    
    notes = fields.Text(
        string='Internal Notes',
        help='Internal notes for administrators'
    )

    @api.constrains('min_amount', 'max_amount')
    def _check_amount_range(self):
        """Validate amount range"""
        for rule in self:
            if rule.max_amount and rule.min_amount > rule.max_amount:
                raise ValidationError(
                    _('Minimum amount cannot be greater than maximum amount')
                )

    @api.constrains('approval_percentage')
    def _check_approval_percentage(self):
        """Validate approval percentage"""
        for rule in self:
            if rule.approval_type == 'percentage':
                if not (0 < rule.approval_percentage <= 100):
                    raise ValidationError(
                        _('Approval percentage must be between 0 and 100')
                    )

    @api.constrains('escalation_hours')
    def _check_escalation_hours(self):
        """Validate escalation hours"""
        for rule in self:
            if rule.escalation_enabled and rule.escalation_hours <= 0:
                raise ValidationError(
                    _('Escalation hours must be greater than 0')
                )

    @api.model
    def get_applicable_rules(self, amount, employee, department=None, company=None):
        """
        Get applicable approval rules for given criteria
        
        Args:
            amount (float): Expense amount in company currency
            employee (hr.employee): Employee submitting expense
            department (hr.department, optional): Employee's department
            company (res.company, optional): Company
            
        Returns:
            approval.rule recordset: Applicable rules ordered by sequence
        """
        if not company:
            company = self.env.company
        
        domain = [
            ('active', '=', True),
            ('company_id', '=', company.id),
            ('min_amount', '<=', amount)
        ]
        
        # Add max amount filter if specified
        domain.append('|')
        domain.append(('max_amount', '=', False))
        domain.append(('max_amount', '>=', amount))
        
        # Get all potentially applicable rules
        potential_rules = self.search(domain, order='sequence, min_amount')
        
        # Filter by department and employee criteria
        applicable_rules = self.env['approval.rule']
        
        for rule in potential_rules:
            # Check department criteria
            if rule.department_ids:
                if not department or department not in rule.department_ids:
                    continue
            
            # Check employee inclusion criteria
            if rule.employee_ids:
                if employee not in rule.employee_ids:
                    continue
            
            # Check employee exclusion criteria
            if rule.exclude_employee_ids:
                if employee in rule.exclude_employee_ids:
                    continue
            
            applicable_rules |= rule
        
        return applicable_rules

    def get_approvers(self, employee, department=None):
        """
        Get list of approvers for this rule
        
        Args:
            employee (hr.employee): Employee submitting expense
            department (hr.department, optional): Employee's department
            
        Returns:
            hr.employee recordset: List of approvers
        """
        self.ensure_one()
        
        approvers = self.env['hr.employee']
        
        if self.approval_type == 'manager':
            if employee.parent_id:
                approvers |= employee.parent_id
        
        elif self.approval_type == 'department_head':
            if department and department.manager_id:
                approvers |= department.manager_id
        
        elif self.approval_type == 'specific_user':
            approvers |= self.approver_ids
        
        elif self.approval_type == 'cfo':
            # Find CFO (employee with CFO job position or specific role)
            cfo_employees = self.env['hr.employee'].search([
                ('company_id', '=', self.company_id.id),
                '|',
                ('job_id.name', 'ilike', 'cfo'),
                ('job_id.name', 'ilike', 'chief financial officer')
            ])
            if cfo_employees:
                approvers |= cfo_employees[0]  # Take first CFO found
        
        elif self.approval_type == 'sequential':
            # For sequential, return all approvers in order
            approvers |= self.approver_ids
        
        elif self.approval_type == 'percentage':
            # For percentage-based, return all potential approvers
            approvers |= self.approver_ids
        
        elif self.approval_type == 'hybrid':
            # Hybrid: Manager + specific approvers based on amount
            if employee.parent_id:
                approvers |= employee.parent_id
            
            # Add additional approvers based on amount thresholds
            approvers |= self.approver_ids
        
        return approvers

    def get_required_approval_count(self):
        """
        Get number of approvals required for this rule
        
        Returns:
            int: Number of required approvals
        """
        self.ensure_one()
        
        if self.approval_type == 'percentage':
            total_approvers = len(self.approver_ids)
            required_count = int((self.approval_percentage / 100.0) * total_approvers)
            return max(1, required_count)  # At least 1 approval required
        
        elif self.approval_type == 'sequential' and self.require_all_approvers:
            return len(self.approver_ids)
        
        else:
            return 1  # Single approval required

    def action_test_rule(self):
        """Test this approval rule with sample data"""
        self.ensure_one()
        
        # Create a test scenario
        test_employee = self.env['hr.employee'].search([
            ('company_id', '=', self.company_id.id)
        ], limit=1)
        
        if not test_employee:
            return {
                'type': 'ir.actions.client',
                'tag': 'display_notification',
                'params': {
                    'title': _('Test Failed'),
                    'message': _('No employees found to test with'),
                    'type': 'warning',
                }
            }
        
        test_amount = self.min_amount + 100  # Test with amount above minimum
        
        try:
            approvers = self.get_approvers(test_employee, test_employee.department_id)
            required_count = self.get_required_approval_count()
            
            message = _(
                'Test Results:\n'
                'Employee: %s\n'
                'Test Amount: %.2f %s\n'
                'Approvers Found: %d\n'
                'Required Approvals: %d\n'
                'Approvers: %s'
            ) % (
                test_employee.name,
                test_amount,
                self.currency_id.name,
                len(approvers),
                required_count,
                ', '.join(approvers.mapped('name'))
            )
            
            return {
                'type': 'ir.actions.client',
                'tag': 'display_notification',
                'params': {
                    'title': _('Rule Test Results'),
                    'message': message,
                    'type': 'success',
                    'sticky': True,
                }
            }
            
        except Exception as e:
            return {
                'type': 'ir.actions.client',
                'tag': 'display_notification',
                'params': {
                    'title': _('Test Error'),
                    'message': _('Error testing rule: %s') % str(e),
                    'type': 'danger',
                    'sticky': True,
                }
            }

    @api.model
    def create_default_rules(self, company):
        """
        Create default approval rules for a company
        
        Args:
            company (res.company): Company to create rules for
        """
        default_rules = [
            {
                'name': 'Auto-approve Small Expenses',
                'company_id': company.id,
                'min_amount': 0.0,
                'max_amount': company.expense_auto_approve_limit,
                'approval_type': 'manager',
                'auto_approve_below_limit': True,
                'sequence': 1,
            },
            {
                'name': 'Manager Approval - Medium Expenses',
                'company_id': company.id,
                'min_amount': company.expense_auto_approve_limit,
                'max_amount': company.expense_manager_approval_limit,
                'approval_type': 'manager',
                'sequence': 2,
            },
            {
                'name': 'CFO Approval - Large Expenses',
                'company_id': company.id,
                'min_amount': company.expense_cfo_approval_required,
                'max_amount': False,  # No upper limit
                'approval_type': 'sequential',
                'sequence': 3,
            }
        ]
        
        created_rules = self.env['approval.rule']
        
        for rule_data in default_rules:
            # Check if similar rule already exists
            existing = self.search([
                ('company_id', '=', company.id),
                ('name', '=', rule_data['name'])
            ])
            
            if not existing:
                rule = self.create(rule_data)
                created_rules |= rule
                _logger.info(f"Created default approval rule: {rule.name}")
        
        return created_rules

    def name_get(self):
        """Custom name display"""
        result = []
        for rule in self:
            name = rule.name
            if rule.min_amount or rule.max_amount:
                amount_range = f"{rule.min_amount:.0f}"
                if rule.max_amount:
                    amount_range += f"-{rule.max_amount:.0f}"
                else:
                    amount_range += "+"
                name += f" ({amount_range} {rule.currency_id.name})"
            result.append((rule.id, name))
        return result
