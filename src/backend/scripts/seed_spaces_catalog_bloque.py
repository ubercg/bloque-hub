#!/usr/bin/env python3
"""
Seed script: Catálogo de Espacios BLOQUE
========================================
Populates spaces, space_relationships, space_booking_rules, and inventory
for a target tenant by parsing docs/catalog_espacios.md.

Usage:
    poetry run python src/backend/scripts/seed_spaces_catalog_bloque.py \\
        --tenant-slug bloque-hub \\
        --horizon-days 30 \\
        [--dry-run] \\
        [--catalog-path docs/catalog_espacios.md]

Strategy:
    - REPLACE: DELETE then INSERT scoped strictly by tenant_id.
    - FK-safe delete order: inventory → space_booking_rules → space_relationships → spaces
    - FK-safe insert order: spaces → space_relationships → space_booking_rules → inventory
    - Uses SUPERADMIN role to bypass RLS.
    - Validates tenant slug before any write.

    El tenant debe existir previamente (p. ej. creado desde Admin → Ajustes con ese slug);
    el script resuelve por `SELECT ... FROM tenants WHERE slug = :slug`.

    Opcional bajo cada `### Espacio` en el Markdown (líneas sueltas):
    - Matterport: https://my.matterport.com/show/?m=...
    - promo_hero: /spaces/sala-hero.jpg  (o URL absoluta; PNG/JPG)
    - galería: /a.png, /b.jpg
"""

from __future__ import annotations

import argparse
import json
import logging
import re
import sys
import uuid
from contextlib import contextmanager
from dataclasses import dataclass, field
from datetime import date, timedelta, time as time_type
from pathlib import Path
from typing import Any, Generator, Optional
import unicodedata
from dotenv import load_dotenv

# ---------------------------------------------------------------------------
# Logging setup
# ---------------------------------------------------------------------------
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)
logger = logging.getLogger("seed_spaces_bloque")

# ---------------------------------------------------------------------------
# Path helpers
# ---------------------------------------------------------------------------
REPO_ROOT = Path(__file__).resolve().parents[2]  # src/backend/scripts -> project root
DEFAULT_CATALOG_PATH = REPO_ROOT / "docs" / "catalog_espacios.md"

# Load local environment for DATABASE_URL / AI_DATABASE_URL.
load_dotenv(dotenv_path=REPO_ROOT / ".env", override=False)

# ---------------------------------------------------------------------------
# Data classes for parsed catalog
# ---------------------------------------------------------------------------


@dataclass
class ParsedSpace:
    """Represents a space extracted from the Markdown catalog."""

    name: str
    slug: str
    capacidad_maxima: Optional[int]
    piso: Optional[str]
    descripcion: Optional[str]
    precio_por_hora: Optional[float]
    is_parent: bool = False  # True for Centro de Convenciones
    child_names: list[str] = field(default_factory=list)  # names of child spaces
    # Opcional: tour Matterport y medios promocionales (URLs o rutas /public) para el FE
    matterport_url: Optional[str] = None
    promo_hero_url: Optional[str] = None
    promo_gallery_urls: list[str] = field(default_factory=list)


# ---------------------------------------------------------------------------
# Markdown parser
# ---------------------------------------------------------------------------


def slugify(name: str) -> str:
    """Convert a space name to a URL-safe slug."""
    slug = name.lower().strip()
    slug = re.sub(r"[áàäâ]", "a", slug)
    slug = re.sub(r"[éèëê]", "e", slug)
    slug = re.sub(r"[íìïî]", "i", slug)
    slug = re.sub(r"[óòöô]", "o", slug)
    slug = re.sub(r"[úùüû]", "u", slug)
    slug = re.sub(r"[ñ]", "n", slug)
    slug = re.sub(r"[^a-z0-9]+", "-", slug)
    slug = slug.strip("-")
    return slug


def normalize_for_match(value: str) -> str:
    """
    Normalize text for fuzzy matching:
    - remove diacritics (accents)
    - lowercase
    - collapse whitespace
    """
    v = unicodedata.normalize("NFKD", value)
    v = "".join(ch for ch in v if not unicodedata.combining(ch))
    v = v.lower()
    v = re.sub(r"\s+", " ", v).strip()
    return v


