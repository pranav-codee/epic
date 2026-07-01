"""
Microsoft Teams Incoming Webhook channel. Uses the MessageCard format, which is the format
supported by Incoming Webhook connectors (per current Microsoft documentation). Adaptive Cards
v1.4+ can be substituted later if EPL standardises on Workflows / Power Automate posting.

TODO (EPL IT): provide TEAMS_WEBHOOK_URL via environment variable before pilot rollout (TBD-3).
"""
import httpx
from .base import NotificationChannel
from ....config import get_settings


class TeamsChannel(NotificationChannel):
    name = "TEAMS"

    async def send(self, *, title, text, facts, action_url=None):
        s = get_settings()
        if not s.TEAMS_NOTIFICATIONS_ENABLED:
            return (True, "Notifications disabled by config")
        if not s.TEAMS_WEBHOOK_URL:
            return (False, "TEAMS_WEBHOOK_URL is not configured")

        card = {
            "@type": "MessageCard",
            "@context": "https://schema.org/extensions",
            "summary": title,
            "themeColor": "0067B8",
            "title": title,
            "text": text,
            "sections": [{
                "facts": [{"name": k, "value": v} for k, v in facts],
            }],
        }
        if action_url:
            card["potentialAction"] = [{
                "@type": "OpenUri",
                "name": "Open Ticket in EPIC",
                "targets": [{"os": "default", "uri": action_url}],
            }]

        try:
            async with httpx.AsyncClient(timeout=10.0) as client:
                r = await client.post(s.TEAMS_WEBHOOK_URL, json=card)
                if r.status_code >= 400:
                    return (False, f"HTTP {r.status_code}: {r.text[:300]}")
            return (True, None)
        except Exception as e:
            return (False, f"{type(e).__name__}: {e}")
