from datetime import datetime, timedelta, timezone
from typing import Any, Optional, Dict

from fastapi import APIRouter, Request, Depends, HTTPException, status, Response
from sqlalchemy.ext.asyncio import AsyncSession
from jose import jwt, JWTError
from pydantic import BaseModel, EmailStr, Field, validator
from sqlalchemy import select

from app.core.security import (
    verify_password,
    create_access_token,
    create_refresh_token,
    get_password_hash,
    log_security_event,
)
from app.core.auth import get_current_user, oauth2_scheme, AuthenticationManager  # Import centralized oauth2_scheme
from app.db.database import get_db
from app.db.models import User
from app.db.models import TokenBlacklist
from app.schemas.token import TokenResponse
from app.schemas.google_auth import GoogleAuthRequest, GoogleAuthResponse, UserResponse
from app.schemas.user import ChangePasswordRequest, ChangePasswordResponse, ChangeUsernameRequest, ChangeUsernameResponse
from app.services.google_oauth import GoogleOAuthService, GoogleTokenValidationError
# from app.services.journal_service import JournalService  # Temporarily disabled
from app.core.config import settings
from app.core.enhanced_auth import enhanced_auth_service
from app.utils.security import get_client_ip
from app.core.security_config import security_config
from app.utils.rate_limiter import apply_auth_rate_limit
import logging

logger = logging.getLogger("auth_endpoints")

router = APIRouter()


class LoginRequest(BaseModel):
    email: EmailStr
    password: str = Field(..., min_length=1, max_length=200)
    grant_type: str = settings.AUTH_DEFAULT_GRANT_TYPE
    scope: Optional[str] = None

    @validator('password')
    def validate_password(cls, v):
        if not v or len(v.strip()) == 0:
            raise ValueError('Password is required')
        return v.strip()


class EnhancedLoginRequest(BaseModel):
    email: EmailStr
    password: str = Field(..., min_length=1, max_length=200)
    grant_type: str = settings.AUTH_DEFAULT_GRANT_TYPE
    scope: Optional[str] = None
    remember_me: bool = False

    @validator('password')
    def validate_password(cls, v):
        if not v or len(v.strip()) == 0:
            raise ValueError('Password is required')
        return v.strip()


class EnhancedTokenResponse(BaseModel):
    access_token: str
    refresh_token: str
    token_type: str
    expires_in: int
    remember_me: bool = False
    user: Optional[Dict[str, Any]] = None


class RegisterSchema(BaseModel):
    email: EmailStr
    password: str = Field(..., min_length=8, max_length=200)
    name: str = Field(..., min_length=1, max_length=100)

    @validator('password')
    def validate_password(cls, v):
        if len(v) < 8:
            raise ValueError('Password must be at least 8 characters long')
        return v

    @validator('name')
    def validate_name(cls, v):
        if not v or len(v.strip()) == 0:
            raise ValueError('Name is required')
        return v.strip()


async def authenticate_user(email: str, password: str, db: AsyncSession) -> User:
    """Authenticate user with email and password."""
    result = await db.execute(select(User).where(User.email == email))
    user = result.scalar_one_or_none()
    if not user or not verify_password(password, user.hashed_password):
        log_security_event(
            event_type="login_failed",
            details={"email": email, "reason": "invalid_credentials"},
            level="warning"
        )
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Incorrect email or password",
            headers={"WWW-Authenticate": "Bearer"},
        )
    return user


