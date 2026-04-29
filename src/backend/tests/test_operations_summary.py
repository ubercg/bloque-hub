"""Tests for operations reservations-summary and bulk generate-slip."""

import uuid
from datetime import date

import pytest
from fastapi.testclient import TestClient

from app.main import app


def test_reservations_summary_requires_auth(client: TestClient):
    r = client.get("/api/operations/reservations-summary")
    assert r.status_code == 401


def test_reservations_summary_operations_ok(client: TestClient, token_operations_a: str):
    r = client.get(
        "/api/operations/reservations-summary",
        headers={"Authorization": f"Bearer {token_operations_a}"},
    )
    assert r.status_code == 200
    data = r.json()
    assert "kpis" in data
    assert "reservations" in data
    assert "events_today" in data["kpis"]
    assert "spaces_occupied_today" in data["kpis"]
    assert "pending_slip_groups_today" in data["kpis"]
    assert "confirmed_groups_today" in data["kpis"]


def test_bulk_generate_slip_validation(client: TestClient, token_commercial_a: str):
    r = client.post(
        "/api/reservations/bulk/generate-slip",
        headers={"Authorization": f"Bearer {token_commercial_a}"},
        json={},
    )
    assert r.status_code == 422
