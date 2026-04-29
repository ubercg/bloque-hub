/**
 * Precios por espacio según docs/catalog_espacios.md § I (MXN).
 * Usado para la columna "Tiempo" y precios unitarios en la precotización.
 */

export interface CatalogPrices {
  porHora: number;
  seisHoras: number;
  doceHoras: number;
  semana: number;
  mes: number;
}

/** Normaliza para matching (sin acentos, minúsculas). */
export function normalizeSpaceName(s: string): string {
  return s
    .normalize('NFD')
    .replace(/\p{M}/gu, '')
    .toLowerCase()
    .trim();
}

/**
 * Filas del catálogo (orden: más específicas primero).
 * Valores tomados de docs/catalog_espacios.md líneas 227-237.
 */
const CATALOG_ROWS: Array<{ test: (n: string) => boolean; prices: CatalogPrices }> = [
  {
    test: (n) => n.includes('cafeteria') || n.includes('cafetería'),
    prices: {
      porHora: 270,
      seisHoras: 649,
      doceHoras: 865,
      semana: 0,
      mes: 0,
    },
  },
  {
    test: (n) => n.includes('sala cisco'),
    prices: {
      porHora: 720,
      seisHoras: 3782,
      doceHoras: 6483,
      semana: 32415,
      mes: 129660,
    },
  },
  {
    test: (n) => n.includes('computo') || n.includes('cómputo'),
    prices: {
      porHora: 5402,
      seisHoras: 27013,
      doceHoras: 48623,
      semana: 243113,
      mes: 972451,
    },
  },
  {
    test: (n) =>
      n.includes('sala mural') ||
      n.includes('aula estandar') ||
      n.includes('aula estándar'),
    prices: {
      porHora: 1296,
      seisHoras: 5186,
      doceHoras: 16856,
      semana: 84279,
      mes: 337116,
    },
  },
  {
    test: (n) => n.includes('sala magna') || n.includes('aula magna'),
    prices: {
      porHora: 2881,
      seisHoras: 17288,
      doceHoras: 22690,
      semana: 113453,
      mes: 453810,
    },
  },
  {
    test: (n) => n.includes('convenciones') && n.includes('sala') && !n.includes('centro'),
    prices: {
      porHora: 2881,
      seisHoras: 17288,
      doceHoras: 22690,
      semana: 113453,
      mes: 453810,
    },
  },
  {
    test: (n) =>
      n.includes('sala 1 centro') ||
      n.includes('sala 2 centro') ||
      n.includes('sala 3 centro') ||
      n.includes('sala 4 centro') ||
      (n.includes('centro de convenciones') && n.includes('sala')),
    prices: {
      porHora: 25212,
      seisHoras: 89681,
      doceHoras: 97245,
      semana: 486225,
      mes: 1944902,
    },
  },
  {
    test: (n) => n.includes('centro de convenciones'),
    prices: {
      porHora: 25212,
      seisHoras: 89681,
      doceHoras: 97245,
      semana: 486225,
      mes: 1944902,
    },
  },
  {
    test: (n) => n.includes('terraza'),
    prices: {
      porHora: 9181,
      seisHoras: 63367,
      doceHoras: 69152,
      semana: 345761,
      mes: 1383041,
    },
  },
  {
    test: (n) => n.includes('explanada'),
    prices: {
      porHora: 15578,
      seisHoras: 71899,
      doceHoras: 78877,
      semana: 394383,
      mes: 1577532,
    },
  },
  {
    test: (n) => n.includes('auditorio'),
    prices: {
      porHora: 7744,
      seisHoras: 46461,
      doceHoras: 60508,
      semana: 302540,
      mes: 1210162,
    },
  },
  {
    test: (n) => n.includes('lobby'),
    prices: {
      porHora: 7204,
      seisHoras: 32415,
      doceHoras: 48623,
      semana: 243113,
      mes: 972451,
    },
  },
  {
    test: (n) => n.includes('salas de convenciones') || n.includes('salas convenciones'),
    prices: {
      porHora: 2881,
      seisHoras: 17288,
      doceHoras: 22690,
      semana: 113453,
      mes: 453810,
    },
  },
];

export function resolveCatalogPrices(spaceName: string): CatalogPrices | null {
  const n = normalizeSpaceName(spaceName);
  for (const row of CATALOG_ROWS) {
    if (row.test(n)) return row.prices;
  }
  return null;
}
