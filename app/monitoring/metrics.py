"""
Production metrics collection for monitoring and alerting.
"""

import time
import asyncio
from typing import Dict, Optional, Callable, Any
from functools import wraps
from prometheus_client import (
    Counter, Histogram, Gauge, Summary, 
    CollectorRegistry, generate_latest, CONTENT_TYPE_LATEST
)
from fastapi import Request, Response
import psutil
import threading

from app.core.config import settings


REGISTRY = CollectorRegistry()

HTTP_REQUESTS_TOTAL = Counter(
    'http_requests_total',
    'Total HTTP requests by method, endpoint and status',
    ['method', 'endpoint', 'status_code'],
    registry=REGISTRY
)

HTTP_REQUEST_DURATION = Histogram(
    'http_request_duration_seconds',
    'HTTP request duration in seconds',
    ['method', 'endpoint'],
    registry=REGISTRY
)

HTTP_REQUEST_SIZE = Histogram(
    'http_request_size_bytes',
    'HTTP request size in bytes',
    ['method', 'endpoint'],
    registry=REGISTRY
)

HTTP_RESPONSE_SIZE = Histogram(
    'http_response_size_bytes',
    'HTTP response size in bytes',
    ['method', 'endpoint', 'status_code'],
    registry=REGISTRY
)

AUTH_ATTEMPTS_TOTAL = Counter(
    'auth_attempts_total',
    'Total authentication attempts',
    ['method', 'result'],
    registry=REGISTRY
)

ACTIVE_SESSIONS = Gauge(
    'active_sessions_total',
    'Currently active user sessions',
    registry=REGISTRY
)

TOKEN_REFRESH_TOTAL = Counter(
    'token_refresh_total',
    'Total token refresh attempts',
    ['result'],
    registry=REGISTRY
)

DB_CONNECTIONS_ACTIVE = Gauge(
    'database_connections_active',
    'Active database connections',
    registry=REGISTRY
)

DB_QUERY_DURATION = Histogram(
    'database_query_duration_seconds',
    'Database query duration in seconds',
    ['operation', 'table'],
    registry=REGISTRY
)

DB_QUERIES_TOTAL = Counter(
    'database_queries_total',
    'Total database queries',
    ['operation', 'table', 'result'],
    registry=REGISTRY
)

USERS_REGISTERED_TOTAL = Counter(
    'users_registered_total',
    'Total user registrations',
    ['method'],
    registry=REGISTRY
)

HABITS_CREATED_TOTAL = Counter(
    'habits_created_total',
    'Total habits created',
    registry=REGISTRY
)

HABIT_COMPLETIONS_TOTAL = Counter(
    'habit_completions_total',
    'Total habit completions',
    registry=REGISTRY
)

GOALS_CREATED_TOTAL = Counter(
    'goals_created_total',
    'Total goals created',
    ['goal_type', 'duration'],
    registry=REGISTRY
)

GOALS_COMPLETED_TOTAL = Counter(
    'goals_completed_total',
    'Total goals completed',
    ['goal_type', 'duration'],
    registry=REGISTRY
)

SYSTEM_CPU_USAGE = Gauge(
    'system_cpu_usage_percent',
    'System CPU usage percentage',
    registry=REGISTRY
)

SYSTEM_MEMORY_USAGE = Gauge(
    'system_memory_usage_bytes',
    'System memory usage in bytes',
    registry=REGISTRY
)

SYSTEM_DISK_USAGE = Gauge(
    'system_disk_usage_bytes',
    'System disk usage in bytes',
    ['device'],
    registry=REGISTRY
)

APP_HEALTH_STATUS = Gauge(
    'app_health_status',
    'Application health status (1=healthy, 0=unhealthy)',
    registry=REGISTRY
)

APP_UPTIME_SECONDS = Gauge(
    'app_uptime_seconds',
    'Application uptime in seconds',
    registry=REGISTRY
)

ERRORS_TOTAL = Counter(
    'errors_total',
    'Total application errors',
    ['error_type', 'endpoint'],
    registry=REGISTRY
)

SECURITY_EVENTS_TOTAL = Counter(
    'security_events_total',
    'Total security events',
    ['event_type', 'severity'],
    registry=REGISTRY
)

CACHE_HITS = Counter(
    'cache_hits_total',
    'Total cache hits',
    ['cache_type'],
    registry=REGISTRY
)

CACHE_MISSES = Counter(
    'cache_misses_total',
    'Total cache misses',
    ['cache_type'],
    registry=REGISTRY
)


