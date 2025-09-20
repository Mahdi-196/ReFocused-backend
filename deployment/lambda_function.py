"""
AWS Lambda handler for ReFocused FastAPI application.
Uses Mangum ASGI adapter to handle HTTP requests with enhanced debugging.
"""

import os
import json
import logging
import asyncio
import time
from typing import Dict, Any

# Configure logging for CloudWatch
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

def validate_event_format(event: Dict[str, Any]) -> bool:
    """Validate if event looks like a valid HTTP request."""
    # Check for basic HTTP event structure
    required_fields = ['httpMethod', 'path']
    has_http_fields = any(field in event for field in required_fields)

    # Check for API Gateway v1 format
    is_apigw_v1 = 'httpMethod' in event and 'path' in event

    # Check for API Gateway v2 format
    is_apigw_v2 = 'requestContext' in event and 'http' in event.get('requestContext', {})

    # Check for ALB format
    is_alb = 'httpMethod' in event and 'path' in event and 'elb' in event.get('requestContext', {})

    is_valid = has_http_fields or is_apigw_v1 or is_apigw_v2 or is_alb

    if not is_valid:
        logger.warning(f"🔍 EVENT VALIDATION: Event does not match expected HTTP formats")
        logger.warning(f"🔍 Available keys: {list(event.keys())}")
        logger.warning(f"🔍 Expected: httpMethod + path (API Gateway) or requestContext.http (v2)")

    return is_valid

