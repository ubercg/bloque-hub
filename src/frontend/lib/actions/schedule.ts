"use server";

import { ScheduleData, DateRange, ScheduleSlot } from '@/types/schedule';
import { addHours, startOfDay, endOfDay, addDays } from 'date-fns';

// Mock data for demonstration purposes
const MOCK_SCHEDULE_DATA: ScheduleData = [
  {
    id: 'mock-1',
    type: 'USO',
    start: addHours(startOfDay(new Date()), 9),
    end: addHours(startOfDay(new Date()), 12),
    spaceId: 'space-1',
    bookingId: 'booking-A',
    tenantId: 'tenant-X'
  },
  {
    id: 'mock-2',
    type: 'MONTAJE',
    start: addHours(startOfDay(new Date()), 7),
    end: addHours(startOfDay(new Date()), 9),
    spaceId: 'space-1',
    bookingId: 'booking-B',
    tenantId: 'tenant-Y'
  },
  {
    id: 'mock-3',
    type: 'DESMONTAJE',
    start: addHours(startOfDay(new Date()), 17),
    end: addHours(startOfDay(new Date()), 19),
    spaceId: 'space-1',
    bookingId: 'booking-C',
    tenantId: 'tenant-X'
  },
  {
    id: 'mock-4',
    type: 'USO',
    start: addHours(startOfDay(addDays(new Date(), 1)), 10),
    end: addHours(startOfDay(addDays(new Date(), 1)), 14),
    spaceId: 'space-1',
    bookingId: 'booking-D',
    tenantId: 'tenant-Y'
  },
];

/**
 * Server Action to fetch schedule data for a given space and date range.
 * In a real application, this would call a backend API.
 */
export async function getSpaceSchedule(
  spaceId: string,
  dateRange: DateRange
): Promise<ScheduleData> {
  console.log(`Fetching schedule for space ${spaceId} from ${dateRange.start} to ${dateRange.end}`);

  // Simulate network delay
  await new Promise((resolve) => setTimeout(resolve, 500));

  // Filter mock data by spaceId and dateRange
  const filteredData = MOCK_SCHEDULE_DATA.filter(slot =>
    slot.spaceId === spaceId &&
    slot.start < dateRange.end &&
    slot.end > dateRange.start
  );

  return filteredData;
}

/**
 * Server Action to save schedule data for a given space.
 * In a real application, this would call a backend API.
 * The backend is the SSOT for final validation.
 */
export async function saveSpaceSchedule(
  spaceId: string,
  scheduleData: ScheduleData
): Promise<void> {
  console.log(`Saving schedule for space ${spaceId}:`, scheduleData);

  // Simulate network delay
  await new Promise((resolve) => setTimeout(resolve, 700));

  // Simulate backend validation failure for demonstration
  const hasOverlapError = scheduleData.some(slot => {
    if (slot.type === 'MONTAJE') {
      return scheduleData.some(otherSlot => {
        if (slot.id === otherSlot.id) return false;
        return slot.start < otherSlot.end && otherSlot.start < slot.end;
      });
    }
    return false;
  });

  if (hasOverlapError) {
    // In a real scenario, the backend would return specific validation errors
    throw new Error('Backend validation failed: MONTAJE slot overlaps with another slot.');
  }

  // If successful, the backend would persist the data.
  console.log('Schedule saved successfully (mock).');
}