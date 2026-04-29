"""Tests CFDI: matriz de compatibilidad (T10.3) y servicio de generación."""

import pytest

from app.modules.finance.matriz_sat import (
    RFC_PUBLICO_GENERAL,
    validar_compatibilidad_regimen_uso_cfdi,
)
from app.modules.finance.services import (
    validar_datos_fiscales_para_cfdi,
    generar_cfdi_para_reserva,
)
from app.modules.finance.models import CfdiEstado


def test_matriz_regimen_616_uso_g03_rechazado() -> None:
    """Régimen 616 (sin obligaciones) con uso G03 debe ser incompatible."""
    err = validar_compatibilidad_regimen_uso_cfdi("616", "G03", "EKU900123ABC")
    assert err is not None
    assert "USO_CFDI_INCOMPATIBLE" in err


def test_matriz_rfc_publico_uso_g03_rechazado() -> None:
    """RFC público en general solo permite S01."""
    err = validar_compatibilidad_regimen_uso_cfdi(
        "616", "G03", RFC_PUBLICO_GENERAL
    )
    assert err is not None
    assert "S01" in err

    err2 = validar_compatibilidad_regimen_uso_cfdi(
        "601", "S01", RFC_PUBLICO_GENERAL
    )
    assert err2 is None


def test_matriz_regimen_601_uso_g03_aceptado() -> None:
    """Régimen 601 con G03 es válido."""
    assert validar_compatibilidad_regimen_uso_cfdi("601", "G03", "EKU900123ABC") is None


def test_validar_datos_fiscales_falta_rfc() -> None:
    """Falta RFC receptor -> error."""
    e = validar_datos_fiscales_para_cfdi(
        rfc_receptor=None,
        regimen_receptor="601",
        uso_cfdi="G03",
    )
    assert "RFC_RECEPTOR_AUSENTE" in e


def test_validar_datos_fiscales_regimen_616_g03() -> None:
    """616 + G03 bloqueado antes de PAC (personas sin obligaciones solo S01)."""
    e = validar_datos_fiscales_para_cfdi(
        rfc_receptor="EKU900123ABC",
        regimen_receptor="616",
        uso_cfdi="G03",
    )
    assert e
    assert any("USO_CFDI" in x for x in e)


def test_generar_cfdi_sin_datos_receptor_crea_error(
    db_super, tenant_a, user_a
) -> None:
    """Sin RFC/receptor se crea CFDI en estado ERROR."""
    from app.modules.booking.models import Reservation, ReservationStatus
    from app.modules.identity.models import Tenant
    from app.modules.inventory.models import Space
    from datetime import date, time

    tenant = tenant_a
    space = db_super.query(Space).filter(Space.tenant_id == tenant.id).first()
    if not space:
        space = Space(
            tenant_id=tenant.id,
            name="Space CFDI",
            slug="space-cfdi-test",
            capacidad_maxima=10,
        )
        db_super.add(space)
        db_super.commit()
        db_super.refresh(space)

    res = Reservation(
        tenant_id=tenant.id,
        user_id=user_a.id,
        space_id=space.id,
        fecha=date(2026, 4, 1),
        hora_inicio=time(10, 0),
        hora_fin=time(12, 0),
        status=ReservationStatus.CONFIRMED,
    )
    db_super.add(res)
    db_super.commit()
    db_super.refresh(res)

    cfdi = generar_cfdi_para_reserva(res, db_super, monto=1000.0)
    db_super.commit()
    assert cfdi.estado == CfdiEstado.ERROR.value
    assert cfdi.error_codigo == "RFC_RECEPTOR_AUSENTE"


def test_generar_cfdi_con_datos_validos_timbrado_mock(
    db_super, tenant_a, user_a
) -> None:
    """Con datos fiscales válidos, mock timbra y queda TIMBRADO."""
    from app.modules.booking.models import Reservation, ReservationStatus
    from app.modules.inventory.models import Space
    from datetime import date, time

    tenant = tenant_a
    space = db_super.query(Space).filter(Space.tenant_id == tenant.id).first()
    if not space:
        space = Space(
            tenant_id=tenant.id,
            name="Space CFDI 2",
            slug="space-cfdi-test-2",
            capacidad_maxima=10,
        )
        db_super.add(space)
        db_super.commit()
        db_super.refresh(space)

    res = Reservation(
        tenant_id=tenant.id,
        user_id=user_a.id,
        space_id=space.id,
        fecha=date(2026, 5, 1),
        hora_inicio=time(10, 0),
        hora_fin=time(12, 0),
        status=ReservationStatus.CONFIRMED,
    )
    db_super.add(res)
    db_super.commit()
    db_super.refresh(res)

    cfdi = generar_cfdi_para_reserva(
        res,
        db_super,
        receptor_rfc="EKU900123ABC",
        receptor_razon_social="Cliente Test",
        receptor_regimen="601",
        receptor_uso_cfdi="G03",
        monto=1160.0,
    )
    db_super.commit()
    assert cfdi.estado == CfdiEstado.TIMBRADO.value
    assert cfdi.uuid_fiscal is not None
    assert cfdi.xml_url is not None
