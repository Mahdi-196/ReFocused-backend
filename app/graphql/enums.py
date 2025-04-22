import strawberry

@strawberry.enum
class GoalDuration:
    """Duration of a goal, either short-term (2 weeks) or long-term"""
    SHORT = "SHORT"  # 2-week goals
    LONG = "LONG"    # long-term goals 