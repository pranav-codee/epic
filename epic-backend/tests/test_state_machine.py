"""State machine tests — these are the safety net for SRS Figure 5 compliance."""
import pytest
from app.modules.tickets.state_machine import next_state, allowed_target_states_for
from app.core.exceptions import InvalidStateTransition


def test_full_happy_path():
    s = "OPEN"
    s = next_state(s, "assign");        assert s == "ASSIGNED"
    s = next_state(s, "start_work");    assert s == "IN_PROGRESS"
    s = next_state(s, "await_user");    assert s == "PENDING_USER"
    s = next_state(s, "user_responds"); assert s == "IN_PROGRESS"
    s = next_state(s, "resolve");       assert s == "RESOLVED"
    s = next_state(s, "confirm");       assert s == "CLOSED"


def test_resolved_can_reopen_to_in_progress():
    """Confirmed by user 30-Jun-2026: Resolved -> In Progress reopen is permitted."""
    assert next_state("RESOLVED", "reopen") == "IN_PROGRESS"


def test_invalid_transition_raises():
    with pytest.raises(InvalidStateTransition):
        next_state("CLOSED", "reopen")
    with pytest.raises(InvalidStateTransition):
        next_state("OPEN", "resolve")


def test_cancel_branches():
    for s in ("OPEN", "ASSIGNED", "IN_PROGRESS", "PENDING_USER"):
        assert next_state(s, "cancel") == "CANCELLED"


def test_terminal_states_have_no_outbound_except_reopen():
    assert "IN_PROGRESS" in allowed_target_states_for("RESOLVED")
    assert allowed_target_states_for("CLOSED") == []
    assert allowed_target_states_for("CANCELLED") == []
