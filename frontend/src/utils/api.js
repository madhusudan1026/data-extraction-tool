/**
 * Safe JSON parser for fetch responses.
 * Handles HTML error pages from Nginx (502, 504, etc.)
 */
export async function safeJson(res) {
  const text = await res.text();
  try {
    return JSON.parse(text);
  } catch {
    const status = res.status;
    if (status === 504) throw new Error('Request timed out (504). The operation may still be running — check backend logs.');
    if (status === 502) throw new Error('Backend not responding (502). Check if the backend container is running.');
    if (status === 503) throw new Error('Service unavailable (503). Backend is starting up or overloaded.');
    throw new Error(`Server error ${status}: ${text.slice(0, 200)}`);
  }
}
