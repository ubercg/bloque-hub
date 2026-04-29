"""Unit tests: would_create_cycle (direct and indirect cycles)."""

import uuid

import pytest
from sqlalchemy.orm import Session

from app.modules.inventory.models import Space, SpaceRelationship, RelationshipType
from app.modules.inventory.services import would_create_cycle


def _make_space(session: Session, tenant_id: uuid.UUID, name: str, slug: str) -> Space:
    s = Space(
        tenant_id=tenant_id,
        name=name,
        slug=slug,
        capacidad_maxima=10,
        precio_por_hora=100,
    )
    session.add(s)
    session.flush()
    return s


def _add_rel(
    session: Session,
    tenant_id: uuid.UUID,
    parent_id: uuid.UUID,
    child_id: uuid.UUID,
) -> None:
    r = SpaceRelationship(
        tenant_id=tenant_id,
        parent_space_id=parent_id,
        child_space_id=child_id,
        relationship_type=RelationshipType.PARENT_CHILD,
    )
    session.add(r)
    session.flush()


@pytest.mark.integration
def test_would_create_cycle_self_loop(tenant_a, db_super: Session):
    """Self-loop (parent == child) is considered a cycle."""
    space_a = _make_space(db_super, tenant_a.id, "A", "space-a-cycle-self")
    db_super.commit()
    assert would_create_cycle(tenant_a.id, space_a.id, space_a.id, db_super) is True


@pytest.mark.integration
def test_would_create_cycle_direct(tenant_a, db_super: Session):
    """Adding B→A when A→B exists creates cycle (direct)."""
    space_a = _make_space(db_super, tenant_a.id, "A", "space-a-cycle-d")
    space_b = _make_space(db_super, tenant_a.id, "B", "space-b-cycle-d")
    db_super.commit()
    _add_rel(db_super, tenant_a.id, space_a.id, space_b.id)
    db_super.commit()
    # Adding parent=B, child=A would create B→A; we have A→B, so cycle B→A→B
    assert would_create_cycle(tenant_a.id, space_b.id, space_a.id, db_super) is True
    # Adding A→B again would be duplicate (handled by unique constraint), not cycle
    assert would_create_cycle(tenant_a.id, space_a.id, space_b.id, db_super) is False


@pytest.mark.integration
def test_would_create_cycle_indirect(tenant_a, db_super: Session):
    """Adding C→A when A→B→C exists creates cycle (indirect)."""
    space_a = _make_space(db_super, tenant_a.id, "A", "space-a-cycle-i")
    space_b = _make_space(db_super, tenant_a.id, "B", "space-b-cycle-i")
    space_c = _make_space(db_super, tenant_a.id, "C", "space-c-cycle-i")
    db_super.commit()
    _add_rel(db_super, tenant_a.id, space_a.id, space_b.id)
    _add_rel(db_super, tenant_a.id, space_b.id, space_c.id)
    db_super.commit()
    # Adding parent=C, child=A: path from A is A→B→C, so we reach C -> cycle
    assert would_create_cycle(tenant_a.id, space_c.id, space_a.id, db_super) is True
