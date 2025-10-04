# type: ignore
import logging
from odoo import models, fields, api, _
from odoo.exceptions import ValidationError, UserError

_logger = logging.getLogger(__name__)


class ExpenseLine(models.Model):
    _name = 'expense.line'
    _description = 'Expense Line Item'
    _inherit = ['mail.thread', 'mail.activity.mixin']
    _order = 'date desc, id desc'

    # Basic Information
    name = fields.Char(
        string='Description',
        required=True,
        tracking=True,
        help='Brief description of the expense'
    )
    
    claim_id = fields.Many2one(
        'expense.claim',
        string='Expense Claim',
        required=True,
        ondelete='cascade',
        index=True
    )
    
    employee_id = fields.Many2one(
        'hr.employee',
        string='Employee',
        related='claim_id.employee_id',
        store=True,
        readonly=True
    )
    
    company_id = fields.Many2one(
        'res.company',
        string='Company',
        related='claim_id.company_id',
        store=True,
        readonly=True
    )
    
    # Date and Category
    date = fields.Date(
        string='Expense Date',
        required=True,
        default=fields.Date.today,
        tracking=True,
        help='Date when the expense was incurred'
    )
    
    category_id = fields.Many2one(
        'expense.category',
        string='Category',
        required=True,
        help='Expense category for reporting and approval rules'
    )
    
    # Financial Information
    currency_id = fields.Many2one(
        'res.currency',
        string='Currency',
        required=True,
        default=lambda self: self.env.company.expense_default_currency_id or self.env.company.currency_id
    )
    
    unit_amount = fields.Monetary(
        string='Unit Amount',
        currency_field='currency_id',
        required=True,
        tracking=True,
        help='Amount per unit'
    )
    
    quantity = fields.Float(
        string='Quantity',
        default=1.0,
        required=True,
        help='Number of units'
    )
    
    total_amount = fields.Monetary(
        string='Total Amount',
        currency_field='currency_id',
        compute='_compute_total_amount',
        store=True,
        tracking=True
    )
    
    tax_amount = fields.Monetary(
        string='Tax Amount',
        currency_field='currency_id',
        help='Tax amount if applicable'
    )
    
    # Receipt and OCR Information
    receipt_attachment_id = fields.Many2one(
        'ir.attachment',
        string='Receipt',
        help='Receipt image or document'
    )
    
    has_receipt = fields.Boolean(
        string='Has Receipt',
        compute='_compute_has_receipt',
        store=True
    )
    
    ocr_processed = fields.Boolean(
        string='OCR Processed',
        default=False,
        help='Whether OCR has been run on the receipt'
    )
    
    ocr_confidence = fields.Float(
        string='OCR Confidence',
        help='Confidence level of OCR processing (0.0-1.0)'
    )
    
    ocr_confidence_low = fields.Boolean(
        string='Low OCR Confidence',
        compute='_compute_ocr_confidence_low',
        store=True,
        help='True if OCR confidence is below threshold'
    )
    
    ocr_extracted_data = fields.Text(
        string='OCR Extracted Data',
        help='Raw text extracted from receipt via OCR'
    )
    
    # Vendor Information
    vendor_name = fields.Char(
        string='Vendor/Merchant',
        help='Name of the vendor or merchant'
    )
    
    vendor_id = fields.Many2one(
        'res.partner',
        string='Vendor',
        help='Vendor partner record if available'
    )
    
    # Location and Travel
    location = fields.Char(
        string='Location',
        help='Location where expense was incurred'
    )
    
    is_travel_expense = fields.Boolean(
        string='Travel Expense',
        default=False,
        help='Whether this is a travel-related expense'
    )
    
    # Approval and Status
    state = fields.Selection([
        ('draft', 'Draft'),
        ('submitted', 'Submitted'),
        ('approved', 'Approved'),
        ('rejected', 'Rejected')
    ], string='Status', default='draft', related='claim_id.state', store=True)
    
    # Additional Information
    notes = fields.Text(
        string='Notes',
        help='Additional notes or comments'
    )
    
    reference = fields.Char(
        string='Reference',
        help='External reference number'
    )
    
    # Computed Fields
    @api.depends('unit_amount', 'quantity')
    def _compute_total_amount(self):
        for line in self:
            line.total_amount = line.unit_amount * line.quantity

    @api.depends('receipt_attachment_id')
    def _compute_has_receipt(self):
        for line in self:
            line.has_receipt = bool(line.receipt_attachment_id)

    @api.depends('ocr_confidence', 'company_id')
    def _compute_ocr_confidence_low(self):
        for line in self:
            if line.ocr_confidence and line.company_id:
                threshold = line.company_id.ocr_confidence_threshold
                line.ocr_confidence_low = line.ocr_confidence < threshold
            else:
                line.ocr_confidence_low = False

    # Actions
    def action_process_ocr(self):
        """Process receipt with OCR"""
        for line in self:
            if not line.receipt_attachment_id:
                raise UserError(_('No receipt attached to process.'))
            
            if line.ocr_processed:
                raise UserError(_('OCR has already been processed for this receipt.'))
            
            try:
                ocr_service = self.env['ocr.service']
                result = ocr_service.process_receipt(line.receipt_attachment_id)
                
                if result:
                    # Update line with OCR results
                    update_vals = {
                        'ocr_processed': True,
                        'ocr_confidence': result.get('confidence', 0.0),
                        'ocr_extracted_data': result.get('raw_text', ''),
                    }
                    
                    # Auto-fill fields if confidence is high enough
                    extracted_data = result.get('extracted_data', {})
                    if extracted_data and result.get('confidence', 0) >= line.company_id.ocr_confidence_threshold:
                        if extracted_data.get('amount') and not line.unit_amount:
                            update_vals['unit_amount'] = extracted_data['amount']
                        
                        if extracted_data.get('date') and not line.date:
                            update_vals['date'] = extracted_data['date']
                        
                        if extracted_data.get('vendor') and not line.vendor_name:
                            update_vals['vendor_name'] = extracted_data['vendor']
                        
                        if extracted_data.get('description') and not line.name:
                            update_vals['name'] = extracted_data['description']
                    
                    line.write(update_vals)
                    
                    # Log OCR processing
                    line.message_post(
                        body=_('OCR processed with confidence: %.1f%%') % (result.get('confidence', 0) * 100),
                        message_type='notification'
                    )
                    
                    return {
                        'type': 'ir.actions.client',
                        'tag': 'display_notification',
                        'params': {
                            'title': _('OCR Processed'),
                            'message': _('Receipt processed successfully. Confidence: %.1f%%') % 
                                     (result.get('confidence', 0) * 100),
                            'type': 'success' if not line.ocr_confidence_low else 'warning',
                        }
                    }
                else:
                    return {
                        'type': 'ir.actions.client',
                        'tag': 'display_notification',
                        'params': {
                            'title': _('OCR Failed'),
                            'message': _('Failed to process receipt. Please enter details manually.'),
                            'type': 'warning',
                        }
                    }
                    
            except Exception as e:
                _logger.error(f"OCR processing failed for line {line.id}: {e}")
                return {
                    'type': 'ir.actions.client',
                    'tag': 'display_notification',
                    'params': {
                        'title': _('OCR Error'),
                        'message': _('OCR processing error: %s') % str(e),
                        'type': 'danger',
                    }
                }

    def action_upload_receipt(self):
        """Action to upload receipt"""
        self.ensure_one()
        return {
            'type': 'ir.actions.act_window',
            'name': _('Upload Receipt'),
            'res_model': 'expense.receipt.wizard',
            'view_mode': 'form',
            'target': 'new',
            'context': {
                'default_expense_line_id': self.id,
            }
        }

    def action_view_receipt(self):
        """Action to view receipt"""
        self.ensure_one()
        if not self.receipt_attachment_id:
            raise UserError(_('No receipt attached.'))
        
        return {
            'type': 'ir.actions.act_url',
            'url': f'/web/content/{self.receipt_attachment_id.id}?download=true',
            'target': 'new',
        }

    def action_match_vendor(self):
        """Try to match vendor name with existing partners"""
        for line in self:
            if not line.vendor_name or line.vendor_id:
                continue
            
            # Search for existing partner
            partner = self.env['res.partner'].search([
                '|',
                ('name', 'ilike', line.vendor_name),
                ('display_name', 'ilike', line.vendor_name)
            ], limit=1)
            
            if partner:
                line.vendor_id = partner.id
                line.message_post(
                    body=_('Vendor matched: %s') % partner.name,
                    message_type='notification'
                )

    # Utility Methods
    def _prepare_account_move_line(self):
        """Prepare account move line data for accounting integration"""
        self.ensure_one()
        
        # This would be used for integration with accounting
        return {
            'name': self.name,
            'account_id': self.category_id.account_id.id if self.category_id.account_id else False,
            'debit': self.total_amount if self.total_amount > 0 else 0,
            'credit': abs(self.total_amount) if self.total_amount < 0 else 0,
            'partner_id': self.vendor_id.id if self.vendor_id else False,
            'date': self.date,
            'ref': self.reference,
        }

    # Constraints
    @api.constrains('unit_amount')
    def _check_unit_amount(self):
        for line in self:
            if line.unit_amount < 0:
                raise ValidationError(_('Unit amount cannot be negative.'))

    @api.constrains('quantity')
    def _check_quantity(self):
        for line in self:
            if line.quantity <= 0:
                raise ValidationError(_('Quantity must be greater than zero.'))

    @api.constrains('date', 'claim_id')
    def _check_date(self):
        for line in self:
            if line.claim_id.claim_date and line.date > line.claim_id.claim_date:
                raise ValidationError(
                    _('Expense date cannot be after claim date.')
                )

    @api.constrains('ocr_confidence')
    def _check_ocr_confidence(self):
        for line in self:
            if line.ocr_confidence and not (0.0 <= line.ocr_confidence <= 1.0):
                raise ValidationError(
                    _('OCR confidence must be between 0.0 and 1.0')
                )

    # Onchange Methods
    @api.onchange('receipt_attachment_id')
    def _onchange_receipt_attachment(self):
        """Auto-process OCR when receipt is uploaded"""
        if (self.receipt_attachment_id and 
            not self.ocr_processed and 
            self.company_id.ocr_enabled):
            
            # Schedule OCR processing
            self.env.context = dict(self.env.context, auto_process_ocr=True)

    @api.onchange('vendor_name')
    def _onchange_vendor_name(self):
        """Auto-match vendor when name is entered"""
        if self.vendor_name and not self.vendor_id:
            self.action_match_vendor()

    @api.onchange('category_id')
    def _onchange_category_id(self):
        """Update fields based on category"""
        if self.category_id:
            # Set default currency if category has one
            if self.category_id.default_currency_id:
                self.currency_id = self.category_id.default_currency_id
            
            # Set travel expense flag
            if 'travel' in self.category_id.name.lower():
                self.is_travel_expense = True


