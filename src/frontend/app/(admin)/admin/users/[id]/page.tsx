'use client';

import { RoleGuard, CAN_ACCESS_SUPERADMIN } from '@/features/auth';
import { UserEditForm } from '@/features/admin/users/UserEditForm';
import { useParams } from 'next/navigation';

export default function AdminUserDetailPage() {
  const params = useParams();
  const userId = params.id as string;

  return (
    <RoleGuard allowedRoles={CAN_ACCESS_SUPERADMIN}>
      <UserEditForm userId={userId} />
    </RoleGuard>
  );
}
