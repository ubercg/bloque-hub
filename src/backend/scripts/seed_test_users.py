#!/usr/bin/env python3
"""
Seed de usuarios de prueba para desarrollo y E2E.
Crea tenant "Test Tenant" y usuarios con password "password".

Ejecutar desde la raíz del repo (donde está docker-compose.yml):
  docker compose exec backend env PYTHONPATH=/app python scripts/seed_test_users.py

Desde backend/ con venv activo:
  python scripts/seed_test_users.py
"""

from app.db.session import get_db_context
from app.modules.identity import services
from app.modules.identity.models import Tenant, User, UserRole

TEST_TENANT_SLUG = "test-tenant"
TEST_USERS = [
    ("customer@test.com", "Cliente Prueba", UserRole.CUSTOMER),
    ("commercial@test.com", "Comercial Prueba", UserRole.COMMERCIAL),
    ("operations@test.com", "Operaciones Prueba", UserRole.OPERATIONS),
    ("finance@test.com", "Finanzas Prueba", UserRole.FINANCE),
    ("admin@test.com", "Admin Prueba", UserRole.SUPERADMIN),
]
PASSWORD = "password"


def main() -> None:
    with get_db_context(tenant_id=None, role="SUPERADMIN") as db:
        tenant = db.query(Tenant).filter(Tenant.slug == TEST_TENANT_SLUG).first()
        if not tenant:
            tenant = Tenant(name="Test Tenant", slug=TEST_TENANT_SLUG)
            db.add(tenant)
            db.commit()
            db.refresh(tenant)
            print(f"Tenant creado: {tenant.slug} ({tenant.id})")
        else:
            print(f"Tenant existente: {tenant.slug}")

        hashed = services.get_password_hash(PASSWORD)
        for email, full_name, role in TEST_USERS:
            user = db.query(User).filter(User.email == email).first()
            if not user:
                user = User(
                    tenant_id=tenant.id,
                    email=email,
                    hashed_password=hashed,
                    full_name=full_name,
                    role=role,
                )
                db.add(user)
                db.commit()
                db.refresh(user)
                print(f"Usuario creado: {email} (role={role.value})")
            else:
                print(f"Usuario existente: {email}")

    print("Listo. Credenciales: customer@test.com, commercial@test.com, operations@test.com, finance@test.com, admin@test.com — todos con password 'password'.")


if __name__ == "__main__":
    main()
