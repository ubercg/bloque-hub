"""Unit tests for `portal_gate/prefill.py` (REQ-013, design.md §6).

Pure tests, no HTTP (design §12: "pure prefill.py tests first"). `raw` here
is the shape `client.py` extracts from `body["data"]["lead_prefill"]` — the
REAL Portal field names as fixed in `portal-mock.py` (Slice E, already
shipped): `nombre_solicitante`, `email_solicitante`, `telefono_solicitante`,
`numero_invitados`, `comentarios`, plus `fecha_tentativa`,
`tipo_evento_sugerido`, `espacio_requerido`, `como_conociste_bloque`,
`ciudad` verbatim. `cargo_puesto` / `institucion_organizacion` are read
under their own Hub-shaped names since Portal's local double never sends
them (best-effort — RN-013 tolerates absent keys identically to null ones).
"""

import dataclasses
import logging

import pytest

from app.core.limits import REQUERIMIENTOS_ESPECIALES_MAX_LENGTH
from app.modules.portal_gate.prefill import (
    TRUNCATION_MARKER,
    LeadPrefill,
    _masked_folio,
    _truncate,
    map_lead_prefill,
)

FOLIO = "BCE-20260715-172822-2973"

_FULL_RAW = {
    "nombre_solicitante": "Ana Torres",
    "cargo_puesto": "Directora de Vinculación",
    "institucion_organizacion": "Municipio de Querétaro",
    "email_solicitante": "ana.torres@example.com",
    "telefono_solicitante": "5512345678",
    "numero_invitados": 150,
    "fecha_tentativa": "2026-08-20",
    "tipo_evento_sugerido": "boda",
    "espacio_requerido": "Salon Jacarandas",
    "comentarios": "Evento con requerimientos de sonido e iluminacion especial.",
    "como_conociste_bloque": "redes_sociales",
    "ciudad": "Queretaro",
}

_ALL_NULL_RAW = {
    "nombre_solicitante": None,
    "email_solicitante": None,
    "telefono_solicitante": None,
    "tipo_evento_sugerido": None,
    "fecha_tentativa": None,
    "espacio_requerido": None,
    "numero_invitados": None,
    "comentarios": None,
    "como_conociste_bloque": None,
    "ciudad": None,
}


class TestLeadPrefillShape:
    """D7/§4.6 — the structural guarantees, checked on the dataclass itself
    so a future field addition cannot silently reintroduce either name."""

    def test_has_exactly_eleven_fields(self):
        assert len(dataclasses.fields(LeadPrefill)) == 11

    def test_has_no_ciudad_field(self):
        """Delivery decision #5 / Phase 0.4: `ciudad` is never mapped."""
        names = {f.name for f in dataclasses.fields(LeadPrefill)}
        assert not any("ciudad" in name for name in names)

    def test_has_no_comentarios_field(self):
        """D7: the name `comentarios` does not exist past prefill.py — RN-021
        made structural, not just a naming convention."""
        names = {f.name for f in dataclasses.fields(LeadPrefill)}
        assert "comentarios" not in names

    def test_has_no_descripcion_evento_field(self):
        """RN-021: prefill can never route into the free-text event
        description field — that name does not exist on LeadPrefill."""
        names = {f.name for f in dataclasses.fields(LeadPrefill)}
        assert "descripcion_evento" not in names

    def test_is_frozen(self):
        prefill = map_lead_prefill(_FULL_RAW, folio=FOLIO)
        with pytest.raises(dataclasses.FrozenInstanceError):
            prefill.nombre_completo = "changed"  # type: ignore[misc]


