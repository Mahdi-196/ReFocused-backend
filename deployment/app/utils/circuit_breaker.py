"""
Circuit breaker pattern for database connections.
Prevents cascading failures by failing fast when database is unhealthy.
"""
import time
import logging
from typing import Optional
from enum import Enum

logger = logging.getLogger("refocused.circuit_breaker")

class CircuitState(Enum):
    CLOSED = "closed"      # Normal operation
    OPEN = "open"          # Failing fast
    HALF_OPEN = "half_open"  # Testing if service recovered

class DatabaseCircuitBreaker:
    """
    Circuit breaker for database connections.
    Production-ready pattern to prevent hanging on failed database connections.
    """
    
    def __init__(self, 
                 failure_threshold: int = 3,
                 recovery_timeout: int = 30,
                 request_timeout: int = 5):
        self.failure_threshold = failure_threshold
        self.recovery_timeout = recovery_timeout
        self.request_timeout = request_timeout
        
        self.state = CircuitState.CLOSED
        self.failure_count = 0
        self.last_failure_time: Optional[float] = None
        
        logger.info(f"🔧 Database circuit breaker initialized")
        logger.info(f"  Failure threshold: {failure_threshold}")
        logger.info(f"  Recovery timeout: {recovery_timeout}s")
        logger.info(f"  Request timeout: {request_timeout}s")
    
    def can_execute(self) -> bool:
        """Check if we should allow database operations."""
        now = time.time()
        
        if self.state == CircuitState.CLOSED:
            return True
        elif self.state == CircuitState.OPEN:
            if self.last_failure_time and (now - self.last_failure_time) >= self.recovery_timeout:
                logger.info("🔄 Circuit breaker transitioning to HALF_OPEN - testing recovery")
                self.state = CircuitState.HALF_OPEN
                return True
            else:
                logger.warning("⚡ Circuit breaker OPEN - failing fast")
                return False
        elif self.state == CircuitState.HALF_OPEN:
            return True
        
        return False
    
    def record_success(self):
        """Record successful database operation."""
        if self.state == CircuitState.HALF_OPEN:
            logger.info("✅ Circuit breaker recovery confirmed - resetting to CLOSED")
            self.state = CircuitState.CLOSED
            self.failure_count = 0
            self.last_failure_time = None
        elif self.state == CircuitState.CLOSED:
            # Reset failure count on success
            if self.failure_count > 0:
                logger.info(f"✅ Database recovery detected - resetting failure count")
                self.failure_count = 0
    
    def record_failure(self):
        """Record failed database operation."""
        self.failure_count += 1
        self.last_failure_time = time.time()
        
        logger.warning(f"❌ Database failure recorded ({self.failure_count}/{self.failure_threshold})")
        
        if self.failure_count >= self.failure_threshold and self.state == CircuitState.CLOSED:
            logger.error("🚨 Circuit breaker OPENING - database appears unhealthy")
            self.state = CircuitState.OPEN
        elif self.state == CircuitState.HALF_OPEN:
            logger.error("🚨 Circuit breaker back to OPEN - recovery failed")
            self.state = CircuitState.OPEN
    
    def get_status(self) -> dict:
        """Get current circuit breaker status."""
        return {
            "state": self.state.value,
            "failure_count": self.failure_count,
            "last_failure_time": self.last_failure_time,
            "can_execute": self.can_execute()
        }

# Global circuit breaker instance
db_circuit_breaker = DatabaseCircuitBreaker()