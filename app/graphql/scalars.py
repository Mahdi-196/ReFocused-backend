import datetime
import strawberry
from typing import Any

@strawberry.scalar(
    description="Date scalar that serializes Python date objects to ISO-8601 strings"
)
class Date:
    @staticmethod
    def serialize(value: datetime.date) -> str:
        return value.isoformat()

    @staticmethod
    def parse_value(value: str) -> datetime.date:
        return datetime.date.fromisoformat(value)


@strawberry.scalar(
    description="DateTime scalar that serializes Python datetime objects to ISO-8601 strings"
)
class DateTime:
    @staticmethod
    def serialize(value: datetime.datetime) -> str:
        return value.isoformat()

    @staticmethod
    def parse_value(value: str) -> datetime.datetime:
        return datetime.datetime.fromisoformat(value) 