class TestMapLeadPrefillCompleteCase:
    def test_full_payload_maps_every_field(self):
        prefill = map_lead_prefill(_FULL_RAW, folio=FOLIO)

        assert prefill.nombre_completo == "Ana Torres"
        assert prefill.cargo_puesto == "Directora de Vinculación"
        assert prefill.institucion_organizacion == "Municipio de Querétaro"
        assert prefill.correo_institucional == "ana.torres@example.com"
        assert prefill.telefono_contacto == "5512345678"
        assert prefill.asistentes_estimados == 150
        assert prefill.fecha_tentativa == "2026-08-20"
        assert prefill.tipo_evento_sugerido == "boda"
        assert prefill.espacio_requerido == "Salon Jacarandas"
        assert (
            prefill.requerimientos_especiales
            == "Evento con requerimientos de sonido e iluminacion especial."
        )
        assert prefill.como_conociste_bloque == "redes_sociales"

    def test_ciudad_key_is_never_surfaced_even_when_present_in_raw(self):
        prefill = map_lead_prefill(_FULL_RAW, folio=FOLIO)
        assert not hasattr(prefill, "ciudad")


class TestMapLeadPrefillNullAndAbsentKeys:
    def test_raw_none_degrades_to_all_none_silently(self, caplog):
        with caplog.at_level("WARNING"):
            prefill = map_lead_prefill(None, folio=FOLIO)

        assert prefill == LeadPrefill(*([None] * 11))
        assert not any("prefill_degraded" in r.getMessage() for r in caplog.records)

    def test_all_null_keys_degrade_gracefully_with_no_error_log(self, caplog):
        with caplog.at_level("WARNING"):
            prefill = map_lead_prefill(_ALL_NULL_RAW, folio=FOLIO)

        assert prefill == LeadPrefill(*([None] * 11))
        assert not any(r.levelno >= logging.WARNING for r in caplog.records)

    def test_missing_keys_not_sent_by_portal_degrade_to_none(self, caplog):
        """`cargo_puesto` / `institucion_organizacion` are absent from the
        real portal-mock fixtures entirely (not even null) — RN-013 treats
        an absent key identically to an explicit null, with no error."""
        raw = dict(_ALL_NULL_RAW)  # no cargo_puesto / institucion_organizacion key at all

        with caplog.at_level("WARNING"):
            prefill = map_lead_prefill(raw, folio=FOLIO)

        assert prefill.cargo_puesto is None
        assert prefill.institucion_organizacion is None
        assert not any(r.levelno >= logging.WARNING for r in caplog.records)


class TestMapLeadPrefillDegradation:
    """RN-013: best-effort, NEVER raises, NEVER blocks the folio status."""

    @pytest.mark.parametrize("garbage", ["a plain string", 12345, ["not", "a", "mapping"]])
    def test_non_mapping_raw_degrades_to_all_none_and_logs(self, garbage, caplog):
        with caplog.at_level("WARNING", logger="app.modules.portal_gate.prefill"):
            prefill = map_lead_prefill(garbage, folio=FOLIO)

        assert prefill == LeadPrefill(*([None] * 11))
        records = [r for r in caplog.records if "portal_gate.prefill_degraded" in r.getMessage()]
        assert len(records) == 1

    def test_map_lead_prefill_never_raises_on_unexpected_shape(self):
        class Hostile:
            def get(self, key, default=None):
                raise RuntimeError("boom")

            def keys(self):
                raise RuntimeError("boom")

        # Must not propagate — RN-013 is best-effort, never blocking.
        prefill = map_lead_prefill(Hostile(), folio=FOLIO)
        assert prefill == LeadPrefill(*([None] * 11))

    def test_degraded_log_contains_no_raw_values(self, caplog):
        with caplog.at_level("WARNING", logger="app.modules.portal_gate.prefill"):
            map_lead_prefill("super secret leaked value", folio=FOLIO)

        for record in caplog.records:
            assert "super secret leaked value" not in record.getMessage()


