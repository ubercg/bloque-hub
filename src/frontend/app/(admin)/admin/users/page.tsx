'use client';

import { RoleGuard, CAN_ACCESS_SUPERADMIN } from '@/features/auth';
import { UserList } from '@/features/admin/users/UserList';

export default function AdminUsersPage() {
  return (
    <RoleGuard allowedRoles={CAN_ACCESS_SUPERADMIN}>
      <UserList />
    </RoleGuard>
  );
}
