# type: ignore
from . import country_service
from . import currency_service
from . import ocr_service
from . import api
# Smart Expense Management Tests
from . import res_company
from . import expense_claim
from . import expense_line
from . import expense_category
from . import approval_rule
from . import approval_request
from . import currency_rate_cache


from . import models
from . import services
from . import controllers

def _post_init_hook(cr, registry):
    """Post-installation hook to initialize default data"""
    from odoo import api, SUPERUSER_ID
    
    env = api.Environment(cr, SUPERUSER_ID, {})
    
    # Initialize currency cache table if needed
    env['currency.rate.cache']._init_cache_table()
    
    # Load default country-currency mappings
    country_service = env['country.service']
    country_service._load_default_mappings()

