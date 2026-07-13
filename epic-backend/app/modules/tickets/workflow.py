"""
SPEC §3 — Status/workflow.

Ticket-type-specific workflow state machines, additive alongside the existing generic
`status` field/state_machine.py (OPEN/ASSIGNED/IN_PROGRESS/PENDING_USER/RESOLVED/CLOSED/
CANCELLED). That generic field remains the ticket's overall lifecycle/visibility status —
untouched, per PROGRESS.md's Session-1 decision to keep additive/non-breaking changes — and
still governs things like "is this ticket terminal" for attachments/notifications/SLA
scanning.

`workflow_status` (new column, see models.py) is the finer-grained, ITIL-flavoured status
SPEC §3 actually asks for, and its allowed values depend on `ticket_type`:

    INCIDENT:        PROGRESSING, ON_HOLD, PEND_3RDPARTY, PEND_USER, APPROVED, RESOLVED
    SERVICE_REQUEST:  PROGRESSING, ON_HOLD, PEND_3RDPARTY, PEND_USER, IN_APPROVAL, FULFILLED

SPEC §3 doesn't lay out the actual transition graph — only the state list plus "Resolution
SLA clock pauses during PEND_USER/PEND_3RDPARTY." The graph below is this session's design
call (documented in /docs/PROGRESS.md): PROGRESSING is the hub state; ON_HOLD/PEND_3RDPARTY/
PEND_USER are all resumable back to PROGRESSING; the approval state
(APPROVED for incidents, IN_APPROVAL for service requests) sits between PROGRESSING and the
terminal state; and the terminal state (RESOLVED/FULFILLED) is reachable from PROGRESSING,
the approval state, and both pause states (so an ticket doesn't have to un-pause purely to
be closed out) but NOT directly from ON_HOLD (an administrative hold — resume first).

PROBLEM and CHANGE_REQUEST ticket types are out of SPEC §3's scope (the spec only defines
state sets for Incidents and Service Requests) — `workflow_status` stays NULL for those and
any attempt to transition it raises DomainError. This is a deliberate scope decision, not an
oversight; see PROGRESS.md.
"""


# ---------- State sets ----------

INCIDENT_WORKFLOW_STATUSES = [
    "PROGRESSING", "ON_HOLD", "PEND_3RDPARTY", "PEND_USER", "APPROVED", "RESOLVED",
]

SERVICE_REQUEST_WORKFLOW_STATUSES = [
    "PROGRESSING", "ON_HOLD", "PEND_3RDPARTY", "PEND_USER", "IN_APPROVAL", "FULFILLED",
]

# Ticket types that SPEC §3 actually defines a workflow for. PROBLEM/CHANGE_REQUEST are
# intentionally excluded (see module docstring).
WORKFLOW_ENABLED_TICKET_TYPES = {"INCIDENT", "SERVICE_REQUEST"}

# States in which the Resolution SLA clock is paused (SPEC §3, literal requirement).
# Same two state *names* appear in both ticket types' sets, so this set applies to both.
PAUSE_WORKFLOW_STATUSES = {"PEND_USER", "PEND_3RDPARTY"}

# Terminal workflow states per ticket type — once reached, no further workflow_status
# transition is allowed for that ticket (mirrors state_machine.py's TERMINAL concept).
TERMINAL_WORKFLOW_STATUSES = {"RESOLVED", "FULFILLED"}

INITIAL_WORKFLOW_STATUS = "PROGRESSING"


def workflow_statuses_for(ticket_type: str) -> list[str]:
    if ticket_type == "INCIDENT":
        return INCIDENT_WORKFLOW_STATUSES
    if ticket_type == "SERVICE_REQUEST":
        return SERVICE_REQUEST_WORKFLOW_STATUSES
    return []


def initial_workflow_status(ticket_type: str) -> str | None:
    """Starting workflow_status for a freshly-created ticket, or None for ticket types
    SPEC §3 doesn't define a workflow for (PROBLEM, CHANGE_REQUEST)."""
    if ticket_type in WORKFLOW_ENABLED_TICKET_TYPES:
        return INITIAL_WORKFLOW_STATUS
    return None


# ---------- Transition graphs ----------
# (from_state, event) -> to_state. Mirrors the (from, event) -> to convention already used
# in state_machine.py so both machines read the same way.

