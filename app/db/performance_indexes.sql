-- Production Database Performance Indexes
-- These indexes optimize critical queries for sub-100ms response times

-- User authentication optimization
-- Frequently used for login and user lookups
CREATE INDEX CONCURRENTLY IF NOT EXISTS idx_users_email_active 
ON users(email) WHERE is_active = true;

CREATE INDEX CONCURRENTLY IF NOT EXISTS idx_users_google_id 
ON users(google_id) WHERE google_id IS NOT NULL;

-- Habit tracking performance
-- Critical for habit completion queries and streak calculations
CREATE INDEX CONCURRENTLY IF NOT EXISTS idx_habit_completions_user_date_range 
ON habit_completions(user_id, date) 
WHERE date >= CURRENT_DATE - INTERVAL '90 days';

CREATE INDEX CONCURRENTLY IF NOT EXISTS idx_habit_completions_user_habit_date
ON habit_completions(user_id, habit_id, date);

CREATE INDEX CONCURRENTLY IF NOT EXISTS idx_habits_user_active_favorite 
ON habits(user_id, is_active, is_favorite) 
WHERE is_active = true;

CREATE INDEX CONCURRENTLY IF NOT EXISTS idx_habits_user_created
ON habits(user_id, created_at DESC) 
WHERE is_active = true;

-- Goal management optimization
-- For active goal queries and completion tracking
CREATE INDEX CONCURRENTLY IF NOT EXISTS idx_goals_2week_user_active_expires 
ON goals_2_week(user_id, is_completed, expires_at) 
WHERE is_completed = false AND expires_at > CURRENT_DATE;

CREATE INDEX CONCURRENTLY IF NOT EXISTS idx_goals_longterm_user_type_completed 
ON goals_long_term(user_id, goal_type, is_completed);

CREATE INDEX CONCURRENTLY IF NOT EXISTS idx_goals_longterm_user_created
ON goals_long_term(user_id, created_at DESC);

-- Statistics and analytics optimization
-- For dashboard and reporting queries
CREATE INDEX CONCURRENTLY IF NOT EXISTS idx_user_statistics_user_date_range 
ON user_statistics(user_id, date) 
WHERE date >= CURRENT_DATE - INTERVAL '365 days';

CREATE INDEX CONCURRENTLY IF NOT EXISTS idx_user_statistics_date_desc
ON user_statistics(user_id, date DESC);

-- Calendar performance
-- For calendar view and date range queries
CREATE INDEX CONCURRENTLY IF NOT EXISTS idx_calendar_entries_user_date_range 
ON calendar_entries(user_id, date) 
WHERE date BETWEEN CURRENT_DATE - INTERVAL '30 days' 
AND CURRENT_DATE + INTERVAL '30 days';

CREATE INDEX CONCURRENTLY IF NOT EXISTS idx_calendar_habit_completions_user_date
ON calendar_habit_completions(user_id, date DESC);

CREATE INDEX CONCURRENTLY IF NOT EXISTS idx_calendar_mood_entries_user_date
ON calendar_mood_entries(user_id, date DESC);

-- Mood tracking optimization
-- For mood analytics and trends
CREATE INDEX CONCURRENTLY IF NOT EXISTS idx_mood_entries_user_date_range
ON mood_entries(user_id, created_at)
WHERE created_at >= CURRENT_DATE - INTERVAL '90 days';

-- Security and audit logs optimization
-- For security monitoring and incident response
CREATE INDEX CONCURRENTLY IF NOT EXISTS idx_security_logs_timestamp 
ON security_logs(created_at DESC) 
WHERE created_at >= CURRENT_DATE - INTERVAL '30 days';

CREATE INDEX CONCURRENTLY IF NOT EXISTS idx_login_attempts_user_timestamp 
ON login_attempts(user_id, created_at DESC) 
WHERE created_at >= CURRENT_DATE - INTERVAL '24 hours';

CREATE INDEX CONCURRENTLY IF NOT EXISTS idx_login_attempts_ip_timestamp
ON login_attempts(ip_address, created_at DESC)
WHERE created_at >= CURRENT_DATE - INTERVAL '24 hours';

-- Token management optimization
-- For authentication and session management
CREATE INDEX CONCURRENTLY IF NOT EXISTS idx_token_blacklist_token_hash
ON token_blacklist(token_hash);

CREATE INDEX CONCURRENTLY IF NOT EXISTS idx_token_blacklist_expires_at
ON token_blacklist(expires_at) 
WHERE expires_at > CURRENT_TIMESTAMP;

-- Journal entries optimization
-- For journal queries and search
CREATE INDEX CONCURRENTLY IF NOT EXISTS idx_journal_entries_user_date
ON journal_entries(user_id, created_at DESC);

-- Composite indexes for complex queries
-- User dashboard query optimization
CREATE INDEX CONCURRENTLY IF NOT EXISTS idx_users_dashboard_composite
ON users(id, timezone, is_active) 
WHERE is_active = true;

-- Habit streak calculation optimization
CREATE INDEX CONCURRENTLY IF NOT EXISTS idx_habit_streak_composite
ON habit_completions(habit_id, date DESC, completed_at)
WHERE date >= CURRENT_DATE - INTERVAL '365 days';

-- Goal progress tracking optimization
CREATE INDEX CONCURRENTLY IF NOT EXISTS idx_goal_progress_composite
ON goals_long_term(user_id, goal_type, current_percentage, target_percentage, is_completed);

-- Clean up old partial indexes and constraints if they exist
-- Note: These commands will only run if the indexes exist
DROP INDEX CONCURRENTLY IF EXISTS old_idx_users_email;
DROP INDEX CONCURRENTLY IF EXISTS old_idx_habits_user_id;
DROP INDEX CONCURRENTLY IF EXISTS old_idx_goals_user_id;

-- Add comments for documentation
COMMENT ON INDEX idx_users_email_active IS 'Optimizes user authentication queries';
COMMENT ON INDEX idx_habit_completions_user_date_range IS 'Optimizes habit completion lookups for recent data';
COMMENT ON INDEX idx_goals_2week_user_active_expires IS 'Optimizes active goal queries';
COMMENT ON INDEX idx_calendar_entries_user_date_range IS 'Optimizes calendar view queries';

-- Query optimization hints (PostgreSQL specific)
-- These help the query planner make better decisions

-- Set work_mem for index creation (if running manually)
-- SET work_mem = '256MB';

-- Update table statistics after index creation
ANALYZE users;
ANALYZE habits;
ANALYZE habit_completions;
ANALYZE goals_2_week;
ANALYZE goals_long_term;
ANALYZE user_statistics;
ANALYZE calendar_entries;
ANALYZE mood_entries; 