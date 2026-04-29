import uuid
import pytest
from datetime import datetime, timedelta
from decimal import Decimal

from app.modules.pricing.models import PricingRule
from app.modules.pricing.services import calculate_hybrid_price


def test_calculate_hybrid_price_under_6h():
    rule = PricingRule(base_6h=Decimal('100.0000'), base_12h=Decimal('180.0000'), extra_hour_rate=Decimal('20.0000'))
    start = datetime(2023, 1, 1, 10, 0)
    end = start + timedelta(hours=5)
    
    total_hours, base_price, extra_price, total_price = calculate_hybrid_price(start, end, rule)
    
    assert total_hours == Decimal('5.00')
    assert base_price == Decimal('100.0000')
    assert extra_price == Decimal('0.0000')
    assert total_price == Decimal('100.0000')


def test_calculate_hybrid_price_under_12h():
    rule = PricingRule(base_6h=Decimal('100.0000'), base_12h=Decimal('180.0000'), extra_hour_rate=Decimal('20.0000'))
    start = datetime(2023, 1, 1, 10, 0)
    end = start + timedelta(hours=10)
    
    total_hours, base_price, extra_price, total_price = calculate_hybrid_price(start, end, rule)
    
    assert total_hours == Decimal('10.00')
    assert base_price == Decimal('180.0000')
    assert extra_price == Decimal('0.0000')
    assert total_price == Decimal('180.0000')


def test_calculate_hybrid_price_over_12h():
    rule = PricingRule(base_6h=Decimal('100.0000'), base_12h=Decimal('180.0000'), extra_hour_rate=Decimal('20.0000'))
    start = datetime(2023, 1, 1, 10, 0)
    end = start + timedelta(hours=14, minutes=30)
    
    total_hours, base_price, extra_price, total_price = calculate_hybrid_price(start, end, rule)
    
    assert total_hours == Decimal('14.50')
    assert base_price == Decimal('180.0000')
    assert extra_price == Decimal('50.0000')
    assert total_price == Decimal('230.0000')