def parse_capacity(text: str) -> Optional[int]:
    """Extract an integer capacity from a text line."""
    match = re.search(r"(\d+)\s*(?:personas|pax|person|cap)", text, re.IGNORECASE)
    if match:
        return int(match.group(1))
    # Fallback: first standalone number
    match = re.search(r"\b(\d+)\b", text)
    if match:
        return int(match.group(1))
    return None


def parse_floor(text: str) -> Optional[str]:
    """Extract floor/location info from a text line."""
    # Match patterns like 'Piso 2', 'Planta baja', 'PB', 'Nivel 3', etc.
    match = re.search(
        r"(piso\s*\d+|planta\s*\w+|nivel\s*\d+|pb|p\.b\.?|\d+°?\s*piso)",
        text,
        re.IGNORECASE,
    )
    if match:
        return match.group(0).strip()
    return None


def parse_piso_to_int(piso: Optional[str]) -> Optional[int]:
    """
    Convert floor/location strings from the catalog into the DB representation.

    Expected DB type: Integer (0-7) with 0 generally meaning "Planta Baja/PB".
    """
    if not piso:
        return None

    raw = piso.strip().lower()

    if "planta" in raw and ("baja" in raw or "baj" in raw):
        return 0
    if raw in {"pb", "p.b.", "p.b", "p.b.a.", "p.baj", "p.baj."}:
        return 0
    if "nivel" in raw and re.search(r"\b(\d+)\b", raw):
        m = re.search(r"\b(\d+)\b", raw)
        if m:
            return int(m.group(1))
    if "piso" in raw and re.search(r"(\d+)", raw):
        m = re.search(r"(\d+)", raw)
        if m:
            return int(m.group(1))
    if re.search(r"\b(\d+)°?\s*piso", raw):
        m = re.search(r"\b(\d+)°?\s*piso", raw)
        if m:
            return int(m.group(1))

    return None


def parse_price_table(content: str) -> dict[str, float]:
    """
    Parse the Markdown price table under section 'I. Precios por Espacio (MXN)'.

    Expected format (pipe-delimited Markdown table):
        | Espacio            | Precio por Hora (MXN) | ... |
        |--------------------|----------------------|-----|
        | Sala de Juntas A   | 1,500                | ... |

    Returns a dict mapping space_name (normalized) -> precio_por_hora.
    """
    prices: dict[str, float] = {}

    # Locate the price section
    section_match = re.search(
        r"I\.\s*Precios por Espacio.*?\
",
        content,
        re.IGNORECASE,
    )
    if not section_match:
        logger.warning(
            "Price section 'I. Precios por Espacio' not found in catalog. "
            "All prices will be None."
        )
        return prices

    # Extract content from that section until the next top-level section (##)
    section_start = section_match.end()
    next_section = re.search(r"^#{1,2}\s", content[section_start:], re.MULTILINE)
    section_end = (
        section_start + next_section.start() if next_section else len(content)
    )
    section_content = content[section_start:section_end]

    # Find all pipe-delimited table rows
    table_rows = re.findall(r"^\|(.+)\|\s*$", section_content, re.MULTILINE)
    if not table_rows:
        logger.warning("No pipe-delimited table rows found in price section.")
        return prices

    # Determine header row (first non-separator row)
    header_row: Optional[list[str]] = None
    name_col_idx: int = 0
    price_col_idx: int = 1

    for row in table_rows:
        cells = [c.strip() for c in row.split("|")]
        # Skip separator rows (e.g., |---|---|)
        if all(re.match(r"^[-:\s]+$", c) for c in cells if c):
            continue
        if header_row is None:
            header_row = cells
            # Detect column indices
            for i, cell in enumerate(cells):
                cell_lower = cell.lower()
                if "espacio" in cell_lower or "nombre" in cell_lower or "space" in cell_lower:
                    name_col_idx = i
                if "precio" in cell_lower or "price" in cell_lower or "hora" in cell_lower:
                    price_col_idx = i
            continue
        # Data row
        if len(cells) > max(name_col_idx, price_col_idx):
            raw_name = cells[name_col_idx].strip()
            raw_price = cells[price_col_idx].strip()
            if not raw_name:
                continue
            # Clean price: remove currency symbols, commas, spaces
            clean_price = re.sub(r"[^\d.]", "", raw_price)
            try:
                price_val = float(clean_price) if clean_price else None
            except ValueError:
                price_val = None

            if price_val is None:
                logger.warning(
                    "Could not parse price for space '%s' (raw: '%s'). Using None.",
                    raw_name,
                    raw_price,
                )
            prices[normalize_for_match(raw_name)] = price_val  # type: ignore[assignment]

    logger.info("Parsed %d prices from price table.", len(prices))
    return prices


