export type Transport = "serial" | "mqtt" | "bluetooth" | "ble" | "dummy";

export type ConnectRequest = {
  transport: Transport;
  port?: string;
  baud?: number;
  host?: string;
  mqtt_port?: number;
  username?: string;
  password?: string;
  topic_prefix?: string;
  address?: string;
  channel?: number;
  pair?: boolean;
};

export type StatusResponse = {
  state: string;
  message: string;
  transport?: string | null;
  connected: boolean;
};

export type PortInfo = {
  device: string;
  description: string;
  hwid: string;
};

export type BtDevice = {
  address: string;
  name: string;
  paired: boolean;
  trusted: boolean;
  has_nus?: boolean;
  rssi?: number | null;
  source?: string;
};

export type BackendEvent = {
  type: string;
  payload: unknown;
  meta?: Record<string, unknown>;
};

export type Telemetry = {
  freq?: number;
  amp?: number;
  vdc?: number;
  vout?: number;
  pset?: number;
  pfb?: number;
  status?: string;
  [key: string]: unknown;
};