@router.post("/login", response_model=EnhancedTokenResponse)
async def enhanced_login(
    request: Request,
    response: Response,
    db: AsyncSession = Depends(get_db)
) -> Any:
    """Enhanced login with cookies and remember me functionality."""
    import time
    login_start_time = time.time()

    # Extract user email for debugging (will be available after parsing request)
    user_email = "unknown"

    try:
        # Apply rate limiting for login attempts
        rate_limit_start = time.time()
        await apply_auth_rate_limit(request, "login")
        rate_limit_time = time.time() - rate_limit_start

        if rate_limit_time > 2.0:
            logger.warning(f"🐌 LOGIN SLOW RATE LIMIT: {rate_limit_time:.2f}s")

        content_type = request.headers.get("content-type", "")
        # Basic brute-force protection: check recent attempts and lockout
        ip_addr = get_client_ip(request)

        if "application/json" in content_type:
            request_parse_start = time.time()
            data = await request.json()
            creds = EnhancedLoginRequest(**data)
            user_email = creds.email[:5] + "...@" + (creds.email.split('@')[1] if '@' in creds.email else 'unknown')
            request_parse_time = time.time() - request_parse_start

            logger.info(f"🔐 LOGIN START: {user_email} from {ip_addr}")

            if request_parse_time > 1.0:
                logger.warning(f"🐌 LOGIN SLOW REQUEST PARSE: {request_parse_time:.2f}s")

        if settings.AUTH_REQUIRE_GRANT_TYPE and creds.grant_type != settings.AUTH_DEFAULT_GRANT_TYPE:
            raise HTTPException(
                status.HTTP_400_BAD_REQUEST,
                detail=f"Invalid grant_type, must be '{settings.AUTH_DEFAULT_GRANT_TYPE}'",
            )
            # Pre-check lockout window if user exists
            pre_user = None
            try:
                db_lookup_start = time.time()
                result = await db.execute(select(User).where(User.email == creds.email))
                pre_user = result.scalar_one_or_none()
                db_lookup_time = time.time() - db_lookup_start

                if db_lookup_time > 2.0:
                    logger.warning(f"🐌 LOGIN SLOW DB LOOKUP: {db_lookup_time:.2f}s for {user_email}")

                if pre_user:
                    logger.info(f"🔍 LOGIN USER FOUND: {user_email} (ID: {pre_user.id})")
                    if pre_user.locked_until and pre_user.locked_until > datetime.now(timezone.utc):
                        logger.warning(f"🔒 LOGIN ACCOUNT LOCKED: {user_email}")
                        retry_after = int((pre_user.locked_until - datetime.now(timezone.utc)).total_seconds())
                        raise HTTPException(
                            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
                            detail="Account temporarily locked due to multiple failed attempts",
                            headers={"Retry-After": str(max(1, retry_after))}
                        )
                else:
                    logger.info(f"❌ LOGIN USER NOT FOUND: {user_email}")
            except HTTPException:
                raise
            except Exception as e:
                logger.error(f"💥 LOGIN DB LOOKUP ERROR: {str(e)} for {user_email}")
                pre_user = None
            try:
                auth_start = time.time()
                user = await authenticate_user(creds.email, creds.password, db)
                auth_time = time.time() - auth_start

                if auth_time > 3.0:
                    logger.warning(f"🐌 LOGIN SLOW AUTH: {auth_time:.2f}s for {user_email}")

                logger.info(f"✅ LOGIN AUTH SUCCESS: {user_email} (ID: {user.id})")

            except HTTPException as e:
                auth_time = time.time() - auth_start
                logger.warning(f"❌ LOGIN AUTH FAILED: {user_email} after {auth_time:.2f}s - {str(e.detail)}")

                # Record failed attempt and lock if needed
                try:
                    from app.db.models import LoginAttempt
                    if pre_user:
                        await LoginAttempt.record_attempt(db, pre_user.id, False, ip_addr)
                        attempts = await LoginAttempt.get_recent_attempts(db, pre_user.id, security_config.LOCKOUT_PERIOD_MINUTES)
                        failed_recent = sum(1 for a in attempts if not a.success)
                        if failed_recent >= security_config.MAX_FAILED_LOGIN_ATTEMPTS:
                            pre_user.locked_until = datetime.now(timezone.utc) + timedelta(minutes=security_config.LOCKOUT_DURATION_MINUTES)
                            await db.commit()
                except Exception:
                    pass
                raise e

            # Record successful attempt
            try:
                from app.db.models import LoginAttempt
                await LoginAttempt.record_attempt(db, user.id, True, ip_addr)
            except Exception:
                pass

            # Create session tokens with remember me
            token_start = time.time()
            tokens = enhanced_auth_service.create_session_tokens(user, creds.remember_me)
            token_time = time.time() - token_start

            if token_time > 3.0:
                logger.warning(f"🐌 LOGIN SLOW TOKEN CREATION: {token_time:.2f}s for {user_email}")

            # Set auth cookies
            enhanced_auth_service.set_auth_cookies(response, tokens)

            # Log successful login
            log_security_event(
                event_type="login_success",
                details={
                    "email": user.email,
                    "user_id": user.id,
                    "remember_me": creds.remember_me,
                    "session_id": "cookie_based"
                },
                level="info"
            )

            total_time = time.time() - login_start_time
            logger.info(f"✅ LOGIN SUCCESS: {user_email} completed in {total_time:.2f}s")

            if total_time > 10.0:
                logger.warning(f"🐌 LOGIN SLOW TOTAL: {total_time:.2f}s for {user_email}")

            return EnhancedTokenResponse(
                access_token=tokens["access_token"],
                refresh_token=tokens["refresh_token"],
                token_type="bearer",
                expires_in=tokens["expires_in"],
                remember_me=creds.remember_me,
                user={
                    "id": user.id,
                    "email": user.email,
                    "name": user.name,
                    "profile_picture": user.profile_picture
                }
            )

        elif "application/x-www-form-urlencoded" in content_type:
            form = await request.form()
            grant = form.get("grant_type", settings.AUTH_DEFAULT_GRANT_TYPE)

            if settings.AUTH_REQUIRE_GRANT_TYPE and grant != settings.AUTH_DEFAULT_GRANT_TYPE:
                raise HTTPException(
                    status.HTTP_400_BAD_REQUEST,
                    detail=f"Invalid grant_type, must be '{settings.AUTH_DEFAULT_GRANT_TYPE}'",
                )

            email = form.get("username") or form.get("email")
            if not email:
                raise HTTPException(
                    status.HTTP_400_BAD_REQUEST,
                    detail="Email is required"
                )

            remember_me = form.get("remember_me", "").lower() in ("true", "1", "yes")
            # Pre-check lockout window if user exists
            pre_user = None
            try:
                result = await db.execute(select(User).where(User.email == email))
                pre_user = result.scalar_one_or_none()
                if pre_user and pre_user.locked_until and pre_user.locked_until > datetime.now(timezone.utc):
                    retry_after = int((pre_user.locked_until - datetime.now(timezone.utc)).total_seconds())
                    raise HTTPException(
                        status_code=status.HTTP_429_TOO_MANY_REQUESTS,
                        detail="Account temporarily locked due to multiple failed attempts",
                        headers={"Retry-After": str(max(1, retry_after))}
                    )
            except HTTPException:
                raise
            except Exception:
                pre_user = None

            try:
                user = await authenticate_user(email, form["password"], db)
            except HTTPException as e:
                # Record failed attempt and lock if needed
                try:
                    from app.db.models import LoginAttempt
                    if pre_user:
                        await LoginAttempt.record_attempt(db, pre_user.id, False, ip_addr)
                        attempts = await LoginAttempt.get_recent_attempts(db, pre_user.id, security_config.LOCKOUT_PERIOD_MINUTES)
                        failed_recent = sum(1 for a in attempts if not a.success)
                        if failed_recent >= security_config.MAX_FAILED_LOGIN_ATTEMPTS:
                            pre_user.locked_until = datetime.now(timezone.utc) + timedelta(minutes=security_config.LOCKOUT_DURATION_MINUTES)
                            await db.commit()
                except Exception:
                    pass
                raise e
            # Record successful attempt
            try:
                from app.db.models import LoginAttempt
                await LoginAttempt.record_attempt(db, user.id, True, ip_addr)
            except Exception:
                pass

            # Create session tokens
            tokens = enhanced_auth_service.create_session_tokens(user, remember_me)

            # Set auth cookies
            enhanced_auth_service.set_auth_cookies(response, tokens)

            # Log successful login
            log_security_event(
                event_type="login_success",
                details={
                    "email": user.email,
                    "user_id": user.id,
                    "remember_me": remember_me
                },
                level="info"
            )

            return EnhancedTokenResponse(
                access_token=tokens["access_token"],
                refresh_token=tokens["refresh_token"],
                token_type="bearer",
                expires_in=tokens["expires_in"],
                remember_me=remember_me,
                user={
                    "id": user.id,
                    "email": user.email,
                    "name": user.name,
                    "profile_picture": user.profile_picture
                }
            )

        raise HTTPException(
            status.HTTP_415_UNSUPPORTED_MEDIA_TYPE,
            detail="Unsupported Media Type",
        )

    except HTTPException:
        # Re-raise HTTP exceptions without modification
        error_time = time.time() - login_start_time
        logger.info(f"❌ LOGIN HTTP EXCEPTION: {user_email} after {error_time:.2f}s")
        raise
    except Exception as e:
        error_time = time.time() - login_start_time
        logger.error(f"💥 LOGIN CRITICAL FAILURE: {user_email} after {error_time:.2f}s - {str(e)}")
        logger.exception("Login critical exception details:")
        raise


