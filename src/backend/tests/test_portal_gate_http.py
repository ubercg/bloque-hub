"""Unit tests for `api/portal_gate_http.py` (REQ-013, design.md §5).

`raise_for_portal_status` is the ONE shared helper used by both the gate and
submit-revalidation call sites (RN-016) — no per-site catch-all `else`
branch that could silently swallow a newly added `PortalFolioStatus` member
as `403 FOLIO_NOT_ELIGIBLE`.
"""

import pytest
from fastapi import HTTPException

from app.api.portal_gate_http import (
    PORTAL_AUTH_FAILURE_HTTP_STATUS,
    _STATUS_TO_ERROR,
    raise_for_portal_status,
)
from app.modules.portal_gate.client import PortalFolioStatus


class TestRaiseForPortalStatusNoOp:
    def test_eligible_is_a_no_op(self):
        assert raise_for_portal_status(PortalFolioStatus.ELIGIBLE) is None


class TestRaiseForPortalStatusMappedMembers:
    def test_not_eligible_raises_403_with_reason(self):
        with pytest.raises(HTTPException) as exc_info:
            raise_for_portal_status(PortalFolioStatus.NOT_ELIGIBLE)

        assert exc_info.value.status_code == 403
        assert exc_info.value.detail["reason"] == "FOLIO_NOT_ELIGIBLE"

    def test_unavailable_raises_503_with_reason(self):
        with pytest.raises(HTTPException) as exc_info:
            raise_for_portal_status(PortalFolioStatus.UNAVAILABLE)

        assert exc_info.value.status_code == 503
        assert exc_info.value.detail["reason"] == "PORTAL_UNAVAILABLE"

    def test_auth_failure_raises_configured_status_with_reason(self):
        with pytest.raises(HTTPException) as exc_info:
            raise_for_portal_status(PortalFolioStatus.INTEGRATION_AUTH_FAILURE)

        assert exc_info.value.status_code == PORTAL_AUTH_FAILURE_HTTP_STATUS
        assert exc_info.value.detail["reason"] == "INTEGRATION_AUTH_FAILURE"

    def test_auth_failure_message_has_no_call_to_action(self):
        """Delivery decision #4 / design §7: system fault, NO call to
        action — never invites a retry, never claims an alert was raised."""
        with pytest.raises(HTTPException) as exc_info:
            raise_for_portal_status(PortalFolioStatus.INTEGRATION_AUTH_FAILURE)

        message = exc_info.value.detail["message"].lower()
        assert "intenta de nuevo" not in message
        assert "intenta más tarde" not in message
        assert "contacta" not in message
        assert "soporte" not in message


class TestEveryPortalStatusIsMapped:
    def test_every_portal_status_is_mapped(self):
        # Adding a PortalFolioStatus member without a matching entry here
        # turns THIS test red — the test-time half of "fails loudly twice"
        # (design §5).
        assert set(PortalFolioStatus) == {PortalFolioStatus.ELIGIBLE} | set(_STATUS_TO_ERROR)


class TestUnmappedStatusFailsLoudly:
    def test_unmapped_status_resolves_to_500_never_403(self, monkeypatch):
        import app.api.portal_gate_http as portal_gate_http

        # Simulate a hypothetical unmapped member without needing a real
        # fifth enum value — patch the mapping dict to omit NOT_ELIGIBLE.
        monkeypatch.setattr(
            portal_gate_http,
            "_STATUS_TO_ERROR",
            {k: v for k, v in _STATUS_TO_ERROR.items() if k != PortalFolioStatus.NOT_ELIGIBLE},
        )

        with pytest.raises(HTTPException) as exc_info:
            portal_gate_http.raise_for_portal_status(PortalFolioStatus.NOT_ELIGIBLE)

        assert exc_info.value.status_code == 500
        assert exc_info.value.detail["reason"] == "PORTAL_STATUS_UNMAPPED"
        assert exc_info.value.status_code != 403

    def test_unmapped_status_logs_the_unmapped_marker(self, monkeypatch, caplog):
        import app.api.portal_gate_http as portal_gate_http

        monkeypatch.setattr(
            portal_gate_http,
            "_STATUS_TO_ERROR",
            {k: v for k, v in _STATUS_TO_ERROR.items() if k != PortalFolioStatus.NOT_ELIGIBLE},
        )

        with caplog.at_level("ERROR", logger="app.api.portal_gate_http"):
            with pytest.raises(HTTPException):
                portal_gate_http.raise_for_portal_status(PortalFolioStatus.NOT_ELIGIBLE)

        records = [r for r in caplog.records if "portal_gate.unmapped_status" in r.getMessage()]
        assert len(records) == 1
        assert "not_eligible" in records[0].getMessage()
