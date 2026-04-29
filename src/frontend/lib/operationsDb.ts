/**
 * IndexedDB for operations PWA: cache service orders and queue offline mutations.
 */

import { openDB, DBSchema, IDBPDatabase } from 'idb';

const DB_NAME = 'bloque-operations';
const DB_VERSION = 1;

interface OperationsDB extends DBSchema {
  orders: {
    key: string;
    value: { id: string; data: unknown; updatedAt: number };
  };
  pending_mutations: {
    key: number;
    value: { id?: number; itemId: string; status: string; createdAt: number };
    indexes: { by_created: number };
  };
}

let dbPromise: Promise<IDBPDatabase<OperationsDB>> | null = null;

function getDB() {
  if (!dbPromise) {
    dbPromise = openDB<OperationsDB>(DB_NAME, DB_VERSION, {
      upgrade(db) {
        if (!db.objectStoreNames.contains('orders')) {
          db.createObjectStore('orders', { keyPath: 'id' });
        }
        if (!db.objectStoreNames.contains('pending_mutations')) {
          const store = db.createObjectStore('pending_mutations', { keyPath: 'id', autoIncrement: true });
          store.createIndex('by_created', 'createdAt');
        }
      },
    });
  }
  return dbPromise;
}

export async function cacheOrder(orderId: string, data: unknown): Promise<void> {
  const db = await getDB();
  await db.put('orders', {
    id: orderId,
    data,
    updatedAt: Date.now(),
  });
}

export async function getCachedOrder(orderId: string): Promise<unknown | null> {
  const db = await getDB();
  const row = await db.get('orders', orderId);
  return row?.data ?? null;
}

export async function cacheOrdersList(orders: unknown[]): Promise<void> {
  const db = await getDB();
  const tx = db.transaction('orders', 'readwrite');
  const now = Date.now();
  for (const o of orders as { id: string }[]) {
    await tx.store.put({ id: o.id, data: o, updatedAt: now });
  }
  await tx.done;
}

export async function getCachedOrdersList(): Promise<unknown[]> {
  const db = await getDB();
  const all = await db.getAll('orders');
  return all.map((r) => r.data);
}

export async function addPendingMutation(itemId: string, status: string): Promise<void> {
  const db = await getDB();
  await db.add('pending_mutations', {
    itemId,
    status,
    createdAt: Date.now(),
  });
}

export async function getPendingMutations(): Promise<{ id: number; itemId: string; status: string }[]> {
  const db = await getDB();
  const all = await db.getAllFromIndex('pending_mutations', 'by_created');
  return all.map((m) => ({ id: m.id!, itemId: m.itemId, status: m.status }));
}

export async function removePendingMutation(id: number): Promise<void> {
  const db = await getDB();
  await db.delete('pending_mutations', id);
}

export async function clearPendingMutations(): Promise<void> {
  const db = await getDB();
  await db.clear('pending_mutations');
}
