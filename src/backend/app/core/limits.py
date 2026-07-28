"""Shared length caps that must stay in sync across independent modules.

REQ-013 design.md §2 D5: this constant lives here, NOT in `crm/schemas.py`,
because `crm/schemas.py` already imports `portal_gate.client.is_valid_folio_
format`. Declaring the cap in `crm` and importing it from `portal_gate`
would create a cycle `crm -> portal_gate -> crm`. A neutral `core` module is
the only placement that gives both `crm/schemas.py` and `portal_gate/
prefill.py` one shared source of truth without that cycle.
"""

# D3/D5: the wizard's `requerimientos_especiales` field and the Portal
# `comentarios` -> `requerimientos_especiales` prefill mapping share this one
# cap so a value that fits when typed by hand also fits when it arrives
# truncated from Portal.
REQUERIMIENTOS_ESPECIALES_MAX_LENGTH = 5000
