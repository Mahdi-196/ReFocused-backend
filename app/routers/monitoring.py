"""
Monitoring endpoints for metrics and health checks.
"""

from fastapi import APIRouter, Response, Depends
from fastapi.responses import PlainTextResponse
from prometheus_client import CONTENT_TYPE_LATEST

from app.monitoring.metrics import metrics
from app.core.config import settings

router = APIRouter()


@router.get("/metrics", response_class=PlainTextResponse)
async def get_metrics():
    """
    Prometheus metrics endpoint.
    
    Returns application metrics in Prometheus text format.
    This endpoint should be scraped by Prometheus or compatible monitoring systems.
    """
    return Response(
        content=metrics.get_metrics(),
        media_type=CONTENT_TYPE_LATEST,
        headers={
            "Cache-Control": "no-cache, no-store, must-revalidate",
            "Pragma": "no-cache",
            "Expires": "0"
        }
    )


@router.get("/health")
async def health_check():
    """
    Basic health check endpoint.
    
    Returns 200 if the application is healthy, 503 if unhealthy.
    Used by load balancers and monitoring systems.
    """
    try:
        # Test database connection
        from app.db.database import async_session
        from sqlalchemy import text
        
        async with async_session() as db:
            await db.execute(text("SELECT 1"))
        
        # Set healthy status
        metrics.set_health_status(True)
        
        return {
            "status": "healthy",
            "service": settings.APP_NAME,
            "version": "1.0.0",
            "environment": settings.APP_ENV
        }
        
    except Exception as e:
        metrics.set_health_status(False)
        
        # Return 503 for unhealthy status
        from fastapi import HTTPException, status
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail={
                "status": "unhealthy",
                "error": str(e),
                "service": settings.APP_NAME
            }
        )


@router.get("/health/ready")
async def readiness_check():
    """
    Kubernetes readiness probe.
    
    Checks if the application is ready to receive traffic.
    Should verify all critical dependencies are available.
    """
    checks = {}
    all_ready = True
    
    # Database readiness
    try:
        from app.db.database import async_session
        from sqlalchemy import text
        
        async with async_session() as db:
            await db.execute(text("SELECT 1"))
        checks["database"] = "ready"
    except Exception as e:
        checks["database"] = f"not ready: {str(e)}"
        all_ready = False
    
    # Additional readiness checks can be added here
    # For example: Redis, external APIs, etc.
    
    status_code = 200 if all_ready else 503
    
    if not all_ready:
        from fastapi import HTTPException, status
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail={
                "status": "not ready",
                "checks": checks
            }
        )
    
    return {
        "status": "ready",
        "checks": checks
    }


@router.get("/health/live")
async def liveness_check():
    """
    Kubernetes liveness probe.
    
    Simple check to verify the application is running.
    Should be lightweight and not depend on external services.
    """
    return {
        "status": "alive",
        "service": settings.APP_NAME
    }


@router.get("/info")
async def application_info():
    """
    Application information endpoint.
    
    Returns basic information about the application for debugging and monitoring.
    """
    import time
    import platform
    import sys
    
    return {
        "application": {
            "name": settings.APP_NAME,
            "version": "1.0.0",
            "environment": settings.APP_ENV,
            "debug": settings.DEBUG if hasattr(settings, 'DEBUG') else False
        },
        "system": {
            "platform": platform.platform(),
            "python_version": sys.version,
            "hostname": platform.node()
        },
        "timestamp": time.time()
    } 