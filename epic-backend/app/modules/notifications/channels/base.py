"""
Notification channel abstraction. v1 ships only TeamsChannel.
Future work (email, Graph API bot DMs, etc.) plugs in here without touching ticket code.
"""
from abc import ABC, abstractmethod


class NotificationChannel(ABC):
    name: str = "BASE"

    @abstractmethod
    async def send(self, *, title: str, text: str, facts: list[tuple[str, str]],
                   action_url: str | None = None) -> tuple[bool, str | None]:
        """Returns (success, error_message_or_None)."""
        ...
