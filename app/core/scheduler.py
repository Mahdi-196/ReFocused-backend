"""
Content Scheduler - Automatically fetches daily and weekly content
"""

import asyncio
import logging
from datetime import datetime, timezone, timedelta
from typing import Dict, Any, Optional
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, and_, func
from ..db.database import get_db
from ..db.models import DailyContent, WeeklyContent, User
from ..services.ai_service import ai_service

logger = logging.getLogger(__name__)

class ContentScheduler:
    def __init__(self):
        self.is_running = False
        self.daily_task = None
        self.weekly_task = None
        
    async def start(self):
        """Start the content scheduler"""
        if self.is_running:
            logger.info("Scheduler is already running")
            return
            
        self.is_running = True
        logger.info("Starting content scheduler...")
        
        # Start daily content generation task
        self.daily_task = asyncio.create_task(self._daily_content_loop())
        
        # Start weekly content generation task
        self.weekly_task = asyncio.create_task(self._weekly_content_loop())
        
        logger.info("Content scheduler started successfully")
    
    async def stop(self):
        """Stop the content scheduler"""
        if not self.is_running:
            logger.info("Scheduler is not running")
            return
            
        self.is_running = False
        logger.info("Stopping content scheduler...")
        
        # Cancel tasks
        if self.daily_task:
            self.daily_task.cancel()
            try:
                await self.daily_task
            except asyncio.CancelledError:
                pass
                
        if self.weekly_task:
            self.weekly_task.cancel()
            try:
                await self.weekly_task
            except asyncio.CancelledError:
                pass
        
        logger.info("Content scheduler stopped successfully")
    
    async def _daily_content_loop(self):
        """Daily content generation loop"""
        while self.is_running:
            try:
                await self._generate_daily_content()
                
                # Wait until next day at 00:00 UTC
                now = datetime.now(timezone.utc)
                tomorrow = (now + timedelta(days=1)).replace(hour=0, minute=0, second=0, microsecond=0)
                wait_seconds = (tomorrow - now).total_seconds()
                
                logger.info(f"Daily content generated. Next run in {wait_seconds/3600:.1f} hours")
                await asyncio.sleep(wait_seconds)
                
            except asyncio.CancelledError:
                logger.info("Daily content loop cancelled")
                break
            except Exception as e:
                logger.error(f"Error in daily content loop: {e}")
                # Wait 1 hour before retrying
                await asyncio.sleep(3600)
    
    async def _weekly_content_loop(self):
        """Weekly content generation loop"""
        while self.is_running:
            try:
                await self._generate_weekly_content()
                
                # Wait until next Sunday at 00:00 UTC
                now = datetime.now(timezone.utc)
                days_until_sunday = (6 - now.weekday()) % 7
                if days_until_sunday == 0 and now.hour >= 0:
                    days_until_sunday = 7
                    
                next_sunday = (now + timedelta(days=days_until_sunday)).replace(hour=0, minute=0, second=0, microsecond=0)
                wait_seconds = (next_sunday - now).total_seconds()
                
                logger.info(f"Weekly content generated. Next run in {wait_seconds/3600:.1f} hours")
                await asyncio.sleep(wait_seconds)
                
            except asyncio.CancelledError:
                logger.info("Weekly content loop cancelled")
                break
            except Exception as e:
                logger.error(f"Error in weekly content loop: {e}")
                # Wait 6 hours before retrying
                await asyncio.sleep(21600)
    
    async def _generate_daily_content(self):
        """Generate daily content using AI service"""
        try:
            logger.info("Generating daily content...")
            
            # Generate quote of the day
            quote_result = await ai_service.get_quote_of_day()
            if quote_result:
                logger.info("Quote of the day generated successfully")
            else:
                logger.warning("Failed to generate quote of the day")
            
            # Generate word of the day
            word_result = await ai_service.get_word_of_day()
            if word_result:
                logger.info("Word of the day generated successfully")
            else:
                logger.warning("Failed to generate word of the day")
            
            # Generate mind fuel
            mind_fuel_result = await ai_service.get_mind_fuel()
            if mind_fuel_result:
                logger.info("Mind fuel generated successfully")
            else:
                logger.warning("Failed to generate mind fuel")
            
            logger.info("Daily content generation completed")
            
        except Exception as e:
            logger.error(f"Error generating daily content: {e}")
    
    async def _generate_weekly_content(self):
        """Generate weekly content using AI service"""
        try:
            logger.info("Generating weekly content...")
            
            # Generate writing prompts
            prompt_result = await ai_service.get_writing_prompts()
            if prompt_result:
                logger.info("Writing prompts generated successfully")
            else:
                logger.warning("Failed to generate writing prompts")
            
            # Generate AI suggestions
            ai_result = await ai_service.get_ai_suggestions()
            if ai_result:
                logger.info("AI suggestions generated successfully")
            else:
                logger.warning("Failed to generate AI suggestions")
            
            # Generate weekly theme
            theme_result = await ai_service.get_weekly_theme()
            if theme_result:
                logger.info("Weekly theme generated successfully")
            else:
                logger.warning("Failed to generate weekly theme")
            
            logger.info("Weekly content generation completed")
            
        except Exception as e:
            logger.error(f"Error generating weekly content: {e}")
    
    async def trigger_manual_daily_generation(self) -> Dict[str, Any]:
        """Manually trigger daily content generation"""
        try:
            logger.info("Manual daily content generation triggered")
            await self._generate_daily_content()
            return {"status": "success", "message": "Daily content generated manually"}
        except Exception as e:
            logger.error(f"Manual daily content generation failed: {e}")
            return {"status": "error", "message": str(e)}
    
    async def trigger_manual_weekly_generation(self) -> Dict[str, Any]:
        """Manually trigger weekly content generation"""
        try:
            logger.info("Manual weekly content generation triggered")
            await self._generate_weekly_content()
            return {"status": "success", "message": "Weekly content generated manually"}
        except Exception as e:
            logger.error(f"Manual weekly content generation failed: {e}")
            return {"status": "error", "message": str(e)}
    
    def get_next_run_times(self) -> Dict[str, Optional[datetime]]:
        """Get the next scheduled run times"""
        try:
            now = datetime.now(timezone.utc)
            
            # Next daily run (tomorrow at 00:00 UTC)
            tomorrow = (now + timedelta(days=1)).replace(hour=0, minute=0, second=0, microsecond=0)
            
            # Next weekly run (next Sunday at 00:00 UTC)
            days_until_sunday = (6 - now.weekday()) % 7
            if days_until_sunday == 0 and now.hour >= 0:
                days_until_sunday = 7
            next_sunday = (now + timedelta(days=days_until_sunday)).replace(hour=0, minute=0, second=0, microsecond=0)
            
            return {
                "daily": tomorrow,
                "weekly": next_sunday
            }
        except Exception as e:
            logger.error(f"Error calculating next run times: {e}")
            return {"daily": None, "weekly": None}

# Global scheduler instance
content_scheduler = ContentScheduler()