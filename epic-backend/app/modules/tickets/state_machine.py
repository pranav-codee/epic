"""
Authoritative ticket state machine. Mirrors SRS Figure 5 (state diagram).

User decision (30-Jun-2026): RESOLVED -> IN_PROGRESS reopen transition is allowed.
"""
from ...core.exceptions import InvalidStateTransition

OPEN, ASSIGNED, IN_PROGRESS, PENDING_USER, RESOLVED, CLOSED, CANCELLED = (
    "OPEN", "ASSIGNED", "IN_PROGRESS", "PENDING_USER", "RESOLVED", "CLOSED", "CANCELLED"
)

# (from_state, event) -> to_state
TRANSITIONS = {
    (OPEN,         "assign"):        ASSIGNED,
    (ASSIGNED,     "start_work"):    IN_PROGRESS,
    (ASSIGNED,     "await_user"):    PENDING_USER,
    (IN_PROGRESS,  "await_user"):    PENDING_USER,
    (PENDING_USER, "user_responds"): IN_PROGRESS,
    (IN_PROGRESS,  "resolve"):       RESOLVED,
    (PENDING_USER, "resolve"):       RESOLVED,
    (RESOLVED,     "confirm"):       CLOSED,
    # Reopen path (user decision, 30-Jun-2026):
    (RESOLVED,     "reopen"):        IN_PROGRESS,

    # Cancel can be initiated from any pre-resolved state.
    (OPEN,         "cancel"):        CANCELLED,
    (ASSIGNED,     "cancel"):        CANCELLED,
    (IN_PROGRESS,  "cancel"):        CANCELLED,
    (PENDING_USER, "cancel"):        CANCELLED,
}

TERMINAL = {CLOSED, CANCELLED}


def next_state(current: str, event: str) -> str:
    nxt = TRANSITIONS.get((current, event))
    if nxt is None:
        raise InvalidStateTransition(f"Cannot apply '{event}' to ticket in state '{current}'.")
    return nxt


def allowed_target_states_for(current: str) -> list[str]:
    """List of direct status targets reachable from `current` (useful for UI button rendering)."""
    return sorted({to for (frm, _), to in TRANSITIONS.items() if frm == current})


def event_for_target(current: str, target: str) -> str | None:
    """Reverse lookup: given desired status, find the event name."""
    for (frm, evt), to in TRANSITIONS.items():
        if frm == current and to == target:
            return evt
    return None