class ExpenseCategory(models.Model):
    _name = 'expense.category'
    _description = 'Expense Category'
    _order = 'sequence, name'

    name = fields.Char(
        string='Category Name',
        required=True,
        translate=True
    )
    
    code = fields.Char(
        string='Category Code',
        help='Short code for the category'
    )
    
    active = fields.Boolean(
        string='Active',
        default=True
    )
    
    sequence = fields.Integer(
        string='Sequence',
        default=10
    )
    
    description = fields.Text(
        string='Description',
        translate=True
    )
    
    # Accounting Integration
    account_id = fields.Many2one(
        'account.account',
        string='Expense Account',
        help='Default account for expenses in this category'
    )
    
    # Default Settings
    default_currency_id = fields.Many2one(
        'res.currency',
        string='Default Currency',
        help='Default currency for this category'
    )
    
    requires_receipt = fields.Boolean(
        string='Requires Receipt',
        default=True,
        help='Whether receipts are mandatory for this category'
    )
    
    # Approval Settings
    auto_approve_limit = fields.Monetary(
        string='Auto-approve Limit',
        currency_field='currency_id',
        help='Amount below which expenses are auto-approved'
    )
    
    currency_id = fields.Many2one(
        'res.currency',
        string='Currency',
        default=lambda self: self.env.company.currency_id
    )
    
    # Statistics
    expense_count = fields.Integer(
        string='Expense Count',
        compute='_compute_expense_count'
    )

    @api.depends()
    def _compute_expense_count(self):
        for category in self:
            category.expense_count = self.env['expense.line'].search_count([
                ('category_id', '=', category.id)
            ])

    def action_view_expenses(self):
        """View expenses in this category"""
        self.ensure_one()
        return {
            'type': 'ir.actions.act_window',
            'name': _('Expenses - %s') % self.name,
            'res_model': 'expense.line',
            'view_mode': 'tree,form',
            'domain': [('category_id', '=', self.id)],
            'context': {'default_category_id': self.id},
        }

    @api.model
    def create_default_categories(self):
        """Create default expense categories"""
        default_categories = [
            {'name': 'Meals & Entertainment', 'code': 'MEALS', 'requires_receipt': True},
            {'name': 'Travel & Transportation', 'code': 'TRAVEL', 'requires_receipt': True},
            {'name': 'Office Supplies', 'code': 'OFFICE', 'requires_receipt': True},
            {'name': 'Training & Education', 'code': 'TRAINING', 'requires_receipt': True},
            {'name': 'Communication', 'code': 'COMM', 'requires_receipt': False},
            {'name': 'Fuel & Mileage', 'code': 'FUEL', 'requires_receipt': True},
            {'name': 'Accommodation', 'code': 'HOTEL', 'requires_receipt': True},
            {'name': 'Marketing & Advertising', 'code': 'MARKETING', 'requires_receipt': True},
            {'name': 'Software & Subscriptions', 'code': 'SOFTWARE', 'requires_receipt': True},
            {'name': 'Miscellaneous', 'code': 'MISC', 'requires_receipt': False},
        ]
        
        created_categories = self.env['expense.category']
        
        for cat_data in default_categories:
            existing = self.search([('code', '=', cat_data['code'])], limit=1)
            if not existing:
                category = self.create(cat_data)
                created_categories |= category
        
        return created_categories
