# type: ignore
import logging
from datetime import datetime, timedelta
from odoo import models, fields, api, _
from odoo.exceptions import ValidationError

_logger = logging.getLogger(__name__)


class CurrencyRateCache(models.Model):
    _name = 'currency.rate.cache'
    _description = 'Currency Exchange Rate Cache'
    _order = 'base_currency, rate_date desc'
    _rec_name = 'display_name'

    base_currency = fields.Char(
        string='Base Currency',
        required=True,
        size=3,
        help='3-letter ISO currency code (e.g., USD, EUR)'
    )
    
    rate_date = fields.Date(
        string='Rate Date',
        required=True,
        default=fields.Date.today,
        help='Date when the rates were fetched'
    )
    
    rates_json = fields.Text(
        string='Exchange Rates JSON',
        required=True,
        help='JSON string containing all exchange rates for the base currency'
    )
    
    source_url = fields.Char(
        string='Source URL',
        help='URL from which the rates were fetched'
    )
    
    fetched_at = fields.Datetime(
        string='Fetched At',
        required=True,
        default=fields.Datetime.now,
        help='UTC timestamp when rates were fetched'
    )
    
    raw_rates_hash = fields.Char(
        string='Raw Rates Hash',
        help='Hash of the raw API response for audit purposes'
    )
    
    is_fallback = fields.Boolean(
        string='Is Fallback Data',
        default=False,
        help='True if this data comes from local fallback files'
    )
    
    ttl_hours = fields.Integer(
        string='TTL Hours',
        default=24,
        help='Time-to-live in hours for this cache entry'
    )
    
    expires_at = fields.Datetime(
        string='Expires At',
        compute='_compute_expires_at',
        store=True,
        help='When this cache entry expires'
    )
    
    is_expired = fields.Boolean(
        string='Is Expired',
        compute='_compute_is_expired',
        help='Whether this cache entry has expired'
    )
    
    display_name = fields.Char(
        string='Display Name',
        compute='_compute_display_name'
    )

    _sql_constraints = [
        ('unique_base_date', 'UNIQUE(base_currency, rate_date)', 
         'Only one rate entry per base currency per date is allowed.'),
    ]

    @api.depends('fetched_at', 'ttl_hours')
    def _compute_expires_at(self):
        """Compute expiration timestamp"""
        for record in self:
            if record.fetched_at and record.ttl_hours:
                record.expires_at = record.fetched_at + timedelta(hours=record.ttl_hours)
            else:
                record.expires_at = False

    @api.depends('expires_at')
    def _compute_is_expired(self):
        """Check if cache entry has expired"""
        now = fields.Datetime.now()
        for record in self:
            record.is_expired = record.expires_at and record.expires_at < now

    @api.depends('base_currency', 'rate_date', 'is_fallback')
    def _compute_display_name(self):
        """Compute display name for the record"""
        for record in self:
            fallback_text = " (Fallback)" if record.is_fallback else ""
            record.display_name = f"{record.base_currency} - {record.rate_date}{fallback_text}"

    @api.constrains('base_currency')
    def _check_base_currency_format(self):
        """Validate base currency format"""
        for record in self:
            if not record.base_currency or len(record.base_currency) != 3:
                raise ValidationError(
                    _('Base currency must be a 3-letter ISO code (e.g., USD, EUR)')
                )
            if not record.base_currency.isupper():
                raise ValidationError(
                    _('Base currency must be uppercase (e.g., USD, not usd)')
                )

    @api.constrains('ttl_hours')
    def _check_ttl_hours(self):
        """Validate TTL hours"""
        for record in self:
            if record.ttl_hours < 1:
                raise ValidationError(
                    _('TTL hours must be at least 1 hour')
                )

    @api.model
    def get_cached_rates(self, base_currency, target_date=None):
        """
        Get cached exchange rates for a base currency
        
        Args:
            base_currency (str): 3-letter currency code
            target_date (date, optional): Date to get rates for. Defaults to today.
            
        Returns:
            dict: Exchange rates or None if not found/expired
        """
        if not target_date:
            target_date = fields.Date.today()
            
        # First try exact date match
        cache_entry = self.search([
            ('base_currency', '=', base_currency.upper()),
            ('rate_date', '=', target_date),
            ('is_expired', '=', False)
        ], limit=1)
        
        # If no exact match, try most recent non-expired entry
        if not cache_entry:
            cache_entry = self.search([
                ('base_currency', '=', base_currency.upper()),
                ('rate_date', '<=', target_date),
                ('is_expired', '=', False)
            ], order='rate_date desc', limit=1)
        
        if cache_entry and cache_entry.rates_json:
            try:
                import json
                rates = json.loads(cache_entry.rates_json)
                _logger.debug(f"Retrieved cached rates for {base_currency} from {cache_entry.rate_date}")
                return {
                    'rates': rates,
                    'date': cache_entry.rate_date,
                    'source': 'cache',
                    'is_fallback': cache_entry.is_fallback
                }
            except (json.JSONDecodeError, ValueError) as e:
                _logger.error(f"Failed to parse cached rates JSON: {e}")
                
        return None

    @api.model
    def store_rates(self, base_currency, rates_data, source_url=None, raw_hash=None, is_fallback=False):
        """
        Store exchange rates in cache
        
        Args:
            base_currency (str): 3-letter currency code
            rates_data (dict): Exchange rates data
            source_url (str, optional): Source URL
            raw_hash (str, optional): Hash of raw response
            is_fallback (bool): Whether this is fallback data
            
        Returns:
            currency.rate.cache: Created cache record
        """
        import json
        import os
        
        # Get TTL from environment or use default
        ttl_hours = int(os.getenv('CURRENCY_CACHE_TTL_HOURS', '24'))
        
        # Remove existing entry for today if it exists
        today = fields.Date.today()
        existing = self.search([
            ('base_currency', '=', base_currency.upper()),
            ('rate_date', '=', today)
        ])
        if existing:
            existing.unlink()
        
        # Create new cache entry
        cache_entry = self.create({
            'base_currency': base_currency.upper(),
            'rate_date': today,
            'rates_json': json.dumps(rates_data),
            'source_url': source_url,
            'raw_rates_hash': raw_hash,
            'is_fallback': is_fallback,
            'ttl_hours': ttl_hours,
        })
        
        _logger.info(f"Stored rates for {base_currency} in cache (TTL: {ttl_hours}h)")
        return cache_entry

    @api.model
    def cleanup_expired(self):
        """Remove expired cache entries"""
        expired_entries = self.search([('is_expired', '=', True)])
        count = len(expired_entries)
        
        if expired_entries:
            expired_entries.unlink()
            _logger.info(f"Cleaned up {count} expired currency cache entries")
            
        return count

    @api.model
    def get_cache_stats(self):
        """Get cache statistics for monitoring"""
        total_entries = self.search_count([])
        expired_entries = self.search_count([('is_expired', '=', True)])
        fallback_entries = self.search_count([('is_fallback', '=', True)])
        
        # Get unique currencies
        currencies = self.search([]).mapped('base_currency')
        unique_currencies = len(set(currencies))
        
        return {
            'total_entries': total_entries,
            'expired_entries': expired_entries,
            'fallback_entries': fallback_entries,
            'unique_currencies': unique_currencies,
            'active_entries': total_entries - expired_entries,
        }

    @api.model
    def _init_cache_table(self):
        """Initialize cache table with any required setup"""
        _logger.info("Currency rate cache table initialized")
        
        # Clean up any existing expired entries
        self.cleanup_expired()

    def action_refresh_rates(self):
        """Action to refresh rates for this cache entry"""
        currency_service = self.env['currency.service']
        
        try:
            # Fetch fresh rates
            result = currency_service.get_exchange_rates(self.base_currency, force_refresh=True)
            
            if result:
                return {
                    'type': 'ir.actions.client',
                    'tag': 'display_notification',
                    'params': {
                        'title': _('Rates Refreshed'),
                        'message': _('Successfully refreshed rates for %s') % self.base_currency,
                        'type': 'success',
                    }
                }
            else:
                return {
                    'type': 'ir.actions.client',
                    'tag': 'display_notification',
                    'params': {
                        'title': _('Refresh Failed'),
                        'message': _('Failed to refresh rates for %s') % self.base_currency,
                        'type': 'warning',
                    }
                }
                
        except Exception as e:
            _logger.error(f"Failed to refresh rates: {e}")
            return {
                'type': 'ir.actions.client',
                'tag': 'display_notification',
                'params': {
                    'title': _('Refresh Error'),
                    'message': _('Error refreshing rates: %s') % str(e),
                    'type': 'danger',
                }
            }
