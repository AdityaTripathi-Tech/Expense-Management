# Smart Expense Management System

Team Name- Binary Brothers 

Team Leader-Anand Singh                      Email-anands9676@gmail.com                      Graduation year - 2026      contact-9044131372

Team Member1 - Aditya Tripathi               Email-tripathi.aditya384@gmail.com              Graduation Year- 2027       contact-6307273997

Problem statement- Expense Management

Reviewer name - Aman Patel (ampa)

Video presentation link-https://drive.google.com/drive/folders/1otmCd1wIr91M3VPJegzoQvTVMDYjc9-v

A production-ready Odoo module for intelligent expense management with multi-currency support, OCR receipt processing, and smart approval workflows.

## 🚀 Features

### Core Functionality
- **Multi-currency Expense Tracking** with real-time conversion
- **OCR Receipt Processing** (Tesseract + optional Google Vision)
- **Intelligent Approval Workflows** with configurable rules
- **Robust API Integrations** with fallback mechanisms
- **Comprehensive Caching** and error handling
- **Production-ready** with extensive testing

### External API Integrations

#### 1. Country → Currency Mapping
- **Endpoint**: `https://restcountries.com/v3.1/all?fields=name,currencies`
- **Usage**: Automatic currency detection during company onboarding
- **Fallback**: Local static JSON file when API unavailable
- **Caching**: 7 days TTL with automatic refresh

#### 2. Currency Conversion
- **Endpoint**: `https://api.exchangerate-api.com/v4/latest/{BASE_CURRENCY}`
- **Usage**: Real-time currency conversion for expense submissions
- **Fallback**: Cached rates → Local fixtures → Manual review
- **Retry Logic**: Exponential backoff (1s, 2s, 4s) on 429/5xx errors
- **Caching**: Daily rates with configurable TTL

#### 3. OCR Processing
- **Primary**: Google Vision API (configurable)
- **Fallback**: Tesseract OCR
- **Features**: Confidence scoring, field extraction, low-confidence flagging

## 📋 UI/UX Reference

The system follows the design patterns outlined in this Excalidraw mockup:
**https://link.excalidraw.com/l/65VNwvy7c4X/4WSLZDTrhkA**

## 🛠 Installation & Setup

### Prerequisites
- Docker & Docker Compose
- Python 3.8+
- PostgreSQL 12+

### Quick Start

1. **Clone and Setup Environment**
   ```bash
   git clone <repository-url>
   cd smart-expense-management
   cp .env.example .env
   # Edit .env with your configuration
   ```

2. **Start with Docker**
   ```bash
   docker-compose up --build
   ```

3. **Access the Application**
   - Odoo: http://localhost:8069
   - Admin credentials: admin/admin
   - Database: smart_expense_db

### Manual Installation

1. **Install Dependencies**
   ```bash
   pip install requests pytesseract Pillow google-cloud-vision
   ```

2. **Configure Odoo**
   ```bash
   # Add to odoo.conf
   addons_path = /path/to/smart_expense_management
   ```

3. **Install Module**
   ```bash
   odoo -i smart_expense_management -d your_database
   ```

## 🔧 Configuration

### Environment Variables

Create `.env` file from `.env.example`:

```bash
# External API Configuration
EXCHANGE_API_URL=https://api.exchangerate-api.com/v4/latest
RESTCOUNTRIES_API_URL=https://restcountries.com/v3.1/all?fields=name,currencies

# Development & Testing
USE_API_STUBS=False  # Set to True for offline demo
DEBUG_MODE=False

# OCR Configuration
GOOGLE_VISION_API_KEY=your_api_key_here
OCR_CONFIDENCE_THRESHOLD=0.6

# Caching Configuration
CURRENCY_CACHE_TTL_HOURS=24
COUNTRY_CACHE_TTL_DAYS=7

# Notifications
ADMIN_EMAIL=admin@example.com
```

### Company Settings

Navigate to **Smart Expenses > Configuration > Company Settings**:

1. **Approval Limits**
   - Auto-approve limit: $100
   - Manager approval limit: $1,000
   - CFO approval required: $5,000+

2. **Currency Settings**
   - Default expense currency
   - Enable automatic conversion

3. **OCR Settings**
   - Enable OCR processing
   - Confidence threshold (0.6 recommended)
   - Google Vision API key

## 🔌 API Integration Examples

### Sample API Calls

#### 1. REST Countries API
```bash
curl -s 'https://restcountries.com/v3.1/all?fields=name,currencies' | jq '.[] | {name: .name.common, currencies: .currencies}'
```

**Sample Response (India):**
```json
{
  "name": "India",
  "currencies": {
    "INR": {
      "name": "Indian rupee",
      "symbol": "₹"
    }
  }
}
```

#### 2. Exchange Rate API
```bash
curl -s 'https://api.exchangerate-api.com/v4/latest/USD'
```

**Expected Schema:**
```json
{
  "base": "USD",
  "date": "2025-10-04",
  "rates": {
    "INR": 84.15,
    "EUR": 0.94,
    "GBP": 0.73,
    "JPY": 149.50
  }
}
```

### Fallback Policy

#### Network Failures
1. **REST Countries API Down**
   - Log warning with details
   - Use local fixture file
   - Notify admin (once per day)

2. **Exchange Rate API 429 (Rate Limited)**
   - Retry with exponential backoff: 1s → 2s → 4s
   - Use latest cached rates if retries fail
   - Mark expense as `conversion_pending` if no cache
   - Flag for manual review