@router.post("/logout")
async def enhanced_logout(
    request: Request,
    response: Response,
    db: AsyncSession = Depends(get_db)
) -> Any:
    """Enhanced logout with cookie clearing and token blacklisting."""

    # Get current user if authenticated
    user = None
    try:
        user = await get_current_user(request, db)
    except:
        pass  # Not authenticated, proceed with logout anyway

    # Extract tokens from cookies for blacklisting
    access_token = request.cookies.get("access_token")
    refresh_token = request.cookies.get("refresh_token")

    # Blacklist tokens if they exist
    if access_token:
        try:
            # Decode token to get expiration
            payload = jwt.decode(access_token, settings.SECRET_KEY, algorithms=[settings.ALGORITHM])
            exp = payload.get("exp")
            if exp:
                token_blacklist = TokenBlacklist(
                    jti=payload.get("jti", "unknown"),
                    token_type="access",
                    expires_at=datetime.fromtimestamp(exp, tz=timezone.utc)
                )
                db.add(token_blacklist)
        except JWTError:
            pass  # Invalid token, ignore

    if refresh_token:
        try:
            # Decode token to get expiration
            payload = jwt.decode(refresh_token, settings.SECRET_KEY, algorithms=[settings.ALGORITHM])
            exp = payload.get("exp")
            if exp:
                token_blacklist = TokenBlacklist(
                    jti=payload.get("jti", "unknown"),
                    token_type="refresh",
                    expires_at=datetime.fromtimestamp(exp, tz=timezone.utc)
                )
                db.add(token_blacklist)
        except JWTError:
            pass  # Invalid token, ignore

    await db.commit()

    # Clear auth cookies
    enhanced_auth_service.clear_auth_cookies(response)

    # Log logout event
    log_security_event(
        event_type="logout",
        details={"user_id": user.id if user else None, "session_type": "cookie_based"},
        level="info",
        user_id=user.id if user else None
    )

    return {"message": "Successfully logged out"}


