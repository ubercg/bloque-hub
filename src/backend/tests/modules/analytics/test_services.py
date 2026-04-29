import pytest
from uuid import uuid4
from unittest.mock import MagicMock
from app.modules.analytics.services import get_dashboard_metrics

def test_get_dashboard_metrics():
    db_mock = MagicMock()
    tenant_id = uuid4()
    
    # Mocking db.execute().fetchone() for 4 queries
    mock_result = MagicMock()
    mock_result.total_discounts = 10
    mock_result.justified_discounts = 8
    mock_result.total_snapshots = 5
    mock_result.invariant_snapshots = 5
    mock_result.total_hybrid = 20
    mock_result.accurate_hybrid = 19
    mock_result.total_ready = 15
    mock_result.with_checklist = 15
    
    db_mock.execute.return_value.fetchone.return_value = mock_result
    
    metrics = get_dashboard_metrics(db_mock, tenant_id)
    
    assert metrics.kr23.justification_rate == 80.0
    assert metrics.kr24.invariance_rate == 100.0
    assert metrics.kr25.precision_rate == 95.0
    assert metrics.kr27.compliance_rate == 100.0