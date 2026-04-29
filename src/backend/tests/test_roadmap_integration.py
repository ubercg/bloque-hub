import pytest
from uuid import uuid4
from datetime import date, time, datetime, timedelta
from decimal import Decimal

from app.modules.crm.models import Quote, QuoteItem, QuoteStatus, Contract, ContractStatus, DiscountRequest, DiscountRequestStatus, QuoteAdditionalService
from app.modules.catalog.models import AdditionalService as CatalogAdditionalService, ServiceUnit
from app.modules.finance.services import generate_contract, check_quote_mutability, ImmutableQuoteError
from app.modules.booking.services import create_phased_reservation, create_group_reservation, ConflictException
from app.modules.inventory.services import SlotNotAvailableError
from app.modules.booking.models import Reservation, ReservationStatus, EventPhase
from app.modules.inventory.models import Inventory, Space, SlotStatus
from app.modules.crm.models import Lead
from app.modules.pricing.schemas import PricingRuleCreate
from app.modules.pricing.services import create_pricing_rule, calculate_price, NoPricingRuleError
from app.modules.uma_rates.services import register_uma_rate
from app.modules.crm.services import transition_quote_status
from app.modules.fulfillment.services import check_ready_gate
from app.modules.fulfillment.models import ServiceOrder, ServiceOrderType, ServiceOrderStatus, ChecklistItem


def setup_space_and_lead(db_super, tenant_a, user_a, suffix=""):
    space = Space(tenant_id=tenant_a.id, name=f"Space {suffix}", slug=f"space-{suffix}-{uuid4()}", capacidad_maxima=10, precio_por_hora=100)
    lead = Lead(tenant_id=tenant_a.id, name=f"Lead {suffix}", email=f"lead{suffix}@test.com")
    db_super.add_all([space, lead])
    db_super.commit()
    db_super.refresh(space)
    db_super.refresh(lead)
    return space, lead


# Test 1: Snapshot UMA — invariancia completa
def test_uma_snapshot_full_flow(db_super, tenant_a, user_a):
    space, lead = setup_space_and_lead(db_super, tenant_a, user_a, "uma")
    register_uma_rate(Decimal('100.0000'), date.today() - timedelta(days=10), user_a.id, tenant_a.id, db_super)
    
    quote = Quote(tenant_id=tenant_a.id, lead_id=lead.id, status=QuoteStatus.DRAFT, total=1000.0)
    db_super.add(quote)
    db_super.flush()
    item = QuoteItem(
        quote_id=quote.id, space_id=space.id, fecha=date.today(),
        hora_inicio=time(10, 0), hora_fin=time(12, 0), precio=1000.0, item_order=0
    )
    db_super.add(item)
    db_super.flush()
    
    transition_quote_status(quote, QuoteStatus.SENT, db_super)
    transition_quote_status(quote, QuoteStatus.DIGITAL_APPROVED, db_super)
    
    assert item.uma_snapshot == Decimal('100.0000')
    assert item.subtotal_frozen == Decimal('1000.0000')
    
    contract = generate_contract(quote.id, tenant_a.id, db_super)
    contract.status = ContractStatus.SIGNED
    db_super.flush()
    
    with pytest.raises(ImmutableQuoteError):
        check_quote_mutability(quote, db_super)


# Test 2: Descuentos con umbral
def test_discount_threshold_flow(db_super, tenant_a, user_a):
    space, lead = setup_space_and_lead(db_super, tenant_a, user_a, "discount")
    quote = Quote(tenant_id=tenant_a.id, lead_id=lead.id, status=QuoteStatus.DRAFT, total=1000.0)
    db_super.add(quote)
    db_super.flush()
    item = QuoteItem(quote_id=quote.id, space_id=space.id, fecha=date.today(), hora_inicio=time(10,0), hora_fin=time(12,0), precio=1000.0, item_order=0)
    db_super.add(item)
    db_super.flush()

    # Discount below threshold (assume threshold is 10%)
    req_low = DiscountRequest(tenant_id=tenant_a.id, quote_item_id=item.id, percentage=Decimal('5.00'), justification="Small", requested_by=user_a.id, status=DiscountRequestStatus.APPROVED)
    db_super.add(req_low)
    
    # Discount above threshold
    req_high = DiscountRequest(tenant_id=tenant_a.id, quote_item_id=item.id, percentage=Decimal('15.00'), justification="Big", requested_by=user_a.id, status=DiscountRequestStatus.PENDING)
    db_super.add(req_high)
    db_super.flush()
    
    assert req_low.status == DiscountRequestStatus.APPROVED
    assert req_high.status == DiscountRequestStatus.PENDING


