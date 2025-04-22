import logging
import time
from datetime import datetime, timedelta
from typing import Dict, List, Optional
from fastapi import Request
from sqlalchemy.orm import Session
from app.db.models import SecurityLog, SecurityAlert, User, LoginAttempt
from app.core.security_config import security_config

logger = logging.getLogger("security_monitor")

class SecurityMonitor:
    def __init__(self, db: Session):
        self.db = db
        self.anomaly_thresholds = {
            "login_attempts": 5,  # Max failed attempts before alert
            "ip_requests": 100,  # Max requests from single IP
            "user_agents": 3,  # Max different user agents per user
            "password_changes": 3,  # Max password changes per day
        }
        self.ip_activity: Dict[str, Dict] = {}
        self.user_activity: Dict[int, Dict] = {}
    
    def monitor_request(self, request: Request, user_id: Optional[int] = None):
        """Monitor and analyze incoming requests for security threats."""
        client_ip = request.client.host
        user_agent = request.headers.get("user-agent", "")
        
        # Track IP activity
        self._track_ip_activity(client_ip, user_agent)
        
        # Track user activity if authenticated
        if user_id:
            self._track_user_activity(user_id, client_ip, user_agent)
        
        # Check for anomalies
        self._check_anomalies(client_ip, user_id)
    
    def _track_ip_activity(self, ip: str, user_agent: str):
        """Track activity from IP addresses."""
        if ip not in self.ip_activity:
            self.ip_activity[ip] = {
                "requests": 0,
                "user_agents": set(),
                "last_request": datetime.utcnow()
            }
        
        self.ip_activity[ip]["requests"] += 1
        self.ip_activity[ip]["user_agents"].add(user_agent)
        self.ip_activity[ip]["last_request"] = datetime.utcnow()
        
        # Clean old entries
        self._clean_old_ip_activity()
    
    def _track_user_activity(self, user_id: int, ip: str, user_agent: str):
        """Track activity from users."""
        if user_id not in self.user_activity:
            self.user_activity[user_id] = {
                "ips": set(),
                "user_agents": set(),
                "last_activity": datetime.utcnow()
            }
        
        self.user_activity[user_id]["ips"].add(ip)
        self.user_activity[user_id]["user_agents"].add(user_agent)
        self.user_activity[user_id]["last_activity"] = datetime.utcnow()
        
        # Clean old entries
        self._clean_old_user_activity()
    
    def _check_anomalies(self, ip: str, user_id: Optional[int] = None):
        """Check for suspicious activity patterns."""
        # Check IP activity
        ip_data = self.ip_activity.get(ip, {})
        if ip_data.get("requests", 0) > self.anomaly_thresholds["ip_requests"]:
            self._create_alert(
                "high_rate_requests",
                "high",
                f"High rate of requests from IP {ip}",
                ip_address=ip
            )
        
        if len(ip_data.get("user_agents", set())) > self.anomaly_thresholds["user_agents"]:
            self._create_alert(
                "multiple_user_agents",
                "medium",
                f"Multiple user agents detected from IP {ip}",
                ip_address=ip
            )
        
        # Check user activity
        if user_id:
            user_data = self.user_activity.get(user_id, {})
            if len(user_data.get("ips", set())) > 3:  # Multiple IPs for same user
                self._create_alert(
                    "multiple_ips",
                    "medium",
                    f"User {user_id} accessing from multiple IPs",
                    user_id=user_id
                )
    
    def monitor_login_attempt(self, user_id: int, success: bool, ip: str):
        """Monitor login attempts for suspicious patterns."""
        # Get recent failed attempts
        recent_attempts = LoginAttempt.get_recent_attempts(
            self.db,
            user_id,
            security_config.LOCKOUT_DURATION_MINUTES
        )
        
        failed_attempts = [a for a in recent_attempts if not a.success]
        
        if len(failed_attempts) >= self.anomaly_thresholds["login_attempts"]:
            self._create_alert(
                "brute_force_attempt",
                "high",
                f"Multiple failed login attempts for user {user_id}",
                user_id=user_id,
                ip_address=ip
            )
    
    def _create_alert(self, alert_type: str, severity: str, description: str,
                     user_id: Optional[int] = None, ip_address: Optional[str] = None):
        """Create a security alert."""
        SecurityAlert.create_alert(
            self.db,
            alert_type=alert_type,
            severity=severity,
            description=description,
            user_id=user_id,
            ip_address=ip_address
        )
        
        # Log the alert
        logger.warning(f"Security alert: {description}")
    
    def _clean_old_ip_activity(self):
        """Clean old IP activity records."""
        cutoff = datetime.utcnow() - timedelta(minutes=5)
        self.ip_activity = {
            ip: data for ip, data in self.ip_activity.items()
            if data["last_request"] > cutoff
        }
    
    def _clean_old_user_activity(self):
        """Clean old user activity records."""
        cutoff = datetime.utcnow() - timedelta(minutes=30)
        self.user_activity = {
            user_id: data for user_id, data in self.user_activity.items()
            if data["last_activity"] > cutoff
        }
    
    def get_security_metrics(self) -> Dict:
        """Get current security metrics."""
        return {
            "active_ips": len(self.ip_activity),
            "active_users": len(self.user_activity),
            "total_alerts": self.db.query(SecurityAlert).filter(
                SecurityAlert.resolved == False
            ).count(),
            "recent_failed_logins": self.db.query(LoginAttempt).filter(
                LoginAttempt.success == False,
                LoginAttempt.created_at > datetime.utcnow() - timedelta(hours=1)
            ).count()
        }
    
    def get_security_alerts(self, resolved: bool = False) -> List[Dict]:
        """Get security alerts."""
        alerts = self.db.query(SecurityAlert).filter(
            SecurityAlert.resolved == resolved
        ).order_by(SecurityAlert.created_at.desc()).all()
        
        return [{
            "id": alert.id,
            "type": alert.alert_type,
            "severity": alert.severity,
            "description": alert.description,
            "created_at": alert.created_at,
            "ip_address": alert.ip_address,
            "user_id": alert.user_id
        } for alert in alerts] 