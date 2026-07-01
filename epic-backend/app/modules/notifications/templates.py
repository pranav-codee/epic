"""
Event -> (title, text, facts) builders. Kept as pure functions so a future channel
(e.g. Adaptive Cards via bot) can reuse the same field set.
"""
from ..tickets.models import Ticket
from ...config import get_settings


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
        facts.append(("Updated by", actor_name))

    title_map = {
        "TICKET_CREATED":  f"🆕 Ticket created — {ticket.ticket_number}",
        "TICKET_ASSIGNED": f"👤 Ticket assigned — {ticket.ticket_number}",
        "TICKET_UPDATED":  f"✏️ Ticket updated — {ticket.ticket_number}",
        "TICKET_RESOLVED": f"✅ Ticket resolved — {ticket.ticket_number}",
        "TICKET_CLOSED":   f"🔒 Ticket closed — {ticket.ticket_number}",
        "TICKET_CANCELLED": f"🚫 Ticket cancelled — {ticket.ticket_number}",
    }
    title = title_map.get(event, f"Ticket event — {ticket.ticket_number}")
    text = ticket.title
    return title, text, facts, _ticket_url(ticket)