class TestTruncationBoundary:
    """§6: the marker is counted INSIDE the budget — len(result) <= limit
    always, at limit-1 / limit / limit+1 / 3*limit."""

    def test_below_limit_is_untouched(self):
        value = "x" * (REQUERIMIENTOS_ESPECIALES_MAX_LENGTH - 1)
        result, truncated = _truncate(value, REQUERIMIENTOS_ESPECIALES_MAX_LENGTH)
        assert result == value
        assert truncated is False

    def test_at_limit_is_untouched(self):
        value = "x" * REQUERIMIENTOS_ESPECIALES_MAX_LENGTH
        result, truncated = _truncate(value, REQUERIMIENTOS_ESPECIALES_MAX_LENGTH)
        assert result == value
        assert truncated is False
        assert len(result) <= REQUERIMIENTOS_ESPECIALES_MAX_LENGTH

    def test_one_over_limit_is_truncated_with_marker_inside_budget(self):
        value = "x" * (REQUERIMIENTOS_ESPECIALES_MAX_LENGTH + 1)
        result, truncated = _truncate(value, REQUERIMIENTOS_ESPECIALES_MAX_LENGTH)
        assert truncated is True
        assert len(result) <= REQUERIMIENTOS_ESPECIALES_MAX_LENGTH
        assert result.endswith(TRUNCATION_MARKER)

    def test_three_times_limit_is_truncated_with_marker_inside_budget(self):
        value = "x" * (REQUERIMIENTOS_ESPECIALES_MAX_LENGTH * 3)
        result, truncated = _truncate(value, REQUERIMIENTOS_ESPECIALES_MAX_LENGTH)
        assert truncated is True
        assert len(result) <= REQUERIMIENTOS_ESPECIALES_MAX_LENGTH
        assert result.endswith(TRUNCATION_MARKER)


class TestPrefillTruncatedLog:
    def test_truncation_logs_length_only_never_the_text(self, caplog):
        long_text = "A" * (REQUERIMIENTOS_ESPECIALES_MAX_LENGTH + 500)
        raw = dict(_FULL_RAW, comentarios=long_text)

        with caplog.at_level("INFO", logger="app.modules.portal_gate.prefill"):
            map_lead_prefill(raw, folio=FOLIO)

        records = [r for r in caplog.records if "portal_gate.prefill_truncated" in r.getMessage()]
        assert len(records) == 1
        message = records[0].getMessage()
        assert str(REQUERIMIENTOS_ESPECIALES_MAX_LENGTH + 500) in message
        assert long_text not in message
        assert _masked_folio(FOLIO) in message

    def test_no_truncation_log_when_comentarios_fits(self, caplog):
        with caplog.at_level("INFO", logger="app.modules.portal_gate.prefill"):
            map_lead_prefill(_FULL_RAW, folio=FOLIO)

        records = [r for r in caplog.records if "portal_gate.prefill_truncated" in r.getMessage()]
        assert records == []

    def test_truncated_value_still_fits_the_submit_schema_cap(self):
        long_text = "B" * (REQUERIMIENTOS_ESPECIALES_MAX_LENGTH * 2)
        raw = dict(_FULL_RAW, comentarios=long_text)

        prefill = map_lead_prefill(raw, folio=FOLIO)

        assert len(prefill.requerimientos_especiales) <= REQUERIMIENTOS_ESPECIALES_MAX_LENGTH


class TestCommentariosStructuralMapping:
    """D7/RN-021: `comentarios` maps ONLY to `requerimientos_especiales`;
    there is no path from Portal's `comentarios` to `descripcion_evento`."""

    def test_comentarios_lands_only_on_requerimientos_especiales(self):
        prefill = map_lead_prefill(_FULL_RAW, folio=FOLIO)

        assert prefill.requerimientos_especiales == _FULL_RAW["comentarios"]
        assert not hasattr(prefill, "comentarios")
        assert not hasattr(prefill, "descripcion_evento")


class TestMaskedFolio:
    def test_masks_middle_of_folio(self):
        assert _masked_folio(FOLIO) == "BCE-\u2026-2973"

    def test_short_folio_fully_masked(self):
        assert _masked_folio("abc") == "\u2026"
