/**
 * HTTP + WebSocket client for the local Python backend.
 * Default base: http://127.0.0.1:8765 (desktop). Override with EXPO_PUBLIC_API_URL.
 */
import type {
  BackendEvent,
  BtDevice,
  ConnectRequest,
  PortInfo,
  StatusResponse,
  Telemetry,
} from "./types";

const DEFAULT_BASE = "http://127.0.0.1:8765";

export function apiBase(): string {
  // Expo public env (optional)
  const env =
    typeof process !== "undefined" && process.env?.EXPO_PUBLIC_API_URL
      ? process.env.EXPO_PUBLIC_API_URL
      : "";
  return (env || DEFAULT_BASE).replace(/\/$/, "");
}

export function wsUrl(): string {
  const base = apiBase();
  if (base.startsWith("https://")) return base.replace(/^https/, "wss") + "/ws/events";
  return base.replace(/^http/, "ws") + "/ws/events";
}

async function json<T>(path: string, init?: RequestInit): Promise<T> {
  const res = await fetch(`${apiBase()}${path}`, {
    ...init,
    headers: {
      Accept: "application/json",
      "Content-Type": "application/json",
      ...(init?.headers || {}),
    },
  });
  if (!res.ok) {
    let detail = res.statusText;
    try {
      const body = await res.json();
      detail = body.detail || JSON.stringify(body);
    } catch {
      /* ignore */
    }
    throw new Error(typeof detail === "string" ? detail : JSON.stringify(detail));
  }
  return (await res.json()) as T;
}

export const api = {
  health: () => json<{ ok: boolean; version: string }>("/health"),
  status: () => json<StatusResponse>("/status"),
  telemetry: () => json<{ telemetry: Telemetry }>("/telemetry"),
  ports: () => json<PortInfo[]>("/ports"),
  btClassic: (scanSeconds = 10) =>
    json<BtDevice[]>(`/bt/classic?scan_seconds=${scanSeconds}`),
  btBle: (scanSeconds = 6) =>
    json<BtDevice[]>(`/bt/ble?scan_seconds=${scanSeconds}`),
  connect: (body: ConnectRequest) =>
    json<{ ok: boolean; detail: string }>("/connect", {
      method: "POST",
      body: JSON.stringify(body),
    }),
  disconnect: () =>
    json<{ ok: boolean }>("/disconnect", { method: "POST", body: "{}" }),
  command: (line: string) =>
    json<{ ok: boolean }>("/command", {
      method: "POST",
      body: JSON.stringify({ line }),
    }),
};

export type EventHandler = (ev: BackendEvent) => void;

export function openEventSocket(
  onEvent: EventHandler,
  onStatus?: (s: "open" | "close" | "error") => void
): WebSocket {
  const ws = new WebSocket(wsUrl());
  ws.onopen = () => onStatus?.("open");
  ws.onclose = () => onStatus?.("close");
  ws.onerror = () => onStatus?.("error");
  ws.onmessage = (msg) => {
    try {
      const data = JSON.parse(String(msg.data)) as BackendEvent;
      onEvent(data);
    } catch {
      /* ignore malformed */
    }
  };
  return ws;
}
