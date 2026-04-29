"""
Matriz de permisos RBAC (Role-Based Access Control) y SoD (Segregation of Duties).

- CUSTOMER: crear reserva, subir comprobante, ver propias reservas, portal.
- COMMERCIAL: generar pase de caja, CRM (leads/cotizaciones), descargar PDF, enviar contrato; NO aprobar/rechazar pago.
- OPERATIONS: OS, checklists, evidencias, scanner/access.
- FINANCE: aprobar/rechazar pago, audit-package, CFDIs, conciliación.
- SUPERADMIN: todo lo anterior.
"""

# Roles que pueden aprobar o rechazar un pago (SoD: solo Finance + SuperAdmin)
ALLOWED_APPROVE_REJECT_PAYMENT_ROLES = frozenset({"FINANCE", "SUPERADMIN"})

# Roles que pueden generar pase de caja (Commercial, Finance, SuperAdmin)
ALLOWED_GENERATE_SLIP_ROLES = frozenset({"COMMERCIAL", "FINANCE", "SUPERADMIN"})

# Roles que pueden acceder a operaciones (OS, checklists, scanner)
ALLOWED_OPERATIONS_ROLES = frozenset({"OPERATIONS", "SUPERADMIN"})

# Roles que pueden subir evidencias
ALLOWED_EVIDENCE_UPLOAD_ROLES = frozenset({"COMMERCIAL", "OPERATIONS", "SUPERADMIN"})

# Roles que pueden acceder a finanzas (audit-package, CFDIs, conciliación)
ALLOWED_FINANCE_ROLES = frozenset({"FINANCE", "SUPERADMIN"})

# Roles de back-office (no aplican límite anti-hoarding)
STAFF_ROLES = frozenset({"COMMERCIAL", "OPERATIONS", "FINANCE", "SUPERADMIN"})
