# type: ignore
import json
import logging
from odoo import http
from odoo.http import request
from odoo.exceptions import AccessError, UserError

_logger = logging.getLogger(__name__)


class ExpenseAPIController(http.Controller):
    """REST API endpoints for Smart Expense Management"""

    @http.route('/api/expense/claims', type='json', auth='user', methods=['GET'])
    def get_expense_claims(self, **kwargs):
        """Get expense claims for current user"""
        try:
            domain = [('employee_id.user_id', '=', request.env.user.id)]
            
            # Add filters from kwargs
            if kwargs.get('state'):
                domain.append(('state', '=', kwargs['state']))
            
            claims = request.env['expense.claim'].search(domain)
            
            return {
                'success': True,
                'data': [{
                    'id': claim.id,
                    'name': claim.name,
                    'total_amount': claim.total_amount,
                    'currency': claim.currency_id.name,
                    'state': claim.state,
                    'claim_date': claim.claim_date.isoformat() if claim.claim_date else None,
                    'employee': claim.employee_id.name,
                } for claim in claims]
            }
        except Exception as e:
            _logger.error(f"API error getting expense claims: {e}")
            return {'success': False, 'error': str(e)}

    @http.route('/api/expense/claims', type='json', auth='user', methods=['POST'])
    def create_expense_claim(self, **kwargs):
        """Create new expense claim"""
        try:
            employee = request.env.user.employee_id
            if not employee:
                return {'success': False, 'error': 'User not linked to employee'}
            
            claim_data = {
                'employee_id': employee.id,
                'description': kwargs.get('description', ''),
                'currency_id': kwargs.get('currency_id', request.env.company.currency_id.id),
            }
            
            claim = request.env['expense.claim'].create(claim_data)
            
            return {
                'success': True,
                'data': {
                    'id': claim.id,
                    'name': claim.name,
                    'state': claim.state,
                }
            }
        except Exception as e:
            _logger.error(f"API error creating expense claim: {e}")
            return {'success': False, 'error': str(e)}

    @http.route('/api/expense/claims/<int:claim_id>/submit', type='json', auth='user', methods=['POST'])
    def submit_expense_claim(self, claim_id, **kwargs):
        """Submit expense claim for approval"""
        try:
            claim = request.env['expense.claim'].browse(claim_id)
            
            if not claim.exists():
                return {'success': False, 'error': 'Claim not found'}
            
            if claim.employee_id.user_id != request.env.user:
                return {'success': False, 'error': 'Access denied'}
            
            claim.action_submit()
            
            return {
                'success': True,
                'data': {
                    'id': claim.id,
                    'state': claim.state,
                    'current_approver': claim.current_approver_id.name if claim.current_approver_id else None,
                }
            }
        except UserError as e:
            return {'success': False, 'error': str(e)}
        except Exception as e:
            _logger.error(f"API error submitting claim {claim_id}: {e}")
            return {'success': False, 'error': str(e)}

    @http.route('/api/expense/lines', type='json', auth='user', methods=['POST'])
    def create_expense_line(self, **kwargs):
        """Create expense line"""
        try:
            required_fields = ['claim_id', 'name', 'category_id', 'unit_amount']
            for field in required_fields:
                if field not in kwargs:
                    return {'success': False, 'error': f'Missing required field: {field}'}
            
            # Verify claim ownership
            claim = request.env['expense.claim'].browse(kwargs['claim_id'])
            if not claim.exists() or claim.employee_id.user_id != request.env.user:
                return {'success': False, 'error': 'Access denied'}
            
            line_data = {
                'claim_id': kwargs['claim_id'],
                'name': kwargs['name'],
                'category_id': kwargs['category_id'],
                'unit_amount': kwargs['unit_amount'],
                'quantity': kwargs.get('quantity', 1.0),
                'date': kwargs.get('date'),
                'vendor_name': kwargs.get('vendor_name'),
                'notes': kwargs.get('notes'),
            }
            
            line = request.env['expense.line'].create(line_data)
            
            return {
                'success': True,
                'data': {
                    'id': line.id,
                    'name': line.name,
                    'total_amount': line.total_amount,
                    'currency': line.currency_id.name,
                }
            }
        except Exception as e:
            _logger.error(f"API error creating expense line: {e}")
            return {'success': False, 'error': str(e)}

    @http.route('/api/expense/approvals/pending', type='json', auth='user', methods=['GET'])
    def get_pending_approvals(self, **kwargs):
        """Get pending approvals for current user"""
        try:
            employee = request.env.user.employee_id
            if not employee:
                return {'success': False, 'error': 'User not linked to employee'}
            
            approvals = request.env['approval.request'].search([
                ('approver_id', '=', employee.id),
                ('state', '=', 'pending')
            ])
            
            return {
                'success': True,
                'data': [{
                    'id': approval.id,
                    'claim_name': approval.expense_claim_id.name,
                    'employee': approval.expense_claim_id.employee_id.name,
                    'amount': approval.required_amount,
                    'currency': approval.currency_id.name,
                    'request_date': approval.request_date.isoformat(),
                    'days_pending': approval.days_pending,
                } for approval in approvals]
            }
        except Exception as e:
            _logger.error(f"API error getting pending approvals: {e}")
            return {'success': False, 'error': str(e)}

    @http.route('/api/expense/approvals/<int:approval_id>/approve', type='json', auth='user', methods=['POST'])
    def approve_expense(self, approval_id, **kwargs):
        """Approve expense"""
        try:
            approval = request.env['approval.request'].browse(approval_id)
            
            if not approval.exists():
                return {'success': False, 'error': 'Approval not found'}
            
            if approval.approver_id.user_id != request.env.user:
                return {'success': False, 'error': 'Access denied'}
            
            comments = kwargs.get('comments', '')
            approval.action_approve(comments)
            
            return {
                'success': True,
                'data': {
                    'id': approval.id,
                    'state': approval.state,
                    'claim_state': approval.expense_claim_id.state,
                }
            }
        except UserError as e:
            return {'success': False, 'error': str(e)}
        except Exception as e:
            _logger.error(f"API error approving {approval_id}: {e}")
            return {'success': False, 'error': str(e)}

    @http.route('/api/expense/approvals/<int:approval_id>/reject', type='json', auth='user', methods=['POST'])
    def reject_expense(self, approval_id, **kwargs):
        """Reject expense"""
        try:
            approval = request.env['approval.request'].browse(approval_id)
            
            if not approval.exists():
                return {'success': False, 'error': 'Approval not found'}
            
            if approval.approver_id.user_id != request.env.user:
                return {'success': False, 'error': 'Access denied'}
            
            reason = kwargs.get('reason', 'No reason provided')
            approval.action_reject(reason)
            
            return {
                'success': True,
                'data': {
                    'id': approval.id,
                    'state': approval.state,
                    'claim_state': approval.expense_claim_id.state,
                }
            }
        except UserError as e:
            return {'success': False, 'error': str(e)}
        except Exception as e:
            _logger.error(f"API error rejecting {approval_id}: {e}")
            return {'success': False, 'error': str(e)}

    @http.route('/api/expense/categories', type='json', auth='user', methods=['GET'])
    def get_expense_categories(self, **kwargs):
        """Get expense categories"""
        try:
            categories = request.env['expense.category'].search([('active', '=', True)])
            
            return {
                'success': True,
                'data': [{
                    'id': cat.id,
                    'name': cat.name,
                    'code': cat.code,
                    'requires_receipt': cat.requires_receipt,
                } for cat in categories]
            }
        except Exception as e:
            _logger.error(f"API error getting categories: {e}")
            return {'success': False, 'error': str(e)}

    @http.route('/api/expense/currencies', type='json', auth='user', methods=['GET'])
    def get_currencies(self, **kwargs):
        """Get available currencies"""
        try:
            currencies = request.env['res.currency'].search([('active', '=', True)])
            
            return {
                'success': True,
                'data': [{
                    'id': curr.id,
                    'name': curr.name,
                    'symbol': curr.symbol,
                    'position': curr.position,
                } for curr in currencies]
            }
        except Exception as e:
            _logger.error(f"API error getting currencies: {e}")
            return {'success': False, 'error': str(e)}

    @http.route('/api/expense/convert', type='json', auth='user', methods=['POST'])
    def convert_currency(self, **kwargs):
        """Convert currency amount"""
        try:
            required_fields = ['amount', 'from_currency', 'to_currency']
            for field in required_fields:
                if field not in kwargs:
                    return {'success': False, 'error': f'Missing required field: {field}'}
            
            currency_service = request.env['currency.service']
            result = currency_service.convert_amount(
                amount=kwargs['amount'],
                from_currency=kwargs['from_currency'],
                to_currency=kwargs['to_currency'],
                rate_date=kwargs.get('rate_date')
            )
            
            return {
                'success': True,
                'data': result
            }
        except Exception as e:
            _logger.error(f"API error converting currency: {e}")
            return {'success': False, 'error': str(e)}

    @http.route('/api/expense/ocr/process', type='http', auth='user', methods=['POST'], csrf=False)
    def process_ocr(self, **kwargs):
        """Process OCR for uploaded receipt"""
        try:
            if 'receipt' not in request.httprequest.files:
                return json.dumps({'success': False, 'error': 'No receipt file provided'})
            
            receipt_file = request.httprequest.files['receipt']
            
            # Create attachment
            attachment = request.env['ir.attachment'].create({
                'name': receipt_file.filename,
                'datas': receipt_file.read(),
                'mimetype': receipt_file.content_type,
            })
            
            # Process OCR
            ocr_service = request.env['ocr.service']
            result = ocr_service.process_receipt(attachment)
            
            return json.dumps({
                'success': True,
                'data': {
                    'attachment_id': attachment.id,
                    'ocr_result': result
                }
            })
        except Exception as e:
            _logger.error(f"API error processing OCR: {e}")
            return json.dumps({'success': False, 'error': str(e)})

    @http.route('/api/expense/health', type='json', auth='none', methods=['GET'])
    def health_check(self, **kwargs):
        """Health check endpoint"""
        try:
            # Basic health checks
            health_status = {
                'database': True,
                'services': {},
                'timestamp': http.request.env.cr.now().isoformat()
            }
            
            # Test currency service
            try:
                currency_service = request.env['currency.service']
                stats = currency_service.get_cache_statistics()
                health_status['services']['currency'] = {
                    'status': 'healthy',
                    'cache_entries': stats.get('total_entries', 0)
                }
            except Exception as e:
                health_status['services']['currency'] = {
                    'status': 'error',
                    'error': str(e)
                }
            
            # Test OCR service
            try:
                ocr_service = request.env['ocr.service']
                ocr_status = ocr_service.test_ocr_service()
                health_status['services']['ocr'] = {
                    'status': 'healthy',
                    'tesseract_available': ocr_status['tesseract_available'],
                    'google_vision_available': ocr_status['google_vision_available']
                }
            except Exception as e:
                health_status['services']['ocr'] = {
                    'status': 'error',
                    'error': str(e)
                }
            
            return {
                'success': True,
                'data': health_status
            }
        except Exception as e:
            _logger.error(f"Health check error: {e}")
            return {'success': False, 'error': str(e)}

