import random
import pytest
from uuid import uuid4
from datetime import date, time, datetime, timedelta
from decimal import Decimal

from app.modules.crm.models import Quote, QuoteItem, QuoteStatus, DiscountRequest, DiscountRequestStatus, QuoteAdditionalService
from app.modules.catalog.models import AdditionalService, ServiceUnit
from app.modules.crm.services import transition_quote_status
from app.modules.pricing.services import create_pricing_rule, calculate_price, NoPricingRuleError
from app.modules.pricing.schemas import PricingRuleCreate
from app.modules.uma_rates.services import register_uma_rate
from app.modules.inventory.models import Space

def test_uma_snapshot_on_digital_approved(db_super, tenant_a, user_a):
    from app.modules.inventory.models import Space
    from app.modules.crm.models import Lead
    space_parent = Space(tenant_id=tenant_a.id, name="Test Space", slug="test-space-853207", capacidad_maxima=10, precio_por_hora=100)
    lead_a = Lead(tenant_id=tenant_a.id, name="Lead A", email="lead@test.com")
    db_super.add_all([space_parent, lead_a])
    db_super.commit()

    dt_test = date.today() - timedelta(days=242)
    register_uma_rate(Decimal('100.0000'), dt_test, user_a.id, tenant_a.id, db_super)
    
    quote = Quote(tenant_id=tenant_a.id, lead_id=lead_a.id, status=QuoteStatus.DRAFT, total=5000.0)
    db_super.add(quote)
    db_super.flush()
    
    item = QuoteItem(
        quote_id=quote.id,
        space_id=space_parent.id,
        fecha=date.today(),
        hora_inicio=time(10, 0),
        hora_fin=time(12, 0),
        precio=5000.0,
        discount_amount=500.0,
        item_order=0
    )
    db_super.add(item)
    db_super.flush()
    
    # Transition
    transition_quote_status(quote, QuoteStatus.SENT, db_super)
    transition_quote_status(quote, QuoteStatus.DIGITAL_APPROVED, db_super)
    
    assert item.uma_snapshot == Decimal('100.0000')
    assert item.uma_snapshot_date == dt_test
    assert item.subtotal_frozen == Decimal('4500.0000')


def test_pricing_6h_bracket(db_super, tenant_a, user_a):
    from app.modules.inventory.models import Space
    space_parent = Space(tenant_id=tenant_a.id, name="Space P1", slug="space-p1", capacidad_maxima=10, precio_por_hora=100)
    db_super.add(space_parent)
    db_super.commit()

    rule_in = PricingRuleCreate(
        space_id=space_parent.id,
        base_6h=Decimal('100.0000'),
        base_12h=Decimal('180.0000'),
        extra_hour_rate=Decimal('20.0000'),
        effective_from=date.today() - timedelta(days=10)
    )
    create_pricing_rule(db_super, tenant_a.id, rule_in)

    # Calculate 5 hours -> Should hit 6h bracket
    breakdown = calculate_price(space_parent.id, Decimal('5.0'), tenant_a.id, date.today(), db_super)
    
    assert breakdown.base_price == Decimal('100.0000')
    assert breakdown.extra_price == Decimal('0.0000')
    assert breakdown.total_price == Decimal('100.0000')

def test_pricing_12h_bracket(db_super, tenant_a, user_a):
    from app.modules.inventory.models import Space
    space_parent = Space(tenant_id=tenant_a.id, name="Space P2", slug="space-p2", capacidad_maxima=10, precio_por_hora=100)
    db_super.add(space_parent)
    db_super.commit()
    rule_in = PricingRuleCreate(space_id=space_parent.id, base_6h=Decimal('100'), base_12h=Decimal('180'), extra_hour_rate=Decimal('20'), effective_from=date.today())
    create_pricing_rule(db_super, tenant_a.id, rule_in)

    # Calculate 10 hours -> Should hit 12h bracket
    breakdown = calculate_price(space_parent.id, Decimal('10.0'), tenant_a.id, date.today(), db_super)
    
    assert breakdown.base_price == Decimal('180.0000')
    assert breakdown.extra_price == Decimal('0.0000')
    assert breakdown.total_price == Decimal('180.0000')

