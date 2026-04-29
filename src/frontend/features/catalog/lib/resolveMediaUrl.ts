/**
 * Convierte rutas `/api/media/...` en URL absoluta cuando `NEXT_PUBLIC_API_URL` termina en `/api`.
 */

export function resolveMediaUrl(path: string): string {
  if (!path) return '';
  if (path.startsWith('http://') || path.startsWith('https://')) return path;
  const base = process.env.NEXT_PUBLIC_API_URL || '';
  if (base && path.startsWith('/api')) {
    return base.replace(/\/api\/?$/, '') + path;
  }
  return path;
}
