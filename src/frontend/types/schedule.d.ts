export type SlotType = 'USO' | 'MONTAJE' | 'DESMONTAJE';

export interface ISlot {
  id: string;
  type: SlotType;
  start: Date;
  end: Date;
  // Optional: resourceId if scheduling multiple resources/spaces
  // resourceId?: string;
}

export interface ISchedule {
  id: string;
  spaceId: string;
  slots: ISlot[];
}