import logging
from typing import Optional, Dict, Any
from google.auth.transport import requests
from google.oauth2 import id_token
from app.core.config import settings

logger = logging.getLogger(__name__)

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
    
    async def verify_token(self, token: str) -> Optional[Dict[str, Any]]:
        """
        Verify Google ID token and extract user information.
        
        Args:
            token: Google ID token from frontend
            
        Returns:
            Dict containing user info if valid, None if invalid
        """
        try:
            # Verify the token with Google's servers
            idinfo = id_token.verify_oauth2_token(
                token, 
                requests.Request(), 
                self.client_id
            )
            
            # Check that the token was issued by Google
            if idinfo['iss'] not in ['accounts.google.com', 'https://accounts.google.com']:
                logger.warning(f"Invalid token issuer: {idinfo['iss']}")
                return None
                
            # Extract user information
            user_info = {
                'google_id': idinfo['sub'],
                'email': idinfo['email'],
                'email_verified': idinfo.get('email_verified', False),
                'name': idinfo.get('name', ''),
                'given_name': idinfo.get('given_name', ''),
                'family_name': idinfo.get('family_name', ''),
                'picture': idinfo.get('picture', ''),
                'locale': idinfo.get('locale', ''),
            }
            
            # Log successful verification
            logger.info(f"Successfully verified Google token for user: {user_info['email']}")
            
            return user_info
            
        except ValueError as e:
            # Invalid token
            logger.warning(f"Google token verification failed: {str(e)}")
            return None
        except Exception as e:
            # Other errors
            logger.error(f"Unexpected error during Google token verification: {str(e)}")
            return None
    
    def extract_username_from_email(self, email: str) -> str:
        """
        Extract username from email address.
        
        Args:
            email: Email address
            
        Returns:
            Username (part before @)
        """
        return email.split('@')[0]
        
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