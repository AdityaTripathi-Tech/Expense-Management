#!/usr/bin/env python3
"""
Mock API Server for Smart Expense Management Testing

This server provides mock endpoints for:
- REST Countries API
- ExchangeRate API
- Google Vision API (optional)

Usage:
    python mock_server.py
    
Environment Variables:
    FLASK_PORT: Port to run on (default: 8080)
    FLASK_HOST: Host to bind to (default: 0.0.0.0)
"""

import os
import json
import time
import random
from flask import Flask, jsonify, request
from flask_cors import CORS

app = Flask(__name__)
CORS(app)

# Configuration
FIXTURES_DIR = os.path.join(os.path.dirname(__file__), 'fixtures')
PORT = int(os.getenv('FLASK_PORT', 8080))
HOST = os.getenv('FLASK_HOST', '0.0.0.0')

# Rate limiting simulation
request_counts = {}
RATE_LIMIT_PER_MINUTE = 60


def load_fixture(filename):
    """Load JSON fixture file"""
    try:
        filepath = os.path.join(FIXTURES_DIR, filename)
        with open(filepath, 'r', encoding='utf-8') as f:
            return json.load(f)
    except Exception as e:
        app.logger.error(f"Error loading fixture {filename}: {e}")
        return None


def simulate_rate_limiting():
    """Simulate rate limiting"""
    client_ip = request.remote_addr
    current_time = time.time()
    
    # Clean old entries
    minute_ago = current_time - 60
    if client_ip in request_counts:
        request_counts[client_ip] = [
            timestamp for timestamp in request_counts[client_ip] 
            if timestamp > minute_ago
        ]
    else:
        request_counts[client_ip] = []
    
    # Check rate limit
    if len(request_counts[client_ip]) >= RATE_LIMIT_PER_MINUTE:
        return True
    
    # Add current request
    request_counts[client_ip].append(current_time)
    return False


def simulate_network_delay():
    """Simulate network delay"""
    delay = random.uniform(0.1, 0.5)  # 100-500ms delay
    time.sleep(delay)


def simulate_random_failure():
    """Simulate random API failures (5% chance)"""
    return random.random() < 0.05


@app.route('/health')
def health_check():
    """Health check endpoint"""
    return jsonify({
        'status': 'healthy',
        'timestamp': time.time(),
        'service': 'mock-api-server'
    })


@app.route('/v3.1/all')
def rest_countries_all():
    """Mock REST Countries API - Get all countries"""
    simulate_network_delay()
    
    # Simulate rate limiting
    if simulate_rate_limiting():
        return jsonify({'error': 'Rate limit exceeded'}), 429
    
    # Simulate random failures
    if simulate_random_failure():
        return jsonify({'error': 'Internal server error'}), 500
    
    # Check query parameters
    fields = request.args.get('fields', '')
    
    if 'name,currencies' in fields:
        # Load countries fixture
        countries_data = load_fixture('mock_restcountries.json')
        
        if countries_data:
            app.logger.info(f"Served countries data: {len(countries_data)} countries")
            return jsonify(countries_data)
        else:
            return jsonify({'error': 'Fixture data not available'}), 500
    
    return jsonify({'error': 'Invalid fields parameter'}), 400


@app.route('/v4/latest/<currency>')
def exchange_rates(currency):
    """Mock ExchangeRate API - Get latest rates"""
    simulate_network_delay()
    
    # Simulate rate limiting
    if simulate_rate_limiting():
        return jsonify({'error': 'Rate limit exceeded'}), 429
    
    # Simulate random failures
    if simulate_random_failure():
        return jsonify({'error': 'Service temporarily unavailable'}), 503
    
    currency = currency.upper()
    
    # Load rates fixture
    fixture_filename = f'mock_rates_{currency}.json'
    rates_data = load_fixture(fixture_filename)
    
    if rates_data:
        # Update date to current date
        rates_data['date'] = time.strftime('%Y-%m-%d')
        
        app.logger.info(f"Served exchange rates for {currency}")
        return jsonify(rates_data)
    else:
        # Return error for unsupported currency
        return jsonify({
            'error': f'Currency {currency} not supported'
        }), 400


@app.route('/vision/v1/images:annotate', methods=['POST'])
def google_vision_ocr():
    """Mock Google Vision API - Text detection"""
    simulate_network_delay()
    
    # Check authentication
    auth_header = request.headers.get('Authorization')
    if not auth_header or 'Bearer' not in auth_header:
        return jsonify({'error': 'Authentication required'}), 401
    
    # Simulate rate limiting
    if simulate_rate_limiting():
        return jsonify({'error': 'Quota exceeded'}), 429
    
    # Mock OCR response
    mock_response = {
        'responses': [{
            'textAnnotations': [{
                'description': 'RECEIPT\nRestaurant ABC\nDate: 2025-10-04\nAmount: $45.67\nTax: $3.65\nTotal: $49.32',
                'boundingPoly': {
                    'vertices': [
                        {'x': 10, 'y': 10},
                        {'x': 200, 'y': 10},
                        {'x': 200, 'y': 150},
                        {'x': 10, 'y': 150}
                    ]
                }
            }],
            'fullTextAnnotation': {
                'text': 'RECEIPT\nRestaurant ABC\nDate: 2025-10-04\nAmount: $45.67\nTax: $3.65\nTotal: $49.32'
            }
        }]
    }
    
    app.logger.info("Served mock OCR response")
    return jsonify(mock_response)


@app.route('/stats')
def api_stats():
    """Get API usage statistics"""
    total_requests = sum(len(timestamps) for timestamps in request_counts.values())
    
    return jsonify({
        'total_requests': total_requests,
        'active_clients': len(request_counts),
        'rate_limit_per_minute': RATE_LIMIT_PER_MINUTE,
        'fixtures_available': [
            'mock_restcountries.json',
            'mock_rates_USD.json',
            'mock_rates_EUR.json'
        ]
    })


@app.route('/reset')
def reset_stats():
    """Reset API statistics (for testing)"""
    global request_counts
    request_counts = {}
    
    return jsonify({
        'message': 'Statistics reset',
        'timestamp': time.time()
    })


@app.errorhandler(404)
def not_found(error):
    """Handle 404 errors"""
    return jsonify({
        'error': 'Endpoint not found',
        'available_endpoints': [
            '/health',
            '/v3.1/all?fields=name,currencies',
            '/v4/latest/{currency}',
            '/vision/v1/images:annotate',
            '/stats',
            '/reset'
        ]
    }), 404


@app.errorhandler(500)
def internal_error(error):
    """Handle 500 errors"""
    return jsonify({
        'error': 'Internal server error',
        'message': str(error)
    }), 500


if __name__ == '__main__':
    print(f"🚀 Starting Mock API Server on {HOST}:{PORT}")
    print(f"📁 Fixtures directory: {FIXTURES_DIR}")
    print(f"🔗 Health check: http://{HOST}:{PORT}/health")
    print(f"📊 Statistics: http://{HOST}:{PORT}/stats")
    
    # Check if fixtures exist
    fixtures = ['mock_restcountries.json', 'mock_rates_USD.json', 'mock_rates_EUR.json']
    for fixture in fixtures:
        filepath = os.path.join(FIXTURES_DIR, fixture)
        if os.path.exists(filepath):
            print(f"✅ Fixture loaded: {fixture}")
        else:
            print(f"❌ Fixture missing: {fixture}")
    
    app.run(host=HOST, port=PORT, debug=True)