@router.post("/refresh", response_model=TokenResponse)
async def enhanced_refresh_token(
    request: Request,
    response: Response,
    db: AsyncSession = Depends(get_db)
) -> Any:
    """Enhanced token refresh with cookie support."""

    # Try to get refresh token from cookies first, then from body
    refresh_token = request.cookies.get("refresh_token")

    if not refresh_token:
        # Fallback to JSON body for API clients
        try:
            body = await request.json()
            refresh_token = body.get("refresh_token")
        except:
            pass

    if not refresh_token:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Refresh token not found",
            headers={"WWW-Authenticate": "Bearer"},
        )

    try:
        # Validate refresh token
        payload = jwt.decode(refresh_token, settings.SECRET_KEY, algorithms=[settings.ALGORITHM])
        email: str = payload.get("sub")
        token_type: str = payload.get("type")

        if email is None or token_type != "refresh":
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Invalid refresh token",
                headers={"WWW-Authenticate": "Bearer"},
            )

        # Check if token is blacklisted
        jti = payload.get("jti")
        if jti:
            result = await db.execute(
                select(TokenBlacklist).where(
                    TokenBlacklist.jti == jti,
                    TokenBlacklist.token_type == "refresh"
                )
            )
            if result.scalar_one_or_none():
                raise HTTPException(
                    status_code=status.HTTP_401_UNAUTHORIZED,
                    detail="Token has been revoked",
                    headers={"WWW-Authenticate": "Bearer"},
                )

    except JWTError:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid refresh token",
            headers={"WWW-Authenticate": "Bearer"},
        )

    # Get user from database
    result = await db.execute(select(User).where(User.email == email))
    user = result.scalar_one_or_none()
    if user is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="User not found",
            headers={"WWW-Authenticate": "Bearer"},
        )

    # Check if user is active
    if not user.is_active:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Inactive user",
            headers={"WWW-Authenticate": "Bearer"},
        )

    # Create new tokens
    tokens = enhanced_auth_service.create_session_tokens(user, remember_me=True)

    # Update cookies
    enhanced_auth_service.set_auth_cookies(response, tokens)

    # Blacklist old refresh token
    if jti:
        try:
            old_token_blacklist = TokenBlacklist(
                jti=jti,
                token_type="refresh",
                expires_at=datetime.fromtimestamp(payload.get("exp"), tz=timezone.utc)
            )
            db.add(old_token_blacklist)
            await db.commit()
        except Exception:
            pass  # Don't fail refresh if blacklisting fails

    # Log refresh event
    log_security_event(
        event_type="token_refresh",
        details={"user_id": user.id, "session_type": "cookie_based"},
        level="info",
        user_id=user.id
    )

    return TokenResponse(
        access_token=tokens["access_token"],
        refresh_token=tokens["refresh_token"],
        token_type="bearer",
        expires_in=tokens["expires_in"]
    )


