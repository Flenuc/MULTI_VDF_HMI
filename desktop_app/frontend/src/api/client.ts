/**
 * HTTP + WebSocket client for the local Python backend.
 */
import type {
  BackendEvent,
  BtDevice,
  ConnectRequest,
  PortInfo,
  StatusResponse,
  Telemetry,
} from "./types";
import type { ParameterList } from "../lib/params";

const DEFAULT_BASE = "http://127.0.0.1:8765";

export function apiBase(): string {
  const env =
    typeof process !== "undefined" && process.env?.EXPO_PUBLIC_API_URL
      ? String(process.env.EXPO_PUBLIC_API_URL)
      : "";
  if (env) return env.replace(/\/$/, "");

  if (typeof window !== "undefined" && window.location?.protocol?.startsWith("http")) {
    const { protocol, hostname, port } = window.location;
    if (port === "8081" || port === "19006" || port === "19000") {
      return DEFAULT_BASE;
    }
    return `${protocol}//${hostname}${port ? `:${port}` : ""}`.replace(/\/$/, "");
  }
  return DEFAULT_BASE;
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
    let detail: unknown = res.statusText;
    try {
      const body = await res.json();
      detail = body.detail ?? body;
    } catch {
      /* ignore */
    }
    throw new Error(
      typeof detail === "string" ? detail : JSON.stringify(detail)
    );
  }
  if (res.status === 204) return undefined as T;
  return (await res.json()) as T;
}

export type ProfilesStore = {
  wifi_profiles: {
    name: string;
    ssid: string;
    password: string;
    notes?: string;
  }[];
  mqtt_profiles: {
    name: string;
    host: string;
    port: number;
    username: string;
    password: string;
    topic_prefix: string;
    notes?: string;
  }[];
  last_mode: string;
  last_wifi: string;
  last_mqtt: string;
  last_serial_port: string;
  last_serial_baud: number;
  last_bt_address: string;
  last_bt_name: string;
};

export type ParamFileInfo = {
  filename: string;
  stem: string;
  name: string;
  count: number;
};

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

  profiles: () => json<ProfilesStore>("/profiles"),
  saveProfiles: (data: ProfilesStore) =>
    json<ProfilesStore>("/profiles", {
      method: "PUT",
      body: JSON.stringify(data),
    }),
  upsertMqtt: (p: ProfilesStore["mqtt_profiles"][0]) =>
    json<ProfilesStore>("/profiles/mqtt", {
      method: "POST",
      body: JSON.stringify(p),
    }),
  upsertWifi: (p: ProfilesStore["wifi_profiles"][0]) =>
    json<ProfilesStore>("/profiles/wifi", {
      method: "POST",
      body: JSON.stringify(p),
    }),
  patchLasts: (body: Partial<ProfilesStore>) =>
    json<ProfilesStore>("/profiles/lasts", {
      method: "PATCH",
      body: JSON.stringify(body),
    }),

  paramListFiles: () => json<{ files: ParamFileInfo[] }>("/param-lists"),
  getParamList: (filename: string) =>
    json<{ filename: string; list: ParameterList }>(
      `/param-lists/${encodeURIComponent(filename)}`
    ),
  putParamList: (filename: string, list: ParameterList) =>
    json<{ filename: string; list: ParameterList }>(
      `/param-lists/${encodeURIComponent(filename)}`,
      { method: "PUT", body: JSON.stringify(list) }
    ),
  deleteParamList: (filename: string) =>
    json<{ ok: boolean }>(`/param-lists/${encodeURIComponent(filename)}`, {
      method: "DELETE",
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
      /* ignore */
    }
  };
  return ws;
}