_INCIDENT_TRANSITIONS = {
    ("PROGRESSING",    "hold"):            "ON_HOLD",
    ("PROGRESSING",    "pend_3rdparty"):   "PEND_3RDPARTY",
    ("PROGRESSING",    "pend_user"):       "PEND_USER",
    ("PROGRESSING",    "approve"):         "APPROVED",
    ("PROGRESSING",    "resolve"):         "RESOLVED",

    ("ON_HOLD",        "resume"):          "PROGRESSING",
    ("PEND_3RDPARTY",  "resume"):          "PROGRESSING",
    ("PEND_USER",      "resume"):          "PROGRESSING",

    ("PEND_3RDPARTY",  "resolve"):         "RESOLVED",
    ("PEND_USER",      "resolve"):         "RESOLVED",
    ("APPROVED",       "resolve"):         "RESOLVED",
    ("APPROVED",       "resume"):          "PROGRESSING",

    # Reopen path — mirrors state_machine.py's RESOLVED -> IN_PROGRESS reopen decision
    # (30-Jun-2026), applied here as RESOLVED -> PROGRESSING.
    ("RESOLVED",       "reopen"):          "PROGRESSING",
}

_SERVICE_REQUEST_TRANSITIONS = {
    ("PROGRESSING",    "hold"):            "ON_HOLD",
    ("PROGRESSING",    "pend_3rdparty"):   "PEND_3RDPARTY",
    ("PROGRESSING",    "pend_user"):       "PEND_USER",
    ("PROGRESSING",    "submit_for_approval"): "IN_APPROVAL",
    ("PROGRESSING",    "fulfill"):         "FULFILLED",

    ("ON_HOLD",        "resume"):          "PROGRESSING",
    ("PEND_3RDPARTY",  "resume"):          "PROGRESSING",
    ("PEND_USER",      "resume"):          "PROGRESSING",

    ("PEND_3RDPARTY",  "fulfill"):         "FULFILLED",
    ("PEND_USER",      "fulfill"):         "FULFILLED",
    ("IN_APPROVAL",    "fulfill"):         "FULFILLED",
    ("IN_APPROVAL",    "resume"):          "PROGRESSING",

    ("FULFILLED",      "reopen"):          "PROGRESSING",
}

_TRANSITIONS_BY_TYPE = {
    "INCIDENT": _INCIDENT_TRANSITIONS,
    "SERVICE_REQUEST": _SERVICE_REQUEST_TRANSITIONS,
}


class WorkflowNotSupported(Exception):
    """Raised when a ticket_type has no SPEC §3 workflow defined (PROBLEM, CHANGE_REQUEST)."""


def _transitions_for(ticket_type: str) -> dict:
    transitions = _TRANSITIONS_BY_TYPE.get(ticket_type)
    if transitions is None:
        raise WorkflowNotSupported(
            f"SPEC §3 defines no workflow for ticket_type={ticket_type!r}; "
            f"only {sorted(WORKFLOW_ENABLED_TICKET_TYPES)} have one."
        )
    return transitions


def next_workflow_state(ticket_type: str, current: str, event: str) -> str:
    """Raises WorkflowNotSupported for an out-of-scope ticket_type, or KeyError-free
    ValueError for an event that isn't valid from `current`."""
    transitions = _transitions_for(ticket_type)
    nxt = transitions.get((current, event))
    if nxt is None:
        raise ValueError(
            f"Cannot apply '{event}' to a {ticket_type} ticket in workflow_status '{current}'."
        )
    return nxt


def allowed_workflow_target_states_for(ticket_type: str, current: str) -> list[str]:
    """Direct workflow_status targets reachable from `current`, for UI button rendering.
    Returns [] for out-of-scope ticket types instead of raising, so callers building a
    response payload don't need a special case."""
    try:
        transitions = _transitions_for(ticket_type)
    except WorkflowNotSupported:
        return []
    return sorted({to for (frm, _), to in transitions.items() if frm == current})


def event_for_workflow_target(ticket_type: str, current: str, target: str) -> str | None:
    """Reverse lookup: given a desired workflow_status, find the event name. Returns None
    (not an exception) for an out-of-scope ticket type or an unreachable target — callers
    turn that into a DomainError with a clear message."""
    try:
        transitions = _transitions_for(ticket_type)
    except WorkflowNotSupported:
        return None
    for (frm, evt), to in transitions.items():
        if frm == current and to == target:
            return evt
    return None


def is_pause_state(workflow_status: str | None) -> bool:
    return workflow_status in PAUSE_WORKFLOW_STATUSES


def is_terminal_workflow_state(workflow_status: str | None) -> bool:
    return workflow_status in TERMINAL_WORKFLOW_STATUSES