def find_price(prices: dict[str, float], space_name: str) -> Optional[float]:
    """
    Look up price for a space name using normalized exact matching.

    Si no existe una fila exacta en la tabla de precios del catálogo,
    devolvemos `None` para que el seed inserte `0.0` (compat con
    `nullable=False` en el modelo).
    """
    key = normalize_for_match(space_name)
    if key in prices:
        return prices[key]

    logger.warning(
        "No price found for space '%s'. Setting precio_por_hora=None.", space_name
    )
    return None


def parse_catalog(catalog_path: Path) -> list[ParsedSpace]:
    """
    Parse docs/catalog_espacios.md and return a list of ParsedSpace objects.

    Parsing rules:
    - Spaces are extracted from ### <Name> sections.
    - Capacity, floor/location, and description are parsed from bullets/lines
      immediately following each ### heading.
    - Prices come EXCLUSIVELY from the 'I. Precios por Espacio (MXN)' table.
    - Centro de Convenciones is marked as parent; its child sala names are
      extracted from sub-bullets or lines indicating child rooms.
    """
    if not catalog_path.exists():
        logger.error("Catalog file not found: %s", catalog_path)
        sys.exit(1)

    content = catalog_path.read_text(encoding="utf-8")
    logger.info("Read catalog from %s (%d chars)", catalog_path, len(content))

    # --- Parse price table first ---
    prices = parse_price_table(content)

    # --- Extract ### sections ---
    # Split content into chunks by ### headings
    # Pattern: ### <Name> followed by content until next ### or ##
    section_pattern = re.compile(
        r"^###\s+(.+?)\s*$",
        re.MULTILINE,
    )

    sections: list[tuple[str, str]] = []  # (heading_name, section_body)
    matches = list(section_pattern.finditer(content))

    for i, match in enumerate(matches):
        heading_name = match.group(1).strip()
        body_start = match.end()
        body_end = matches[i + 1].start() if i + 1 < len(matches) else len(content)
        # Stop body at next ## or # section (higher level)
        higher_section = re.search(r"^#{1,2}\s", content[body_start:body_end], re.MULTILINE)
        if higher_section:
            body_end = body_start + higher_section.start()
        body = content[body_start:body_end].strip()
        sections.append((heading_name, body))

    logger.info("Found %d ### sections in catalog.", len(sections))

    spaces: list[ParsedSpace] = []

    for heading_name, body in sections:
        # Skip non-space sections (e.g., pricing sections that appear as ###)
        # Heuristic: if heading looks like a roman numeral section, skip
        if re.match(r"^[IVX]+\.", heading_name):
            logger.debug("Skipping non-space section: %s", heading_name)
            continue

        capacidad: Optional[int] = None
        piso: Optional[str] = None
        descripcion_lines: list[str] = []
        child_names: list[str] = []
        matterport_url: Optional[str] = None
        promo_hero_url: Optional[str] = None
        promo_gallery_urls: list[str] = []

        lines = body.splitlines()
        for line in lines:
            stripped = line.strip()
            if not stripped:
                continue

            # Matterport / tour 360 (URL)
            mp = re.search(
                r"(?i)(?:matterport|tour\s*360|360\s*°)\s*[: ]\s*(\S+)",
                stripped,
            )
            if mp:
                matterport_url = mp.group(1).strip().rstrip(").,;")
                continue

            # Imagen hero (PNG/JPG o URL pública)
            ph = re.search(
                r"(?i)(?:promo_hero|imagen\s*hero|hero)\s*[: ]\s*(\S+)",
                stripped,
            )
            if ph:
                promo_hero_url = ph.group(1).strip().rstrip(").,;")
                continue

            # Galería: lista separada por coma o punto y coma
            pg = re.search(r"(?i)(?:promo_gallery|galer[ií]a)\s*[: ]\s*(.+)", stripped)
            if pg:
                raw = pg.group(1).strip()
                for part in re.split(r"[,;]", raw):
                    p = part.strip().rstrip(").,;")
                    if p:
                        promo_gallery_urls.append(p)
                continue

            # Detect capacity lines
            if re.search(
                r"capacidad|aforo|cap\.|personas|pax",
                stripped,
                re.IGNORECASE,
            ):
                cap = parse_capacity(stripped)
                if cap and capacidad is None:
                    capacidad = cap

            # Detect floor/location lines
            if re.search(
                r"piso|planta|nivel|ubicaci[oó]n|location",
                stripped,
                re.IGNORECASE,
            ):
                fl = parse_floor(stripped)
                if fl and piso is None:
                    piso = fl

            # Detect child sala references (for Centro de Convenciones)
            child_match = re.search(
                r"sala\s+(?:hijo|hija|child|\w+)",
                stripped,
                re.IGNORECASE,
            )
            if child_match:
                child_names.append(stripped)

            # Accumulate description (non-empty, non-header lines)
            if not stripped.startswith("#"):
                descripcion_lines.append(stripped)

        # Build description from first meaningful lines (up to 3)
        descripcion = " ".join(descripcion_lines[:3]) if descripcion_lines else None

        # Determine if this is the Centro de Convenciones parent.
        # Important: do NOT mark "Sala X Centro de Convenciones" as parent.
        is_parent = (
            normalize_for_match(heading_name)
            == normalize_for_match("Centro de Convenciones")
        )

        # Extract child sala names from body for Centro de Convenciones
        if is_parent:
            # Look specifically for bullet items that represent child rooms.
            # We only take lines that *start* as a bullet and whose content starts with "Sala".
            child_names = []
            for line in body.splitlines():
                stripped_line = line.strip()
                if not re.match(r"^[-*]\s+", stripped_line):
                    continue

                # Remove bullet marker and common markdown bold markers.
                text = re.sub(r"^[-*]\s+", "", stripped_line)
                text = re.sub(r"^\*\*|\*\*$", "", text).strip()

                # Only accept items that look like actual sala headings (avoid capturing sentences).
                if re.match(r"^sala\b", text, re.IGNORECASE):
                    child_names.append(text)

            # Fallback: try to extract "sala ..." fragments if the catalog isn't strict.
            if not child_names:
                child_names_raw = re.findall(
                    r"(?:sala|room)\s+[\w\s]+",
                    body,
                    re.IGNORECASE,
                )
                child_names = [c.strip() for c in child_names_raw]

        precio = find_price(prices, heading_name)

        space = ParsedSpace(
            name=heading_name,
            slug=slugify(heading_name),
            capacidad_maxima=capacidad,
            piso=piso,
            descripcion=descripcion,
            precio_por_hora=precio,
            is_parent=is_parent,
            child_names=child_names,
            matterport_url=matterport_url,
            promo_hero_url=promo_hero_url,
            promo_gallery_urls=promo_gallery_urls,
        )
        spaces.append(space)
        logger.debug(
            "Parsed space: %s | cap=%s | piso=%s | precio=%s | children=%s",
            space.name,
            space.capacidad_maxima,
            space.piso,
            space.precio_por_hora,
            space.child_names,
        )

    # Post-process parent/child relationships:
    # The Centro section contains descriptive bullets but the real child spaces
    # are the `### Sala ...` sections. If the regex didn't yield exact matches,
    # infer them from known sala headings.
    known_center_children = [
        "Sala de Cómputo",
        "Sala Cisco",
        "Sala Magna",
        "Sala Mural",
        "Sala 1 Centro de Convenciones",
        "Sala 2 Centro de Convenciones",
        "Sala 3 Centro de Convenciones",
        "Sala 4 Centro de Convenciones",
    ]
    space_names_set = {s.name for s in spaces}

    for space in spaces:
        if not space.is_parent:
            continue

        # Keep only exact matches to actual parsed spaces.
        space.child_names = [c for c in space.child_names if c in space_names_set]
        if not space.child_names:
            space.child_names = [
                c for c in known_center_children if c in space_names_set
            ]

    logger.info("Total spaces parsed: %d", len(spaces))
    return spaces


