/**
 * Reglas de dependencias entre capas (ejecutar: npm run verify:deps).
 * @type {import('dependency-cruiser').IConfiguration}
 */
module.exports = {
  forbidden: [
    {
      name: 'no-app-deep-features',
      severity: 'error',
      comment: 'Las rutas app/ no deben importar internals de features (solo barrel index).',
      from: { path: '^app/' },
      to: {
        path: '^features/[^/]+/(components|store|lib)/',
      },
    },
    {
      name: 'lib-no-features',
      severity: 'error',
      comment: 'Infra en lib/ (http, utils, etc.) no importa features; excepción temporal: lib/store re-exports.',
      from: { path: '^lib/', pathNot: '^lib/store/' },
      to: { path: '^features/' },
    },
  ],
  options: {
    doNotFollow: { path: 'node_modules' },
    tsPreCompilationDeps: true,
  },
};
