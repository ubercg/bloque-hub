"""Tests KYC borradores (reservation_documents) por group_event_id."""

from datetime import date, timedelta
from decimal import Decimal
from io import BytesIO
from uuid import UUID, uuid4

import pytest
from fastapi.testclient import TestClient

MIN_PDF = b"%PDF-1.4\n1 0 obj<<>>endobj\ntrailer<<>>\n%%EOF\n"

CONST_ID = UUID("aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaa1")
INE_FRONT_ID = UUID("aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaa2")
INE_BACK_ID = UUID("aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaa3")
DESCUENTO_ID = UUID("aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaa4")
DOMICILIO_ID = UUID("aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaa6")


@pytest.mark.integration
def test_kyc_completeness_and_upload_supersede(
    client: TestClient,
    token_a: str,
    tenant_a,
    db_super,
):
    from app.modules.inventory.models import Space
    from app.modules.pricing.models import PricingRule

    suf = uuid4().hex[:10]
    event_day = (date.today() + timedelta(days=400)).isoformat()
    space_a = Space(
        tenant_id=tenant_a.id,
        name="Sala KYC",
        slug=f"sala-kyc-{suf}",
        capacidad_maxima=100,
        precio_por_hora=500,
    )
    db_super.add(space_a)
    db_super.commit()
    db_super.refresh(space_a)
    db_super.add(
        PricingRule(
            tenant_id=tenant_a.id,
            space_id=space_a.id,
            base_6h=Decimal("100.0000"),
            base_12h=Decimal("180.0000"),
            extra_hour_rate=Decimal("20.0000"),
            discount_threshold=Decimal("0"),
            effective_from=date(2025, 1, 1),
            effective_to=None,
        )
    )
    db_super.commit()

    ev = client.post(
        "/api/reservation-events",
        headers={"Authorization": f"Bearer {token_a}"},
        json={
            "event_name": "Evento KYC",
            "items": [
                {
                    "space_id": str(space_a.id),
                    "fecha": event_day,
                    "hora_inicio": "10:00:00",
                    "hora_fin": "12:00:00",
                },
            ],
        },
    )
    assert ev.status_code == 201, ev.text
    gid = ev.json()["group_event_id"]

    comp = client.get(
        f"/api/group-events/{gid}/documents/completeness",
        headers={"Authorization": f"Bearer {token_a}"},
    )
    assert comp.status_code == 200
    body = comp.json()
    assert body["is_complete"] is False
    codes_req = {x["type"] for x in body["required"]}
    assert "CONSTANCIA_FISCAL" in codes_req
    assert "COMPROBANTE_DOMICILIO" in codes_req
    assert "DESCUENTO_ACUSE" not in codes_req

    def upload(tid: UUID, content: bytes, name: str = "x.pdf") -> None:
        r = client.post(
            f"/api/group-events/{gid}/documents",
            headers={"Authorization": f"Bearer {token_a}"},
            files={"file": (name, BytesIO(content), "application/pdf")},
            data={"document_type_id": str(tid)},
        )
        assert r.status_code == 201, r.text

    upload(CONST_ID, MIN_PDF)
    upload(INE_FRONT_ID, MIN_PDF)
    upload(INE_BACK_ID, MIN_PDF)
    upload(DOMICILIO_ID, MIN_PDF)

    comp2 = client.get(
        f"/api/group-events/{gid}/documents/completeness",
        headers={"Authorization": f"Bearer {token_a}"},
    )
    assert comp2.json()["is_complete"] is True

    upload(CONST_ID, MIN_PDF + b"v2")
    lst = client.get(
        f"/api/group-events/{gid}/documents?include_history=true",
        headers={"Authorization": f"Bearer {token_a}"},
    )
    assert lst.status_code == 200
    rows = lst.json()
    assert sum(1 for x in rows if x["document_type_code"] == "CONSTANCIA_FISCAL") == 2
    assert any(x["status"] == "SUPERSEDED" for x in rows)


@pytest.mark.integration
def test_descuento_required_when_discount_applied(
    client: TestClient,
    token_a: str,
    tenant_a,
    db_super,
):
    from app.modules.discounts.models import DiscountCode
    from app.modules.inventory.models import Space
    from app.modules.pricing.models import PricingRule

    suf = uuid4().hex[:10]
    event_day = (date.today() + timedelta(days=401)).isoformat()
    space_a = Space(
        tenant_id=tenant_a.id,
        name="Sala KYC2",
        slug=f"sala-kyc2-{suf}",
        capacidad_maxima=100,
        precio_por_hora=500,
    )
    db_super.add(space_a)
    db_super.commit()
    db_super.refresh(space_a)
    db_super.add(
        PricingRule(
            tenant_id=tenant_a.id,
            space_id=space_a.id,
            base_6h=Decimal("100.0000"),
            base_12h=Decimal("180.0000"),
            extra_hour_rate=Decimal("20.0000"),
            discount_threshold=Decimal("0"),
            effective_from=date(2025, 1, 1),
            effective_to=None,
        )
    )
    dc = DiscountCode(
        tenant_id=tenant_a.id,
        code=f"KYC{suf[:4]}",
        discount_type="PERCENT",
        discount_value=Decimal("10"),
        active=True,
    )
    db_super.add(dc)
    db_super.commit()
    db_super.refresh(dc)

    ev = client.post(
        "/api/reservation-events",
        headers={"Authorization": f"Bearer {token_a}"},
        json={
            "event_name": "Con descuento",
            "discount_code": dc.code,
            "items": [
                {
                    "space_id": str(space_a.id),
                    "fecha": event_day,
                    "hora_inicio": "10:00:00",
                    "hora_fin": "12:00:00",
                },
            ],
        },
    )
    assert ev.status_code == 201, ev.text
    gid = ev.json()["group_event_id"]

    comp = client.get(
        f"/api/group-events/{gid}/documents/completeness",
        headers={"Authorization": f"Bearer {token_a}"},
    )
    assert comp.status_code == 200
    codes_req = {x["type"] for x in comp.json()["required"]}
    assert "DESCUENTO_ACUSE" in codes_req

    for tid in (CONST_ID, INE_FRONT_ID, INE_BACK_ID, DOMICILIO_ID, DESCUENTO_ID):
        r = client.post(
            f"/api/group-events/{gid}/documents",
            headers={"Authorization": f"Bearer {token_a}"},
            files={"file": ("d.pdf", BytesIO(MIN_PDF), "application/pdf")},
            data={"document_type_id": str(tid)},
        )
        assert r.status_code == 201, r.text

    comp2 = client.get(
        f"/api/group-events/{gid}/documents/completeness",
        headers={"Authorization": f"Bearer {token_a}"},
    )
    assert comp2.json()["is_complete"] is True
