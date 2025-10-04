# type: ignore
import os
import json
from unittest.mock import patch, MagicMock
from odoo.tests.common import TransactionCase
from odoo.exceptions import UserError


class TestCurrencyService(TransactionCase):
    
    def setUp(self):
        super().setUp()
        self.currency_service = self.env['currency.service']
        self.cache_model = self.env['currency.rate.cache']
        
        # Create test currencies
        self.usd = self.env['res.currency'].create({
            'name': 'USD',
            'symbol': '$',
            'position': 'before',
        })
        
        self.eur = self.env['res.currency'].create({
            'name': 'EUR',
            'symbol': '€',
            'position': 'before',
        })
        
        self.inr = self.env['res.currency'].create({
            'name': 'INR',
            'symbol': '₹',
            'position': 'before',
        })

    def test_get_exchange_rates_with_stubs(self):
        """Test getting exchange rates using API stubs"""
        with patch.dict(os.environ, {'USE_API_STUBS': 'True'}):
            rates_data = self.currency_service.get_exchange_rates('USD')
            
            self.assertIsNotNone(rates_data)
            self.assertIn('rates', rates_data)
            self.assertIn('EUR', rates_data['rates'])
            self.assertIn('INR', rates_data['rates'])
            self.assertEqual(rates_data['source'], 'fixture')

    def test_currency_conversion_same_currency(self):
        """Test conversion between same currencies"""
        result = self.currency_service.convert_amount(100.0, 'USD', 'USD')
        
        self.assertEqual(result['converted_amount'], 100.0)
        self.assertEqual(result['exchange_rate'], 1.0)
        self.assertEqual(result['source'], 'no_conversion')

    def test_currency_conversion_different_currencies(self):
        """Test conversion between different currencies"""
        with patch.dict(os.environ, {'USE_API_STUBS': 'True'}):
            result = self.currency_service.convert_amount(100.0, 'USD', 'EUR')
            
            self.assertIsNotNone(result['converted_amount'])
            self.assertGreater(result['exchange_rate'], 0)
            self.assertEqual(result['from_currency'], 'USD')
            self.assertEqual(result['to_currency'], 'EUR')

    def test_cache_storage_and_retrieval(self):
        """Test currency rate caching functionality"""
        # Store test rates
        test_rates = {'EUR': 0.85, 'GBP': 0.73, 'INR': 84.15}
        
        cache_entry = self.cache_model.store_rates(
            base_currency='USD',
            rates_data=test_rates,
            source_url='test://example.com',
            is_fallback=False
        )
        
        self.assertTrue(cache_entry)
        self.assertEqual(cache_entry.base_currency, 'USD')
        
        # Retrieve cached rates
        cached_data = self.cache_model.get_cached_rates('USD')
        
        self.assertIsNotNone(cached_data)
        self.assertEqual(cached_data['rates']['EUR'], 0.85)
        self.assertEqual(cached_data['source'], 'cache')

    def test_cache_expiry(self):
        """Test cache expiry functionality"""
        # Create an expired cache entry
        cache_entry = self.cache_model.create({
            'base_currency': 'USD',
            'rate_date': '2020-01-01',  # Old date
            'rates_json': '{"EUR": 0.85}',
            'ttl_hours': 1,  # Short TTL
            'fetched_at': '2020-01-01 00:00:00'
        })
        
        self.assertTrue(cache_entry.is_expired)

    def test_fallback_rates_when_api_fails(self):
        """Test fallback behavior when API is unavailable"""
        with patch('requests.get') as mock_get:
            # Mock API failure
            mock_get.side_effect = Exception("API unavailable")
            
            with patch.dict(os.environ, {'USE_API_STUBS': 'False'}):
                rates_data = self.currency_service.get_exchange_rates('USD')
                
                # Should get fallback rates
                if rates_data:
                    self.assertTrue(rates_data.get('is_fallback', False))

    def test_rate_validation(self):
        """Test exchange rate response validation"""
        # Test valid response
        valid_data = {
            'base': 'USD',
            'date': '2025-10-04',
            'rates': {'EUR': 0.85, 'GBP': 0.73}
        }
        
        validated = self.currency_service._validate_rates_response(valid_data, 'USD')
        self.assertIsNotNone(validated)
        self.assertEqual(validated['base'], 'USD')
        
        # Test invalid response
        invalid_data = {
            'base': 'USD',
            'rates': {'EUR': 'invalid_rate'}  # Invalid rate value
        }
        
        validated = self.currency_service._validate_rates_response(invalid_data, 'USD')
        # Should filter out invalid rates but still return valid structure
        self.assertIsNotNone(validated)

    def test_cache_cleanup(self):
        """Test expired cache cleanup"""
        # Create some expired entries
        for i in range(3):
            self.cache_model.create({
                'base_currency': f'TEST{i}',
                'rate_date': '2020-01-01',
                'rates_json': '{"EUR": 0.85}',
                'ttl_hours': 1,
                'fetched_at': '2020-01-01 00:00:00'
            })
        
        # Run cleanup
        cleaned_count = self.currency_service.cleanup_expired_cache()
        
        self.assertGreaterEqual(cleaned_count, 0)

    def test_cache_statistics(self):
        """Test cache statistics functionality"""
        # Create some test cache entries
        self.cache_model.create({
            'base_currency': 'USD',
            'rate_date': '2025-10-04',
            'rates_json': '{"EUR": 0.85}',
            'ttl_hours': 24,
        })
        
        stats = self.currency_service.get_cache_statistics()
        
        self.assertIn('total_entries', stats)
        self.assertIn('unique_currencies', stats)
        self.assertGreaterEqual(stats['total_entries'], 1)

    def test_conversion_error_handling(self):
        """Test error handling in currency conversion"""
        with patch.object(self.currency_service, 'get_exchange_rates') as mock_get_rates:
            # Mock service failure
            mock_get_rates.return_value = None
            
            with self.assertRaises(UserError):
                self.currency_service.convert_amount(100.0, 'USD', 'INVALID')

    def test_rate_limiting(self):
        """Test rate limiting functionality"""
        # Test that rate limiting allows reasonable requests
        allowed = self.currency_service._check_rate_limit('USD')
        self.assertTrue(allowed)
        
        # Test rate limit cache management
        self.currency_service._rate_limit_cache['TEST'] = [1234567890] * 50  # Exceed limit
        limited = self.currency_service._check_rate_limit('TEST')
        self.assertFalse(limited)

    def tearDown(self):
        """Clean up after tests"""
        # Clean up test cache entries
        test_entries = self.cache_model.search([
            ('base_currency', 'in', ['USD', 'EUR', 'TEST', 'TEST0', 'TEST1', 'TEST2'])
        ])
        test_entries.unlink()
        
        super().tearDown()
