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


class TestMapLeadPrefillPortalRealAliases:
    """Live Portal (2026-07-28) sends Hub-shaped keys + English synonyms in
    the same object, and does NOT send the local-double names
    (`nombre_solicitante` / `email_solicitante` / …). Prefill must read the
    Hub names so Step 3 hydrates; `space_id` must still be ignored (RN-015).
    """

    _PORTAL_REAL_SHAPE = {
        "nombre_completo": "Ana Real",
        "nombre_solicitante": None,  # absent-equivalent on real Portal
        "requestor_name": "Ana Real",
        "cargo_puesto": "director",
        "position": "director",
        "institucion_organizacion": "silvercorp",
        "institution": "silvercorp",
        "correo_institucional": "ana@example.com",
        "email_solicitante": None,
        "contact_email": "ana@example.com",
        "telefono_contacto": "5511111111",
        "telefono_solicitante": None,
        "contact_phone": "5511111111",
        "asistentes_estimados": 40,
        "numero_invitados": None,
        "attendees": 40,
        "fecha_tentativa": "2026-07-30",
        "date": "2026-07-30",
        "tipo_evento_sugerido": None,
        "event_type": None,
        "espacio_requerido": "Auditorio",
        "comentarios": "ninguno",
        "special_notes": "ninguno",
        "como_conociste_bloque": "recomendacion",
        "how_learned_bloque": "recomendacion",
        "ciudad": "Queretaro",
        "space_id": "should-never-become-espacio",
    }

    def test_hub_shaped_keys_hydrate_every_identity_field(self):
        prefill = map_lead_prefill(self._PORTAL_REAL_SHAPE, folio=FOLIO)
        assert prefill.nombre_completo == "Ana Real"
        assert prefill.correo_institucional == "ana@example.com"
        assert prefill.telefono_contacto == "5511111111"
        assert prefill.asistentes_estimados == 40
        assert prefill.cargo_puesto == "director"
        assert prefill.institucion_organizacion == "silvercorp"
        assert prefill.fecha_tentativa == "2026-07-30"
        assert prefill.espacio_requerido == "Auditorio"
        assert prefill.requerimientos_especiales == "ninguno"
        assert prefill.como_conociste_bloque == "recomendacion"

    def test_space_id_never_becomes_espacio_requerido(self):
        raw = {"space_id": "uuid-of-doom", "espacio_requerido": None}
        prefill = map_lead_prefill(raw, folio=FOLIO)
        assert prefill.espacio_requerido is None

    def test_english_only_payload_still_maps(self):
        raw = {
            "requestor_name": "Bob",
            "contact_email": "bob@example.com",
            "contact_phone": "5599999999",
            "attendees": 12,
            "special_notes": "wifi",
            "how_learned_bloque": "redes_sociales",
            "institution": "Acme",
            "position": "PM",
            "date": "2026-09-01",
        }
        prefill = map_lead_prefill(raw, folio=FOLIO)
        assert prefill.nombre_completo == "Bob"
        assert prefill.correo_institucional == "bob@example.com"
        assert prefill.telefono_contacto == "5599999999"
        assert prefill.asistentes_estimados == 12
        assert prefill.requerimientos_especiales == "wifi"
        assert prefill.como_conociste_bloque == "redes_sociales"
        assert prefill.institucion_organizacion == "Acme"
        assert prefill.cargo_puesto == "PM"
        assert prefill.fecha_tentativa == "2026-09-01"


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

    def test_comentarios_over_300_words_survives_prefill_without_word_cap(self):
        """DoD / RN-021 motivating case: Portal comentarios can exceed the
        300-word RN-006 cap that applies to `descripcion_evento`. Prefill must
        still land the text on `requerimientos_especiales` (no word validator)
        so a hydrated submit does not fail on a value the applicant never typed.
        """
        from pydantic import ValidationError

        from app.modules.crm.models import (
            CaracterEvento,
            ComoConociste,
            MontajeRequerido,
            Sector,
            TipoEvento,
        )
        from app.modules.crm.schemas import PublicQuoteRequestCreate

        over_300 = " ".join(f"palabra{i}" for i in range(301))
        assert len(over_300.split()) == 301

        prefill = map_lead_prefill(
            dict(_FULL_RAW, comentarios=over_300), folio=FOLIO
        )
        assert prefill.requerimientos_especiales is not None
        assert len(prefill.requerimientos_especiales.split()) == 301
        assert not hasattr(prefill, "descripcion_evento")

        item = {
            "space_id": "00000000-0000-4000-8000-000000000001",
            "fecha": "2026-09-01",
            "hora_inicio": "10:00:00",
            "hora_fin": "12:00:00",
        }
        base_kwargs = dict(
            folio=FOLIO,
            tipo_evento=TipoEvento.CONFERENCIA,
            caracter_evento=CaracterEvento.PUBLICO,
            asistentes_estimados=50,
            habra_prensa=False,
            items=[item],
            nombre_completo="Ana Lopez",
            sector=Sector.GOBIERNO_MUNICIPAL_ESTATAL_FEDERAL,
            correo_institucional="ana@example.com",
            telefono_contacto="5555555555",
            como_conociste_bloque=ComoConociste.REDES_SOCIALES,
            montaje_requerido=MontajeRequerido.TEATRO,
            acepta_info_correcta_autorizacion=True,
            acepta_reglamento_y_aviso_privacidad=True,
        )

        # Contrast: the SAME 301 words in descripcion_evento trip RN-006.
        with pytest.raises(ValidationError) as rn006:
            PublicQuoteRequestCreate(
                **base_kwargs,
                descripcion_evento=over_300,
                requerimientos_especiales=None,
            )
        assert "300" in str(rn006.value)

        # Same 301 words on requerimientos_especiales validate cleanly —
        # that field has no word-count rule (only the shared char cap).
        ok = PublicQuoteRequestCreate(
            **base_kwargs,
            descripcion_evento="Evento corto",
            requerimientos_especiales=prefill.requerimientos_especiales,
        )
        assert len(ok.requerimientos_especiales.split()) == 301


class TestMaskedFolio:
    def test_masks_middle_of_folio(self):
        assert _masked_folio(FOLIO) == "BCE-\u2026-2973"

    def test_short_folio_fully_masked(self):
        assert _masked_folio("abc") == "\u2026"
