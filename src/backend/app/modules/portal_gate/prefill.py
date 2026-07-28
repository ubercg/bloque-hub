"""Portal-shape to Hub-shape lead prefill mapping (REQ-013, design.md §6).

Best-effort, additive only (RN-013): `map_lead_prefill` NEVER raises. A
missing or malformed `lead_prefill` payload degrades to an all-`None`
`LeadPrefill` and never changes the folio's eligibility — prefill is
best-effort, eligibility is not (§6's failure-boundary distinction).

Portal's `comentarios` key is renamed to `requerimientos_especiales` AT this
boundary (D7), so RN-021 becomes structural: the name `comentarios` does not
exist on `LeadPrefill`, so no downstream layer can plausibly route it to
`descripcion_evento`.

`ciudad` is intentionally never read (REQ-013 §4.6, proposal §7.3, delivery
decision #5) — there is no field on `LeadPrefill` to hold it.
"""

import logging
from dataclasses import dataclass, fields
from typing import Any, Mapping

from app.core.limits import REQUERIMIENTOS_ESPECIALES_MAX_LENGTH

logger = logging.getLogger(__name__)

# §6, Phase 0.1 frozen value: a VISIBLE marker, never a silent cut or a
# drop (delivery decision #3). Spanish, because it is user-visible copy
# inside a Spanish form.
TRUNCATION_MARKER = "… [texto recortado]"


@dataclass(frozen=True, slots=True)
class LeadPrefill:
    """Hub-shaped prefill data for Step 3 of the public wizard (design §6).

    11 fields, deliberately NO `ciudad` field — it is read nowhere past
    this module's `map_lead_prefill`.
    """

    nombre_completo: str | None
    cargo_puesto: str | None
    institucion_organizacion: str | None
    correo_institucional: str | None
    telefono_contacto: str | None
    asistentes_estimados: int | None
    fecha_tentativa: str | None  # ISO date, REFERENCE ONLY (RN-022)
    tipo_evento_sugerido: str | None  # frequently null (RN-014)
    espacio_requerido: str | None  # REFERENCE ONLY, never a space_id (RN-015)
    requerimientos_especiales: str | None  # from Portal `comentarios` (D7, RN-021)
    como_conociste_bloque: str | None


_EMPTY_PREFILL = LeadPrefill(*([None] * len(fields(LeadPrefill))))


def _masked_folio(folio: str) -> str:
    """RN-018: never log the full folio — keep the prefix and last 4 digits."""
    if len(folio) <= 4:
        return "…"
    return f"{folio[:4]}…-{folio[-4:]}"


def _shape_keys(mapping: Any) -> list[str]:
    """Sorted top-level keys, or [] for a non-mapping. NEVER returns values."""
    return sorted(mapping.keys()) if isinstance(mapping, Mapping) else []


def _truncate(value: str, limit: int) -> tuple[str, bool]:
    """Marker counted INSIDE the budget: len(result) <= limit always."""
    if len(value) <= limit:
        return value, False
    return value[: limit - len(TRUNCATION_MARKER)].rstrip() + TRUNCATION_MARKER, True


def _str_or_none(value: Any) -> str | None:
    if value is None:
        return None
    return value if isinstance(value, str) else str(value)


def _int_or_none(value: Any) -> int | None:
    if value is None or isinstance(value, bool):
        return None
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


def _map_comentarios(value: Any, *, folio: str) -> str | None:
    """The ONLY place Portal's `comentarios` key is ever read (D7)."""
    text = _str_or_none(value)
    if text is None:
        return None
    truncated, was_truncated = _truncate(text, REQUERIMIENTOS_ESPECIALES_MAX_LENGTH)
    if was_truncated:
        # RN-018: length only, NEVER the text itself.
        logger.info(
            "portal_gate.prefill_truncated folio=%s original_length=%d limit=%d",
            _masked_folio(folio),
            len(text),
            REQUERIMIENTOS_ESPECIALES_MAX_LENGTH,
        )
    return truncated


def _log_degraded(folio: str, raw: Any) -> None:
    logger.warning(
        "portal_gate.prefill_degraded folio=%s received_keys=%s",
        _masked_folio(folio),
        _shape_keys(raw),
    )


def map_lead_prefill(raw: Mapping[str, Any] | None, *, folio: str) -> LeadPrefill:
    """Best-effort, NEVER raises (RN-013).

    `raw` is the value of `body["data"]["lead_prefill"]` from the real
    Portal envelope. A missing key (`None`) or an all-null-keys payload are
    both NORMAL, silent cases. A payload that is not a mapping at all, or
    that raises while being read, is a genuine contract violation on this
    best-effort field only — it degrades to all-`None` and logs
    `portal_gate.prefill_degraded`, but it does NOT change the folio status
    (that decision was already made one layer up in `client.py`).
    """
    if raw is None:
        return _EMPTY_PREFILL
    if not isinstance(raw, Mapping):
        _log_degraded(folio, raw)
        return _EMPTY_PREFILL
    try:
        return LeadPrefill(
            nombre_completo=_str_or_none(raw.get("nombre_solicitante")),
            cargo_puesto=_str_or_none(raw.get("cargo_puesto")),
            institucion_organizacion=_str_or_none(raw.get("institucion_organizacion")),
            correo_institucional=_str_or_none(raw.get("email_solicitante")),
            telefono_contacto=_str_or_none(raw.get("telefono_solicitante")),
            asistentes_estimados=_int_or_none(raw.get("numero_invitados")),
            fecha_tentativa=_str_or_none(raw.get("fecha_tentativa")),
            tipo_evento_sugerido=_str_or_none(raw.get("tipo_evento_sugerido")),
            espacio_requerido=_str_or_none(raw.get("espacio_requerido")),
            requerimientos_especiales=_map_comentarios(raw.get("comentarios"), folio=folio),
            como_conociste_bloque=_str_or_none(raw.get("como_conociste_bloque")),
        )
    except Exception:  # noqa: BLE001 — RN-013: best-effort, must never raise
        _log_degraded(folio, raw)
        return _EMPTY_PREFILL