# ---------------------------------------------------------------------------
# Database helpers
# ---------------------------------------------------------------------------


def set_rls_context(db: Any, tenant_id: Optional[str], role: str) -> None:
    """
    Set PostgreSQL RLS session variables.

    Policies are written against:
    - `current_setting('app.current_tenant_id')`
    - `current_setting('app.role')`
    """
    from sqlalchemy import text

    db.execute(
        text("SELECT set_config('app.role', :role, TRUE)"),
        {"role": role},
    )
    if tenant_id is not None:
        db.execute(
            text("SELECT set_config('app.current_tenant_id', :tid, TRUE)"),
            {"tid": tenant_id},
        )


def get_db_context(tenant_id: Optional[str], role: str = "SUPERADMIN"):
    """
    Obtain a database session with the specified role.

    This function attempts to import the application's get_db_context.
    Falls back to a minimal SQLAlchemy session if the app context is unavailable.
    """
    return _fallback_db_context(tenant_id=tenant_id, role=role)


@contextmanager
def _fallback_db_context(tenant_id: Optional[str], role: str) -> Generator[Any, None, None]:
    """Minimal SQLAlchemy session fallback."""
    import os

    from sqlalchemy import create_engine
    from sqlalchemy.orm import sessionmaker
    from sqlalchemy import text

    # Prefer backend DB URLs (business schema).
    # `AI_DATABASE_URL` points to a different Postgres used by the AI stack.
    database_url = (
        os.environ.get("DATABASE_URL")
        or os.environ.get("APP_DATABASE_URL")
        or os.environ.get("database_url")
    )
    if not database_url:
        # Defaults matching docker-compose.yml for the business Postgres:
        # - service `db` on port 5432
        # - POSTGRES_USER: bloque
        # - POSTGRES_PASSWORD: bloque_secret
        # - POSTGRES_DB: bloque_hub
        database_url = (
            "postgresql://bloque:bloque_secret@127.0.0.1:5432/bloque_hub"
        )
        logger.warning(
            "DATABASE_URL not set; using docker-compose defaults: %s", database_url
        )

    engine = create_engine(database_url)
    Session = sessionmaker(bind=engine)
    session = Session()
    try:
        # Ensure RLS policies see the intended role + tenant.
        session.execute(
            text("SELECT set_config('app.role', :role, TRUE)"),
            {"role": role},
        )
        if tenant_id is not None:
            session.execute(
                text("SELECT set_config('app.current_tenant_id', :tid, TRUE)"),
                {"tid": tenant_id},
            )
        yield session
        session.commit()
    except Exception:
        session.rollback()
        raise
    finally:
        session.close()


