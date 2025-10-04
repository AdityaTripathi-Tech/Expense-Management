# type: ignore
import logging
import json
import os
import hashlib
import time
from datetime import datetime, timedelta
import requests
from odoo import models, api, fields, _
from odoo.exceptions import UserError

_logger = logging.getLogger(__name__)


class CurrencyService(models.AbstractModel):
    _name = 'currency.service'
    _description = 'Currency Exchange Rate Service with Caching and Fallbacks'

    # Rate limiting: simple in-memory cache
    _rate_limit_cache = {}
    _max_requests_per_minute = 30

    @api.model
    def get_exchange_rates(self, base_currency, target_date=None, force_refresh=False):
        """
        Get exchange rates for a base currency with caching and fallbacks
        
        Args:
            base_currency (str): 3-letter currency code (e.g., 'USD')
            target_date (date, optional): Date for rates. Defaults to today.
            force_refresh (bool): Force refresh from API
            
        Returns:
            dict: Exchange rates data with metadata
        """
        base_currency = base_currency.upper()
        
        if not target_date:
            target_date = fields.Date.today()
        
        # Check rate limiting
        if not self._check_rate_limit(base_currency):
            _logger.warning(f"Rate limit exceeded for {base_currency}")
            return self._get_fallback_rates(base_currency, target_date)
        
        # Check if we should use API stubs
        use_stubs = os.getenv('USE_API_STUBS', 'False').lower() == 'true'
        
        if use_stubs:
            _logger.info(f"Using API stubs for currency rates: {base_currency}")
            return self._load_fixture_rates(base_currency)
        
        # Try cache first (unless force refresh)
        if not force_refresh:
            cached_rates = self._get_cached_rates(base_currency, target_date)
            if cached_rates:
                return cached_rates
        
        # Fetch from API with retries
        try:
            rates_data = self._fetch_rates_with_retry(base_currency)
            
            if rates_data:
                # Store in cache
                self._store_rates_in_cache(base_currency, rates_data)
                return rates_data
            else:
                _logger.warning(f"No rates data received for {base_currency}")
                
        except Exception as e:
            _logger.error(f"Failed to fetch rates for {base_currency}: {e}")
        
        # Fallback to cached or fixture data
        return self._get_fallback_rates(base_currency, target_date)

    @api.model
    def convert_amount(self, amount, from_currency, to_currency, rate_date=None):
        """
        Convert amount between currencies
        
        Args:
            amount (float): Amount to convert
            from_currency (str): Source currency code
            to_currency (str): Target currency code
            rate_date (date, optional): Date for conversion rate
            
        Returns:
            dict: Conversion result with metadata
        """
        from_currency = from_currency.upper()
        to_currency = to_currency.upper()
        
        # Same currency - no conversion needed
        if from_currency == to_currency:
            return {
                'converted_amount': amount,
                'exchange_rate': 1.0,
                'from_currency': from_currency,
                'to_currency': to_currency,
                'conversion_date': rate_date or fields.Date.today(),
                'source': 'no_conversion',
                'metadata': {}
            }
        
        try:
            # Get exchange rates for the base currency
            rates_data = self.get_exchange_rates(from_currency, rate_date)
            
            if not rates_data or 'rates' not in rates_data:
                raise UserError(
                    _('Unable to get exchange rates for %s. Please try again later or contact administrator.') 
                    % from_currency
                )
            
            rates = rates_data['rates']
            
            # Check if target currency is available
            if to_currency not in rates:
                raise UserError(
                    _('Exchange rate not available for %s to %s conversion.') 
                    % (from_currency, to_currency)
                )
            
            exchange_rate = rates[to_currency]
            converted_amount = amount * exchange_rate
            
            return {
                'converted_amount': converted_amount,
                'exchange_rate': exchange_rate,
                'from_currency': from_currency,
                'to_currency': to_currency,
                'conversion_date': rates_data.get('date', rate_date or fields.Date.today()),
                'source': rates_data.get('source', 'api'),
                'metadata': {
                    'source_url': rates_data.get('source_url'),
                    'fetched_at': rates_data.get('fetched_at'),
                    'is_fallback': rates_data.get('is_fallback', False),
                    'raw_hash': rates_data.get('raw_hash')
                }
            }
            
        except UserError:
            raise
        except Exception as e:
            _logger.error(f"Currency conversion error: {e}")
            raise UserError(
                _('Currency conversion failed: %s. Please contact administrator.') % str(e)
            )

    @api.model
    def _fetch_rates_with_retry(self, base_currency, max_retries=3):
        """
        Fetch rates from API with exponential backoff retry
        
        Args:
            base_currency (str): Base currency code
            max_retries (int): Maximum retry attempts
            
        Returns:
            dict: Rates data or None
        """
        api_url = os.getenv('EXCHANGE_API_URL', 'https://api.exchangerate-api.com/v4/latest')
        url = f"{api_url}/{base_currency}"
        
        for attempt in range(max_retries + 1):
            try:
                _logger.debug(f"Fetching rates for {base_currency} (attempt {attempt + 1})")
                
                response = requests.get(url, timeout=10)
                
                # Handle rate limiting (429)
                if response.status_code == 429:
                    if attempt < max_retries:
                        wait_time = 2 ** attempt  # Exponential backoff: 1s, 2s, 4s
                        _logger.warning(f"Rate limited (429), waiting {wait_time}s before retry")
                        time.sleep(wait_time)
                        continue
                    else:
                        _logger.error("Rate limit exceeded, no more retries")
                        return None
                
                # Handle server errors (5xx)
                if 500 <= response.status_code < 600:
                    if attempt < max_retries:
                        wait_time = 2 ** attempt
                        _logger.warning(f"Server error ({response.status_code}), waiting {wait_time}s before retry")
                        time.sleep(wait_time)
                        continue
                    else:
                        _logger.error(f"Server error {response.status_code}, no more retries")
                        return None
                
                response.raise_for_status()
                
                # Parse and validate response
                data = response.json()
                validated_data = self._validate_rates_response(data, base_currency)
                
                if validated_data:
                    # Add metadata
                    validated_data.update({
                        'source_url': url,
                        'fetched_at': datetime.utcnow().isoformat(),
                        'raw_hash': hashlib.md5(response.text.encode()).hexdigest(),
                        'source': 'api'
                    })
                    
                    _logger.info(f"Successfully fetched rates for {base_currency}")
                    return validated_data
                else:
                    _logger.error("Invalid response format from API")
                    return None
                
            except requests.exceptions.RequestException as e:
                if attempt < max_retries:
                    wait_time = 2 ** attempt
                    _logger.warning(f"Network error: {e}, waiting {wait_time}s before retry")
                    time.sleep(wait_time)
                    continue
                else:
                    _logger.error(f"Network error after {max_retries} retries: {e}")
                    return None
                    
            except (json.JSONDecodeError, ValueError) as e:
                _logger.error(f"JSON parsing error: {e}")
                return None
                
            except Exception as e:
                _logger.error(f"Unexpected error fetching rates: {e}")
                return None
        
        return None

    @api.model
    def _validate_rates_response(self, data, expected_base):
        """
        Validate API response format and content
        
        Args:
            data (dict): Raw API response
            expected_base (str): Expected base currency
            
        Returns:
            dict: Validated data or None
        """
        try:
            # Check required fields
            if not isinstance(data, dict):
                _logger.error("Response is not a dictionary")
                return None
            
            if 'rates' not in data:
                _logger.error("No 'rates' field in response")
                return None
            
            rates = data['rates']
            if not isinstance(rates, dict):
                _logger.error("'rates' field is not a dictionary")
                return None
            
            # Validate base currency
            base = data.get('base', '').upper()
            if base != expected_base.upper():
                _logger.warning(f"Base currency mismatch: expected {expected_base}, got {base}")
            
            # Validate rate values
            validated_rates = {}
            for currency, rate in rates.items():
                if not isinstance(currency, str) or len(currency) != 3:
                    _logger.warning(f"Invalid currency code: {currency}")
                    continue
                
                if not isinstance(rate, (int, float)) or rate <= 0:
                    _logger.warning(f"Invalid rate for {currency}: {rate}")
                    continue
                
                validated_rates[currency.upper()] = float(rate)
            
            if not validated_rates:
                _logger.error("No valid rates found in response")
                return None
            
            return {
                'base': expected_base.upper(),
                'date': data.get('date', fields.Date.today().isoformat()),
                'rates': validated_rates
            }
            
        except Exception as e:
            _logger.error(f"Error validating rates response: {e}")
            return None

    @api.model
    def _get_cached_rates(self, base_currency, target_date):
        """
        Get rates from cache
        
        Args:
            base_currency (str): Base currency code
            target_date (date): Target date
            
        Returns:
            dict: Cached rates or None
        """
        try:
            cache_model = self.env['currency.rate.cache']
            cached_data = cache_model.get_cached_rates(base_currency, target_date)
            
            if cached_data:
                _logger.debug(f"Using cached rates for {base_currency}")
                return cached_data
                
        except Exception as e:
            _logger.error(f"Error getting cached rates: {e}")
            
        return None

    @api.model
    def _store_rates_in_cache(self, base_currency, rates_data):
        """
        Store rates in cache
        
        Args:
            base_currency (str): Base currency code
            rates_data (dict): Rates data to store
        """
        try:
            cache_model = self.env['currency.rate.cache']
            cache_model.store_rates(
                base_currency=base_currency,
                rates_data=rates_data['rates'],
                source_url=rates_data.get('source_url'),
                raw_hash=rates_data.get('raw_hash'),
                is_fallback=False
            )
            
        except Exception as e:
            _logger.error(f"Error storing rates in cache: {e}")

    @api.model
    def _get_fallback_rates(self, base_currency, target_date):
        """
        Get fallback rates from cache or fixtures
        
        Args:
            base_currency (str): Base currency code
            target_date (date): Target date
            
        Returns:
            dict: Fallback rates or None
        """
        # Try most recent cached rates first
        try:
            cache_model = self.env['currency.rate.cache']
            
            # Get most recent entry (even if expired)
            recent_entry = cache_model.search([
                ('base_currency', '=', base_currency.upper())
            ], order='rate_date desc', limit=1)
            
            if recent_entry and recent_entry.rates_json:
                rates = json.loads(recent_entry.rates_json)
                _logger.info(f"Using recent cached rates for {base_currency} from {recent_entry.rate_date}")
                
                return {
                    'rates': rates,
                    'date': recent_entry.rate_date,
                    'source': 'fallback_cache',
                    'is_fallback': True,
                    'metadata': {
                        'original_fetch_date': recent_entry.rate_date,
                        'fallback_reason': 'api_unavailable'
                    }
                }
                
        except Exception as e:
            _logger.error(f"Error getting fallback cached rates: {e}")
        
        # Try fixture data
        fixture_rates = self._load_fixture_rates(base_currency)
        if fixture_rates:
            return fixture_rates
        
        # Last resort: mark as conversion pending
        _logger.error(f"No fallback rates available for {base_currency}")
        return None

    @api.model
    def _load_fixture_rates(self, base_currency):
        """
        Load rates from fixture file
        
        Args:
            base_currency (str): Base currency code
            
        Returns:
            dict: Fixture rates or None
        """
        try:
            fixture_filename = f'mock_rates_{base_currency.upper()}.json'
            fixture_path = self._get_fixture_path(fixture_filename)
            
            if os.path.exists(fixture_path):
                with open(fixture_path, 'r', encoding='utf-8') as f:
                    fixture_data = json.load(f)
                
                validated_data = self._validate_rates_response(fixture_data, base_currency)
                
                if validated_data:
                    validated_data.update({
                        'source': 'fixture',
                        'is_fallback': True,
                        'metadata': {
                            'fixture_file': fixture_filename,
                            'fallback_reason': 'using_stubs'
                        }
                    })
                    
                    _logger.info(f"Loaded fixture rates for {base_currency}")
                    return validated_data
            else:
                _logger.warning(f"Fixture file not found: {fixture_path}")
                
        except Exception as e:
            _logger.error(f"Error loading fixture rates: {e}")
        
        # Return minimal fallback rates
        return self._get_minimal_fallback_rates(base_currency)

    @api.model
    def _get_minimal_fallback_rates(self, base_currency):
        """
        Get minimal hardcoded rates as last resort
        
        Args:
            base_currency (str): Base currency code
            
        Returns:
            dict: Minimal rates data
        """
        # Hardcoded rates (approximate, for emergency fallback only)
        fallback_rates = {
            'USD': {'EUR': 0.85, 'GBP': 0.73, 'INR': 83.0, 'JPY': 110.0, 'CAD': 1.25, 'AUD': 1.35},
            'EUR': {'USD': 1.18, 'GBP': 0.86, 'INR': 98.0, 'JPY': 130.0, 'CAD': 1.47, 'AUD': 1.59},
            'GBP': {'USD': 1.37, 'EUR': 1.16, 'INR': 114.0, 'JPY': 151.0, 'CAD': 1.71, 'AUD': 1.85},
            'INR': {'USD': 0.012, 'EUR': 0.010, 'GBP': 0.009, 'JPY': 1.33, 'CAD': 0.015, 'AUD': 0.016},
        }
        
        base_rates = fallback_rates.get(base_currency.upper(), {})
        
        if base_rates:
            _logger.warning(f"Using minimal fallback rates for {base_currency}")
            return {
                'base': base_currency.upper(),
                'date': fields.Date.today().isoformat(),
                'rates': base_rates,
                'source': 'minimal_fallback',
                'is_fallback': True,
                'metadata': {
                    'fallback_reason': 'no_other_source_available',
                    'warning': 'These are approximate rates for emergency use only'
                }
            }
        
        return None

    @api.model
    def _get_fixture_path(self, filename):
        """Get path to fixture file"""
        module_path = os.path.dirname(os.path.dirname(__file__))
        return os.path.join(module_path, 'tests', 'fixtures', filename)

    @api.model
    def _check_rate_limit(self, base_currency):
        """
        Simple rate limiting check
        
        Args:
            base_currency (str): Currency being requested
            
        Returns:
            bool: True if request is allowed
        """
        now = time.time()
        minute_ago = now - 60
        
        # Clean old entries
        self._rate_limit_cache = {
            key: timestamps for key, timestamps in self._rate_limit_cache.items()
            if any(ts > minute_ago for ts in timestamps)
        }
        
        # Check current currency
        if base_currency not in self._rate_limit_cache:
            self._rate_limit_cache[base_currency] = []
        
        # Remove old timestamps for this currency
        self._rate_limit_cache[base_currency] = [
            ts for ts in self._rate_limit_cache[base_currency] if ts > minute_ago
        ]
        
        # Check if limit exceeded
        if len(self._rate_limit_cache[base_currency]) >= self._max_requests_per_minute:
            return False
        
        # Add current request
        self._rate_limit_cache[base_currency].append(now)
        return True

    @api.model
    def get_cache_statistics(self):
        """
        Get currency cache statistics for monitoring
        
        Returns:
            dict: Cache statistics
        """
        try:
            cache_model = self.env['currency.rate.cache']
            return cache_model.get_cache_stats()
        except Exception as e:
            _logger.error(f"Error getting cache statistics: {e}")
            return {'error': str(e)}

    @api.model
    def cleanup_expired_cache(self):
        """
        Clean up expired cache entries
        
        Returns:
            int: Number of entries cleaned up
        """
        try:
            cache_model = self.env['currency.rate.cache']
            return cache_model.cleanup_expired()
        except Exception as e:
            _logger.error(f"Error cleaning up cache: {e}")
            return 0
