import logging
from typing import Optional, Dict, Any
import asyncio
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
            logger.info("🔍 GOOGLE TOKEN VERIFICATION: Starting token verification")

            # Verify the token with Google's servers using the official library
            # This validates signature, expiration, issuer, and audience
            # Run in a thread with a 20-second timeout (increased from 8s to handle network latency)
            def _verify_sync() -> Dict[str, Any]:
                logger.info("🔍 GOOGLE TOKEN VERIFICATION: Calling Google API")
                result = id_token.verify_oauth2_token(
                    token,
                    requests.Request(),
                    self.client_id,
                )
                logger.info("✅ GOOGLE TOKEN VERIFICATION: Google API call successful")
                return result

            try:
                idinfo = await asyncio.wait_for(asyncio.to_thread(_verify_sync), timeout=20.0)
                logger.info("✅ GOOGLE TOKEN VERIFICATION: Token verified successfully")
            except asyncio.TimeoutError:
                logger.error("💥 GOOGLE TOKEN VERIFICATION: Timeout after 20 seconds")
                raise GoogleTokenValidationError("Token verification timed out - Google API may be slow or unavailable")
            
            # Verify the token was issued by Google
            logger.info(f"🔍 GOOGLE TOKEN VERIFICATION: Checking issuer: {idinfo.get('iss')}")
            if idinfo['iss'] not in ['accounts.google.com', 'https://accounts.google.com']:
                error_msg = f"Invalid token issuer: {idinfo['iss']}"
                logger.warning(f"❌ GOOGLE TOKEN VERIFICATION: {error_msg}")
                raise GoogleTokenValidationError(error_msg)

            # Verify audience matches our client ID
            logger.info(f"🔍 GOOGLE TOKEN VERIFICATION: Checking audience")
            if idinfo['aud'] != self.client_id:
                error_msg = "Token audience does not match client ID"
                logger.warning(f"❌ GOOGLE TOKEN VERIFICATION: {error_msg}")
                raise GoogleTokenValidationError(error_msg)

            # Extract and validate required fields
            google_id = idinfo.get('sub')
            email = idinfo.get('email')

            logger.info(f"🔍 GOOGLE TOKEN VERIFICATION: Extracting user data for {email}")

            if not google_id:
                error_msg = "Token missing required 'sub' field"
                logger.warning(f"❌ GOOGLE TOKEN VERIFICATION: {error_msg}")
                raise GoogleTokenValidationError(error_msg)
            if not email:
                error_msg = "Token missing required 'email' field"
                logger.warning(f"❌ GOOGLE TOKEN VERIFICATION: {error_msg}")
                raise GoogleTokenValidationError(error_msg)

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
            logger.info(f"✅ GOOGLE TOKEN VERIFICATION: Successfully verified token for user: {email}")

            return user_info

        except GoogleTokenValidationError:
            # Re-raise our custom errors
            raise
        except asyncio.TimeoutError:
            # Already handled above, but catch again just in case
            raise
        except ValueError as e:
            # Invalid token (signature, expiration, etc.)
            error_msg = f"Invalid Google token: {str(e)}"
            logger.warning(f"❌ GOOGLE TOKEN VERIFICATION: {error_msg}")
            raise GoogleTokenValidationError(error_msg)
        except GoogleAuthError as e:
            # Google Auth library specific errors
            error_msg = f"Google authentication error: {str(e)}"
            logger.warning(f"❌ GOOGLE TOKEN VERIFICATION: {error_msg}")
            raise GoogleTokenValidationError(error_msg)
        except Exception as e:
            # Other unexpected errors
            error_msg = f"Unexpected error during Google token verification: {str(e)}"
            logger.error(f"💥 GOOGLE TOKEN VERIFICATION: {error_msg}")
            logger.exception("Google token verification exception details:")
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