def resolve_tenant(db: Any, tenant_slug: str) -> dict:
    """
    Resolve tenant by slug. Returns tenant dict with 'id' and 'slug'.
    Exits with code 1 if tenant not found.
    """
    from sqlalchemy import text

    result = db.execute(
        text("SELECT id, slug, name FROM tenants WHERE slug = :slug LIMIT 1"),
        {"slug": tenant_slug},
    ).fetchone()

    if result is None:
        logger.error(
            "Tenant with slug '%s' not found. Aborting seed.", tenant_slug
        )
        sys.exit(1)

    tenant = {"id": str(result[0]), "slug": result[1], "name": result[2]}
    logger.info(
        "Resolved tenant: id=%s slug=%s name=%s",
        tenant["id"],
        tenant["slug"],
        tenant["name"],
    )
    return tenant


# ---------------------------------------------------------------------------
# Seed operations
# ---------------------------------------------------------------------------


def delete_existing_data(db: Any, tenant_id: str) -> dict[str, int]:
    """
    Delete existing seed data for the tenant in FK-safe order.
    Returns counts of deleted rows per table.
    """
    from sqlalchemy import text

    counts: dict[str, int] = {}

    tables_in_order = [
        "inventory",
        "space_booking_rules",
        "space_relationships",
        "spaces",
    ]

    for table in tables_in_order:
        result = db.execute(
            text(f"DELETE FROM {table} WHERE tenant_id = :tenant_id"),  # noqa: S608
            {"tenant_id": tenant_id},
        )
        deleted = result.rowcount
        counts[table] = deleted
        logger.info("Deleted %d rows from %s for tenant %s", deleted, table, tenant_id)

    return counts


