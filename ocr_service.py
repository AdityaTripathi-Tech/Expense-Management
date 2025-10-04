# type: ignore
import logging
import os
import re
from datetime import datetime
from odoo import models, api, _
from odoo.exceptions import UserError

_logger = logging.getLogger(__name__)


class OCRService(models.AbstractModel):
    _name = 'ocr.service'
    _description = 'OCR Service for Receipt Processing'

    @api.model
    def process_receipt(self, attachment):
        """
        Process receipt attachment with OCR
        
        Args:
            attachment (ir.attachment): Receipt attachment to process
            
        Returns:
            dict: OCR results with extracted data and confidence
        """
        if not attachment:
            raise UserError(_('No attachment provided for OCR processing'))
        
        # Check if Google Vision is enabled and available
        use_google_vision = self._should_use_google_vision()
        
        try:
            if use_google_vision:
                return self._process_with_google_vision(attachment)
            else:
                return self._process_with_tesseract(attachment)
                
        except Exception as e:
            _logger.error(f"OCR processing failed: {e}")
            return {
                'success': False,
                'error': str(e),
                'confidence': 0.0,
                'raw_text': '',
                'extracted_data': {}
            }

    @api.model
    def _should_use_google_vision(self):
        """
        Check if Google Vision API should be used
        
        Returns:
            bool: True if Google Vision should be used
        """
        # Check company settings
        company = self.env.company
        if not company.use_google_vision:
            return False
        
        # Check if API key is configured
        api_key = company.google_vision_api_key or os.getenv('GOOGLE_VISION_API_KEY')
        if not api_key:
            _logger.warning("Google Vision enabled but no API key configured")
            return False
        
        # Check if library is available
        try:
            from google.cloud import vision
            return True
        except ImportError:
            _logger.warning("Google Vision library not available, falling back to Tesseract")
            return False

    @api.model
    def _process_with_google_vision(self, attachment):
        """
        Process receipt using Google Vision API
        
        Args:
            attachment (ir.attachment): Receipt attachment
            
        Returns:
            dict: OCR results
        """
        try:
            from google.cloud import vision
            import base64
            
            # Get API key
            api_key = self.env.company.google_vision_api_key or os.getenv('GOOGLE_VISION_API_KEY')
            
            # Initialize client
            client = vision.ImageAnnotatorClient()
            
            # Prepare image data
            image_data = base64.b64decode(attachment.datas)
            image = vision.Image(content=image_data)
            
            # Perform text detection
            response = client.text_detection(image=image)
            texts = response.text_annotations
            
            if response.error.message:
                raise Exception(f"Google Vision API error: {response.error.message}")
            
            if not texts:
                return {
                    'success': True,
                    'confidence': 0.0,
                    'raw_text': '',
                    'extracted_data': {},
                    'source': 'google_vision'
                }
            
            # Extract text
            raw_text = texts[0].description if texts else ''
            
            # Calculate confidence (Google Vision doesn't provide confidence directly)
            # We'll estimate based on text quality
            confidence = self._estimate_confidence(raw_text)
            
            # Extract structured data
            extracted_data = self._extract_structured_data(raw_text)
            
            _logger.info(f"Google Vision OCR completed with estimated confidence: {confidence}")
            
            return {
                'success': True,
                'confidence': confidence,
                'raw_text': raw_text,
                'extracted_data': extracted_data,
                'source': 'google_vision'
            }
            
        except Exception as e:
            _logger.error(f"Google Vision OCR failed: {e}")
            # Fallback to Tesseract
            return self._process_with_tesseract(attachment)

    @api.model
    def _process_with_tesseract(self, attachment):
        """
        Process receipt using Tesseract OCR
        
        Args:
            attachment (ir.attachment): Receipt attachment
            
        Returns:
            dict: OCR results
        """
        try:
            import pytesseract
            from PIL import Image
            import io
            import base64
            
            # Decode image data
            image_data = base64.b64decode(attachment.datas)
            image = Image.open(io.BytesIO(image_data))
            
            # Convert to RGB if necessary
            if image.mode != 'RGB':
                image = image.convert('RGB')
            
            # Get OCR configuration
            config = self._get_tesseract_config()
            
            # Perform OCR with confidence data
            ocr_data = pytesseract.image_to_data(
                image, 
                config=config,
                output_type=pytesseract.Output.DICT
            )
            
            # Extract text and calculate confidence
            raw_text = pytesseract.image_to_string(image, config=config)
            confidence = self._calculate_tesseract_confidence(ocr_data)
            
            # Extract structured data
            extracted_data = self._extract_structured_data(raw_text)
            
            _logger.info(f"Tesseract OCR completed with confidence: {confidence}")
            
            return {
                'success': True,
                'confidence': confidence,
                'raw_text': raw_text,
                'extracted_data': extracted_data,
                'source': 'tesseract'
            }
            
        except ImportError as e:
            _logger.error("Tesseract not available: %s", e)
            return self._create_mock_ocr_result(attachment)
            
        except Exception as e:
            _logger.error(f"Tesseract OCR failed: {e}")
            return self._create_mock_ocr_result(attachment)

    @api.model
    def _get_tesseract_config(self):
        """
        Get Tesseract OCR configuration
        
        Returns:
            str: Tesseract configuration string
        """
        # Optimize for receipt text
        return '--oem 3 --psm 6 -c tessedit_char_whitelist=0123456789ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz.,/$:-'

    @api.model
    def _calculate_tesseract_confidence(self, ocr_data):
        """
        Calculate average confidence from Tesseract OCR data
        
        Args:
            ocr_data (dict): Tesseract OCR output data
            
        Returns:
            float: Average confidence (0.0-1.0)
        """
        confidences = [conf for conf in ocr_data.get('conf', []) if conf > 0]
        
        if not confidences:
            return 0.0
        
        avg_confidence = sum(confidences) / len(confidences)
        return avg_confidence / 100.0  # Convert from 0-100 to 0.0-1.0

    @api.model
    def _estimate_confidence(self, text):
        """
        Estimate OCR confidence based on text characteristics
        
        Args:
            text (str): Extracted text
            
        Returns:
            float: Estimated confidence (0.0-1.0)
        """
        if not text:
            return 0.0
        
        # Basic heuristics for confidence estimation
        score = 0.5  # Base score
        
        # Check for common receipt patterns
        if re.search(r'\$\d+\.\d{2}|\d+\.\d{2}', text):  # Currency amounts
            score += 0.2
        
        if re.search(r'\d{1,2}[/-]\d{1,2}[/-]\d{2,4}', text):  # Dates
            score += 0.1
        
        if re.search(r'total|subtotal|tax', text, re.IGNORECASE):  # Receipt keywords
            score += 0.1
        
        # Penalize for too many special characters (OCR errors)
        special_char_ratio = len(re.findall(r'[^a-zA-Z0-9\s.,/$:-]', text)) / len(text)
        if special_char_ratio > 0.1:
            score -= special_char_ratio
        
        return max(0.0, min(1.0, score))

    @api.model
    def _extract_structured_data(self, raw_text):
        """
        Extract structured data from raw OCR text
        
        Args:
            raw_text (str): Raw text from OCR
            
        Returns:
            dict: Structured data extracted from text
        """
        if not raw_text:
            return {}
        
        extracted = {}
        
        # Extract amounts (look for currency patterns)
        amounts = self._extract_amounts(raw_text)
        if amounts:
            # Use the largest amount as the total (common pattern)
            extracted['amount'] = max(amounts)
        
        # Extract dates
        date = self._extract_date(raw_text)
        if date:
            extracted['date'] = date
        
        # Extract vendor/merchant name
        vendor = self._extract_vendor_name(raw_text)
        if vendor:
            extracted['vendor'] = vendor
        
        # Extract description (first meaningful line)
        description = self._extract_description(raw_text)
        if description:
            extracted['description'] = description
        
        return extracted

    @api.model
    def _extract_amounts(self, text):
        """Extract monetary amounts from text"""
        # Pattern for currency amounts
        patterns = [
            r'\$(\d+(?:,\d{3})*\.\d{2})',  # $123.45 or $1,234.56
            r'(\d+(?:,\d{3})*\.\d{2})',   # 123.45 or 1,234.56
            r'\$(\d+\.\d{2})',            # $123.45
            r'(\d+\.\d{2})',              # 123.45
        ]
        
        amounts = []
        for pattern in patterns:
            matches = re.findall(pattern, text)
            for match in matches:
                try:
                    # Remove commas and convert to float
                    amount = float(match.replace(',', ''))
                    if 0.01 <= amount <= 100000:  # Reasonable range
                        amounts.append(amount)
                except ValueError:
                    continue
        
        return amounts

    @api.model
    def _extract_date(self, text):
        """Extract date from text"""
        # Common date patterns
        patterns = [
            r'(\d{1,2}[/-]\d{1,2}[/-]\d{4})',  # MM/DD/YYYY or DD/MM/YYYY
            r'(\d{1,2}[/-]\d{1,2}[/-]\d{2})',  # MM/DD/YY or DD/MM/YY
            r'(\d{4}[/-]\d{1,2}[/-]\d{1,2})',  # YYYY/MM/DD
        ]
        
        for pattern in patterns:
            matches = re.findall(pattern, text)
            for match in matches:
                try:
                    # Try different date formats
                    for fmt in ['%m/%d/%Y', '%d/%m/%Y', '%m-%d-%Y', '%d-%m-%Y', 
                               '%Y/%m/%d', '%Y-%m-%d', '%m/%d/%y', '%d/%m/%y']:
                        try:
                            date_obj = datetime.strptime(match, fmt)
                            # Adjust year for 2-digit years
                            if date_obj.year < 1950:
                                date_obj = date_obj.replace(year=date_obj.year + 100)
                            return date_obj.date()
                        except ValueError:
                            continue
                except Exception:
                    continue
        
        return None

    @api.model
    def _extract_vendor_name(self, text):
        """Extract vendor/merchant name from text"""
        lines = [line.strip() for line in text.split('\n') if line.strip()]
        
        if not lines:
            return None
        
        # Usually the vendor name is in the first few lines
        # Skip very short lines or lines with only numbers/symbols
        for line in lines[:3]:
            if (len(line) > 3 and 
                not line.isdigit() and 
                not re.match(r'^[\d\s.,/$:-]+$', line)):
                return line
        
        return None

    @api.model
    def _extract_description(self, text):
        """Extract description from text"""
        lines = [line.strip() for line in text.split('\n') if line.strip()]
        
        # Look for lines that might be item descriptions
        for line in lines:
            # Skip lines that are clearly amounts, dates, or vendor info
            if (len(line) > 5 and 
                not re.search(r'\$\d+\.\d{2}', line) and
                not re.search(r'\d{1,2}[/-]\d{1,2}[/-]\d{2,4}', line) and
                not line.upper() in ['TOTAL', 'SUBTOTAL', 'TAX', 'RECEIPT']):
                return line
        
        return None

    @api.model
    def _create_mock_ocr_result(self, attachment):
        """
        Create mock OCR result when OCR libraries are not available
        
        Args:
            attachment (ir.attachment): Receipt attachment
            
        Returns:
            dict: Mock OCR result
        """
        _logger.warning("OCR libraries not available, returning mock result")
        
        # Generate mock data based on filename or return empty result
        mock_text = f"RECEIPT\nMock Vendor\nDate: {datetime.now().strftime('%m/%d/%Y')}\nAmount: $0.00"
        
        return {
            'success': True,
            'confidence': 0.1,  # Low confidence for mock data
            'raw_text': mock_text,
            'extracted_data': {
                'amount': 0.00,
                'date': datetime.now().date(),
                'vendor': 'Mock Vendor',
                'description': 'Mock Receipt'
            },
            'source': 'mock',
            'warning': 'OCR libraries not available - using mock data'
        }

    @api.model
    def test_ocr_service(self):
        """
        Test OCR service functionality
        
        Returns:
            dict: Test results
        """
        results = {
            'tesseract_available': False,
            'google_vision_available': False,
            'google_vision_configured': False,
        }
        
        # Test Tesseract
        try:
            import pytesseract
            from PIL import Image
            results['tesseract_available'] = True
        except ImportError:
            pass
        
        # Test Google Vision
        try:
            from google.cloud import vision
            results['google_vision_available'] = True
            
            # Check if configured
            api_key = self.env.company.google_vision_api_key or os.getenv('GOOGLE_VISION_API_KEY')
            results['google_vision_configured'] = bool(api_key)
            
        except ImportError:
            pass
        
        return results

    @api.model
    def get_ocr_statistics(self):
        """
        Get OCR usage statistics
        
        Returns:
            dict: OCR statistics
        """
        # Count processed receipts
        total_receipts = self.env['expense.line'].search_count([
            ('receipt_attachment_id', '!=', False)
        ])
        
        processed_receipts = self.env['expense.line'].search_count([
            ('ocr_processed', '=', True)
        ])
        
        low_confidence = self.env['expense.line'].search_count([
            ('ocr_confidence_low', '=', True)
        ])
        
        return {
            'total_receipts': total_receipts,
            'processed_receipts': processed_receipts,
            'processing_rate': (processed_receipts / total_receipts * 100) if total_receipts > 0 else 0,
            'low_confidence_count': low_confidence,
            'low_confidence_rate': (low_confidence / processed_receipts * 100) if processed_receipts > 0 else 0,
        }
