/** WebSocket endpoint for the realtime monitor broadcast (1 Hz).
 *
 * Same-origin on purpose: the dev server (vite proxy "/ws") and the
 * production nginx (location /ws/) both proxy WebSocket traffic to the
 * backend, so the client must NOT hardcode the backend host/port — a
 * hardcoded ws://host:8000 breaks behind any reverse proxy or tunnel,
 * and ws:// is blocked as mixed content on https pages.
 */
const wsProtocol = window.location.protocol === "https:" ? "wss" : "ws";
export const MONITOR_WS_URL = `${wsProtocol}://${window.location.host}/ws/monitor`;
