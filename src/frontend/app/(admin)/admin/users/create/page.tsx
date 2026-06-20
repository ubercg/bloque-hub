'use client';

import { RoleGuard, CAN_ACCESS_SUPERADMIN } from '@/features/auth';
import { UserCreateForm } from '@/features/admin/users/UserCreateForm';

export default function AdminUserCreatePage() {
  return (
    <RoleGuard allowedRoles={CAN_ACCESS_SUPERADMIN}>
      <UserCreateForm />
    </RoleGuard>
  );
}
