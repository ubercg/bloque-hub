/**
 * Centralized API client with JWT authentication (infra).
 */

import axios from 'axios';

const apiClient = axios.create({
  baseURL: process.env.NEXT_PUBLIC_API_URL || 'http://localhost/api',
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
        window.location.href = '/login';
      }
    }
    return Promise.reject(error);
  }
);

export default apiClient;