class MetricsCollector:
    """Centralized metrics collection class."""
    
    def __init__(self):
        self.start_time = time.time()
        self._system_metrics_enabled = settings.is_production()
        
        if self._system_metrics_enabled:
            self._start_system_metrics_collection()
    
    def _start_system_metrics_collection(self):
        """Start background system metrics collection."""
        def collect_system_metrics():
            while True:
                try:
                    cpu_percent = psutil.cpu_percent(interval=1)
                    SYSTEM_CPU_USAGE.set(cpu_percent)
                    
                    memory = psutil.virtual_memory()
                    SYSTEM_MEMORY_USAGE.set(memory.used)
                    
                    for partition in psutil.disk_partitions():
                        try:
                            disk_usage = psutil.disk_usage(partition.mountpoint)
                            SYSTEM_DISK_USAGE.labels(device=partition.device).set(disk_usage.used)
                        except PermissionError:
                            continue
                    
                    uptime = time.time() - self.start_time
                    APP_UPTIME_SECONDS.set(uptime)
                    
                    time.sleep(30)
                    
                except Exception as e:
                    pass
        
        thread = threading.Thread(target=collect_system_metrics, daemon=True)
        thread.start()
    
    def record_http_request(self, method: str, endpoint: str, status_code: int, duration: float, request_size: int = 0, response_size: int = 0):
        """Record HTTP request metrics."""
        HTTP_REQUESTS_TOTAL.labels(
            method=method,
            endpoint=endpoint,
            status_code=str(status_code)
        ).inc()
        
        HTTP_REQUEST_DURATION.labels(
            method=method,
            endpoint=endpoint
        ).observe(duration)
        
        if request_size > 0:
            HTTP_REQUEST_SIZE.labels(
                method=method,
                endpoint=endpoint
            ).observe(request_size)
        
        if response_size > 0:
            HTTP_RESPONSE_SIZE.labels(
                method=method,
                endpoint=endpoint,
                status_code=str(status_code)
            ).observe(response_size)
    
    def record_auth_attempt(self, method: str, result: str):
        """Record authentication attempt."""
        AUTH_ATTEMPTS_TOTAL.labels(method=method, result=result).inc()
    
    def record_token_refresh(self, result: str):
        """Record token refresh attempt."""
        TOKEN_REFRESH_TOTAL.labels(result=result).inc()
    
    def set_active_sessions(self, count: int):
        """Set active sessions count."""
        ACTIVE_SESSIONS.set(count)
    
    def record_db_query(self, operation: str, table: str, duration: float, result: str = "success"):
        """Record database query metrics."""
        DB_QUERIES_TOTAL.labels(
            operation=operation,
            table=table,
            result=result
        ).inc()
        
        DB_QUERY_DURATION.labels(
            operation=operation,
            table=table
        ).observe(duration)
    
    def set_db_connections(self, count: int):
        """Set active database connections count."""
        DB_CONNECTIONS_ACTIVE.set(count)
    
    def record_user_registration(self, method: str = "email"):
        """Record user registration."""
        USERS_REGISTERED_TOTAL.labels(method=method).inc()
    
    def record_habit_created(self):
        """Record habit creation."""
        HABITS_CREATED_TOTAL.inc()
    
    def record_habit_completion(self):
        """Record habit completion."""
        HABIT_COMPLETIONS_TOTAL.inc()
    
    def record_goal_created(self, goal_type: str, duration: str):
        """Record goal creation."""
        GOALS_CREATED_TOTAL.labels(goal_type=goal_type, duration=duration).inc()
    
    def record_goal_completed(self, goal_type: str, duration: str):
        """Record goal completion."""
        GOALS_COMPLETED_TOTAL.labels(goal_type=goal_type, duration=duration).inc()
    
    def record_error(self, error_type: str, endpoint: str):
        """Record application error."""
        ERRORS_TOTAL.labels(error_type=error_type, endpoint=endpoint).inc()
    
    def record_security_event(self, event_type: str, severity: str = "medium"):
        """Record security event."""
        SECURITY_EVENTS_TOTAL.labels(event_type=event_type, severity=severity).inc()
    
    def set_health_status(self, healthy: bool):
        """Set application health status."""
        APP_HEALTH_STATUS.set(1 if healthy else 0)
    
    def get_metrics(self) -> str:
        """Get Prometheus metrics in text format."""
        return generate_latest(REGISTRY).decode('utf-8')


# Global metrics collector instance
metrics = MetricsCollector()


def track_time(metric: Histogram, labels: Optional[Dict[str, str]] = None):
    """Decorator to track execution time."""
    def decorator(func: Callable) -> Callable:
        @wraps(func)
        def sync_wrapper(*args, **kwargs):
            start_time = time.time()
            try:
                result = func(*args, **kwargs)
                return result
            finally:
                duration = time.time() - start_time
                if labels:
                    metric.labels(**labels).observe(duration)
                else:
                    metric.observe(duration)
        
        @wraps(func)
        async def async_wrapper(*args, **kwargs):
            start_time = time.time()
            try:
                result = await func(*args, **kwargs)
                return result
            finally:
                duration = time.time() - start_time
                if labels:
                    metric.labels(**labels).observe(duration)
                else:
                    metric.observe(duration)
        
        return async_wrapper if asyncio.iscoroutinefunction(func) else sync_wrapper
    return decorator


def count_calls(metric: Counter, labels: Optional[Dict[str, str]] = None):
    """Decorator to count function calls."""
    def decorator(func: Callable) -> Callable:
        @wraps(func)
        def wrapper(*args, **kwargs):
            if labels:
                metric.labels(**labels).inc()
            else:
                metric.inc()
            return func(*args, **kwargs)
        
        return wrapper
    return decorator 