export type SlotType = 'USO' | 'MONTAJE' | 'DESMONTAJE';

export interface ScheduleSlot {
  id: string;
  type: SlotType;
  start: Date;
  end: Date;
  spaceId: string;
  // Optional: bookingId for existing slots from other bookings/tenants
  bookingId?: string;
  // Optional: tenantId for existing slots from other tenants (for display/validation context)
  tenantId?: string;
}

export type ScheduleData = ScheduleSlot[];

export interface DateRange {
  start: Date;
  end: Date;
}

export interface ISlot {
  id: string;
  date: string;
  startTime: string;
  endTime: string;
  type: SlotType;
  price?: number;
}

export interface ISchedule {
  slots: ISlot[];
  totalPrice?: number;
}
