declare module '@/types/user' {
  export enum UserRole {
    SUPERADMIN = 'SUPERADMIN',
    COMMERCIAL = 'COMMERCIAL',
    OPERATOR = 'OPERATOR',
  }

  export interface User {
    id: string;
    name: string;
    email: string;
    role: UserRole;
    tenantId: string | null; // Nullable for superadmins or users not assigned to a specific tenant
    isActive: boolean;
  }
}
