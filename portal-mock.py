"""Local HMAC-verifying double of bloque_portal's folio-access API (REQ-013 RN-019).

Serves GET /api/integrations/bloque-hub/leads/{folio}/access with the real
contract: three X-Bloque-* credential headers, HMAC-SHA256 signature, and a
`data.status` envelope. Stdlib only — no backend import, no shared package
(design.md §8): this is an independent reader of REQ-013 §4.3, not a re-export
of `signing.py`. The compose smoke (backend signs, this double verifies) is
the proof the two readings agree; importing signing.py here would agree with
it by construction and prove nothing.

This is a committed, permanent local double (RN-019) — not disposable. Do NOT
delete this file. It is required for `docker compose up` to answer the real
Portal integration route in local dev.
"""

import base64
import hashlib
import hmac
import json
import os
import re
import time
from http.server import BaseHTTPRequestHandler, HTTPServer

API_KEY_HEADER = "X-Bloque-Api-Key"
TIMESTAMP_HEADER = "X-Bloque-Timestamp"
SIGNATURE_HEADER = "X-Bloque-Signature"

PORTAL_HUB_API_KEY = os.environ.get("PORTAL_HUB_API_KEY", "dev-local-portal-hub-key")
PORTAL_HUB_API_SECRET = os.environ.get(
    "PORTAL_HUB_API_SECRET", "dev-local-portal-hub-secret"
)

TIMESTAMP_WINDOW_SECONDS = 300

ROUTE_PATTERN = re.compile(
    r"^/api/integrations/bloque-hub/leads/(?P<folio>[^/?]+)/access$"
)

# REQ-013 §4.3 — same canonical string definition as
# app.modules.portal_gate.signing.canonical_string(), re-implemented
# independently (design.md §8: no import from the backend).
#
# Known vector (also asserted independently in
# src/backend/tests/test_portal_gate_signing.py::test_known_vector), computed
# via a standalone python -c one-liner, never derived from this file or from
# signing.py:
#   secret    = "test-secret-vector"
#   method    = "GET"
#   path      = "/api/integrations/bloque-hub/leads/BCE-20260715-172822-2973/access"
#   timestamp = "1767225600"
#   signature = "cVq1YbWSfBtJ6/9/LrBEwU33gazDGTxcKE3Bi7o3ITA="


def _canonical_string(method: str, path: str, timestamp: str) -> str:
    return f"{method}\n{path}\n{timestamp}"


def _sign(secret: str, canonical: str) -> str:
    digest = hmac.new(
        secret.encode("utf-8"), canonical.encode("utf-8"), hashlib.sha256
    ).digest()
    return base64.b64encode(digest).decode("ascii")


# Fixtures: folio -> (http_status, body). All folios satisfy FOLIO_PATTERN
# (^BCE-\d{8}-\d{6}-\d{4}$, see app.modules.portal_gate.client.FOLIO_PATTERN)
# or the backend never calls out to begin with.
FIXTURES = {
    # Eligible, full lead_prefill (every optional key populated).
    "BCE-20260715-172822-2973": (
        200,
        {
            "data": {
                "status": "quotation_in_progress",
                "status_label": "En cotización",
                "lead_prefill": {
                    "nombre_solicitante": "Ana Torres",
                    "email_solicitante": "ana.torres@example.com",
                    "telefono_solicitante": "5512345678",
                    "tipo_evento_sugerido": "boda",
                    "fecha_tentativa": "2026-08-20",
                    "espacio_requerido": "Salon Jacarandas",
                    "numero_invitados": 150,
                    "comentarios": "Evento con requerimientos de sonido e iluminacion especial.",
                    "como_conociste_bloque": "redes_sociales",
                    "ciudad": "Queretaro",
                },
            }
        },
    ),
    # Eligible, every optional lead_prefill key null.
    "BCE-20260716-091500-1010": (
        200,
        {
            "data": {
                "status": "quotation_in_progress",
                "status_label": "En cotización",
                "lead_prefill": {
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
                },
            }
        },
    ),
    # Eligible, comentarios exceeds 5000 chars (exercises D3 truncation locally).
    "BCE-20260717-140030-2020": (
        200,
        {
            "data": {
                "status": "quotation_in_progress",
                "status_label": "En cotización",
                "lead_prefill": {
                    "nombre_solicitante": "Luis Mendoza",
                    "email_solicitante": "luis.mendoza@example.com",
                    "telefono_solicitante": "5598765432",
                    "tipo_evento_sugerido": "corporativo",
                    "fecha_tentativa": "2026-09-05",
                    "espacio_requerido": "Terraza Norte",
                    "numero_invitados": 300,
                    "comentarios": "Requerimiento especial extenso. " * 200,
                    "como_conociste_bloque": "referido",
                    "ciudad": "Queretaro",
                },
            }
        },
    ),
    # Terminal (already resolved) folio.
    "BCE-20260718-101010-3030": (403, {"error_code": "TERMINAL"}),
    # Explicitly not eligible.
    "BCE-20260719-121212-4040": (403, {"error_code": "NOT_ELIGIBLE"}),
}


class Handler(BaseHTTPRequestHandler):
    def do_GET(self):  # noqa: N802
        path, _, _ = self.path.partition("?")
        match = ROUTE_PATTERN.match(path)
        if not match:
            self._json(404, {"error_code": "FOLIO_NOT_FOUND"})
            return

        folio = match.group("folio")

        api_key = self.headers.get(API_KEY_HEADER)
        timestamp = self.headers.get(TIMESTAMP_HEADER)
        signature = self.headers.get(SIGNATURE_HEADER)
        if not api_key or not timestamp or not signature:
            self._json(401, {"error_code": "MISSING_CREDENTIALS"})
            return

        if not hmac.compare_digest(api_key, PORTAL_HUB_API_KEY):
            self._json(401, {"error_code": "UNKNOWN_API_KEY"})
            return

        if not timestamp.isdigit():
            self._json(401, {"error_code": "MALFORMED_TIMESTAMP"})
            return

        if abs(int(time.time()) - int(timestamp)) > TIMESTAMP_WINDOW_SECONDS:
            self._json(401, {"error_code": "TIMESTAMP_EXPIRED"})
            return

        canonical = _canonical_string("GET", path, timestamp)
        expected_signature = _sign(PORTAL_HUB_API_SECRET, canonical)
        if not hmac.compare_digest(expected_signature, signature):
            self._json(401, {"error_code": "INVALID_SIGNATURE"})
            return

        if folio not in FIXTURES:
            self._json(404, {"error_code": "FOLIO_NOT_FOUND"})
            return

        status_code, body = FIXTURES[folio]
        self._json(status_code, body)

    def _json(self, code, body):
        data = json.dumps(body).encode()
        self.send_response(code)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(data)))
        self.end_headers()
        self.wfile.write(data)

    def log_message(self, fmt, *args):  # quiet, but print decisions for visibility
        print("portal-mock:", self.path, "->", fmt % args)


if __name__ == "__main__":
    print(
        "portal-mock listening on 0.0.0.0:9000; fixtures:",
        ", ".join(FIXTURES.keys()),
    )
    HTTPServer(("0.0.0.0", 9000), Handler).serve_forever()