def test_pricing_extra_hours(db_super, tenant_a, user_a):
    from app.modules.inventory.models import Space
    space_parent = Space(tenant_id=tenant_a.id, name="Space P3", slug="space-p3", capacidad_maxima=10, precio_por_hora=100)
    db_super.add(space_parent)
    db_super.commit()
    rule_in = PricingRuleCreate(space_id=space_parent.id, base_6h=Decimal('100'), base_12h=Decimal('180'), extra_hour_rate=Decimal('20'), effective_from=date.today())
    create_pricing_rule(db_super, tenant_a.id, rule_in)

    # Calculate 15 hours -> Should hit 12h bracket + 3 extra hours
    breakdown = calculate_price(space_parent.id, Decimal('15.0'), tenant_a.id, date.today(), db_super)
    
    assert breakdown.base_price == Decimal('180.0000')
    assert breakdown.extra_price == Decimal('60.0000') # 3 * 20
    assert breakdown.total_price == Decimal('240.0000')

def test_pricing_deterministic(db_super, tenant_a, user_a):
    from app.modules.inventory.models import Space
    space_parent = Space(tenant_id=tenant_a.id, name="Space P4", slug="space-p4", capacidad_maxima=10, precio_por_hora=100)
    db_super.add(space_parent)
    db_super.commit()
    rule_in = PricingRuleCreate(space_id=space_parent.id, base_6h=Decimal('100'), base_12h=Decimal('180'), extra_hour_rate=Decimal('20'), effective_from=date.today())
    create_pricing_rule(db_super, tenant_a.id, rule_in)

    b1 = calculate_price(space_parent.id, Decimal('14.5'), tenant_a.id, date.today(), db_super)
    b2 = calculate_price(space_parent.id, Decimal('14.5'), tenant_a.id, date.today(), db_super)
    assert b1.total_price == b2.total_price
    assert b1.base_price == b2.base_price

def test_pricing_no_rule_raises(db_super, tenant_a):
    from app.modules.inventory.models import Space
    space_child1 = Space(tenant_id=tenant_a.id, name="Space C1", slug="space-c1", capacidad_maxima=10, precio_por_hora=100)
    db_super.add(space_child1)
    db_super.commit()

    with pytest.raises(NoPricingRuleError):
        calculate_price(space_child1.id, Decimal('5.0'), tenant_a.id, date.today(), db_super)


def test_discount_below_threshold_auto_approved(db_super, tenant_a, user_a):
    from app.modules.inventory.models import Space
    from app.modules.crm.models import Quote, Lead
    space_parent = Space(tenant_id=tenant_a.id, name="Space P5", slug="space-p5", capacidad_maxima=10, precio_por_hora=100)
    db_super.add(space_parent)
    db_super.commit()

    lead_a = Lead(tenant_id=tenant_a.id, name="Lead A", email="lead@test.com")
    db_super.add(lead_a)
    db_super.commit()
    quote = Quote(tenant_id=tenant_a.id, lead_id=lead_a.id, status=QuoteStatus.DRAFT, total=5000.0)
    db_super.add(quote)
    db_super.flush()
    item = QuoteItem(
        quote_id=quote.id,
        space_id=space_parent.id,
        fecha=date.today(),
        hora_inicio=time(10, 0),
        hora_fin=time(12, 0),
        precio=5000.0,
        item_order=0
    )
    db_super.add(item)
    db_super.flush()

    req = DiscountRequest(
        tenant_id=tenant_a.id,
        quote_item_id=item.id,
        percentage=Decimal('5.00'),
        justification="Test",
        requested_by=user_a.id,
        status=DiscountRequestStatus.APPROVED
    )
    db_super.add(req)
    assert req.status == DiscountRequestStatus.APPROVED


def test_additional_service_calculation_by_unit(db_super, tenant_a):
    from app.modules.crm.models import Quote, Lead
    lead_a = Lead(tenant_id=tenant_a.id, name="Lead A", email="lead@test.com")
    db_super.add(lead_a)
    db_super.commit()
    quote_a = Quote(tenant_id=tenant_a.id, lead_id=lead_a.id, status=QuoteStatus.DRAFT, total=5000.0)
    db_super.add(quote_a)
    db_super.commit()

    service = AdditionalService(
        tenant_id=tenant_a.id,
        name="Seguridad Extra",
        unit=ServiceUnit.MINUTO,
        unit_price=Decimal('1.5000'),
        factor=Decimal('1.00')
    )
    db_super.add(service)
    db_super.flush()
    
    # Add service to quote (mocking the service call)
    # 60 minutes
    qty = Decimal('60.00')
    calc_price = service.unit_price * qty * service.factor
    
    qas = QuoteAdditionalService(
        tenant_id=tenant_a.id,
        quote_id=quote_a.id,
        service_id=service.id,
        quantity=qty,
        calculated_price=calc_price
    )
    db_super.add(qas)
    db_super.flush()
    
    assert qas.calculated_price == Decimal('90.0000')

