/**
 * Event Cart (Bandeja de Evento) state management with Zustand
 * Multi-space cart for B2B reservations
 */

import { create } from 'zustand';

export interface EventCartItem {
  spaceId: string;
  spaceName: string;
  fecha: string; // ISO date string (YYYY-MM-DD)
  horaInicio: string; // Time string (HH:MM)
  horaFin: string; // Time string (HH:MM)
  precio: number;
  capacidad?: number;
}

/** Key for a single cart line: spaceId|fecha|horaInicio|horaFin (for remove by item) */
export function itemKey(item: EventCartItem): string {
  return `${item.spaceId}|${item.fecha}|${item.horaInicio}|${item.horaFin}`;
}

/** Agrupa ítems del carrito por espacio + día (fecha). Los slots del mismo día se listan juntos. */
export function cartGroupKey(item: EventCartItem): string {
  return `${item.spaceId}|${item.fecha}`;
}

export interface EventCartGroup {
  key: string;
  spaceId: string;
  spaceName: string;
  fecha: string;
  items: EventCartItem[];
}

export function groupCartItemsBySpaceAndDate(items: EventCartItem[]): EventCartGroup[] {
  const map = new Map<string, EventCartItem[]>();
  for (const item of items) {
    const k = cartGroupKey(item);
    if (!map.has(k)) map.set(k, []);
    map.get(k)!.push(item);
  }
  for (const arr of map.values()) {
    arr.sort((a, b) => a.horaInicio.localeCompare(b.horaInicio));
  }
  const groups = Array.from(map.entries()).map(([key, groupItems]) => ({
    key,
    spaceId: groupItems[0].spaceId,
    spaceName: groupItems[0].spaceName,
    fecha: groupItems[0].fecha,
    items: groupItems,
  }));
  groups.sort((a, b) => {
    const byDate = a.fecha.localeCompare(b.fecha);
    if (byDate !== 0) return byDate;
    return a.spaceName.localeCompare(b.spaceName, 'es');
  });
  return groups;
}

/**
 * Agrupa por espacio en todo el periodo de la reservación (fecha inicio → fecha fin),
 * sin separar por día. Para precotización / confirmación cuando el evento abarca varias fechas.
 */
export function groupCartItemsBySpaceForReservationPeriod(items: EventCartItem[]): EventCartGroup[] {
  const map = new Map<string, EventCartItem[]>();
  for (const item of items) {
    const k = item.spaceId;
    if (!map.has(k)) map.set(k, []);
    map.get(k)!.push(item);
  }
  for (const arr of map.values()) {
    arr.sort((a, b) => {
      const c = a.fecha.localeCompare(b.fecha);
      if (c !== 0) return c;
      return a.horaInicio.localeCompare(b.horaInicio);
    });
  }
  return Array.from(map.entries()).map(([key, groupItems]) => ({
    key,
    spaceId: groupItems[0].spaceId,
    spaceName: groupItems[0].spaceName,
    /** Primera fecha del periodo (inicio cronológico). */
    fecha: groupItems[0].fecha,
    items: groupItems,
  })).sort((a, b) => a.spaceName.localeCompare(b.spaceName, 'es'));
}

interface EventCartState {
  items: EventCartItem[];
  eventGroupId: string | null;

  addSpace: (item: EventCartItem) => void;
  removeSpace: (spaceId: string) => void;
  removeCartItem: (key: string) => void;
  clearCart: () => void;
  setEventGroupId: (id: string) => void;
  getTotalPrice: () => number;
  getItemCount: () => number;
}

export const useEventCartStore = create<EventCartState>((set, get) => ({
  items: [],
  eventGroupId: null,

  addSpace: (item) =>
    set((state) => {
      const exists = state.items.some(
        (i) =>
          i.spaceId === item.spaceId &&
          i.fecha === item.fecha &&
          i.horaInicio === item.horaInicio &&
          i.horaFin === item.horaFin
      );

      if (exists) {
        return state;
      }

      return { items: [...state.items, item] };
    }),

  removeSpace: (spaceId) =>
    set((state) => ({
      items: state.items.filter((i) => i.spaceId !== spaceId),
    })),

  removeCartItem: (key) =>
    set((state) => ({
      items: state.items.filter((i) => itemKey(i) !== key),
    })),

  clearCart: () => set({ items: [], eventGroupId: null }),

  setEventGroupId: (id) => set({ eventGroupId: id }),

  getTotalPrice: () => {
    const { items } = get();
    return items.reduce((sum, item) => sum + item.precio, 0);
  },

  getItemCount: () => get().items.length,
}));