def insert_spaces(
    db: Any,
    spaces: list[ParsedSpace],
    tenant_id: str,
) -> dict[str, str]:  # name -> uuid
    """
    Insert spaces into the spaces table.
    Returns a mapping of space_name -> space_id (UUID string).
    """
    from sqlalchemy import text

    space_id_map: dict[str, str] = {}

    for space in spaces:
        space_id = str(uuid.uuid4())
        space_id_map[space.name] = space_id

        capacidad_maxima = space.capacidad_maxima if space.capacidad_maxima is not None else 0
        precio_por_hora = float(space.precio_por_hora) if space.precio_por_hora is not None else 0.0
        piso_int = parse_piso_to_int(space.piso)

        gallery_json = json.dumps(space.promo_gallery_urls or [])
        db.execute(
            text(
                """
                INSERT INTO spaces (
                    id, tenant_id, name, slug, booking_mode,
                    capacidad_maxima, precio_por_hora, piso, descripcion,
                    matterport_url, promo_hero_url, promo_gallery_urls,
                    is_active, created_at, updated_at
                ) VALUES (
                    :id, :tenant_id, :name, :slug, :booking_mode,
                    :capacidad_maxima, :precio_por_hora, :piso, :descripcion,
                    :matterport_url, :promo_hero_url, CAST(:promo_gallery_urls AS jsonb),
                    :is_active, NOW(), NOW()
                )
                """
            ),
            {
                "id": space_id,
                "tenant_id": tenant_id,
                "name": space.name,
                "slug": space.slug,
                # Default compatible con enum del modelo.
                "booking_mode": "QUOTE_REQUIRED",
                "capacidad_maxima": capacidad_maxima,
                "precio_por_hora": precio_por_hora,
                "piso": piso_int,
                "descripcion": space.descripcion,
                "matterport_url": space.matterport_url,
                "promo_hero_url": space.promo_hero_url,
                "promo_gallery_urls": gallery_json,
                "is_active": True,
            },
        )
        logger.debug("Inserted space: %s (id=%s)", space.name, space_id)

    logger.info("Inserted %d spaces.", len(spaces))
    return space_id_map


def insert_space_relationships(
    db: Any,
    spaces: list[ParsedSpace],
    space_id_map: dict[str, str],
    tenant_id: str,
) -> int:
    """
    Insert parent→child relationships for Centro de Convenciones.
    Returns count of inserted relationships.
    """
    from sqlalchemy import text

    count = 0
    for space in spaces:
        if not space.is_parent or not space.child_names:
            continue

        parent_id = space_id_map.get(space.name)
        if not parent_id:
            logger.warning("Parent space '%s' not found in id map.", space.name)
            continue

        for child_name in space.child_names:
            # Try exact match first, then partial
            child_id = space_id_map.get(child_name)
            if not child_id:
                # Partial match
                for name, sid in space_id_map.items():
                    if child_name.lower() in name.lower() or name.lower() in child_name.lower():
                        child_id = sid
                        break

            if not child_id:
                logger.warning(
                    "Child space '%s' not found for parent '%s'. Skipping relationship.",
                    child_name,
                    space.name,
                )
                continue

            rel_id = str(uuid.uuid4())
            db.execute(
                text(
                    """
                    INSERT INTO space_relationships (
                        id, tenant_id, parent_space_id, child_space_id,
                        relationship_type, created_at
                    ) VALUES (
                        :id, :tenant_id, :parent_space_id, :child_space_id,
                        :relationship_type, NOW()
                    )
                    """
                ),
                {
                    "id": rel_id,
                    "tenant_id": tenant_id,
                    "parent_space_id": parent_id,
                    "child_space_id": child_id,
                    "relationship_type": "PARENT_CHILD",
                },
            )
            count += 1
            logger.debug(
                "Inserted relationship: %s -> %s", space.name, child_name
            )

    logger.info("Inserted %d space_relationships.", count)
    return count