@router.post("/refresh-token", response_model=TokenResponse)
async def enhanced_refresh_token_alias(
    request: Request,
    response: Response,
    db: AsyncSession = Depends(get_db)
) -> Any:
    """Alias for clients calling /auth/refresh-token; delegates to refresh."""
    return await enhanced_refresh_token(request, response, db)

@router.post("/register", status_code=status.HTTP_201_CREATED)
async def register(data: RegisterSchema, response: Response, request: Request, db: AsyncSession = Depends(get_db)) -> Any:
    import time
    import asyncio
    import os

    register_start_time = time.time()
    user_email = f"{data.email[:5]}...@{data.email.split('@')[1] if '@' in data.email else 'unknown'}"

    # Network and infrastructure debugging
    logger.info(f"🚀 REGISTER START: {user_email}")
    logger.info(f"🌐 AWS_LAMBDA_FUNCTION_NAME: {os.getenv('AWS_LAMBDA_FUNCTION_NAME', 'None')}")
    logger.info(f"🌐 DATABASE_URL: {settings.DATABASE_URL[:50]}...")
    logger.info(f"🌐 REDIS_URL: {settings.REDIS_URL[:30]}...")

    # VPC and network connectivity check
    logger.info(f"🔌 NETWORK ENV CHECK:")
    logger.info(f"   - AWS_REGION: {os.getenv('AWS_REGION', 'unknown')}")
    logger.info(f"   - AWS_DEFAULT_REGION: {os.getenv('AWS_DEFAULT_REGION', 'unknown')}")
    logger.info(f"   - VPC_ID: {os.getenv('VPC_ID', 'unknown')}")
    logger.info(f"   - SUBNET_IDS: {os.getenv('SUBNET_IDS', 'unknown')}")
    logger.info(f"   - SECURITY_GROUP_ID: {os.getenv('SECURITY_GROUP_ID', 'unknown')}")

    try:
        # Step 1: Rate limiting with detailed network debugging
        logger.info(f"📊 STEP 1/7: Rate limiting check for {user_email}")
        rate_limit_start = time.time()

        try:
            await apply_auth_rate_limit(request, "register")
            rate_limit_time = time.time() - rate_limit_start
            logger.info(f"✅ STEP 1/7 COMPLETE: Rate limit check in {rate_limit_time:.2f}s")

            if rate_limit_time > 2.0:
                logger.warning(f"🐌 SLOW RATE LIMIT: {rate_limit_time:.2f}s - possible Redis connectivity issue")
        except Exception as rate_error:
            rate_error_time = time.time() - rate_limit_start
            logger.error(f"💥 STEP 1/7 FAILED: Rate limit after {rate_error_time:.2f}s - {str(rate_error)}")
            logger.exception("Rate limit exception details:")
            raise

        # Step 2: Database connectivity test
        logger.info(f"📊 STEP 2/7: Database connectivity test for {user_email}")
        db_test_start = time.time()

        try:
            from sqlalchemy import text
            test_result = await db.execute(text("SELECT 1 as test_value"))
            test_value = test_result.scalar()
            db_test_time = time.time() - db_test_start

            if test_value == 1:
                logger.info(f"✅ STEP 2/7 COMPLETE: Database connectivity OK in {db_test_time:.2f}s")
            else:
                logger.error(f"💥 STEP 2/7 FAILED: Database test returned {test_value} instead of 1")
                raise Exception(f"Database connectivity test failed: got {test_value}")

            if db_test_time > 3.0:
                logger.warning(f"🐌 SLOW DB CONNECTIVITY: {db_test_time:.2f}s - possible VPC/NAT gateway issue")

        except Exception as db_test_error:
            db_test_error_time = time.time() - db_test_start
            logger.error(f"💥 STEP 2/7 FAILED: Database connectivity test after {db_test_error_time:.2f}s - {str(db_test_error)}")
            logger.exception("Database connectivity exception details:")
            raise

        # Step 3: Check for existing user
        logger.info(f"📊 STEP 3/7: Checking existing user for {user_email}")
        user_check_start = time.time()

        try:
            logger.info(f"   - Executing: SELECT User WHERE email = '{data.email[:10]}...'")
            result = await db.execute(select(User).where(User.email == data.email))
            logger.info(f"   - Query executed, fetching result...")
            existing_user = result.scalar_one_or_none()
            user_check_time = time.time() - user_check_start

            logger.info(f"✅ STEP 3/7 COMPLETE: User lookup in {user_check_time:.2f}s (exists: {existing_user is not None})")

            if user_check_time > 3.0:
                logger.warning(f"🐌 SLOW USER LOOKUP: {user_check_time:.2f}s - possible database index issue")

        except Exception as user_check_error:
            user_check_error_time = time.time() - user_check_start
            logger.error(f"💥 STEP 3/7 FAILED: User lookup after {user_check_error_time:.2f}s - {str(user_check_error)}")
            logger.exception("User lookup exception details:")
            raise

        if existing_user:
            logger.info(f"❌ REGISTER EMAIL EXISTS: {user_email}")
            raise HTTPException(status.HTTP_400_BAD_REQUEST, detail="Email already registered")

        # Step 4: DeletedEmail cooldown disabled per request
        logger.info(f"📊 STEP 4/7: Deleted email cooldown disabled")

        # Step 5: Password hashing with detailed timing
        logger.info(f"📊 STEP 5/7: Password hashing for {user_email}")
        password_hash_start = time.time()

        try:
            logger.info(f"   - Starting bcrypt password hash...")
            hashed_password = get_password_hash(data.password)
            password_hash_time = time.time() - password_hash_start

            logger.info(f"✅ STEP 5/7 COMPLETE: Password hashing in {password_hash_time:.2f}s")

            if password_hash_time > 8.0:
                logger.warning(f"🐌 SLOW PASSWORD HASH: {password_hash_time:.2f}s - high CPU load or bcrypt rounds too high")

        except Exception as hash_error:
            hash_error_time = time.time() - password_hash_start
            logger.error(f"💥 STEP 5/7 FAILED: Password hashing after {hash_error_time:.2f}s - {str(hash_error)}")
            logger.exception("Password hashing exception details:")
            raise

        # Step 6: User creation and database commit
        logger.info(f"📊 STEP 6/7: Creating user and database commit for {user_email}")
        db_commit_start = time.time()

        try:
            logger.info(f"   - Creating User object...")
            user = User(
                email=data.email,
                hashed_password=hashed_password,
                name=data.name,
                is_active=True,
            )

            logger.info(f"   - Adding user to session...")
            db.add(user)

            logger.info(f"   - Committing to database...")
            await db.commit()

            logger.info(f"   - Refreshing user object...")
            await db.refresh(user)

            db_commit_time = time.time() - db_commit_start
            logger.info(f"✅ STEP 6/7 COMPLETE: User creation and commit in {db_commit_time:.2f}s (user_id: {user.id})")

            if db_commit_time > 8.0:
                logger.warning(f"🐌 SLOW DB COMMIT: {db_commit_time:.2f}s - possible database lock or VPC network issue")

        except Exception as commit_error:
            commit_error_time = time.time() - db_commit_start
            logger.error(f"💥 STEP 6/7 FAILED: Database commit after {commit_error_time:.2f}s - {str(commit_error)}")
            logger.exception("Database commit exception details:")

            # Attempt rollback
            try:
                logger.info(f"   - Attempting database rollback...")
                await db.rollback()
                logger.info(f"   - Rollback successful")
            except Exception as rollback_error:
                logger.error(f"   - Rollback failed: {str(rollback_error)}")
            raise

        # Step 7: Token creation and response
        logger.info(f"📊 STEP 7/7: Token creation for {user_email}")
        token_start = time.time()

        try:
            logger.info(f"   - Creating session tokens...")
            tokens = enhanced_auth_service.create_session_tokens(user, remember_me=False)

            logger.info(f"   - Setting auth cookies...")
            enhanced_auth_service.set_auth_cookies(response, tokens)

            token_time = time.time() - token_start
            logger.info(f"✅ STEP 7/7 COMPLETE: Token creation in {token_time:.2f}s")

            if token_time > 5.0:
                logger.warning(f"🐌 SLOW TOKEN CREATION: {token_time:.2f}s - possible JWT signing issue")

        except Exception as token_error:
            token_error_time = time.time() - token_start
            logger.error(f"💥 STEP 7/7 FAILED: Token creation after {token_error_time:.2f}s - {str(token_error)}")
            logger.exception("Token creation exception details:")
            raise

        # Log security event
        log_security_event(
            event_type="registration_success",
            details={"email": user.email, "user_id": user.id},
            level="info"
        )

        response_data = {
            "message": "User created successfully",
            "access_token": tokens["access_token"],
            "refresh_token": tokens["refresh_token"],
            "token_type": "bearer",
            "expires_in": tokens["expires_in"]
        }

        total_time = time.time() - register_start_time
        logger.info(f"🎉 REGISTER SUCCESS: {user_email} completed in {total_time:.2f}s (user_id: {user.id})")

        if total_time > 15.0:
            logger.warning(f"🐌 SLOW REGISTER TOTAL: {total_time:.2f}s - investigate network or database performance")

        return response_data

    except HTTPException:
        # Re-raise HTTP exceptions without modification
        error_time = time.time() - register_start_time
        logger.info(f"❌ REGISTER HTTP EXCEPTION: {user_email} after {error_time:.2f}s")
        raise
    except Exception as e:
        error_time = time.time() - register_start_time
        logger.error(f"💥 REGISTER CRITICAL FAILURE: {user_email} after {error_time:.2f}s - {str(e)}")
        logger.exception("Register critical exception details:")

        # Attempt to get current step for debugging
        current_step = "unknown"
        if error_time < 2:
            current_step = "rate_limiting"
        elif error_time < 5:
            current_step = "database_connectivity"
        elif error_time < 10:
            current_step = "user_lookup"
        elif error_time < 15:
            current_step = "deleted_email_check"
        elif error_time < 25:
            current_step = "password_hashing"
        elif error_time < 40:
            current_step = "database_commit"
        else:
            current_step = "token_creation"

        logger.error(f"💥 FAILURE ANALYSIS: Likely failed during step '{current_step}' at {error_time:.2f}s")
        raise


