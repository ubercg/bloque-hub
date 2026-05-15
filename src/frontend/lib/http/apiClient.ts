/**
 * Centralized API client with JWT authentication (infra).
 */

import axios from 'axios';

/**
 * Base URL del backend en el navegador (mismo origen que la app).
 * - Con nginx solo de BLOQUE Hub: suele ser `/api`.
 * - Tras proxy con prefijo (ej. taskflow en `/bloque`): `/bloque/api`.
 * Definir `NEXT_PUBLIC_API_URL` en `.env` antes de `docker compose build frontend`
 * (se inyecta en tiempo de build).
 */
const defaultApiBase =
  process.env.NEXT_PUBLIC_API_URL?.replace(/\/$/, '') || '/api';

const apiClient = axios.create({
  baseURL: defaultApiBase,
  headers: {
    'Content-Type': 'application/json',
  },
});

// Request interceptor: Add JWT token from localStorage
apiClient.interceptors.request.use(
  (config) => {
    // FormData: no fijar Content-Type (axios/json default rompe multipart: boundary y 422 en el backend).
    if (typeof FormData !== 'undefined' && config.data instanceof FormData) {
      delete config.headers['Content-Type'];
    }
    // Only access localStorage in browser environment
    if (typeof window !== 'undefined') {
      const token = localStorage.getItem('auth_token');
      if (token) {
        config.headers.Authorization = `Bearer ${token}`;
      }
    }
    return config;
  },
  (error) => {
    return Promise.reject(error);
  }
);

// Response interceptor: Handle 401 Unauthorized
apiClient.interceptors.response.use(
  (response) => response,
  (error) => {
    if (error.response?.status === 401) {
      if (typeof window !== 'undefined') {
        const url = String(error.config?.url ?? '');
        // Credenciales inválidas en login: dejar que la página maneje el error (sin recarga).
        if (url.includes('/auth/login')) {
          return Promise.reject(error);
        }
        localStorage.removeItem('auth_token');
        const prefix = process.env.NEXT_PUBLIC_BASE_PATH || '';
        window.location.href = `${prefix}/login`;
      }
    }
    return Promise.reject(error);
  }
);

export default apiClient;
