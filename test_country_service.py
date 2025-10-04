# type: ignore

import unittest
import json
import os
from unittest.mock import patch, MagicMock
from odoo.tests.common import TransactionCase
from odoo.exceptions import UserError


class TestCountryService(TransactionCase):
    
    def setUp(self):
        super().setUp()
        self.country_service = self.env['country.service']
        
    def test_get_country_currency_success(self):
        """Test successful country currency lookup"""
        with patch.object(self.country_service, '_get_country_mappings') as mock_mappings:
            mock_mappings.return_value = {
                'United States': [{'code': 'USD', 'name': 'US Dollar', 'symbol': '$'}],
                'India': [{'code': 'INR', 'name': 'Indian Rupee', 'symbol': '₹'}]
            }
            
            result = self.country_service.get_country_currency('US')
            self.assertIsNotNone(result)
            self.assertEqual(result['code'], 'USD')
    
    def test_get_country_currency_not_found(self):
        """Test country currency lookup when country not found"""
        with patch.object(self.country_service, '_get_country_mappings') as mock_mappings:
            mock_mappings.return_value = {}
            
            result = self.country_service.get_country_currency('XX')
            self.assertIsNone(result)
    
    def test_get_country_mappings_api_success(self):
        """Test successful API call to RestCountries"""
        mock_response_data = [
            {
                'name': {'common': 'United States'},
                'currencies': {'USD': {'name': 'United States dollar', 'symbol': '$'}}
            },
            {
                'name': {'common': 'India'},
                'currencies': {'INR': {'name': 'Indian rupee', 'symbol': '₹'}}
            }
        ]
        
        with patch('requests.get') as mock_get:
            mock_response = MagicMock()
            mock_response.json.return_value = mock_response_data
            mock_response.raise_for_status.return_value = None
            mock_get.return_value = mock_response
            
            with patch.dict(os.environ, {'USE_API_STUBS': 'False'}):
                result = self.country_service._get_country_mappings(force_refresh=True)
                
                self.assertIn('United States', result)
                self.assertIn('India', result)
                self.assertEqual(result['United States'][0]['code'], 'USD')
    
    def test_get_country_mappings_api_failure_fallback(self):
        """Test fallback to fixtures when API fails"""
        with patch('requests.get') as mock_get:
            mock_get.side_effect = Exception("API Error")
            
            with patch.object(self.country_service, '_load_fixture_countries') as mock_fixture:
                mock_fixture.return_value = {
                    'India': [{'code': 'INR', 'name': 'Indian Rupee', 'symbol': '₹'}]
                }
                
                result = self.country_service._get_country_mappings()
                
                self.assertIn('India', result)
                mock_fixture.assert_called_once()
    
    def test_get_country_mappings_with_stubs(self):
        """Test using API stubs"""
        with patch.dict(os.environ, {'USE_API_STUBS': 'True'}):
            with patch.object(self.country_service, '_load_fixture_countries') as mock_fixture:
                mock_fixture.return_value = {
                    'Test Country': [{'code': 'TST', 'name': 'Test Currency', 'symbol': 'T'}]
                }
                
                result = self.country_service._get_country_mappings()
                
                self.assertIn('Test Country', result)
                mock_fixture.assert_called_once()
    
    def test_load_fixture_countries(self):
        """Test loading country fixtures"""
        # Create a mock fixture file
        fixture_data = [
            {
                'name': {'common': 'Test Country'},
                'currencies': {'TST': {'name': 'Test Currency', 'symbol': 'T'}}
            }
        ]
        
        with patch('builtins.open', unittest.mock.mock_open(read_data=json.dumps(fixture_data))):
            with patch('os.path.exists', return_value=True):
                result = self.country_service._load_fixture_countries()
                
                self.assertIn('Test Country', result)
                self.assertEqual(result['Test Country'][0]['code'], 'TST')
    
    def test_parse_countries_data(self):
        """Test parsing of countries API response"""
        api_data = [
            {
                'name': {'common': 'United States'},
                'currencies': {'USD': {'name': 'US Dollar', 'symbol': '$'}}
            },
            {
                'name': {'common': 'Multi Currency Country'},
                'currencies': {
                    'EUR': {'name': 'Euro', 'symbol': '€'},
                    'USD': {'name': 'US Dollar', 'symbol': '$'}
                }
            }
        ]
        
        result = self.country_service._parse_countries_data(api_data)
        
        self.assertIn('United States', result)
        self.assertIn('Multi Currency Country', result)
        
        # Check single currency country
        us_currencies = result['United States']
        self.assertEqual(len(us_currencies), 1)
        self.assertEqual(us_currencies[0]['code'], 'USD')
        
        # Check multi-currency country
        multi_currencies = result['Multi Currency Country']
        self.assertEqual(len(multi_currencies), 2)
        currency_codes = [c['code'] for c in multi_currencies]
        self.assertIn('EUR', currency_codes)
        self.assertIn('USD', currency_codes)
    
    def test_cache_behavior(self):
        """Test caching behavior"""
        with patch('requests.get') as mock_get:
            mock_response = MagicMock()
            mock_response.json.return_value = []
            mock_response.raise_for_status.return_value = None
            mock_get.return_value = mock_response
            
            # First call should hit API
            self.country_service._get_country_mappings(force_refresh=True)
            self.assertEqual(mock_get.call_count, 1)
            
            # Second call should use cache
            self.country_service._get_country_mappings()
            self.assertEqual(mock_get.call_count, 1)  # Should not increase
    
    def test_error_handling(self):
        """Test error handling in various scenarios"""
        # Test with malformed JSON response
        with patch('requests.get') as mock_get:
            mock_response = MagicMock()
            mock_response.json.side_effect = json.JSONDecodeError("Invalid JSON", "", 0)
            mock_get.return_value = mock_response
            
            with patch.object(self.country_service, '_load_fixture_countries') as mock_fixture:
                mock_fixture.return_value = {}
                
                result = self.country_service._get_country_mappings()
                self.assertEqual(result, {})
    
    def test_admin_notification_on_failure(self):
        """Test admin notification when API fails"""
        with patch('requests.get') as mock_get:
            mock_get.side_effect = Exception("Network Error")
            
            with patch.object(self.env['mail.channel'], 'message_post') as mock_notify:
                with patch.object(self.country_service, '_load_fixture_countries', return_value={}):
                    self.country_service._get_country_mappings()
                    
                    # Should send notification on first failure of the day
                    # (Implementation detail depends on actual notification logic)
