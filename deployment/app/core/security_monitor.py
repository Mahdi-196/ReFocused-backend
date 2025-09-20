import logging
from datetime import datetime, timedelta
from typing import Dict, List, Optional
from fastapi import Request
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from sqlalchemy.sql import func
from app.db.models import SecurityAlert, User, LoginAttempt
from app.core.security_config import security_config

logger = logging.getLogger("security_monitor")

class SecurityMonitor:
    def __init__(self, db: AsyncSession):
        self.db = db
        self.anomaly_thresholds = {
            "login_attempts": getattr(security_config, 'MAX_FAILED_LOGIN_ATTEMPTS', 5),
            "ip_requests": getattr(security_config, 'RATE_LIMIT_MAX_REQUESTS', 100) * 2,
            "user_agents_per_ip": getattr(security_config, 'MAX_USER_AGENTS_PER_IP', 5),
            "user_agents_per_user": getattr(security_config, 'MAX_USER_AGENTS_PER_USER', 5),
            "ips_per_user": getattr(security_config, 'MAX_IPS_PER_USER', 3),
        }
        self.ip_activity: Dict[str, Dict] = {}
        self.user_activity: Dict[int, Dict] = {}
    
    async def monitor_request(self, request: Request, user_id: Optional[int] = None):
        """Monitor and analyze incoming requests for security threats."""
        client_ip = request.client.host if request.client else "unknown"
        user_agent = request.headers.get("user-agent", "")
        
        # Track IP activity
        self._track_ip_activity(client_ip, user_agent)
        
        # Track user activity if authenticated
        if user_id:
            self._track_user_activity(user_id, client_ip, user_agent)
        
        # Check for anomalies
        await self._check_anomalies(client_ip, user_id)
    
    def _track_ip_activity(self, ip: str, user_agent: str):
        """Track activity from IP addresses."""
        if ip == "unknown": return
        now = datetime.utcnow()
        if ip not in self.ip_activity:
            self.ip_activity[ip] = {
                "requests": 0,
                "user_agents": set(),
                "first_request": now,
                "last_request": now
            }
        
        self.ip_activity[ip]["requests"] += 1
        if user_agent:
            self.ip_activity[ip]["user_agents"].add(user_agent)
        self.ip_activity[ip]["last_request"] = now
        
        # Clean old entries
        self._clean_old_ip_activity()
    
    def _track_user_activity(self, user_id: int, ip: str, user_agent: str):
        """Track activity from users."""
        now = datetime.utcnow()
        if user_id not in self.user_activity:
            self.user_activity[user_id] = {
                "ips": set(),
                "user_agents": set(),
                "first_activity": now,
                "last_activity": now
            }
        
        if ip != "unknown":
            self.user_activity[user_id]["ips"].add(ip)
        if user_agent:
            self.user_activity[user_id]["user_agents"].add(user_agent)
        self.user_activity[user_id]["last_activity"] = now
        
        # Clean old entries
        self._clean_old_user_activity()
    
    async def _check_anomalies(self, ip: str, user_id: Optional[int] = None):
        """Check for suspicious activity patterns."""
        # Check IP activity
        ip_data = self.ip_activity.get(ip)
        if ip_data:
            if ip_data["requests"] > self.anomaly_thresholds["ip_requests"]:
                await self._create_alert(
                    "high_request_count_ip",
                    "medium",
                    f"High request count ({ip_data['requests']}) detected from IP {ip}",
                    ip_address=ip
                )
            if len(ip_data["user_agents"]) > self.anomaly_thresholds["user_agents_per_ip"]:
                await self._create_alert(
                    "multiple_user_agents_ip",
                    "medium",
                    f"Multiple user agents ({len(ip_data['user_agents'])}) detected from IP {ip}",
                    ip_address=ip
                )
        
        # Check user activity
        if user_id:
            user_data = self.user_activity.get(user_id)
            if user_data:
                if len(user_data["ips"]) > self.anomaly_thresholds["ips_per_user"]:
                    await self._create_alert(
                        "multiple_ips_user",
                        "medium",
                        f"User {user_id} accessed from {len(user_data['ips'])} IPs recently",
                        user_id=user_id
                    )
                if len(user_data["user_agents"]) > self.anomaly_thresholds["user_agents_per_user"]:
                    await self._create_alert(
                        "multiple_user_agents_user",
                        "medium",
                        f"Multiple user agents ({len(user_data['user_agents'])}) detected for user {user_id}",
                        user_id=user_id
                    )
    
    async def monitor_login_attempt(self, username: str, success: bool, ip: str):
        """Monitor login attempts for suspicious patterns."""
        user = await User.get_by_username(self.db, username)
        if not user:
            logger.warning(f"Login attempt for non-existent user: {username} from IP {ip}")
            await self._create_alert(
                "invalid_user_login_attempt",
                "low",
                f"Login attempt for unknown user '{username}' from IP {ip}",
                ip_address=ip
            )
            return

        await LoginAttempt.record_attempt(
            db=self.db,
            user_id=user.id,
            success=success,
            ip_address=ip
        )

        if not success:
            failed_attempts_count = await LoginAttempt.count_recent_failed_attempts(
                db=self.db,
                user_id=user.id,
                minutes=getattr(security_config, 'LOCKOUT_PERIOD_MINUTES', 15)
            )

            if failed_attempts_count >= self.anomaly_thresholds["login_attempts"]:
                await self._create_alert(
                    "brute_force_attempt",
                    "high",
                    f"Multiple ({failed_attempts_count}) failed login attempts for user {username} (ID: {user.id}) from IP {ip}",
                    user_id=user.id,
                    ip_address=ip
                )
    
    async def _create_alert(self, alert_type: str, severity: str, description: str,
                     user_id: Optional[int] = None, ip_address: Optional[str] = None):
        """Create a security alert."""
        try:
            alert = await SecurityAlert.create_alert(
                db=self.db,
                alert_type=alert_type,
                severity=severity,
                description=description,
                user_id=user_id,
                ip_address=ip_address
            )
            await self.db.commit()
            logger.warning(f"Security Alert Created: {alert.id} - Type: {alert_type}, Severity: {severity}, Desc: {description}")
        except Exception as e:
            logger.error(f"Failed to create security alert: {e}", exc_info=True)
            await self.db.rollback()
    
    def _clean_old_ip_activity(self):
        """Clean old IP activity records."""
        cutoff = datetime.utcnow() - timedelta(minutes=60)
        self.ip_activity = {
            ip: data for ip, data in self.ip_activity.items()
            if data["last_request"] > cutoff
        }
    
    def _clean_old_user_activity(self):
        """Clean old user activity records."""
        cutoff = datetime.utcnow() - timedelta(minutes=120)
        self.user_activity = {
            user_id: data for user_id, data in self.user_activity.items()
            if data["last_activity"] > cutoff
        }
    
    async def get_security_metrics(self) -> Dict:
        """Get current security metrics."""
        try:
            unresolved_alerts_query = select(func.count(SecurityAlert.id)).where(SecurityAlert.resolved == False)
            unresolved_alerts_result = await self.db.execute(unresolved_alerts_query)
            total_alerts = unresolved_alerts_result.scalar_one_or_none() or 0

            one_hour_ago = datetime.utcnow() - timedelta(hours=1)
            failed_logins_query = select(func.count(LoginAttempt.id)).where(
                LoginAttempt.success == False,
                LoginAttempt.timestamp > one_hour_ago
            )
            failed_logins_result = await self.db.execute(failed_logins_query)
            recent_failed_logins = failed_logins_result.scalar_one_or_none() or 0

            return {
                "active_ips": len(self.ip_activity),
                "active_users": len(self.user_activity),
                "unresolved_alerts": total_alerts,
                "recent_failed_logins_last_hour": recent_failed_logins
            }
        except Exception as e:
            logger.error(f"Error getting security metrics: {e}", exc_info=True)
            return {"error": "Failed to retrieve metrics"}
    
    async def get_security_alerts(self, resolved: Optional[bool] = None, limit: int = 100) -> List[Dict]:
        """Get security alerts."""
        try:
            stmt = select(SecurityAlert)
            if resolved is not None:
                stmt = stmt.where(SecurityAlert.resolved == resolved)

            stmt = stmt.order_by(SecurityAlert.timestamp.desc()).limit(limit)
            result = await self.db.execute(stmt)
            alerts = result.scalars().all()

            return [{
                "id": alert.id,
                "alert_type": alert.alert_type,
                "severity": alert.severity,
                "description": alert.description,
                "timestamp": alert.timestamp.isoformat(),
                "ip_address": alert.ip_address,
                "user_id": alert.user_id,
                "resolved": alert.resolved
            } for alert in alerts]
        except Exception as e:
            logger.error(f"Error getting security alerts: {e}", exc_info=True)
            return [{"error": "Failed to retrieve alerts"}] 