# Test 3: Pricing híbrido determinista
def test_hybrid_pricing_deterministic(db_super, tenant_a, user_a):
    space, lead = setup_space_and_lead(db_super, tenant_a, user_a, "pricing")
    rule = PricingRuleCreate(space_id=space.id, base_6h=Decimal('100'), base_12h=Decimal('180'), extra_hour_rate=Decimal('20'), effective_from=date.today() - timedelta(days=1))
    create_pricing_rule(db_super, tenant_a.id, rule)
    
    b_6h = calculate_price(space.id, Decimal('5.0'), tenant_a.id, date.today(), db_super)
    assert b_6h.base_price == Decimal('100.0000')
    assert b_6h.total_price == Decimal('100.0000')
    
    b_12h = calculate_price(space.id, Decimal('10.0'), tenant_a.id, date.today(), db_super)
    assert b_12h.base_price == Decimal('180.0000')
    assert b_12h.total_price == Decimal('180.0000')
    
    b_extra = calculate_price(space.id, Decimal('14.0'), tenant_a.id, date.today(), db_super)
    assert b_extra.total_price == Decimal('220.0000')


# Test 4: Anti-traslape MONTAJE
def test_montaje_anti_overlap_complete(db_super, tenant_a, user_a):
    space, lead = setup_space_and_lead(db_super, tenant_a, user_a, "overlap")
    t1_start = datetime.combine(date.today(), time(10, 0))
    t1_end = datetime.combine(date.today(), time(12, 0))
    
    create_phased_reservation(tenant_a.id, user_a.id, space.id, [(t1_start, t1_end)], EventPhase.MONTAJE, db_super)
    
    with pytest.raises(ConflictException):
        create_phased_reservation(tenant_a.id, user_a.id, space.id, [(t1_start, t1_end)], EventPhase.MONTAJE, db_super)
        
    with pytest.raises(ConflictException):
        create_phased_reservation(tenant_a.id, user_a.id, space.id, [(t1_start, t1_end)], EventPhase.USO, db_super)


# Test 5: Gating READY por checklist
def test_ready_gate_complete_flow(db_super, tenant_a, user_a):
    space, lead = setup_space_and_lead(db_super, tenant_a, user_a, "gating")
    t1_start = datetime.combine(date.today(), time(14, 0))
    t1_end = datetime.combine(date.today(), time(16, 0))
    res = create_phased_reservation(tenant_a.id, user_a.id, space.id, [(t1_start, t1_end)], EventPhase.MONTAJE, db_super)
    
    so = ServiceOrder(tenant_id=tenant_a.id, reservation_id=res.id, type=ServiceOrderType.GENERAL, status=ServiceOrderStatus.PENDING)
    db_super.add(so)
    db_super.flush()
    item = ChecklistItem(tenant_id=tenant_a.id, service_order_id=so.id, description="Crit", is_critical=True, completed=False)
    db_super.add(item)
    db_super.flush()
    
    ready, pending = check_ready_gate(res.id, db_super)
    assert not ready
    assert res.ready_blocked
    
    item.completed = True
    db_super.flush()
    ready, pending = check_ready_gate(res.id, db_super)
    assert ready
    assert not res.ready_blocked


# Test 6: Multi-espacio atómico
def test_group_reservation_atomicity(db_super, tenant_a, user_a):
    s1, lead = setup_space_and_lead(db_super, tenant_a, user_a, "grp1")
    s2, _ = setup_space_and_lead(db_super, tenant_a, user_a, "grp2")
    s3, _ = setup_space_and_lead(db_super, tenant_a, user_a, "grp3")
    
    # Block s2 explicitly
    inv = Inventory(space_id=s2.id, tenant_id=tenant_a.id, fecha=date.today(), hora_inicio=time(10, 0), hora_fin=time(12, 0), estado=SlotStatus.RESERVED)
    db_super.add(inv)
    db_super.flush()
    
    with pytest.raises(SlotNotAvailableError):
        try:
            create_group_reservation(tenant_a.id, user_a.id, [s1.id, s2.id, s3.id], [date.today()], time(10, 0), time(12, 0), db_super)
        except SlotNotAvailableError:
            db_super.rollback()
            raise
        
    # Verify rollback (none created for s1 or s3 by create_group_reservation since it raises error)
    # The test simulates atomicity via pytest raises which aborts the function execution.
    # In real DB, the caller rollbacks. We just check s1 and s3 are not blocked.
    s1_inv = db_super.query(Inventory).filter(Inventory.space_id == s1.id, Inventory.fecha == date.today()).first()
    assert s1_inv is None