@router.post("/google", response_model=GoogleAuthResponse)
async def google_auth(
    request: GoogleAuthRequest,
    response: Response,
    db: AsyncSession = Depends(get_db)
) -> Any:
    """
    Authenticate user with Google OAuth ID token.

    This endpoint:
    1. Verifies the Google ID token using secure validation
    2. Creates a new user if they don't exist
    3. Returns a JWT access token for API access
    """
    import logging
    logger = logging.getLogger(__name__)

    try:
        logger.info(f"Google OAuth request received with token length: {len(request.id_token)}")

        google_service = GoogleOAuthService()

        # Verify Google token and extract user info with enhanced security validation
        logger.info("Attempting to verify Google token...")
        user_info = await google_service.verify_token(request.id_token)

        logger.info(f"Google token verified successfully for email: {user_info.get('email')}")

        # Check if email is verified
        if not user_info.get('email_verified', False):
            logger.warning(f"Email not verified for user: {user_info['email']}")
            log_security_event(
                event_type="google_auth_failed",
                details={"reason": "email_not_verified", "email": user_info['email']},
                level="warning"
            )
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Google account email is not verified"
            )

        logger.info("Starting database operations...")

        # Check if user exists by Google ID first
        logger.info(f"Checking for existing user with Google ID: {user_info['google_id']}")
        result = await db.execute(
            select(User).where(User.google_id == user_info['google_id'])
        )
        user = result.scalar_one_or_none()

        # If not found by Google ID, check by email
        if not user:
            logger.info(f"No user found with Google ID, checking by email: {user_info['email']}")
            result = await db.execute(
                select(User).where(User.email == user_info['email'])
            )
            user = result.scalar_one_or_none()

            # If found by email, update with Google ID (link accounts)
            if user:
                logger.info(f"Found existing user by email, linking Google account: {user.email}")
                user.google_id = user_info['google_id']
                user.auth_provider = "google"
                user.profile_picture = user_info.get('picture')
                if not user.name and user_info.get('name'):
                    user.name = user_info['name']
                await db.commit()
                await db.refresh(user)

                log_security_event(
                    event_type="account_linked",
                    details={"email": user.email, "provider": "google"},
                    level="info",
                    user_id=user.id
                )

        # If user doesn't exist, create new one
        if not user:
            logger.info("Creating new user from Google OAuth data")

            # Get existing emails to ensure uniqueness
            email_check = await db.execute(select(User).where(User.email == user_info['email']))
            if email_check.scalar_one_or_none():
                logger.warning(f"Email {user_info['email']} already exists but with different Google ID")
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail="Email address is already registered with a different account"
                )

            # DeletedEmail cooldown disabled per request

            user = User(
                email=user_info['email'],
                google_id=user_info['google_id'],
                name=user_info.get('name', 'Google User'),
                profile_picture=user_info.get('picture'),
                auth_provider="google",
                is_active=True
            )
            db.add(user)
            await db.commit()
            await db.refresh(user)

            # Set up default journal collection for new user
            # await JournalService.setup_user_journal_async(db, user.id)  # Temporarily disabled

            logger.info(f"New user created with Google OAuth: {user.email} (ID: {user.id})")

            log_security_event(
                event_type="google_registration_success",
                details={"email": user.email, "user_id": user.id, "google_id": user_info['google_id']},
                level="info",
                user_id=user.id
            )

        # Check if user is active
        if not user.is_active:
            logger.warning(f"Inactive user attempted login: {user.email}")
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Account is deactivated"
            )

        # Create access token
        access_token_expires = timedelta(minutes=settings.ACCESS_TOKEN_EXPIRE_MINUTES)
        access_token = create_access_token(
            data={"sub": user.email, "user_id": user.id},
            expires_delta=access_token_expires
        )

        logger.info(f"Google OAuth successful for user: {user.email}")

        log_security_event(
            event_type="google_login_success",
            details={"email": user.email, "user_id": user.id},
            level="info",
            user_id=user.id
        )

        return GoogleAuthResponse(
            access_token=access_token,
            token_type="bearer",
            expires_in=settings.ACCESS_TOKEN_EXPIRE_MINUTES * 60,
            user=UserResponse(
                id=user.id,
                email=user.email,
                name=user.name,
                profile_picture=user.profile_picture,
                auth_provider=user.auth_provider,
                is_active=user.is_active
            )
        )

    except HTTPException:
        raise
    except GoogleTokenValidationError as e:
        logger.error(f"Google token validation failed: {str(e)}")
        log_security_event(
            event_type="google_auth_failed",
            details={"reason": "token_validation_error", "error": str(e)},
            level="warning"
        )
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid Google token"
        )
    except Exception as e:
        logger.error(f"Google OAuth error: {str(e)}")
        logger.exception("Google OAuth exception details:")
        log_security_event(
            event_type="google_auth_error",
            details={"error": str(e)},
            level="error"
        )
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Google authentication failed"
        )


