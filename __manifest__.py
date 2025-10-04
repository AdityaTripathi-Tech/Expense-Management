{
    'name': 'Smart Expense Management',
    'version': '17.0.1.0.0',
    'category': 'Accounting/Accounting',
    'summary': 'Advanced expense management with multi-currency, OCR, and smart approvals',
    'description': '''
        Smart Expense Management Module
        ===============================
        
        Features:
        - Multi-currency expense tracking with real-time conversion
        - OCR receipt processing (Tesseract + optional Google Vision)
        - Intelligent approval workflows
        - External API integrations with robust fallbacks
        - Comprehensive caching and error handling
        - Production-ready with extensive testing
    ''',
    'author': 'Smart Expense Team',
    'website': 'https://github.com/your-org/smart-expense-management',
    'license': 'LGPL-3',
    'depends': [
        'base',
        'account',
        'hr',
        'mail',
        'web',
    ],
    'external_dependencies': {
        'python': [
            'requests',
            'pytesseract',
            'Pillow',
            'google-cloud-vision',  # optional
        ],
    },
    'data': [
        'security/ir.model.access.csv',
        'data/approval_rules_data.xml',
        'data/currency_cache_data.xml',
        'views/expense_claim_views.xml',
        'views/expense_line_views.xml',
        'views/approval_rule_views.xml',
        'views/approval_request_views.xml',
        'views/res_company_views.xml',
        'views/currency_rate_cache_views.xml',
        'views/menu_views.xml',
    ],
    'assets': {
        'web.assets_backend': [
            'smart_expense_management/static/src/js/approval_graph.js',
            'smart_expense_management/static/src/css/expense_management.css',
        ],
    },
    'demo': [
        'demo/demo_data.xml',
    ],
    'installable': True,
    'auto_install': False,
    'application': True,
    'post_init_hook': '_post_init_hook',
}
