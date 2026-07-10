"""
Event -> (title, text, facts) builders. Kept as pure functions so a future channel
(e.g. Adaptive Cards via bot) can reuse the same field set.

SECURITY (stored content injection / phishing): `ticket.title` (and `actor_name`) are
free-text fields fully controlled by the ticket creator / identity provider claims. The
Teams channel renders MessageCard `title`/`text`/`facts` as Markdown, so an attacker could
craft a ticket title like "[Password expired - click here](https://evil.example/phish)"
and have it render as a clickable, legitimate-looking link inside a notification that lands
in IT staff channels. Every free-text value that goes into the card MUST be sanitized here,
*before* it reaches the Teams channel — never rely on the channel layer to do this, since
other future channels (e.g. Adaptive Cards, email) would each have to remember to redo it.
"""
import re
from ..tickets.models import Ticket
from ...config import get_settings

# Escape characters Markdown (as used by Teams MessageCard/Adaptive Card renderers) treats
# as formatting/link syntax, so untrusted text renders as literal characters instead of
# being interpreted (links, images, headers, emphasis, etc).
_MD_SPECIAL_CHARS = re.compile(r'([\\`*_{}\[\]()#+\-.!>|~])')
_MAX_FIELD_LEN = 300


def _sanitize(value: str | None, *, max_len: int = _MAX_FIELD_LEN) -> str:
    """Neutralize Markdown control characters and collapse newlines in untrusted text
    before it is embedded in a Teams notification. Defense-in-depth: also hard-caps
    length so a huge title can't be used to pad/hide a payload or bloat the webhook call."""
    if not value:
        return ""
    # Collapse newlines/carriage returns so multi-line payloads can't fake extra card fields.
    flattened = value.replace("\r\n", " ").replace("\r", " ").replace("\n", " ")
    escaped = _MD_SPECIAL_CHARS.sub(r"\\\1", flattened)
    if len(escaped) > max_len:
        escaped = escaped[: max_len - 1].rstrip() + "\u2026"
    return escaped


def _ticket_url(ticket: Ticket) -> str:
    base = get_settings().FRONTEND_BASE_URL.rstrip("/")
    return f"{base}/employee/tickets/{ticket.id}"


def build(event: str, ticket: Ticket, *, actor_name: str | None = None, extra: dict | None = None):
    facts = [
        ("Ticket", ticket.ticket_number),
        ("Status", ticket.status),
        ("Priority", ticket.priority),
        ("Category", ticket.category),
    ]
    if actor_name:
        facts.append(("Updated by", _sanitize(actor_name, max_len=120)))

    title_map = {
        "TICKET_CREATED":  f"Ticket created — {ticket.ticket_number}",
        "TICKET_ASSIGNED": f"Ticket assigned — {ticket.ticket_number}",
        "TICKET_UPDATED":  f"Ticket updated — {ticket.ticket_number}",
        "TICKET_RESOLVED": f"Ticket resolved — {ticket.ticket_number}",
        "TICKET_CLOSED":   f"Ticket closed — {ticket.ticket_number}",
        "TICKET_CANCELLED": f"Ticket cancelled — {ticket.ticket_number}",
        # NEW — app.core.sla_scanner escalations
        "SLA_AT_RISK":     f"⚠ SLA at risk — {ticket.ticket_number}",
        "SLA_BREACHED":    f"🔴 SLA breached — {ticket.ticket_number}",
    }
    title = title_map.get(event, f"Ticket event — {ticket.ticket_number}")
    # `ticket.title` is attacker-controlled free text — always sanitize before it is
    # embedded as Markdown in the outgoing notification.
    text = _sanitize(ticket.title)
    return title, text, facts, _ticket_url(ticket)