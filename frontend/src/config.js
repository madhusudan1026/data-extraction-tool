// API base URL — uses env var in production, falls back to localhost for dev
const API_HOST = import.meta.env.VITE_API_BASE_URL || 'http://localhost:8000';

export const API_V2 = `${API_HOST}/api/v2/extraction`;
export const API_V4 = `${API_HOST}/api/v4/extraction`;
export const API_V5 = `${API_HOST}/api/v5/extraction`;
export const API_VECTOR = `${API_HOST}/api/v4/vector`;
