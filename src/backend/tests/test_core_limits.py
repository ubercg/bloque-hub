"""Unit tests for the shared length-cap constants (REQ-013, design.md §2 D5).

`REQUERIMIENTOS_ESPECIALES_MAX_LENGTH` is the single source of truth shared
by `crm/schemas.py` (the wizard's own field) and `portal_gate/prefill.py`
(the Portal `comentarios` -> `requerimientos_especiales` mapping), so a
value that fits when typed by hand also fits when it arrives truncated from
Portal. Declared in `app.core.limits`, not `crm`, to avoid a `crm ->
portal_gate -> crm` import cycle (`crm/schemas.py` already imports
`portal_gate.client.is_valid_folio_format`).
"""

from app.core.limits import REQUERIMIENTOS_ESPECIALES_MAX_LENGTH
from app.modules.crm.schemas import PublicQuoteRequestCreate


def test_requerimientos_especiales_max_length_is_5000():
    assert REQUERIMIENTOS_ESPECIALES_MAX_LENGTH == 5000


def test_crm_schema_field_reads_the_shared_constant_not_a_hardcoded_literal():
    field_info = PublicQuoteRequestCreate.model_fields["requerimientos_especiales"]
    assert field_info.metadata[0].max_length == REQUERIMIENTOS_ESPECIALES_MAX_LENGTH
