import strawberry
from enum import Enum

@strawberry.enum
class GoalDuration(Enum):
    """Duration of a goal, either short-term (2 weeks) or long-term"""
    SHORT = "SHORT"  # 2-week goals
    LONG = "LONG"    # long-term goals 