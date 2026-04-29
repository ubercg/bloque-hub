import pytest
import uuid
from datetime import date, timedelta
from decimal import Decimal
from sqlalchemy.exc import IntegrityError

from app.modules.uma_rates.models import UMARate
from app.modules.uma_rates.services import register_uma_rate, get_current_uma, UmaRateConflictException, UmaRateNotFoundException

def test_uma_rate_append_only(db_super, tenant_a, user_finance_a):
    # Test inserting an UMA rate works
    rate = register_uma_rate(
        value=Decimal('108.5700'),
        effective_date=date.today(),
        user_id=user_finance_a.id,
        tenant_id=tenant_a.id,
        db=db_super
    )
    assert rate.value == Decimal('108.5700')
    assert rate.created_by == user_finance_a.id
    
    # Duplicate effective_date should raise UmaRateConflictException
    with pytest.raises(UmaRateConflictException):
        register_uma_rate(
            value=Decimal('110.0000'),
            effective_date=date.today(),
            user_id=user_finance_a.id,
            tenant_id=tenant_a.id,
            db=db_super
        )

def test_uma_rate_current_resolution(db_super, tenant_a, user_finance_a):
    db_super.query(UMARate).delete()
    db_super.commit()
    
    # 3 rates over time
    d1 = date.today() - timedelta(days=30)
    d2 = date.today() - timedelta(days=15)
    d3 = date.today() + timedelta(days=15) # Future
    
    register_uma_rate(Decimal('100.0000'), d1, user_finance_a.id, tenant_a.id, db_super)
    register_uma_rate(Decimal('105.0000'), d2, user_finance_a.id, tenant_a.id, db_super)
    register_uma_rate(Decimal('110.0000'), d3, user_finance_a.id, tenant_a.id, db_super)
    
    # Current UMA (today) should be d2
    current = get_current_uma(tenant_a.id, date.today(), db_super)
    assert current.value == Decimal('105.0000')

    # Ask for date exactly at d1
    past_uma = get_current_uma(tenant_a.id, d1, db_super)
    assert past_uma.value == Decimal('100.0000')
    
    # Ask for far past before d1
    with pytest.raises(UmaRateNotFoundException):
        get_current_uma(tenant_a.id, d1 - timedelta(days=5), db_super)