def handle_with_timeout(mangum_handler, event, context, timeout_seconds=50):
    """Handle request with timeout protection and VPC debugging."""
    import signal
    import threading

    debug_start = time.time()
    request_path = event.get('path', 'UNKNOWN')
    request_method = event.get('httpMethod', 'UNKNOWN')

    # Enhanced VPC and network debugging
    logger.info(f"🚀 LAMBDA REQUEST START: {request_method} {request_path}")
    logger.info(f"🌐 VPC ENVIRONMENT CHECK:")
    logger.info(f"   - AWS_REGION: {os.getenv('AWS_REGION', 'unknown')}")
    logger.info(f"   - VPC_ID: {os.getenv('VPC_ID', 'unknown')}")
    logger.info(f"   - SUBNET_IDS: {os.getenv('SUBNET_IDS', 'unknown')}")
    logger.info(f"   - SECURITY_GROUP_ID: {os.getenv('SECURITY_GROUP_ID', 'unknown')}")
    logger.info(f"   - NAT_GATEWAY_ID: {os.getenv('NAT_GATEWAY_ID', 'unknown')}")
    logger.info(f"   - INTERNET_GATEWAY_ID: {os.getenv('INTERNET_GATEWAY_ID', 'unknown')}")

    # Database connectivity environment check
    db_url = os.getenv('DATABASE_URL', '')
    if db_url:
        # Extract hostname from database URL for connectivity analysis
        if '://' in db_url:
            try:
                from urllib.parse import urlparse
                parsed = urlparse(db_url)
                logger.info(f"📊 DATABASE CONNECTIVITY:")
                logger.info(f"   - Host: {parsed.hostname}")
                logger.info(f"   - Port: {parsed.port or 5432}")
                if parsed.hostname and ('rds' in parsed.hostname or 'amazonaws.com' in parsed.hostname):
                    logger.info(f"   - Type: AWS RDS (requires VPC connectivity)")
                elif parsed.hostname in ['localhost', '127.0.0.1']:
                    logger.error(f"   - ERROR: localhost database will not work in Lambda VPC")
                else:
                    logger.info(f"   - Type: External database")
            except Exception as parse_error:
                logger.warning(f"   - Could not parse DATABASE_URL: {str(parse_error)}")

    # Redis connectivity environment check
    redis_url = os.getenv('REDIS_URL', '')
    if redis_url:
        logger.info(f"📊 REDIS CONNECTIVITY:")
        if 'elasticache' in redis_url or 'cache.amazonaws.com' in redis_url:
            logger.info(f"   - Type: AWS ElastiCache (requires VPC connectivity)")
        elif 'localhost' in redis_url or '127.0.0.1' in redis_url:
            logger.error(f"   - ERROR: localhost Redis will not work in Lambda VPC")
        else:
            logger.info(f"   - Type: External Redis")

    def timeout_handler(signum, frame):
        timeout_time = time.time() - debug_start
        logger.error(f"🚨 LAMBDA TIMEOUT after {timeout_time:.1f}s (limit: {timeout_seconds}s)")
        logger.error(f"💀 HANGING REQUEST: {request_method} {request_path}")
        logger.error(f"🔍 TIMEOUT ANALYSIS: Request likely hanging in database or network I/O")

        # Enhanced timeout analysis
        if request_path == '/api/v1/auth/register':
            logger.error(f"🔍 REGISTER TIMEOUT: Check database connectivity and VPC routing")
        elif request_path == '/api/v1/auth/login':
            logger.error(f"🔍 LOGIN TIMEOUT: Check Redis and database connectivity")
        elif '/api/' in request_path:
            logger.error(f"🔍 API TIMEOUT: Check authentication middleware and database")

        # Log VPC troubleshooting hints
        logger.error(f"🔍 VPC TROUBLESHOOTING:")
        logger.error(f"   - Ensure Lambda is in private subnets with NAT Gateway for outbound")
        logger.error(f"   - Check security groups allow outbound to RDS (port 5432) and Redis (port 6379)")
        logger.error(f"   - Verify RDS security group allows inbound from Lambda security group")
        logger.error(f"   - Check route tables have default route (0.0.0.0/0) to NAT Gateway")

        # Log the event details that caused the hang
        logger.error(f"🔍 HANGING EVENT DETAILS: {json.dumps(event, default=str)[:500]}...")

        # Log network and database status if available
        try:
            import socket
            hostname = socket.gethostname()
            logger.error(f"🔍 LAMBDA HOSTNAME: {hostname}")
        except:
            pass

        raise TimeoutError(f"Lambda request timed out after {timeout_time:.1f} seconds processing {request_method} {request_path}")

    # Set timeout signal
    signal.signal(signal.SIGALRM, timeout_handler)
    signal.alarm(timeout_seconds)

    try:
        logger.info(f"🚀 PROCESSING: Starting {request_method} {request_path}")
        processing_start = time.time()
        result = mangum_handler(event, context)
        processing_time = time.time() - processing_start
        total_time = time.time() - debug_start

        logger.info(f"✅ REQUEST SUCCESS: {request_method} {request_path} completed in {processing_time:.2f}s (total: {total_time:.2f}s)")

        # Performance analysis
        if processing_time > 10.0:
            logger.warning(f"🐌 SLOW REQUEST: {request_method} {request_path} took {processing_time:.2f}s")
            if request_path == '/api/v1/auth/register':
                logger.warning(f"🐌 SLOW REGISTER: Check database connection pool and VPC latency")
            elif request_path == '/api/v1/auth/login':
                logger.warning(f"🐌 SLOW LOGIN: Check Redis latency and authentication overhead")

        return result
    except Exception as e:
        error_time = time.time() - debug_start
        logger.error(f"💥 REQUEST FAILED: {request_method} {request_path} after {error_time:.2f}s - {str(e)}")
        logger.exception(f"REQUEST EXCEPTION DETAILS for {request_method} {request_path}:")

        # Error analysis based on timing and path
        if error_time < 5.0:
            logger.error(f"🔍 FAST FAILURE: Likely authentication, validation, or rate limiting error")
        elif error_time < 20.0:
            logger.error(f"🔍 MEDIUM FAILURE: Likely database or business logic error")
        else:
            logger.error(f"🔍 SLOW FAILURE: Likely network connectivity or timeout issue")

        raise
    finally:
        signal.alarm(0)  # Cancel the alarm