def insert_booking_rules(
    db: Any,
    spaces: list[ParsedSpace],
    space_id_map: dict[str, str],
    tenant_id: str,
) -> int:
    """
    Insert default booking rules for each space.

    Compatible with current schema:
    - `min_duration_minutes` (int)
    - `allowed_start_times` (JSONB list[str] like "09:00")
    """
    from sqlalchemy import text

    allowed_start_times = [f"{h:02d}:00" for h in range(9, 21)]
    min_duration_minutes = 60

    count = 0
    import json
    allowed_start_times_json = json.dumps(allowed_start_times)
    for space in spaces:
        space_id = space_id_map.get(space.name)
        if not space_id:
            logger.warning("Space '%s' not in id map, skipping booking rules.", space.name)
            continue

        rule_id = str(uuid.uuid4())
        db.execute(
            text(
                """
                INSERT INTO space_booking_rules (
                    id, tenant_id, space_id,
                    min_duration_minutes, allowed_start_times,
                    created_at, updated_at
                ) VALUES (
                    :id, :tenant_id, :space_id,
                    :min_duration_minutes, (:allowed_start_times)::jsonb,
                    NOW(), NOW()
                )
                """
            ),
            {
                "id": rule_id,
                "tenant_id": tenant_id,
                "space_id": space_id,
                "min_duration_minutes": min_duration_minutes,
                # `allowed_start_times` is JSONB in the DB.
                "allowed_start_times": allowed_start_times_json,
            },
        )
        count += 1

    logger.info("Inserted %d space_booking_rules.", count)
    return count


