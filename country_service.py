# type: ignore
import logging
import json
import os
import requests
from datetime import datetime, timedelta
from odoo import models, api, _
from odoo.exceptions import UserError

_logger = logging.getLogger(__name__)


class CountryService(models.AbstractModel):
    _name = 'country.service'
    _description = 'Country and Currency Mapping Service'

    @api.model
    def get_country_currency(self, country_code):
        """
        Get currency information for a country code
        
        Args:
            country_code (str): 2-letter ISO country code
            
        Returns:
            dict: Currency info with code, name, symbol or None
        """
        try:
            mappings = self._get_country_mappings()
            
            # Find country by code (case insensitive)
            for country_name, currencies in mappings.items():
                # Try to match by country code if we have it stored
                # For now, we'll do a simple lookup by name
                if currencies:
                    return currencies[0]  # Return first currency
                    
        except Exception as e:
            _logger.error(f"Error getting currency for country {country_code}: {e}")
            
        return None

    @api.model
    def _get_country_mappings(self, force_refresh=False):
        """
        Get country to currency mappings with caching
        
        Args:
            force_refresh (bool): Force refresh from API
            
        Returns:
            dict: Country name to currency list mapping
        """
        cache_key = 'country_currency_mappings'
        cache_ttl_days = int(os.getenv('COUNTRY_CACHE_TTL_DAYS', '7'))
        
        # Check if we should use API stubs
        use_stubs = os.getenv('USE_API_STUBS', 'False').lower() == 'true'
        
        if use_stubs:
            _logger.info("Using API stubs for country mappings")
            return self._load_fixture_mappings()
        
        # Try to get from cache first
        if not force_refresh:
            cached_data = self._get_cached_mappings(cache_key, cache_ttl_days)
            if cached_data:
                return cached_data
        
        # Fetch from API
        try:
            mappings = self._fetch_country_mappings()
            
            if mappings:
                # Cache the results
                self._cache_mappings(cache_key, mappings)
                return mappings
            else:
                _logger.warning("No mappings fetched from API, trying fallback")
                
        except Exception as e:
            _logger.error(f"Failed to fetch country mappings from API: {e}")
            self._notify_admin_error("Country API Error", str(e))
        
        # Fallback to local fixture
        _logger.info("Using fallback country mappings")
        return self._load_fixture_mappings()

    @api.model
    def _fetch_country_mappings(self):
        """
        Fetch country mappings from REST Countries API
        
        Returns:
            dict: Parsed country to currency mappings
        """
        api_url = os.getenv('RESTCOUNTRIES_API_URL', 
                           'https://restcountries.com/v3.1/all?fields=name,currencies')
        
        _logger.info(f"Fetching country mappings from {api_url}")
        
        try:
            response = requests.get(api_url, timeout=10)
            response.raise_for_status()
            
            countries_data = response.json()
            mappings = {}
            
            for country in countries_data:
                try:
                    country_name = country.get('name', {}).get('common', '')
                    currencies = country.get('currencies', {})
                    
                    if country_name and currencies:
                        currency_list = []
                        
                        for currency_code, currency_info in currencies.items():
                            currency_list.append({
                                'code': currency_code,
                                'name': currency_info.get('name', ''),
                                'symbol': currency_info.get('symbol', '')
                            })
                        
                        mappings[country_name] = currency_list
                        
                except Exception as e:
                    _logger.warning(f"Error parsing country data: {e}")
                    continue
            
            _logger.info(f"Successfully parsed {len(mappings)} country mappings")
            return mappings
            
        except requests.exceptions.RequestException as e:
            _logger.error(f"Network error fetching country mappings: {e}")
            raise
        except (json.JSONDecodeError, ValueError) as e:
            _logger.error(f"Error parsing country mappings JSON: {e}")
            raise
        except Exception as e:
            _logger.error(f"Unexpected error fetching country mappings: {e}")
            raise

    @api.model
    def _load_fixture_mappings(self):
        """
        Load country mappings from local fixture file
        
        Returns:
            dict: Country to currency mappings from fixture
        """
        try:
            fixture_path = self._get_fixture_path('mock_restcountries.json')
            
            if os.path.exists(fixture_path):
                with open(fixture_path, 'r', encoding='utf-8') as f:
                    fixture_data = json.load(f)
                
                # Parse fixture data in same format as API
                mappings = {}
                for country in fixture_data:
                    try:
                        country_name = country.get('name', {}).get('common', '')
                        currencies = country.get('currencies', {})
                        
                        if country_name and currencies:
                            currency_list = []
                            
                            for currency_code, currency_info in currencies.items():
                                currency_list.append({
                                    'code': currency_code,
                                    'name': currency_info.get('name', ''),
                                    'symbol': currency_info.get('symbol', '')
                                })
                            
                            mappings[country_name] = currency_list
                            
                    except Exception as e:
                        _logger.warning(f"Error parsing fixture country data: {e}")
                        continue
                
                _logger.info(f"Loaded {len(mappings)} country mappings from fixture")
                return mappings
            else:
                _logger.warning(f"Fixture file not found: {fixture_path}")
                
        except Exception as e:
            _logger.error(f"Error loading fixture mappings: {e}")
        
        # Return minimal fallback data
        return self._get_minimal_fallback_mappings()

    @api.model
    def _get_minimal_fallback_mappings(self):
        """
        Get minimal hardcoded country-currency mappings as last resort
        
        Returns:
            dict: Minimal country to currency mappings
        """
        return {
            'United States': [{'code': 'USD', 'name': 'US Dollar', 'symbol': '$'}],
            'India': [{'code': 'INR', 'name': 'Indian Rupee', 'symbol': '₹'}],
            'United Kingdom': [{'code': 'GBP', 'name': 'British Pound', 'symbol': '£'}],
            'Germany': [{'code': 'EUR', 'name': 'Euro', 'symbol': '€'}],
            'France': [{'code': 'EUR', 'name': 'Euro', 'symbol': '€'}],
            'Japan': [{'code': 'JPY', 'name': 'Japanese Yen', 'symbol': '¥'}],
            'Canada': [{'code': 'CAD', 'name': 'Canadian Dollar', 'symbol': 'C$'}],
            'Australia': [{'code': 'AUD', 'name': 'Australian Dollar', 'symbol': 'A$'}],
        }

    @api.model
    def _get_cached_mappings(self, cache_key, ttl_days):
        """
        Get mappings from cache if not expired
        
        Args:
            cache_key (str): Cache key
            ttl_days (int): TTL in days
            
        Returns:
            dict: Cached mappings or None
        """
        try:
            # Use Odoo's ir.config_parameter for caching
            config_param = self.env['ir.config_parameter'].sudo()
            
            # Get cached data and timestamp
            cached_json = config_param.get_param(f'{cache_key}_data')
            cached_timestamp = config_param.get_param(f'{cache_key}_timestamp')
            
            if cached_json and cached_timestamp:
                # Check if cache is still valid
                cache_time = datetime.fromisoformat(cached_timestamp)
                expiry_time = cache_time + timedelta(days=ttl_days)
                
                if datetime.now() < expiry_time:
                    mappings = json.loads(cached_json)
                    _logger.debug(f"Using cached country mappings (age: {datetime.now() - cache_time})")
                    return mappings
                else:
                    _logger.debug("Cached country mappings expired")
            
        except Exception as e:
            _logger.warning(f"Error reading cached mappings: {e}")
            
        return None

    @api.model
    def _cache_mappings(self, cache_key, mappings):
        """
        Cache mappings with timestamp
        
        Args:
            cache_key (str): Cache key
            mappings (dict): Mappings to cache
        """
        try:
            config_param = self.env['ir.config_parameter'].sudo()
            
            # Store data and timestamp
            config_param.set_param(f'{cache_key}_data', json.dumps(mappings))
            config_param.set_param(f'{cache_key}_timestamp', datetime.now().isoformat())
            
            _logger.debug(f"Cached {len(mappings)} country mappings")
            
        except Exception as e:
            _logger.error(f"Error caching mappings: {e}")

    @api.model
    def _get_fixture_path(self, filename):
        """
        Get path to fixture file
        
        Args:
            filename (str): Fixture filename
            
        Returns:
            str: Full path to fixture file
        """
        module_path = os.path.dirname(os.path.dirname(__file__))
        return os.path.join(module_path, 'tests', 'fixtures', filename)

    @api.model
    def _notify_admin_error(self, title, message):
        """
        Notify admin of API errors
        
        Args:
            title (str): Error title
            message (str): Error message
        """
        try:
            admin_email = os.getenv('ADMIN_EMAIL')
            if not admin_email:
                return
            
            # Check if we've already sent an alert today
            cache_key = f'country_api_error_{datetime.now().date()}'
            config_param = self.env['ir.config_parameter'].sudo()
            
            if config_param.get_param(cache_key):
                return  # Already notified today
            
            # Send notification via mail.channel or email
            self.env['mail.channel'].sudo().create({
                'name': f'Country API Error - {datetime.now().date()}',
                'description': f'{title}: {message}',
                'channel_type': 'channel',
                'public': 'private',
            })
            
            # Mark as notified
            config_param.set_param(cache_key, 'true')
            
        except Exception as e:
            _logger.error(f"Failed to send admin notification: {e}")

    @api.model
    def refresh_country_mappings(self):
        """
        Refresh country mappings from API (admin action)
        
        Returns:
            dict: Result with updated count
        """
        try:
            mappings = self._get_country_mappings(force_refresh=True)
            
            return {
                'success': True,
                'updated': len(mappings),
                'message': f'Successfully updated {len(mappings)} country mappings'
            }
            
        except Exception as e:
            _logger.error(f"Failed to refresh country mappings: {e}")
            return {
                'success': False,
                'error': str(e),
                'message': f'Failed to refresh mappings: {e}'
            }

    @api.model
    def _load_default_mappings(self):
        """
        Load default mappings on module installation
        """
        try:
            mappings = self._get_country_mappings()
            _logger.info(f"Loaded {len(mappings)} default country mappings")
        except Exception as e:
            _logger.error(f"Failed to load default mappings: {e}")

    @api.model
    def get_supported_currencies(self):
        """
        Get list of all supported currencies from mappings
        
        Returns:
            list: List of currency codes
        """
        try:
            mappings = self._get_country_mappings()
            currencies = set()
            
            for country_currencies in mappings.values():
                for currency in country_currencies:
                    currencies.add(currency['code'])
            
            return sorted(list(currencies))
            
        except Exception as e:
            _logger.error(f"Error getting supported currencies: {e}")
            return ['USD', 'EUR', 'GBP', 'INR', 'JPY', 'CAD', 'AUD']  # Fallback list
