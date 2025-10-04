# type: ignore
import logging
from odoo import models, fields, api, _
from odoo.exceptions import ValidationError

_logger = logging.getLogger(__name__)


class ResCompany(models.Model):
    _inherit = 'res.company'

    # Expense Management Configuration
    expense_approval_required = fields.Boolean(
        string='Require Expense Approval',
        default=True,
        help='If enabled, expenses must be approved before processing'
    )
    
    expense_auto_approve_limit = fields.Monetary(
        string='Auto-Approve Limit',
        default=100.0,
        help='Expenses below this amount are automatically approved'
    )
    
    expense_manager_approval_limit = fields.Monetary(
        string='Manager Approval Limit',
        default=1000.0,
        help='Maximum amount managers can approve without CFO approval'
    )
    
    expense_cfo_approval_required = fields.Monetary(
        string='CFO Approval Required Above',
        default=5000.0,
        help='Expenses above this amount require CFO approval'
    )
    
    # Multi-currency Configuration
    expense_default_currency_id = fields.Many2one(
        'res.currency',
        string='Default Expense Currency',
        help='Default currency for expense submissions'
    )
    
    expense_currency_conversion_enabled = fields.Boolean(
        string='Enable Currency Conversion',
        default=True,
        help='Automatically convert expenses to company currency'
    )
    
    # OCR Configuration
    ocr_enabled = fields.Boolean(
        string='Enable OCR Processing',
        default=True,
        help='Enable automatic receipt processing with OCR'
    )
    
    ocr_confidence_threshold = fields.Float(
        string='OCR Confidence Threshold',
        default=0.6,
        help='Minimum confidence level for OCR results (0.0-1.0)'
    )
    
    # API Configuration
    use_google_vision = fields.Boolean(
        string='Use Google Vision API',
        default=False,
        help='Use Google Vision API for OCR (requires API key)'
    )
    
    google_vision_api_key = fields.Char(
        string='Google Vision API Key',
        help='API key for Google Vision OCR service'
    )
    
    # Notification Settings
    expense_notification_emails = fields.Text(
        string='Notification Emails',
        help='Comma-separated list of emails for expense notifications'
    )

    @api.model
    def create(self, vals):
        """Override create to set up default currency based on country"""
        company = super().create(vals)
        
        if company.country_id and not company.expense_default_currency_id:
            try:
                # Use country service to get default currency
                country_service = self.env['country.service']
                currency_info = country_service.get_country_currency(company.country_id.code)
                
                if currency_info:
                    currency = self.env['res.currency'].search([
                        ('name', '=', currency_info.get('code'))
                    ], limit=1)
                    
                    if currency:
                        company.expense_default_currency_id = currency.id
                        _logger.info(
                            f"Set default expense currency {currency.name} "
                            f"for company {company.name} based on country {company.country_id.name}"
                        )
                    
            except Exception as e:
                _logger.warning(
                    f"Failed to set default currency for company {company.name}: {e}"
                )
        
        return company

    @api.constrains('ocr_confidence_threshold')
    def _check_ocr_confidence_threshold(self):
        """Validate OCR confidence threshold is between 0 and 1"""
        for company in self:
            if not (0.0 <= company.ocr_confidence_threshold <= 1.0):
                raise ValidationError(
                    _('OCR confidence threshold must be between 0.0 and 1.0')
                )

    @api.constrains('expense_auto_approve_limit', 'expense_manager_approval_limit', 'expense_cfo_approval_required')
    def _check_approval_limits(self):
        """Validate approval limits are in ascending order"""
        for company in self:
            if company.expense_auto_approve_limit > company.expense_manager_approval_limit:
                raise ValidationError(
                    _('Auto-approve limit cannot exceed manager approval limit')
                )
            
            if company.expense_manager_approval_limit > company.expense_cfo_approval_required:
                raise ValidationError(
                    _('Manager approval limit cannot exceed CFO approval threshold')
                )

    def action_test_currency_service(self):
        """Test currency service connection (for admin use)"""
        try:
            currency_service = self.env['currency.service']
            rates = currency_service.get_exchange_rates('USD')
            
            if rates:
                return {
                    'type': 'ir.actions.client',
                    'tag': 'display_notification',
                    'params': {
                        'title': _('Currency Service Test'),
                        'message': _('Successfully fetched %d exchange rates') % len(rates),
                        'type': 'success',
                        'sticky': False,
                    }
                }
            else:
                return {
                    'type': 'ir.actions.client',
                    'tag': 'display_notification',
                    'params': {
                        'title': _('Currency Service Test'),
                        'message': _('No exchange rates available - check configuration'),
                        'type': 'warning',
                        'sticky': True,
                    }
                }
                
        except Exception as e:
            _logger.error(f"Currency service test failed: {e}")
            return {
                'type': 'ir.actions.client',
                'tag': 'display_notification',
                'params': {
                    'title': _('Currency Service Test'),
                    'message': _('Test failed: %s') % str(e),
                    'type': 'danger',
                    'sticky': True,
                }
            }

    def action_refresh_country_currencies(self):
        """Refresh country-currency mappings from external API"""
        try:
            country_service = self.env['country.service']
            result = country_service.refresh_country_mappings()
            
            return {
                'type': 'ir.actions.client',
                'tag': 'display_notification',
                'params': {
                    'title': _('Country Currency Refresh'),
                    'message': _('Successfully updated %d country mappings') % result.get('updated', 0),
                    'type': 'success',
                    'sticky': False,
                }
            }
            
        except Exception as e:
            _logger.error(f"Country currency refresh failed: {e}")
            return {
                'type': 'ir.actions.client',
                'tag': 'display_notification',
                'params': {
                    'title': _('Country Currency Refresh'),
                    'message': _('Refresh failed: %s') % str(e),
                    'type': 'danger',
                    'sticky': True,
                }
            }
