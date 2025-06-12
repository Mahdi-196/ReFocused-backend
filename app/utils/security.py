import secrets
import string
import re
import ipaddress
from typing import Optional, List, Dict, Any
from fastapi import Request, HTTPException, status
import logging

logger = logging.getLogger(__name__)

def generate_secure_random_string(length: int = 32) -> str:
    """Generate a cryptographically secure random string."""
    alphabet = string.ascii_letters + string.digits
    return ''.join(secrets.choice(alphabet) for _ in range(length))

def sanitize_input(input_string: str) -> str:
    """Basic input sanitization to prevent injection attacks."""
    # Remove any HTML tags
    sanitized = re.sub(r'<[^>]*>', '', input_string)
    # Remove potential SQL injection patterns
    sanitized = re.sub(r'(\b(SELECT|INSERT|UPDATE|DELETE|DROP|ALTER|EXEC|UNION|CREATE|WHERE)\b)|(-{2})', 
                      lambda match: match.group(0).lower(), sanitized, flags=re.IGNORECASE)
    return sanitized

def validate_email_domain(email: str, allowed_domains: Optional[List[str]] = None) -> bool:
    """Validate email domain against allowed domains."""
    if not allowed_domains:
        return True
        
    domain = email.split('@')[-1].lower()
    return domain in allowed_domains

def is_valid_ip(ip: str) -> bool:
    """Check if an IP address is valid."""
    try:
        ipaddress.ip_address(ip)
        return True
    except ValueError:
        return False

def is_private_ip(ip: str) -> bool:
    """Check if an IP address is private."""
    try:
        return ipaddress.ip_address(ip).is_private
    except ValueError:
        return False

def get_client_ip(request: Request) -> str:
    """Get the real client IP address, considering proxies."""
    # Check for common proxy headers
    forwarded_for = request.headers.get("X-Forwarded-For")
    if forwarded_for:
        # Take the first IP in the chain
        return forwarded_for.split(",")[0].strip()
    
    real_ip = request.headers.get("X-Real-IP")
    if real_ip:
        return real_ip
    
    # Fallback to direct client IP
    return request.client.host if request.client else "unknown"

def check_content_security(content: str) -> bool:
    """Check content for potential security threats."""
    # Check for script tags
    if re.search(r'<script', content, re.IGNORECASE):
        return False
    
    # Check for common XSS attack vectors
    if re.search(r'javascript:', content, re.IGNORECASE):
        return False
    
    # Check for iframe tags
    if re.search(r'<iframe', content, re.IGNORECASE):
        return False
    
    # Check for other potentially dangerous HTML elements
    if re.search(r'<(object|embed|base|link|meta)', content, re.IGNORECASE):
        return False
    
    return True

def log_security_event(event_type: str, ip: str, request: Request, details: Dict[str, Any] = None) -> None:
    """Log security-related events."""
    log_data = {
        "event": event_type,
        "ip": ip,
        "method": request.method,
        "url": str(request.url),
        "user_agent": request.headers.get("User-Agent", "unknown"),
        "details": details or {}
    }
    
    # Log with appropriate severity
    if event_type.startswith("attempt"):
        logger.warning(f"Security event: {log_data}")
    elif event_type.startswith("block"):
        logger.error(f"Security event: {log_data}")
    else:
        logger.info(f"Security event: {log_data}")

def verify_request_origin(request: Request, allowed_origins: List[str]) -> bool:
    """Verify that the request origin is allowed."""
    origin = request.headers.get("Origin")
    if not origin:
        return False
    
    return origin in allowed_origins

def validate_request_security(request: Request, allowed_origins: List[str]) -> None:
    """Validate various security aspects of a request and throw exceptions if problems found."""
    # Check for suspicious headers
    user_agent = request.headers.get("User-Agent", "")
    if not user_agent or "curl" in user_agent or "wget" in user_agent:
        ip = get_client_ip(request)
        log_security_event("suspicious_user_agent", ip, request)
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Access denied")
    
    # Check origin for non-GET requests that could modify data
    if request.method not in ["GET", "HEAD", "OPTIONS"]:
        if not verify_request_origin(request, allowed_origins):
            ip = get_client_ip(request)
            log_security_event("invalid_origin", ip, request)
            raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Invalid origin")

def validate_content_type(content_type: str) -> bool:
    """Validate if the content type is allowed."""
    allowed_types = [
        "application/json",
        "multipart/form-data",
        "application/x-www-form-urlencoded"
    ]
    
    if not content_type:
        return False
    
    return any(allowed_type in content_type for allowed_type in allowed_types)

def sanitize_input(value: str, max_length: int = 1000) -> str:
    """Sanitize user input by removing potentially dangerous characters."""
    if not isinstance(value, str):
        return str(value)[:max_length]
    
    # Remove null bytes and control characters
    sanitized = ''.join(char for char in value if ord(char) >= 32 or char in '\t\n\r')
    
    return sanitized[:max_length]

def validate_email_format(email: str) -> bool:
    """Basic email format validation."""
    import re
    pattern = r'^[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}$'
    return bool(re.match(pattern, email))

def hash_sensitive_data(data: str) -> str:
    """Hash sensitive data for logging purposes."""
    import hashlib
    return hashlib.sha256(data.encode()).hexdigest()[:16] 