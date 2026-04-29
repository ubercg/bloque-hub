import React from 'react';
import { ScheduleSlot, SlotType } from '@/types/schedule';
import { format } from 'date-fns';

interface SlotInputProps {
  slot: ScheduleSlot;
  onChange: (updates: Partial<ScheduleSlot>) => void;
  onRemove: () => void;
  errors: string[];
  isExisting?: boolean; // To indicate if it's a non-editable existing slot
}

const slotTypeColors: Record<SlotType, string> = {
  USO: 'bg-slot-uso text-text-default',
  MONTAJE: 'bg-slot-montaje text-text-default',
  DESMONTAJE: 'bg-slot-desmontaje text-text-default',
};

const SlotInput: React.FC<SlotInputProps> = ({ slot, onChange, onRemove, errors, isExisting = false }) => {
  const handleDateChange = (field: 'start' | 'end', value: string) => {
    onChange({ [field]: new Date(value) });
  };

  const handleTypeChange = (e: React.ChangeEvent<HTMLSelectElement>) => {
    onChange({ type: e.target.value as SlotType });
  };

  const formattedStartDate = format(slot.start, "yyyy-MM-dd'T'HH:mm");
  const formattedEndDate = format(slot.end, "yyyy-MM-dd'T'HH:mm");

  const slotColorClass = slotTypeColors[slot.type] || 'bg-gray-200';

  return (
    <div className={`p-4 border rounded-lg shadow-soft mb-4 ${errors.length > 0 ? 'border-slot-overlap-error' : 'border-border-default'} ${slotColorClass}`}>
      <div className="flex justify-between items-center mb-2">
        <h3 className="font-semibold text-lg">{slot.type} Slot</h3>
        {!isExisting && (
          <button
            onClick={onRemove}
            className="text-red-600 hover:text-red-800 transition-colors duration-150 focus:outline-none focus:ring-2 focus:ring-red-500 focus:ring-offset-2"
            aria-label="Remove slot"
          >
            Remove
          </button>
        )}
      </div>

      <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
        <div>
          <label htmlFor={`slot-type-${slot.id}`} className="block text-sm font-medium text-text-light mb-1">
            Type
          </label>
          <select
            id={`slot-type-${slot.id}`}
            value={slot.type}
            onChange={handleTypeChange}
            disabled={isExisting}
            className={`w-full p-2 border rounded-md focus:ring-primary focus:border-primary transition-colors duration-150 ${isExisting ? 'bg-gray-100 cursor-not-allowed' : 'bg-white'}`}
          >
            <option value="USO">USO</option>
            <option value="MONTAJE">MONTAJE</option>
            <option value="DESMONTAJE">DESMONTAJE</option>
          </select>
        </div>

        <div>
          <label htmlFor={`slot-start-${slot.id}`} className="block text-sm font-medium text-text-light mb-1">
            Start Time
          </label>
          <input
            id={`slot-start-${slot.id}`}
            type="datetime-local"
            value={formattedStartDate}
            onChange={(e) => handleDateChange('start', e.target.value)}
            disabled={isExisting}
            className={`w-full p-2 border rounded-md focus:ring-primary focus:border-primary transition-colors duration-150 ${isExisting ? 'bg-gray-100 cursor-not-allowed' : 'bg-white'} ${errors.length > 0 ? 'border-slot-overlap-error' : 'border-border-default'}`}
            aria-invalid={errors.length > 0}
          />
        </div>

        <div>
          <label htmlFor={`slot-end-${slot.id}`} className="block text-sm font-medium text-text-light mb-1">
            End Time
          </label>
          <input
            id={`slot-end-${slot.id}`}
            type="datetime-local"
            value={formattedEndDate}
            onChange={(e) => handleDateChange('end', e.target.value)}
            disabled={isExisting}
            className={`w-full p-2 border rounded-md focus:ring-primary focus:border-primary transition-colors duration-150 ${isExisting ? 'bg-gray-100 cursor-not-allowed' : 'bg-white'} ${errors.length > 0 ? 'border-slot-overlap-error' : 'border-border-default'}`}
            aria-invalid={errors.length > 0}
          />
        </div>
      </div>

      {errors.length > 0 && (
        <div className="mt-3 text-sm text-slot-overlap-error" role="alert">
          {errors.map((error, index) => (
            <p key={index}>{error}</p>
          ))}
        </div>
      )}
    </div>
  );
};

export default SlotInput;