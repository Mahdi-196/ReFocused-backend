import logging
from typing import Optional, Dict, Any
from google.auth.transport import requests
from google.oauth2 import id_token
from google.auth.exceptions import GoogleAuthError
from app.core.config import settings

logger = logging.getLogger(__name__)

class GoogleTokenValidationError(Exception):
    """Custom exception for Google token validation errors."""
    pass

class GoogleOAuthService:
    """Service for handling Google OAuth token verification and user data extraction."""
    
    def __init__(self):
        self.client_id = self._get_client_id()
        
    def _get_client_id(self) -> str:
        """Get Google Client ID from environment variables."""
        client_id = getattr(settings, 'GOOGLE_CLIENT_ID', None)
        if not client_id:
            raise ValueError(
                "GOOGLE_CLIENT_ID environment variable is required for Google OAuth. "
                "Please set it in your environment or disable Google OAuth endpoints."
            )
        return client_id
    
    async def verify_token(self, token: str) -> Dict[str, Any]:
        """
        Verify Google ID token and extract user information.
        
        Args:
            token: Google ID token from frontend
            
        Returns:
            Dict containing user info if valid
            
        Raises:
            GoogleTokenValidationError: If token validation fails
        """
        if not token or not token.strip():
            raise GoogleTokenValidationError("Token cannot be empty")
            
        try:
            # Verify the token with Google's servers using the official library
            # This validates signature, expiration, issuer, and audience
            # Create request with timeout to avoid hanging
            import urllib3
            http = urllib3.PoolManager(timeout=urllib3.Timeout(total=10))
            request = requests.Request(http=http)

            logger.info(f"Verifying Google token with client_id: {self.client_id[:20]}...")
            idinfo = id_token.verify_oauth2_token(
                token,
                request,
                self.client_id
            )
            logger.info("Google token verification completed successfully")
            
            # Verify the token was issued by Google
            if idinfo['iss'] not in ['accounts.google.com', 'https://accounts.google.com']:
                raise GoogleTokenValidationError(f"Invalid token issuer: {idinfo['iss']}")
            
            # Verify audience matches our client ID
            if idinfo['aud'] != self.client_id:
                raise GoogleTokenValidationError("Token audience does not match client ID")
                
            # Extract and validate required fields
            google_id = idinfo.get('sub')
            email = idinfo.get('email')
            
            if not google_id:
                raise GoogleTokenValidationError("Token missing required 'sub' field")
            if not email:
                raise GoogleTokenValidationError("Token missing required 'email' field")
            
            # Extract user information
            user_info = {
                'google_id': google_id,
                'email': email,
                'email_verified': idinfo.get('email_verified', False),
                'name': idinfo.get('name', ''),
                'given_name': idinfo.get('given_name', ''),
                'family_name': idinfo.get('family_name', ''),
                'picture': idinfo.get('picture', ''),
                'locale': idinfo.get('locale', ''),
            }
            
            # Log successful verification
            logger.info(f"Successfully verified Google token for user: {email}")
            
            return user_info
            
        except ValueError as e:
            # Invalid token (signature, expiration, etc.)
            error_msg = f"Invalid Google token: {str(e)}"
            logger.warning(error_msg)
            raise GoogleTokenValidationError(error_msg)
        except GoogleAuthError as e:
            # Google Auth library specific errors
            error_msg = f"Google authentication error: {str(e)}"
            logger.warning(error_msg)
            raise GoogleTokenValidationError(error_msg)
        except Exception as e:
            # Other unexpected errors
            error_msg = f"Unexpected error during Google token verification: {str(e)}"
            logger.error(error_msg)
            raise GoogleTokenValidationError(error_msg)
    
    async def verify_id_token(self, id_token: str) -> Dict[str, Any]:
        """
        Verify Google ID token and extract user information.
        Alias for verify_token method to match auth endpoint expectations.
        
        Args:
            id_token: Google ID token from frontend
            
        Returns:
            Dict containing user info if valid
            
        Raises:
            GoogleTokenValidationError: If token validation fails
        """
        return await self.verify_token(id_token)
    
    def extract_username_from_email(self, email: str) -> str:
        """
        Extract username from email address.
        
        Args:
            email: Email address
            
        Returns:
            Username (part before @)
        """
        return email.split('@')[0]
        
    def extract_email_from_user_info(self, user_info: Dict[str, Any]) -> str:
        """
        Extract email from user info.
        
        Args:
            user_info: User information from Google
            
        Returns:
            Email address
        """
        return user_info.get('email', '')
    
    def generate_unique_email(self, base_email: str, existing_emails: set) -> str:
        """
        Generate a unique email by adding suffix if needed.
        
        Args:
            base_email: Base email to use
            existing_emails: Set of existing emails
            
        Returns:
            Unique email
        """
        if base_email not in existing_emails:
            return base_email
            
        username, domain = base_email.split('@', 1)
        counter = 1
        while f"{username}_{counter}@{domain}" in existing_emails:
            counter += 1
            
        return f"{username}_{counter}@{domain}"
    
    def generate_unique_username(self, base_username: str, existing_usernames: set) -> str:
        """
        Generate a unique username by adding suffix if needed.
        
        Args:
            base_username: Base username to use
            existing_usernames: Set of existing usernames
            
        Returns:
            Unique username
        """
        if base_username not in existing_usernames:
            return base_username
            
        counter = 1
        while f"{base_username}_{counter}" in existing_usernames:
            counter += 1
            
        return f"{base_username}_{counter}" 