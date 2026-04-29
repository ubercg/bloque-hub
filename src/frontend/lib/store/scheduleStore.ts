import { create } from 'zustand';
import { ScheduleSlot, ScheduleData, SlotType, DateRange } from '@/types/schedule';
import { getSpaceSchedule, saveSpaceSchedule } from '@/lib/actions/schedule';
import { toast } from 'sonner';
import { isAfter, isBefore, differenceInMinutes } from 'date-fns';

interface ScheduleState {
  slots: ScheduleSlot[];
  existingSlots: ScheduleSlot[]; // Slots fetched from backend, not editable by user directly
  selectedSlotId: string | null;
  validationErrors: Record<string, string[]>;
  isLoading: boolean;
  isSaving: boolean;
  currentDateRange: DateRange;
}

interface ScheduleActions {
  setSlots: (slots: ScheduleSlot[]) => void;
  setExistingSlots: (slots: ScheduleSlot[]) => void;
  addSlot: (slot: Omit<ScheduleSlot, 'id'>) => void;
  updateSlot: (id: string, updates: Partial<ScheduleSlot>) => void;
  removeSlot: (id: string) => void;
  setSelectedSlot: (id: string | null) => void;
  setValidationErrors: (errors: Record<string, string[]>) => void;
  clearValidationErrors: () => void;
  setCurrentDateRange: (range: DateRange) => void;
  fetchSchedule: (spaceId: string, dateRange: DateRange) => Promise<void>;
  saveSchedule: (spaceId: string) => Promise<void>;
  validateSlots: (slotsToValidate: ScheduleSlot[], allSlots: ScheduleSlot[]) => Record<string, string[]>;
}

const MIN_SLOT_DURATION_MINUTES = 30;

export const useScheduleStore = create<ScheduleState & ScheduleActions>((set, get) => ({
  slots: [],
  existingSlots: [],
  selectedSlotId: null,
  validationErrors: {},
  isLoading: false,
  isSaving: false,
  currentDateRange: {
    start: new Date(),
    end: new Date(new Date().setHours(23, 59, 59, 999)),
  },

  setSlots: (slots) => set({ slots }),
  setExistingSlots: (slots) => set({ existingSlots: slots }),
  addSlot: (newSlot) => {
    const id = crypto.randomUUID();
    set((state) => ({
      slots: [...state.slots, { ...newSlot, id }],
      selectedSlotId: id,
    }));
  },
  updateSlot: (id, updates) => {
    set((state) => {
      const updatedSlots = state.slots.map((slot) =>
        slot.id === id ? { ...slot, ...updates } : slot
      );
      return { slots: updatedSlots };
    });
  },
  removeSlot: (id) => {
    set((state) => ({
      slots: state.slots.filter((slot) => slot.id !== id),
      selectedSlotId: state.selectedSlotId === id ? null : state.selectedSlotId,
    }));
  },
  setSelectedSlot: (id) => set({ selectedSlotId: id }),
  setValidationErrors: (errors) => set({ validationErrors: errors }),
  clearValidationErrors: () => set({ validationErrors: {} }),
  setCurrentDateRange: (range) => set({ currentDateRange: range }),

  fetchSchedule: async (spaceId, dateRange) => {
    set({ isLoading: true, validationErrors: {} });
    try {
      const data = await getSpaceSchedule(spaceId, dateRange);
      // Filter out slots that are part of the current user's editable schedule
      // For this mock, we assume all fetched slots are 'existing' and not editable by current user
      set({ existingSlots: data, slots: [] }); // Clear editable slots on fetch for simplicity
      toast.success('Schedule fetched successfully.');
    } catch (error: any) {
      toast.error(`Failed to fetch schedule: ${error.message}`);
      set({ existingSlots: [], slots: [] });
    } finally {
      set({ isLoading: false });
    }
  },

  saveSchedule: async (spaceId) => {
    set({ isSaving: true, validationErrors: {} });
    const { slots, existingSlots } = get();
    const allSlotsForValidation = [...slots, ...existingSlots];

    const clientErrors = get().validateSlots(slots, allSlotsForValidation);

    if (Object.keys(clientErrors).length > 0) {
      set({ validationErrors: clientErrors, isSaving: false });
      toast.error('Please correct the errors in your schedule.');
      return;
    }

    try {
      await saveSpaceSchedule(spaceId, slots);
      toast.success('Schedule saved successfully!');
      // After successful save, refetch to get the latest state including newly saved slots as 'existing'
      await get().fetchSchedule(spaceId, get().currentDateRange);
    } catch (error: any) {
      toast.error(`Failed to save schedule: ${error.message}`);
      // Optionally, parse backend errors and set validationErrors
    } finally {
      set({ isSaving: false });
    }
  },

  validateSlots: (slotsToValidate: ScheduleSlot[], allSlots: ScheduleSlot[]) => {
    const errors: Record<string, string[]> = {};

    slotsToValidate.forEach((currentSlot) => {
      const slotErrors: string[] = [];

      // REGLA 4: All slots must have a `start` time strictly before their `end` time.
      if (!isBefore(currentSlot.start, currentSlot.end)) {
        slotErrors.push('Start time must be before end time.');
      }

      // REGLA 6: Minimum slot duration
      if (differenceInMinutes(currentSlot.end, currentSlot.start) < MIN_SLOT_DURATION_MINUTES) {
        slotErrors.push(`Minimum duration is ${MIN_SLOT_DURATION_MINUTES} minutes.`);
      }

      // Overlap checks
      allSlots.forEach((otherSlot) => {
        // Don't compare a slot with itself, unless it's an existing slot being compared to a new one with same ID
        if (currentSlot.id === otherSlot.id && slotsToValidate.includes(otherSlot)) return; // Skip if comparing the same editable slot

        // Check for overlap: [start1, end1) overlaps with [start2, end2) if start1 < end2 AND start2 < end1
        const overlaps = currentSlot.start < otherSlot.end && otherSlot.start < currentSlot.end;

        if (overlaps) {
          // REGLA 1: 'MONTAJE' slots cannot overlap with any other 'MONTAJE', 'DESMONTAJE', or 'USO' slots for the same space.
          if (currentSlot.type === 'MONTAJE') {
            slotErrors.push(`MONTAJE slot overlaps with an existing ${otherSlot.type} slot (ID: ${otherSlot.id}).`);
          }
          // REGLA 2: 'DESMONTAJE' slots cannot overlap with 'USO' or 'MONTAJE' slots for the same space.
          else if (currentSlot.type === 'DESMONTAJE' && (otherSlot.type === 'USO' || otherSlot.type === 'MONTAJE')) {
            slotErrors.push(`DESMONTAJE slot overlaps with an existing ${otherSlot.type} slot (ID: ${otherSlot.id}).`);
          }
          // REGLA 3: 'USO' slots can be discontinuous and can overlap with other 'USO' slots for the same space, but not with 'MONTAJE' or 'DESMONTAJE' slots.
          else if (currentSlot.type === 'USO' && (otherSlot.type === 'MONTAJE' || otherSlot.type === 'DESMONTAJE')) {
            slotErrors.push(`USO slot overlaps with an existing ${otherSlot.type} slot (ID: ${otherSlot.id}).`);
          }
        }
      });

      if (slotErrors.length > 0) {
        errors[currentSlot.id] = [...(errors[currentSlot.id] || []), ...slotErrors];
      }
    });

    return errors;
  }
}));