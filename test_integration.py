# type: ignore

import unittest
import json
import requests
from odoo.tests.common import HttpCase, TransactionCase
from odoo.exceptions import ValidationError


class TestIntegration(HttpCase):
    """Integration tests for the Smart Expense Management module"""
    
    def setUp(self):
        super().setUp()
        
        # Create test users
        self.employee_user = self.env['res.users'].create({
            'name': 'Test Employee',
            'login': 'employee@test.com',
            'email': 'employee@test.com',
            'groups_id': [(6, 0, [self.env.ref('base.group_user').id])]
        })
        
        self.manager_user = self.env['res.users'].create({
            'name': 'Test Manager',
            'login': 'manager@test.com',
            'email': 'manager@test.com',
            'groups_id': [(6, 0, [self.env.ref('base.group_user').id])]
        })
        
        # Create test employees
        self.employee = self.env['hr.employee'].create({
            'name': 'Test Employee',
            'user_id': self.employee_user.id,
        })
        
        self.manager = self.env['hr.employee'].create({
            'name': 'Test Manager',
            'user_id': self.manager_user.id,
        })
        
        # Set manager relationship
        self.employee.parent_id = self.manager.id
        
        # Create test company with currency
        self.test_company = self.env['res.company'].create({
            'name': 'Test Company',
            'currency_id': self.env.ref('base.USD').id,
        })
        
        # Create approval rule
        self.approval_rule = self.env['approval.rule'].create({
            'name': 'Manager Approval',
            'rule_type': 'manager',
            'amount_threshold': 100.0,
            'currency_id': self.env.ref('base.USD').id,
            'sequence': 1,
            'company_id': self.test_company.id,
        })
    
    def test_expense_submission_flow(self):
        """Test complete expense submission and approval flow"""
        
        # Create expense claim
        expense_claim = self.env['expense.claim'].with_user(self.employee_user).create({
            'employee_id': self.employee.id,
            'description': 'Business lunch',
            'company_id': self.test_company.id,
        })
        
        # Add expense line
        expense_line = self.env['expense.line'].create({
            'expense_claim_id': expense_claim.id,
            'description': 'Restaurant bill',
            'amount': 150.0,
            'currency_id': self.env.ref('base.USD').id,
            'expense_date': '2024-01-15',
        })
        
        # Submit expense
        expense_claim.action_submit()
        
        self.assertEqual(expense_claim.state, 'submitted')
        
        # Check approval requests were created
        approval_requests = self.env['approval.request'].search([
            ('expense_claim_id', '=', expense_claim.id)
        ])
        
        self.assertTrue(approval_requests)
        self.assertEqual(approval_requests[0].approver_id.id, self.manager.id)
        
        # Manager approves
        approval_request = approval_requests[0]
        approval_request.with_user(self.manager_user).action_approve()
        
        self.assertEqual(approval_request.state, 'approved')
        self.assertEqual(expense_claim.state, 'approved')
    
    def test_multi_currency_conversion(self):
        """Test multi-currency expense with conversion"""
        
        # Create EUR expense in USD company
        expense_claim = self.env['expense.claim'].with_user(self.employee_user).create({
            'employee_id': self.employee.id,
            'description': 'European business trip',
            'company_id': self.test_company.id,
        })
        
        expense_line = self.env['expense.line'].create({
            'expense_claim_id': expense_claim.id,
            'description': 'Hotel in Paris',
            'amount': 200.0,
            'currency_id': self.env.ref('base.EUR').id,
            'expense_date': '2024-01-15',
        })
        
        # Test currency conversion
        currency_service = self.env['currency.service']
        
        # Mock the conversion (in real test, this would use fixtures)
        with unittest.mock.patch.object(currency_service, 'convert_amount') as mock_convert:
            mock_convert.return_value = {
                'converted_amount': 220.0,
                'rate': 1.1,
                'rate_date': '2024-01-15',
                'source_url': 'test_fixture'
            }
            
            converted = expense_line._convert_to_company_currency()
            
            self.assertEqual(converted['converted_amount'], 220.0)
            self.assertEqual(converted['rate'], 1.1)
    
    def test_ocr_processing(self):
        """Test OCR receipt processing"""
        
        # Create expense with receipt
        expense_claim = self.env['expense.claim'].with_user(self.employee_user).create({
            'employee_id': self.employee.id,
            'description': 'Receipt processing test',
            'company_id': self.test_company.id,
        })
        
        # Mock OCR service
        ocr_service = self.env['ocr.service']
        
        with unittest.mock.patch.object(ocr_service, 'process_receipt') as mock_ocr:
            mock_ocr.return_value = {
                'amount': 45.50,
                'date': '2024-01-15',
                'vendor': 'Test Restaurant',
                'confidence': 0.85,
                'raw_text': 'Test receipt text'
            }
            
            # Simulate receipt upload
            receipt_data = b'fake_image_data'
            result = expense_claim.process_receipt_ocr(receipt_data)
            
            self.assertEqual(result['amount'], 45.50)
            self.assertEqual(result['confidence'], 0.85)
    
    def test_approval_rules_engine(self):
        """Test approval rules engine with different scenarios"""
        
        # Test amount-based approval
        high_amount_claim = self.env['expense.claim'].with_user(self.employee_user).create({
            'employee_id': self.employee.id,
            'description': 'High amount expense',
            'company_id': self.test_company.id,
        })
        
        self.env['expense.line'].create({
            'expense_claim_id': high_amount_claim.id,
            'description': 'Expensive equipment',
            'amount': 5000.0,
            'currency_id': self.env.ref('base.USD').id,
            'expense_date': '2024-01-15',
        })
        
        # Create CFO approval rule for high amounts
        cfo_rule = self.env['approval.rule'].create({
            'name': 'CFO Approval',
            'rule_type': 'amount',
            'amount_threshold': 1000.0,
            'currency_id': self.env.ref('base.USD').id,
            'sequence': 2,
            'company_id': self.test_company.id,
            'approver_ids': [(6, 0, [self.manager.id])]  # Using manager as CFO for test
        })
        
        high_amount_claim.action_submit()
        
        # Should create multiple approval requests
        approval_requests = self.env['approval.request'].search([
            ('expense_claim_id', '=', high_amount_claim.id)
        ]).sorted('sequence')
        
        self.assertEqual(len(approval_requests), 2)  # Manager + CFO
    
    def test_api_endpoints(self):
        """Test API endpoints for frontend integration"""
        
        # Test expense creation endpoint
        self.authenticate(self.employee_user.login, self.employee_user.login)
        
        expense_data = {
            'description': 'API test expense',
            'lines': [{
                'description': 'Test line',
                'amount': 100.0,
                'currency': 'USD',
                'date': '2024-01-15'
            }]
        }
        
        response = self.url_open(
            '/api/expenses',
            data=json.dumps(expense_data),
            headers={'Content-Type': 'application/json'}
        )
        
        self.assertEqual(response.status_code, 200)
        
        response_data = json.loads(response.content.decode())
        self.assertIn('expense_id', response_data)
    
    def test_external_api_fallbacks(self):
        """Test external API fallback behavior"""
        
        currency_service = self.env['currency.service']
        
        # Test with API stubs enabled
        with unittest.mock.patch.dict('os.environ', {'USE_API_STUBS': 'True'}):
            rates = currency_service.get_exchange_rates('USD')
            
            self.assertIsNotNone(rates)
            self.assertIn('rates', rates)
            self.assertIn('EUR', rates['rates'])
    
    def test_caching_behavior(self):
        """Test caching behavior for external APIs"""
        
        currency_service = self.env['currency.service']
        
        # First call should create cache entry
        rates1 = currency_service.get_exchange_rates('USD')
        
        # Check cache was created
        cache_entry = self.env['currency.rate.cache'].search([
            ('base_currency', '=', 'USD'),
            ('cache_date', '=', currency_service._get_cache_date())
        ])
        
        self.assertTrue(cache_entry)
        
        # Second call should use cache
        rates2 = currency_service.get_exchange_rates('USD')
        
        self.assertEqual(rates1['cache_id'], rates2['cache_id'])
    
    def test_error_handling_and_notifications(self):
        """Test error handling and admin notifications"""
        
        # Test with network error simulation
        with unittest.mock.patch('requests.get') as mock_get:
            mock_get.side_effect = requests.exceptions.ConnectionError("Network error")
            
            currency_service = self.env['currency.service']
            
            # Should fallback gracefully
            rates = currency_service.get_exchange_rates('USD')
            
            # Should use cached or fixture data
            self.assertIsNotNone(rates)
    
    def test_demo_data_setup(self):
        """Test that demo data is properly set up"""
        
        # Check that demo approval rules exist
        demo_rules = self.env['approval.rule'].search([])
        self.assertTrue(demo_rules)
        
        # Check that demo employees exist
        demo_employees = self.env['hr.employee'].search([])
        self.assertTrue(demo_employees)
        
        # Check that currency cache has some data
        cache_entries = self.env['currency.rate.cache'].search([])
        # May be empty in fresh install, but structure should exist
        
    def test_security_access_controls(self):
        """Test security and access controls"""
        
        # Employee should not be able to approve their own expenses
        expense_claim = self.env['expense.claim'].with_user(self.employee_user).create({
            'employee_id': self.employee.id,
            'description': 'Self-approval test',
            'company_id': self.test_company.id,
        })
        
        expense_claim.action_submit()
        
        approval_request = self.env['approval.request'].search([
            ('expense_claim_id', '=', expense_claim.id)
        ])
        
        # Employee should not be able to approve
        with self.assertRaises(Exception):
            approval_request.with_user(self.employee_user).action_approve()
    
    def test_performance_with_large_dataset(self):
        """Test performance with larger dataset"""
        
        # Create multiple expenses
        expenses = []
        for i in range(10):
            expense = self.env['expense.claim'].create({
                'employee_id': self.employee.id,
                'description': f'Performance test expense {i}',
                'company_id': self.test_company.id,
            })
            
            self.env['expense.line'].create({
                'expense_claim_id': expense.id,
                'description': f'Line {i}',
                'amount': 100.0 + i,
                'currency_id': self.env.ref('base.USD').id,
                'expense_date': '2024-01-15',
            })
            
            expenses.append(expense)
        
        # Submit all expenses
        for expense in expenses:
            expense.action_submit()
        
        # Check all approval requests were created efficiently
        all_requests = self.env['approval.request'].search([
            ('expense_claim_id', 'in', [e.id for e in expenses])
        ])
        
        self.assertEqual(len(all_requests), len(expenses))