def lambda_handler(event, context):
    """AWS Lambda entry point with enhanced VPC and connectivity debugging."""
    start_time = time.time()
    lambda_request_id = getattr(context, 'aws_request_id', 'unknown')

    try:
        logger.info(f"🚀 LAMBDA INVOCATION [{lambda_request_id}]: Started")
        logger.info(f"📊 LAMBDA CONTEXT: remaining_time={getattr(context, 'get_remaining_time_in_millis', lambda: 'unknown')()}, memory={getattr(context, 'memory_limit_in_mb', 'unknown')}MB")
        logger.info(f"📊 EVENT KEYS: {list(event.keys())}")

        # Enhanced event validation with debugging
        if not validate_event_format(event):
            # Check if this is a test event (empty or minimal)
            if not event or len(event) == 0:
                logger.info(f"🧪 TEST EVENT DETECTED [{lambda_request_id}]: Empty event received - returning health check")
                return {
                    'statusCode': 200,
                    'headers': {
                        'Content-Type': 'application/json'
                    },
                    'body': json.dumps({
                        'status': 'healthy',
                        'message': 'ReFocused Lambda function is running',
                        'timestamp': time.time(),
                        'request_id': lambda_request_id,
                        'note': 'This was a direct Lambda invocation test. For HTTP requests, use the Function URL or API Gateway.'
                    })
                }

            logger.warning(f"❌ INVALID EVENT FORMAT [{lambda_request_id}]: {json.dumps(event, default=str)[:500]}...")
            logger.warning(f"🔍 Expected keys: httpMethod, path, requestContext")
            return {
                'statusCode': 400,
                'body': json.dumps({
                    'error': 'Invalid event format',
                    'expected_keys': ['httpMethod', 'path', 'requestContext'],
                    'received_keys': list(event.keys())
                })
            }

        # Log the specific request being processed
        request_method = event.get('httpMethod', 'UNKNOWN')
        request_path = event.get('path', 'UNKNOWN')
        logger.info(f"🌐 PROCESSING REQUEST [{lambda_request_id}]: {request_method} {request_path}")

        # Import with enhanced error handling
        import_start = time.time()
        try:
            logger.info(f"📦 IMPORTING [{lambda_request_id}]: Loading FastAPI app...")
            from mangum import Mangum
            from app.main_production import app
            import_time = time.time() - import_start
            logger.info(f"✅ IMPORT SUCCESS [{lambda_request_id}]: FastAPI app loaded in {import_time:.2f}s")

            if import_time > 3.0:
                logger.warning(f"🐌 SLOW IMPORT [{lambda_request_id}]: {import_time:.2f}s - check for cold start optimization")

        except Exception as import_error:
            import_error_time = time.time() - import_start
            logger.error(f"💥 IMPORT FAILED [{lambda_request_id}]: After {import_error_time:.2f}s - {str(import_error)}")
            logger.exception(f"IMPORT EXCEPTION DETAILS [{lambda_request_id}]:")
            return {
                'statusCode': 500,
                'body': json.dumps({
                    'error': 'Application import failed',
                    'message': str(import_error),
                    'import_time': import_error_time
                })
            }

        # Create Mangum handler with logging
        logger.info(f"🔧 MANGUM SETUP [{lambda_request_id}]: Creating ASGI handler...")
        handler = Mangum(app, lifespan="off")

        # Handle request with enhanced timeout protection
        logger.info(f"🚀 REQUEST START [{lambda_request_id}]: {request_method} {request_path}")
        result = handle_with_timeout(handler, event, context)

        total_time = time.time() - start_time
        logger.info(f"✅ LAMBDA SUCCESS [{lambda_request_id}]: {request_method} {request_path} completed in {total_time:.2f}s")

        # Performance monitoring
        if total_time > 15.0:
            logger.warning(f"🐌 SLOW LAMBDA [{lambda_request_id}]: {total_time:.2f}s total time")

        return result

    except Exception as e:
        error_time = time.time() - start_time
        logger.error(f"💥 LAMBDA HANDLER FAILED [{lambda_request_id}]: After {error_time:.2f}s - {str(e)}")
        logger.exception(f"LAMBDA HANDLER EXCEPTION [{lambda_request_id}]:")

        # Enhanced error analysis
        if error_time < 1.0:
            logger.error(f"🔍 FAST LAMBDA FAILURE: Likely import or validation error")
        elif error_time < 10.0:
            logger.error(f"🔍 MEDIUM LAMBDA FAILURE: Likely application startup or configuration error")
        else:
            logger.error(f"🔍 SLOW LAMBDA FAILURE: Likely network connectivity or database timeout")

        return {
            'statusCode': 500,
            'headers': {
                'Content-Type': 'application/json',
                'Access-Control-Allow-Origin': '*',
                'Access-Control-Allow-Methods': 'GET, POST, PUT, DELETE, OPTIONS',
                'Access-Control-Allow-Headers': 'Content-Type, Authorization'
            },
            'body': json.dumps({
                'error': 'Internal server error',
                'message': str(e),
                'timestamp': time.time(),
                'request_id': lambda_request_id,
                'error_time': error_time
            })
        }

# Set Docker environment variable (required for main.py)
os.environ['DOCKER_ENV'] = 'lambda'

# Enhanced Lambda initialization logging
logger.info(f"🚀 LAMBDA INITIALIZATION: ReFocused backend starting")
logger.info(f"📍 Runtime: Python {os.sys.version.split()[0]}, AWS Lambda")
logger.info(f"📍 Environment: {os.getenv('AWS_LAMBDA_FUNCTION_NAME', 'unknown')}")
logger.info(f"📍 Memory: {os.getenv('AWS_LAMBDA_FUNCTION_MEMORY_SIZE', 'unknown')}MB")
logger.info(f"📍 Timeout: {os.getenv('AWS_LAMBDA_FUNCTION_TIMEOUT', 'unknown')}s")
logger.info(f"🚀 LAMBDA READY: Initialization complete")