@router.post("/change-password", response_model=ChangePasswordResponse)
async def change_password(
    request: ChangePasswordRequest,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    """Change user password with current password verification."""

    # Verify current password
    if not verify_password(request.current_password, current_user.hashed_password):
        log_security_event(
            event_type="password_change_failed",
            details={"user_id": current_user.id, "reason": "invalid_current_password"},
            level="warning",
            user_id=current_user.id
        )
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Current password is incorrect"
        )

    # Hash new password
    new_hashed_password = get_password_hash(request.new_password)

    # Update password in database
    current_user.hashed_password = new_hashed_password
    await db.commit()

    log_security_event(
        event_type="password_change_success",
        details={"user_id": current_user.id},
        level="info",
        user_id=current_user.id
    )

    return ChangePasswordResponse(message="Password changed successfully")


@router.post("/change-username", response_model=ChangeUsernameResponse)
async def change_username(
    request: ChangeUsernameRequest,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    """Change username with validation."""

    # Check if username already exists
    result = await db.execute(select(User).where(User.name == request.new_username))
    if result.scalar_one_or_none():
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Username already taken"
        )

    # Update username
    old_username = current_user.name
    current_user.name = request.new_username
    await db.commit()

    log_security_event(
        event_type="username_change",
        details={"user_id": current_user.id, "old_username": old_username, "new_username": request.new_username},
        level="info",
        user_id=current_user.id
    )

    return ChangeUsernameResponse(
        message="Username changed successfully",
        new_username=request.new_username
    )