3. **OCR Low Confidence (< 0.6)**
   - Pre-fill extracted fields
   - Set `ocr_confidence_low=True`
   - Require employee verification before submit

4. **API Schema Changes**
   - Validate response structure
   - Log error with sample payload
   - Send admin alert
   - Fall back to safe defaults

## 🧪 Testing

### Run Tests
```bash
# Unit tests
pytest smart_expense_management/tests/

# Odoo tests
odoo -i smart_expense_management --test-enable --stop-after-init

# Integration tests with mock server
docker-compose --profile testing up
```

### Mock Server for Testing
```bash
# Start mock API server
python mock_server.py

# Test endpoints
curl http://localhost:8080/health
curl http://localhost:8080/v3.1/all?fields=name,currencies
curl http://localhost:8080/v4/latest/USD
```

### Demo Mode

For offline demonstrations:

1. **Enable API Stubs**
   ```bash
   export USE_API_STUBS=True
   # or set in .env file
   ```

2. **Use Demo Data**
   - Mock country mappings: `tests/fixtures/mock_restcountries.json`
   - Mock USD rates: `tests/fixtures/mock_rates_USD.json`
   - Mock EUR rates: `tests/fixtures/mock_rates_EUR.json`

## 📊 Usage Examples

### 1. Employee Expense Submission

```python
# Create expense claim
claim = env['expense.claim'].create({
    'employee_id': employee.id,
    'currency_id': usd_currency.id,
    'description': 'Business trip to NYC'
})

# Add expense line with receipt
line = env['expense.line'].create({
    'claim_id': claim.id,
    'name': 'Hotel accommodation',
    'category_id': hotel_category.id,
    'unit_amount': 150.00,
    'date': '2025-10-04'
})

# Process OCR if receipt attached
if line.receipt_attachment_id:
    line.action_process_ocr()

# Submit for approval
claim.action_submit()
```

### 2. Currency Conversion

```python
# Convert expense amount
currency_service = env['currency.service']
result = currency_service.convert_amount(
    amount=100.00,
    from_currency='USD',
    to_currency='EUR',
    rate_date='2025-10-04'
)

print(f"Converted: {result['converted_amount']} EUR")
print(f"Rate: {result['exchange_rate']}")
print(f"Source: {result['source']}")
```

### 3. Approval Workflow

```python
# Get applicable approval rules
rules = env['approval.rule'].get_applicable_rules(
    amount=1500.00,
    employee=employee,
    department=employee.department_id,
    company=env.company
)

# Create approval requests
for rule in rules:
    approvers = rule.get_approvers(employee, employee.department_id)
    # Create approval requests...
```

## 🔒 Security Features

- **API Key Management**: Environment variables only, never hardcoded
- **Input Validation**: Schema validation for all external API responses
- **Rate Limiting**: In-memory rate limiting to prevent API abuse
- **Access Control**: Role-based permissions (Employee/Manager/Admin)
- **Audit Trail**: Complete logging of all API calls and conversions

## 🚨 Troubleshooting

### Common Issues

#### Currency Rates Missing
```bash
# Check API configuration
curl -s "$EXCHANGE_API_URL/USD"

# Enable API stubs for testing
export USE_API_STUBS=True

# Check cache status
# Navigate to: Smart Expenses > Configuration > Currency Rate Cache
```

#### OCR Not Working
```bash
# Check Tesseract installation
tesseract --version

# Test Google Vision (if configured)
export GOOGLE_VISION_API_KEY=your_key
python -c "from google.cloud import vision; print('OK')"

# Check OCR service status
# Navigate to: Smart Expenses > Configuration > Company Settings
```

#### API Rate Limits
- Check rate limiting in logs
- Verify API quotas with providers
- Enable caching to reduce API calls
- Use `USE_API_STUBS=True` for development

### Log Analysis

```bash
# Check Odoo logs
tail -f /var/log/odoo/odoo.log | grep -E "(currency|ocr|country)"

# Check API call logs
grep "currency_service\|country_service\|ocr_service" odoo.log
```

## 📈 Performance & Monitoring

### Caching Statistics
- Navigate to **Smart Expenses > Configuration > Currency Rate Cache**
- View cache hit rates, expiry status, and cleanup statistics

### API Usage Monitoring
- Built-in rate limiting with configurable thresholds
- Automatic retry logic with exponential backoff
- Comprehensive error logging and admin notifications

### Database Optimization
- Indexed foreign keys for performance
- Automatic cleanup of expired cache entries
- Efficient query patterns for large datasets

## 🤝 Contributing

1. Fork the repository
2. Create feature branch: `git checkout -b feature/amazing-feature`
3. Run tests: `pytest tests/`
4. Commit changes: `git commit -m 'Add amazing feature'`
5. Push branch: `git push origin feature/amazing-feature`
6. Open Pull Request

## 📄 License

This project is licensed under the LGPL-3 License - see the [LICENSE](LICENSE) file for details.

## 🆘 Support

- **Documentation**: [Wiki](https://github.com/your-org/smart-expense-management/wiki)
- **Issues**: [GitHub Issues](https://github.com/your-org/smart-expense-management/issues)
- **Discussions**: [GitHub Discussions](https://github.com/your-org/smart-expense-management/discussions)

---

**Built with ❤️ for modern expense management**
