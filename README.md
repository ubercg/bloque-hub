# BLOQUE Hub

Plataforma para gestion de espacios, reservas y operacion interna de BLOQUE Hub.
Incluye:

- `frontend`: Next.js 16 + React 19 (portal cliente y panel admin)
- `backend`: FastAPI + PostgreSQL + Celery + Redis
- `nginx`: punto de entrada unico para frontend y backend

## Arquitectura

Servicios principales definidos en `docker-compose.yml`:

- `frontend` (`:3000`) app Next.js
- `backend` (`:8000`) API FastAPI
- `nginx` (`:80`) reverse proxy de entrada
- `db` (`:5432`) Postgres de aplicacion
- `redis` (`6379` interno) broker para Celery
- `celery_worker` y `celery_beat` para tareas async

## Funcionalidades cubiertas

- Catalogo de espacios y flujo de reserva cliente.
- Autenticacion por rol (customer, commercial, operations, finance, admin).
- Gestion operativa/admin: CRM, finanzas, descuentos, inventario, operaciones.
- Healthcheck de infraestructura en `GET /api/v1/system/health`.
- Suite E2E Playwright en `src/frontend/tests/e2e`.

## Requisitos

- Docker Desktop (Compose v2)
- Al menos 4 GB RAM libres para levantar todo el stack
- Puertos libres: `80`, `5432`

## Inicio rapido

### 1. Configurar entorno

```bash
cp .env.example .env
```

### 2. Levantar stack

```bash
docker compose up -d --build
```

### 3. Ver estado

```bash
docker compose ps
```

### 4. Ejecutar migraciones (obligatorio en primer arranque)

```bash
docker compose exec backend alembic upgrade head
```

Se aplican 31 migraciones que crean: tablas de usuarios, tenants, RLS, CRM, reservas, contratos, fulfillment, CFDI, pagos, accesos QR, inventario, descuentos, KYC y vistas materializadas.

### 5. Poblar datos de prueba (desarrollo)

**Usuarios de prueba** (5 roles):

```bash
docker compose exec backend env PYTHONPATH=/app python scripts/seed_test_users.py
```

Crea tenant `bloque-hub` y 5 usuarios (`customer`, `commercial`, `operations`, `finance`, `admin@test.com` — todos con password `password`).

**Catalogo de espacios** (opcional):

```bash
docker compose exec backend env PYTHONPATH=/app python scripts/seed_spaces_catalog_bloque.py --tenant-slug bloque-hub --horizon-days 30
```

Parsea `docs/catalog_espacios.md` y crea: 15 espacios, 4 relaciones parent-child, 15 reglas de reserva, ~5400 slots de inventario (30 dias).

### Seed completo en un solo comando

```bash
docker compose exec backend sh -c "
  alembic upgrade head &&
  env PYTHONPATH=/app python scripts/seed_test_users.py &&
  env PYTHONPATH=/app python scripts/seed_spaces_catalog_bloque.py --tenant-slug bloque-hub --horizon-days 30
"
```

## URLs locales

- App (nginx): `http://localhost`
- API docs: `http://localhost/api/v1/docs`
- Health: `http://localhost/api/v1/system/health`

## Verificacion rapida

1) Health backend:

```bash
curl -s http://localhost/api/v1/system/health
```

2) Home frontend:

```bash
curl -I http://localhost/
```

3) Login page:

```bash
curl -I http://localhost/login
```

4) Test API minimo:

```bash
docker compose exec backend pytest tests/api/test_health.py -q
```

## Credenciales de prueba

Despues de correr `seed_test_users.py`:

- `customer@test.com` / `password`
- `commercial@test.com` / `password`
- `operations@test.com` / `password`
- `finance@test.com` / `password`
- `admin@test.com` / `password`

## Flujo de desarrollo

- Frontend source: `src/frontend`
- Backend source: `src/backend`
- Dockerfiles: `infra/docker`
- Documentacion tecnica: `docs/`

Compose usa `docker-compose.override.yml` para modo desarrollo (hot reload en backend/frontend).

## Solucion de problemas

- Si `docker compose up` falla por `.env` faltante: crear `.env` en la raiz (ver Inicio rapido).
- Si frontend queda en 500 por dependencias: reconstruir `frontend` (`docker compose up -d --build frontend`).
- Si health devuelve `degraded`: revisar logs de `backend` y `db`.
- Si login falla en E2E: correr seed de usuarios de prueba.
- Si Postgres local ocupa puerto `5432`: parar servicio local o cambiar port en compose.

## Apagar stack

```bash
docker compose down
```

## Produccion

Ver `docs/DEPLOYMENT.md` para guia completa de despliegue en servidor Linux con Docker.
