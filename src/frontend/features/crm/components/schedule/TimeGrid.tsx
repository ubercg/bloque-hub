import React from 'react';
import { ScheduleSlot, SlotType } from '@/types/schedule';
import { format, startOfDay, addHours, isSameDay } from 'date-fns';

interface TimeGridProps {
  slots: ScheduleSlot[];
  existingSlots: ScheduleSlot[];
  onSlotClick: (id: string) => void;
  selectedSlotId: string | null;
  date: Date; // The day to display the grid for
  validationErrors: Record<string, string[]>;
}

const slotTypeColors: Record<SlotType, string> = {
  USO: 'bg-slot-uso',
  MONTAJE: 'bg-slot-montaje',
  DESMONTAJE: 'bg-slot-desmontaje',
};

const TimeGrid: React.FC<TimeGridProps> = ({ slots, existingSlots, onSlotClick, selectedSlotId, date, validationErrors }) => {
  const hours = Array.from({ length: 24 }, (_, i) => i);
  const currentDayStart = startOfDay(date);

  const allSlots = [...slots, ...existingSlots].filter(slot => isSameDay(slot.start, date));

  return (
    <div className="border border-border-default rounded-lg overflow-hidden shadow-soft bg-white">
      <div className="grid grid-cols-[60px_1fr] divide-x divide-border-default">
        {/* Time Axis */}
        <div className="flex flex-col bg-gray-50">
          {hours.map((hour) => (
            <div key={hour} className="h-12 flex items-center justify-end pr-2 text-xs text-text-light border-b border-border-default last:border-b-0">
              {format(addHours(currentDayStart, hour), 'ha')}
            </div>
          ))}
        </div>

        {/* Schedule Grid */}
        <div className="relative">
          {/* Hour Lines */}
          {hours.map((hour) => (
            <div
              key={`line-${hour}`}
              className="absolute left-0 right-0 border-b border-border-default"
              style={{ top: `${hour * 48}px`, height: '48px' }}
            ></div>
          ))}

          {/* Slots */}
          {allSlots.map((slot) => {
            const slotStart = slot.start.getTime();
            const slotEnd = slot.end.getTime();
            const dayStart = currentDayStart.getTime();

                        const topOffset = ((slotStart - dayStart) / (1000 * 60 * 60)) * 48; // 48px per hour
            const height = ((slotEnd - slotStart) / (1000 * 60 * 60)) * 48;
            
            return (
              <div 
                key={slot.id} 
                className="absolute left-2 right-2 rounded border border-gray-200 p-2 text-xs shadow-sm bg-blue-100"
                style={{ top: `${topOffset}px`, height: `${height}px` }}
                onClick={() => onSlotClick(slot.id)}
              >
                <div className="font-semibold">{slot.type}</div>
                <div>{format(slot.start, 'HH:mm')} - {format(slot.end, 'HH:mm')}</div>
              </div>
            );
          })}
        </div>
      </div>
    </div>
  );
};

export default TimeGrid;