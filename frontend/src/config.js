// API base URL configuration
// - Docker/production: VITE_API_BASE_URL="" → uses relative URLs (proxied by Nginx)
// - Local dev: VITE_API_BASE_URL is undefined → falls back to http://localhost:8000
const envUrl = import.meta.env.VITE_API_BASE_URL;
const API_HOST = envUrl !== undefined ? envUrl : 'http://localhost:8000';

export const API_V2 = `${API_HOST}/api/v2/extraction`;
export const API_V4 = `${API_HOST}/api/v4/extraction`;
export const API_V5 = `${API_HOST}/api/v5/extraction`;
export const API_VECTOR = `${API_HOST}/api/v4/vector`;
