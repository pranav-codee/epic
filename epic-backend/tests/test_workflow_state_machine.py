"""Pure unit tests for app/modules/tickets/workflow.py (SPEC §3) — the safety net for the
ticket-type-specific workflow graphs, mirroring how test_state_machine.py covers the
pre-existing generic state machine."""
import pytest
from app.modules.tickets.workflow import (
    next_workflow_state, allowed_workflow_target_states_for, event_for_workflow_target,
    initial_workflow_status, workflow_statuses_for, is_pause_state, is_terminal_workflow_state,
    WorkflowNotSupported, INCIDENT_WORKFLOW_STATUSES, SERVICE_REQUEST_WORKFLOW_STATUSES,
)


def test_state_sets_match_spec_exactly():
    assert INCIDENT_WORKFLOW_STATUSES == [
        "PROGRESSING", "ON_HOLD", "PEND_3RDPARTY", "PEND_USER", "APPROVED", "RESOLVED",
    ]
    assert SERVICE_REQUEST_WORKFLOW_STATUSES == [
        "PROGRESSING", "ON_HOLD", "PEND_3RDPARTY", "PEND_USER", "IN_APPROVAL", "FULFILLED",
    ]


def test_initial_status_progressing_for_workflow_enabled_types():
    assert initial_workflow_status("INCIDENT") == "PROGRESSING"
    assert initial_workflow_status("SERVICE_REQUEST") == "PROGRESSING"


def test_initial_status_none_for_out_of_scope_types():
    assert initial_workflow_status("PROBLEM") is None
    assert initial_workflow_status("CHANGE_REQUEST") is None
    assert workflow_statuses_for("PROBLEM") == []
    assert workflow_statuses_for("CHANGE_REQUEST") == []


def test_incident_happy_path():
    s = "PROGRESSING"
    s = next_workflow_state("INCIDENT", s, "pend_user");  assert s == "PEND_USER"
    s = next_workflow_state("INCIDENT", s, "resume");     assert s == "PROGRESSING"
    s = next_workflow_state("INCIDENT", s, "approve");    assert s == "APPROVED"
    s = next_workflow_state("INCIDENT", s, "resolve");    assert s == "RESOLVED"


def test_service_request_happy_path():
    s = "PROGRESSING"
    s = next_workflow_state("SERVICE_REQUEST", s, "submit_for_approval"); assert s == "IN_APPROVAL"
    s = next_workflow_state("SERVICE_REQUEST", s, "fulfill");             assert s == "FULFILLED"


def test_pend_3rdparty_and_pend_user_are_pause_states():
    assert is_pause_state("PEND_USER") is True
    assert is_pause_state("PEND_3RDPARTY") is True
    assert is_pause_state("PROGRESSING") is False
    assert is_pause_state("ON_HOLD") is False
    assert is_pause_state(None) is False


def test_terminal_states():
    assert is_terminal_workflow_state("RESOLVED") is True
    assert is_terminal_workflow_state("FULFILLED") is True
    assert is_terminal_workflow_state("PROGRESSING") is False


def test_invalid_transition_raises_value_error():
    with pytest.raises(ValueError):
        next_workflow_state("INCIDENT", "RESOLVED", "hold")
    with pytest.raises(ValueError):
        next_workflow_state("INCIDENT", "ON_HOLD", "resolve")  # must resume first


def test_unsupported_ticket_type_raises():
    with pytest.raises(WorkflowNotSupported):
        next_workflow_state("PROBLEM", "PROGRESSING", "hold")


def test_incident_and_service_request_states_do_not_cross_over():
    """APPROVED only exists for Incidents; IN_APPROVAL/FULFILLED only for Service Requests."""
    with pytest.raises(ValueError):
        next_workflow_state("SERVICE_REQUEST", "PROGRESSING", "approve")
    with pytest.raises(ValueError):
        next_workflow_state("INCIDENT", "PROGRESSING", "submit_for_approval")


def test_allowed_target_states_for_progressing():
    incident_targets = allowed_workflow_target_states_for("INCIDENT", "PROGRESSING")
    assert incident_targets == sorted(["ON_HOLD", "PEND_3RDPARTY", "PEND_USER", "APPROVED", "RESOLVED"])

    sr_targets = allowed_workflow_target_states_for("SERVICE_REQUEST", "PROGRESSING")
    assert sr_targets == sorted(["ON_HOLD", "PEND_3RDPARTY", "PEND_USER", "IN_APPROVAL", "FULFILLED"])


def test_allowed_target_states_empty_for_unsupported_type():
    assert allowed_workflow_target_states_for("PROBLEM", "PROGRESSING") == []


def test_terminal_states_have_no_outbound_except_reopen():
    assert allowed_workflow_target_states_for("INCIDENT", "RESOLVED") == ["PROGRESSING"]
    assert allowed_workflow_target_states_for("SERVICE_REQUEST", "FULFILLED") == ["PROGRESSING"]


def test_event_for_workflow_target_reverse_lookup():
    assert event_for_workflow_target("INCIDENT", "PROGRESSING", "PEND_USER") == "pend_user"
    assert event_for_workflow_target("INCIDENT", "PROGRESSING", "IN_APPROVAL") is None
    assert event_for_workflow_target("PROBLEM", "PROGRESSING", "ON_HOLD") is None


def test_on_hold_requires_resume_before_resolving():
    """Deliberate design decision (see workflow.py docstring): ON_HOLD is an administrative
    hold, not resolvable directly — must resume to PROGRESSING first."""
    assert event_for_workflow_target("INCIDENT", "ON_HOLD", "RESOLVED") is None
    assert event_for_workflow_target("SERVICE_REQUEST", "ON_HOLD", "FULFILLED") is None