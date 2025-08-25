"""
Input sanitization utilities for security hardening.
Provides comprehensive input validation and sanitization functions.
"""

import html
import re
import bleach
from typing import Any, Dict, List, Optional
import logging

logger = logging.getLogger("input_sanitizer")

class InputSanitizer:
    """Comprehensive input sanitization class."""
    
    # Allowed HTML tags for rich text content (very restrictive)
    ALLOWED_TAGS = [
        'p', 'br', 'strong', 'em', 'u', 'ol', 'ul', 'li', 
        'h1', 'h2', 'h3', 'h4', 'h5', 'h6', 'blockquote'
    ]
    
    # Allowed attributes for HTML tags
    ALLOWED_ATTRIBUTES = {
        'a': ['href'],
        'img': ['src', 'alt', 'width', 'height'],
    }
    
    @staticmethod
    def sanitize_html(text: str, allow_tags: bool = False) -> str:
        """
        Remove or escape HTML content from text.
        
        Args:
            text: Input text that may contain HTML
            allow_tags: If True, allows safe HTML tags; if False, removes all HTML
            
        Returns:
            Sanitized text
        """
        if not text or not isinstance(text, str):
            return ""
        
        if allow_tags:
            # Allow only safe tags with bleach
            clean_text = bleach.clean(
                text,
                tags=InputSanitizer.ALLOWED_TAGS,
                attributes=InputSanitizer.ALLOWED_ATTRIBUTES,
                strip=True
            )
        else:
            # Remove all HTML tags
            clean_text = bleach.clean(text, tags=[], strip=True)
        
        # Additional XSS protection
        clean_text = html.escape(clean_text, quote=False)
        
        return clean_text.strip()
    
    @staticmethod
    def sanitize_sql_input(text: str) -> str:
        """
        Basic SQL injection prevention through input sanitization.
        
        Note: This is a defense-in-depth measure. Primary protection
        should always be parameterized queries.
        
        Args:
            text: Input text that might contain SQL injection attempts
            
        Returns:
            Text with dangerous SQL patterns removed
        """
        if not text or not isinstance(text, str):
            return ""
        
        # Remove dangerous SQL patterns
        dangerous_patterns = [
            r"['\"];",  # Quote characters and semicolons
            r"--.*$",   # SQL comments
            r"/\*.*?\*/",  # Block comments
            r"\b(SELECT|INSERT|UPDATE|DELETE|DROP|CREATE|ALTER|EXEC|EXECUTE|UNION|SCRIPT)\b",
            r"\b(OR|AND)\s+\d+\s*=\s*\d+",  # Common injection patterns
            r"\bEXEC\s*\(",  # Function execution
            r"\bxp_\w+",     # Extended procedures
            r"\bsp_\w+",     # Stored procedures
        ]
        
        clean_text = text
        for pattern in dangerous_patterns:
            clean_text = re.sub(pattern, "", clean_text, flags=re.IGNORECASE | re.MULTILINE)
        
        return clean_text.strip()
    
    @staticmethod
    def sanitize_filename(filename: str) -> str:
        """
        Sanitize filename to prevent directory traversal and other attacks.
        
        Args:
            filename: Original filename
            
        Returns:
            Safe filename
        """
        if not filename or not isinstance(filename, str):
            return "untitled"
        
        # Remove path separators and dangerous characters
        safe_chars = re.sub(r'[<>:"/\\|?*]', '', filename)
        safe_chars = re.sub(r'\.\.+', '.', safe_chars)  # Remove multiple dots
        safe_chars = safe_chars.strip('. ')  # Remove leading/trailing dots and spaces
        
        # Ensure filename is not empty and not too long
        if not safe_chars or len(safe_chars) > 255:
            return "untitled"
        
        # Avoid reserved names on Windows
        reserved_names = {
            'CON', 'PRN', 'AUX', 'NUL', 'COM1', 'COM2', 'COM3', 'COM4',
            'COM5', 'COM6', 'COM7', 'COM8', 'COM9', 'LPT1', 'LPT2',
            'LPT3', 'LPT4', 'LPT5', 'LPT6', 'LPT7', 'LPT8', 'LPT9'
        }
        
        name_without_ext = safe_chars.split('.')[0].upper()
        if name_without_ext in reserved_names:
            return f"file_{safe_chars}"
        
        return safe_chars
    
    @staticmethod
    def sanitize_url(url: str) -> Optional[str]:
        """
        Validate and sanitize URL input.
        
        Args:
            url: URL to validate
            
        Returns:
            Clean URL or None if invalid
        """
        if not url or not isinstance(url, str):
            return None
        
        # Basic URL validation
        url_pattern = re.compile(
            r'^https?://'  # http:// or https://
            r'(?:(?:[A-Z0-9](?:[A-Z0-9-]{0,61}[A-Z0-9])?\.)+[A-Z]{2,6}\.?|'  # domain...
            r'localhost|'  # localhost...
            r'\d{1,3}\.\d{1,3}\.\d{1,3}\.\d{1,3})'  # ...or ip
            r'(?::\d+)?'  # optional port
            r'(?:/?|[/?]\S+)$', re.IGNORECASE)
        
        if not url_pattern.match(url):
            return None
        
        # Block dangerous schemes
        dangerous_schemes = ['javascript:', 'data:', 'vbscript:', 'file:']
        if any(url.lower().startswith(scheme) for scheme in dangerous_schemes):
            return None
        
        # Limit URL length
        if len(url) > 2048:
            return None
        
        return url.strip()
    
    @staticmethod
    def sanitize_dict(data: Dict[str, Any], allow_html_fields: Optional[List[str]] = None) -> Dict[str, Any]:
        """
        Recursively sanitize dictionary values.
        
        Args:
            data: Dictionary to sanitize
            allow_html_fields: List of field names that can contain safe HTML
            
        Returns:
            Sanitized dictionary
        """
        if not isinstance(data, dict):
            return data
        
        allow_html_fields = allow_html_fields or []
        sanitized = {}
        
        for key, value in data.items():
            if isinstance(value, str):
                # Check if this field allows HTML
                allow_tags = key in allow_html_fields
                sanitized[key] = InputSanitizer.sanitize_html(value, allow_tags)
            elif isinstance(value, dict):
                sanitized[key] = InputSanitizer.sanitize_dict(value, allow_html_fields)
            elif isinstance(value, list):
                sanitized[key] = [
                    InputSanitizer.sanitize_html(item, key in allow_html_fields) 
                    if isinstance(item, str) else item
                    for item in value
                ]
            else:
                sanitized[key] = value
        
        return sanitized
    
    @staticmethod
    def validate_email_format(email: str) -> bool:
        """
        Validate email format (additional validation beyond Pydantic EmailStr).
        
        Args:
            email: Email address to validate
            
        Returns:
            True if email format is valid
        """
        if not email or not isinstance(email, str):
            return False
        
        # Basic email regex (not RFC compliant but good for most cases)
        email_pattern = re.compile(
            r'^[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}$'
        )
        
        return bool(email_pattern.match(email.strip()))
    
    @staticmethod
    def sanitize_phone_number(phone: str) -> Optional[str]:
        """
        Sanitize and format phone number.
        
        Args:
            phone: Phone number to sanitize
            
        Returns:
            Clean phone number or None if invalid
        """
        if not phone or not isinstance(phone, str):
            return None
        
        # Remove all non-digit characters
        digits_only = re.sub(r'\D', '', phone)
        
        # Validate length (7-15 digits is reasonable for most phone numbers)
        if len(digits_only) < 7 or len(digits_only) > 15:
            return None
        
        return digits_only
    
    @staticmethod
    def sanitize_user_input(
        text: str,
        max_length: Optional[int] = None,
        allow_html: bool = False,
        strip_sql: bool = True
    ) -> str:
        """
        Comprehensive user input sanitization.
        
        Args:
            text: Input text to sanitize
            max_length: Maximum allowed length
            allow_html: Whether to allow safe HTML tags
            strip_sql: Whether to remove SQL injection patterns
            
        Returns:
            Sanitized text
        """
        if not text or not isinstance(text, str):
            return ""
        
        # HTML sanitization
        clean_text = InputSanitizer.sanitize_html(text, allow_html)
        
        # SQL injection prevention
        if strip_sql:
            clean_text = InputSanitizer.sanitize_sql_input(clean_text)
        
        # Length limiting
        if max_length and len(clean_text) > max_length:
            clean_text = clean_text[:max_length].strip()
        
        return clean_text

# Convenient functions for common use cases
def sanitize_text_input(text: str, max_length: int = 1000) -> str:
    """Quick sanitization for regular text input."""
    return InputSanitizer.sanitize_user_input(text, max_length, allow_html=False)

def sanitize_rich_text(text: str, max_length: int = 5000) -> str:
    """Quick sanitization for rich text content that may contain HTML."""
    return InputSanitizer.sanitize_user_input(text, max_length, allow_html=True)

def sanitize_search_query(query: str) -> str:
    """Sanitize search query input."""
    return InputSanitizer.sanitize_user_input(query, max_length=200, allow_html=False)