"""
PDF service for extracting text from PDF files.
Uses multiple extraction methods for robust PDF text extraction:
1. pdfplumber - Best for structured PDFs with proper text encoding
2. PyPDF2 - Fallback for simple PDFs
3. pymupdf (fitz) - Better for complex layouts and fonts
4. OCR with pytesseract - For scanned/image-based PDFs
"""
from typing import Optional, Tuple
import io
import re
import httpx

from app.core.config import settings
from app.core.exceptions import PDFProcessingError
from app.utils.logger import logger


class PDFService:
    """Service for PDF text extraction with multiple fallback methods."""

    def __init__(self):
        self.max_size_bytes = settings.get_pdf_max_size_bytes()
        self.timeout = 60  # Increased timeout for large PDFs

    async def extract_text_from_url(self, pdf_url: str) -> str:
        """
        Download and extract text from a PDF URL.

        Args:
            pdf_url: URL to the PDF file.

        Returns:
            Extracted text content.

        Raises:
            PDFProcessingError: If download or processing fails.
        """
        try:
            logger.info(f"Downloading PDF from: {pdf_url}")
            
            async with httpx.AsyncClient(timeout=self.timeout) as client:
                response = await client.get(
                    pdf_url, 
                    follow_redirects=True,
                    headers={
                        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36'
                    }
                )
                response.raise_for_status()
                
                # Check content type
                content_type = response.headers.get('content-type', '')
                if 'pdf' not in content_type.lower() and not pdf_url.lower().endswith('.pdf'):
                    logger.warning(f"URL may not be a PDF: content-type={content_type}")
                
                pdf_content = response.content
                logger.info(f"Downloaded PDF: {len(pdf_content)} bytes")
                
                return await self.extract_text_from_pdf(pdf_content, source_url=pdf_url)
                
        except httpx.HTTPError as e:
            logger.error(f"Failed to download PDF from {pdf_url}: {str(e)}")
            raise PDFProcessingError(f"Failed to download PDF: {str(e)}")
        except Exception as e:
            logger.error(f"PDF URL processing error: {str(e)}")
            raise PDFProcessingError(f"Failed to process PDF from URL: {str(e)}")

    async def extract_text_from_pdf(self, pdf_content: bytes, source_url: str = None) -> str:
        """
        Extract text from PDF file using multiple methods.

        Args:
            pdf_content: PDF file content as bytes.
            source_url: Source URL for logging purposes.

        Returns:
            Extracted text content.

        Raises:
            PDFProcessingError: If PDF processing fails.
        """
        try:
            # Check file size
            if len(pdf_content) > self.max_size_bytes:
                raise PDFProcessingError(
                    f"PDF file too large (maximum {settings.PDF_MAX_SIZE_MB}MB)"
                )

            logger.info(f"Processing PDF of size: {len(pdf_content)} bytes")
            
            extraction_results = []
            
            # Method 1: Try pdfplumber FIRST - most reliable, handles tables well
            text_plumber = self._extract_with_pdfplumber(pdf_content)
            if text_plumber:
                quality = self._assess_text_quality(text_plumber)
                extraction_results.append(('pdfplumber', text_plumber, quality))
                logger.info(f"pdfplumber extracted {len(text_plumber)} chars, quality: {quality}")
                
                # If pdfplumber gives good results, use it immediately
                if quality >= 0.6 and len(text_plumber) >= 100:
                    cleaned_text = self._clean_extracted_text(text_plumber)
                    logger.info(f"Using pdfplumber result: {len(cleaned_text)} chars")
                    return cleaned_text.strip()

            # Method 2: Try pymupdf (fitz) - best for complex fonts and layouts
            text_fitz = self._extract_with_pymupdf(pdf_content)
            if text_fitz:
                quality = self._assess_text_quality(text_fitz)
                extraction_results.append(('pymupdf', text_fitz, quality))
                logger.info(f"pymupdf extracted {len(text_fitz)} chars, quality: {quality}")

            # Method 3: Try PyPDF2 - fallback
            text_pypdf2 = self._extract_with_pypdf2(pdf_content)
            if text_pypdf2:
                quality = self._assess_text_quality(text_pypdf2)
                extraction_results.append(('PyPDF2', text_pypdf2, quality))
                logger.info(f"PyPDF2 extracted {len(text_pypdf2)} chars, quality: {quality}")

            # Choose the best extraction result
            if extraction_results:
                # Sort by quality score (descending)
                extraction_results.sort(key=lambda x: x[2], reverse=True)
                best_method, best_text, best_quality = extraction_results[0]
                logger.info(f"Best extraction method: {best_method} with quality {best_quality}")
                
                # Clean the text
                cleaned_text = self._clean_extracted_text(best_text)
                
                # If quality is still poor, try OCR
                if best_quality < 0.3 and len(cleaned_text) < 500:
                    logger.info("Text quality poor, attempting OCR...")
                    ocr_text = self._extract_with_ocr(pdf_content)
                    if ocr_text and self._assess_text_quality(ocr_text) > best_quality:
                        cleaned_text = self._clean_extracted_text(ocr_text)
                        logger.info(f"OCR produced better results: {len(cleaned_text)} chars")
                
                if len(cleaned_text.strip()) >= 50:
                    logger.info(f"Successfully extracted {len(cleaned_text)} characters from PDF")
                    return cleaned_text.strip()

            # If all methods failed, try OCR as last resort
            logger.info("Standard extraction failed, attempting OCR...")
            ocr_text = self._extract_with_ocr(pdf_content)
            if ocr_text and len(ocr_text.strip()) >= 50:
                cleaned_text = self._clean_extracted_text(ocr_text)
                logger.info(f"OCR extracted {len(cleaned_text)} characters")
                return cleaned_text.strip()

            raise PDFProcessingError("Could not extract meaningful text from PDF")

        except PDFProcessingError:
            raise
        except Exception as e:
            logger.error(f"PDF processing error: {str(e)}")
            raise PDFProcessingError(f"Failed to process PDF: {str(e)}")

    def _extract_with_pymupdf(self, pdf_content: bytes) -> str:
        """
        Extract text using PyMuPDF (fitz) - handles complex fonts better.
        """
        try:
            import fitz  # PyMuPDF
            
            pdf_file = io.BytesIO(pdf_content)
            doc = fitz.open(stream=pdf_file, filetype="pdf")
            text_parts = []
            
            for page_num in range(len(doc)):
                page = doc[page_num]
                # Use "text" for plain text, preserves layout better
                text = page.get_text("text")
                if text:
                    text_parts.append(text)
            
            doc.close()
            return "\n".join(text_parts)
            
        except ImportError:
            logger.warning("PyMuPDF (fitz) not installed, skipping this method")
            return ""
        except Exception as e:
            logger.warning(f"PyMuPDF extraction failed: {str(e)}")
            return ""

    def _extract_with_pdfplumber(self, pdf_content: bytes) -> str:
        """
        Extract text using pdfplumber.
        """
        try:
            import pdfplumber
            
            pdf_file = io.BytesIO(pdf_content)
            text_parts = []

            with pdfplumber.open(pdf_file) as pdf:
                for page in pdf.pages:
                    # Try extracting text
                    page_text = page.extract_text()
                    if page_text:
                        text_parts.append(page_text)
                    
                    # Also try extracting tables and convert to text
                    tables = page.extract_tables()
                    for table in tables:
                        if table:
                            for row in table:
                                if row:
                                    row_text = " | ".join([str(cell) if cell else "" for cell in row])
                                    text_parts.append(row_text)

            return "\n".join(text_parts)

        except ImportError:
            logger.warning("pdfplumber not installed, skipping this method")
            return ""
        except Exception as e:
            logger.warning(f"pdfplumber extraction failed: {str(e)}")
            return ""

    def _extract_with_pypdf2(self, pdf_content: bytes) -> str:
        """
        Extract text using PyPDF2.
        """
        try:
            from PyPDF2 import PdfReader
            
            pdf_file = io.BytesIO(pdf_content)
            pdf_reader = PdfReader(pdf_file)
            text_parts = []

            for page in pdf_reader.pages:
                page_text = page.extract_text()
                if page_text:
                    text_parts.append(page_text)

            return "\n".join(text_parts)

        except ImportError:
            logger.warning("PyPDF2 not installed, skipping this method")
            return ""
        except Exception as e:
            logger.warning(f"PyPDF2 extraction failed: {str(e)}")
            return ""

    def _extract_with_ocr(self, pdf_content: bytes) -> str:
        """
        Extract text using OCR (Optical Character Recognition).
        Converts PDF pages to images and runs OCR.
        """
        try:
            import fitz  # PyMuPDF for PDF to image conversion
            import pytesseract
            from PIL import Image
            
            pdf_file = io.BytesIO(pdf_content)
            doc = fitz.open(stream=pdf_file, filetype="pdf")
            text_parts = []
            
            for page_num in range(min(len(doc), 10)):  # Limit to first 10 pages for OCR
                page = doc[page_num]
                # Convert page to image with higher resolution for better OCR
                mat = fitz.Matrix(2.0, 2.0)  # 2x zoom for better quality
                pix = page.get_pixmap(matrix=mat)
                
                # Convert to PIL Image
                img = Image.frombytes("RGB", [pix.width, pix.height], pix.samples)
                
                # Run OCR
                page_text = pytesseract.image_to_string(img, lang='eng')
                if page_text:
                    text_parts.append(page_text)
            
            doc.close()
            return "\n".join(text_parts)
            
        except ImportError as e:
            logger.warning(f"OCR dependencies not installed: {e}")
            return ""
        except Exception as e:
            logger.warning(f"OCR extraction failed: {str(e)}")
            return ""

    def _assess_text_quality(self, text: str) -> float:
        """
        Assess the quality of extracted text.
        Returns a score between 0 and 1.
        
        Factors considered:
        - Proportion of readable ASCII characters
        - Presence of common English words
        - Reasonable word length distribution
        - Not too many special characters
        """
        if not text or len(text) < 10:
            return 0.0
        
        # Check proportion of readable characters (letters, digits, common punctuation)
        readable_chars = len(re.findall(r'[a-zA-Z0-9\s.,!?;:\-\'"()%$@#&*/]', text))
        readable_ratio = readable_chars / len(text)
        
        # Check for common English words
        common_words = ['the', 'and', 'for', 'are', 'but', 'not', 'you', 'all', 'can', 'has', 
                       'her', 'was', 'one', 'our', 'out', 'card', 'fee', 'annual', 'benefit',
                       'cashback', 'reward', 'credit', 'bank', 'offer', 'free', 'terms']
        text_lower = text.lower()
        word_matches = sum(1 for word in common_words if word in text_lower)
        word_score = min(word_matches / 10, 1.0)
        
        # Check for gibberish patterns (too many consecutive consonants, repeated chars)
        gibberish_patterns = len(re.findall(r'[bcdfghjklmnpqrstvwxz]{5,}|(.)\1{4,}', text.lower()))
        gibberish_penalty = min(gibberish_patterns * 0.1, 0.5)
        
        # Calculate average word length
        words = text.split()
        if words:
            avg_word_len = sum(len(w) for w in words) / len(words)
            # Penalize if average word length is too short or too long
            length_score = 1.0 if 3 <= avg_word_len <= 12 else 0.5
        else:
            length_score = 0.0
        
        # Combine scores
        quality = (readable_ratio * 0.4 + word_score * 0.3 + length_score * 0.3) - gibberish_penalty
        return max(0.0, min(1.0, quality))

    def _clean_extracted_text(self, text: str) -> str:
        """
        Clean and normalize extracted text.
        """
        if not text:
            return ""
        
        # Replace multiple whitespace with single space
        text = re.sub(r'[ \t]+', ' ', text)
        
        # Replace multiple newlines with double newline
        text = re.sub(r'\n{3,}', '\n\n', text)
        
        # Remove null characters and other control characters
        text = re.sub(r'[\x00-\x08\x0b\x0c\x0e-\x1f\x7f]', '', text)
        
        # Fix common OCR/extraction errors
        text = text.replace('ﬁ', 'fi')
        text = text.replace('ﬂ', 'fl')
        text = text.replace('ﬀ', 'ff')
        text = text.replace('ﬃ', 'ffi')
        text = text.replace('ﬄ', 'ffl')
        
        # Remove lines that are just numbers or special characters
        lines = text.split('\n')
        cleaned_lines = []
        for line in lines:
            stripped = line.strip()
            # Keep line if it has at least some letters
            if stripped and re.search(r'[a-zA-Z]{2,}', stripped):
                cleaned_lines.append(line)
            elif stripped and len(stripped) > 20:
                # Keep longer lines even without letters (might be data)
                cleaned_lines.append(line)
        
        return '\n'.join(cleaned_lines)

    def validate_pdf(self, pdf_content: bytes) -> Tuple[bool, Optional[str]]:
        """
        Validate PDF file.
        """
        try:
            # Check size
            if len(pdf_content) > self.max_size_bytes:
                return False, f"PDF file too large (maximum {settings.PDF_MAX_SIZE_MB}MB)"

            # Try to open PDF with PyMuPDF (most robust)
            try:
                import fitz
                pdf_file = io.BytesIO(pdf_content)
                doc = fitz.open(stream=pdf_file, filetype="pdf")
                doc.close()
                return True, None
            except ImportError:
                pass
            
            # Fallback to PyPDF2
            from PyPDF2 import PdfReader
            pdf_file = io.BytesIO(pdf_content)
            PdfReader(pdf_file)
            return True, None

        except Exception as e:
            return False, f"Invalid PDF file: {str(e)}"


# Global PDF service instance
pdf_service = PDFService()