def insert_inventory(
    db: Any,
    spaces: list[ParsedSpace],
    space_id_map: dict[str, str],
    tenant_id: str,
    horizon_days: int,
) -> int:
    """
    Insert inventory slots for each space for `horizon_days`.

    Schema-compatible with current `inventory`:
    - `fecha` (date)
    - `hora_inicio` / `hora_fin` (time)
    - `estado` (enum SlotStatus, default AVAILABLE)
    """
    from sqlalchemy import text

    today = date.today()
    records: list[dict] = []

    allowed_start_times = [f"{h:02d}:00" for h in range(9, 21)]
    min_duration_minutes = 60
    estado = "AVAILABLE"

    for space in spaces:
        space_id = space_id_map.get(space.name)
        if not space_id:
            logger.warning("Space '%s' not in id map, skipping inventory.", space.name)
            continue

        for day_offset in range(horizon_days):
            slot_date = today + timedelta(days=day_offset)
            for start_str in allowed_start_times:
                start_hour_str, start_min_str = start_str.split(":")
                start_h = int(start_hour_str)
                start_m = int(start_min_str)
                hora_inicio = time_type(start_h, start_m)

                end_minutes = start_h * 60 + start_m + min_duration_minutes
                hora_fin = time_type(end_minutes // 60, end_minutes % 60)

                records.append(
                    {
                        "id": str(uuid.uuid4()),
                        "tenant_id": tenant_id,
                        "space_id": space_id,
                        "fecha": slot_date,
                        "hora_inicio": hora_inicio,
                        "hora_fin": hora_fin,
                        "estado": estado,
                    }
                )

    if not records:
        logger.warning("No inventory records to insert.")
        return 0

    # Bulk insert in batches of 500 to avoid parameter limits
    batch_size = 200
    total_inserted = 0

    for i in range(0, len(records), batch_size):
        batch = records[i : i + batch_size]
        # Build parameterized bulk insert
        values_placeholders = ", ".join(
            f"(:id_{j}, :tenant_id_{j}, :space_id_{j}, :fecha_{j}, :hora_inicio_{j}, :hora_fin_{j}, :estado_{j}, NOW(), NOW())"
            for j in range(len(batch))
        )
        params: dict = {}
        for j, rec in enumerate(batch):
            params[f"id_{j}"] = rec["id"]
            params[f"tenant_id_{j}"] = rec["tenant_id"]
            params[f"space_id_{j}"] = rec["space_id"]
            params[f"fecha_{j}"] = rec["fecha"]
            params[f"hora_inicio_{j}"] = rec["hora_inicio"]
            params[f"hora_fin_{j}"] = rec["hora_fin"]
            params[f"estado_{j}"] = rec["estado"]

        db.execute(
            text(
                f"""
                INSERT INTO inventory (
                    id, tenant_id, space_id, fecha, hora_inicio, hora_fin, estado, created_at, updated_at
                ) VALUES {values_placeholders}
                """  # noqa: S608
            ),
            params,
        )
        total_inserted += len(batch)
        logger.debug("Inserted inventory batch %d-%d", i, i + len(batch))

    logger.info(
        "Inserted %d inventory records (%d spaces x %d days).",
        total_inserted,
        len(spaces),
        horizon_days,
    )
    return total_inserted


# ---------------------------------------------------------------------------
# Summary reporting
# ---------------------------------------------------------------------------


def print_summary(
    tenant: dict,
    spaces: list[ParsedSpace],
    deleted_counts: dict[str, int],
    inserted_counts: dict[str, int],
    dry_run: bool,
) -> None:
    """Print a structured summary of the seed operation."""
    mode = "DRY-RUN" if dry_run else "LIVE"
    print("\
" + "=" * 60)
    print(f"  SEED SUMMARY [{mode}]")
    print("=" * 60)
    print(f"  Tenant : {tenant['name']} (slug={tenant['slug']}, id={tenant['id']})")
    print(f"  Spaces parsed from catalog: {len(spaces)}")
    print()

    if not dry_run:
        print("  DELETED (replace strategy):")
        for table, count in deleted_counts.items():
            print(f"    {table:<30} {count:>6} rows")
        print()
        print("  INSERTED:")
        for table, count in inserted_counts.items():
            print(f"    {table:<30} {count:>6} rows")
    else:
        print("  Would insert:")
        for space in spaces:
            print(
                f"    - {space.name} | cap={space.capacidad_maxima} "
                f"| piso={space.piso} | precio={space.precio_por_hora}"
            )

    print("=" * 60)


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Seed catálogo espacios BLOQUE (parseo + dry-run seguro)."
    )
    parser.add_argument("--tenant-slug", required=True, help="Slug de la tenant objetivo.")
    parser.add_argument(
        "--horizon-days",
        type=int,
        default=30,
        help="Horizonte para inventario (solo informativo en dry-run).",
    )
    parser.add_argument(
        "--catalog-path",
        type=str,
        default=str(DEFAULT_CATALOG_PATH),
        help="Ruta al archivo Markdown `docs/catalog_espacios.md`.",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        default=False,
        help="Ejecuta sin escribir en la base de datos (solo parsea + resume).",
    )

    args = parser.parse_args()
    catalog_path = Path(args.catalog_path)

    spaces = parse_catalog(catalog_path)

    # Dry-run seguro: no tocamos BD (solo parsea + resume).
    if args.dry_run:
        tenant = {
            "id": "DRY-RUN",
            "slug": args.tenant_slug,
            "name": args.tenant_slug,
        }
        print_summary(
            tenant=tenant,
            spaces=spaces,
            deleted_counts={},
            inserted_counts={},
            dry_run=True,
        )
        return 0

    # LIVE: replace completo (DELETE -> INSERT) acotado por tenant_id.
    with get_db_context(tenant_id=None, role="SUPERADMIN") as db:
        # Asegurar rol antes de consultar/operar.
        set_rls_context(db, tenant_id=None, role="SUPERADMIN")

        tenant = resolve_tenant(db, args.tenant_slug)
        set_rls_context(db, tenant_id=tenant["id"], role="SUPERADMIN")

        deleted_counts = delete_existing_data(db, tenant["id"])

        space_id_map = insert_spaces(db, spaces, tenant["id"])
        relationships_count = insert_space_relationships(
            db,
            spaces,
            space_id_map,
            tenant["id"],
        )
        booking_rules_count = insert_booking_rules(
            db,
            spaces,
            space_id_map,
            tenant["id"],
        )
        inventory_count = insert_inventory(
            db,
            spaces,
            space_id_map,
            tenant["id"],
            horizon_days=args.horizon_days,
        )

        inserted_counts = {
            "spaces": len(spaces),
            "space_relationships": relationships_count,
            "space_booking_rules": booking_rules_count,
            "inventory": inventory_count,
        }

        print_summary(
            tenant=tenant,
            spaces=spaces,
            deleted_counts=deleted_counts,
            inserted_counts=inserted_counts,
            dry_run=False,
        )

    return 0


if __name__ == "__main__":
    raise SystemExit(main())