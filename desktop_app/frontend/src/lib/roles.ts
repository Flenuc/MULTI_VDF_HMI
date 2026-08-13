/**
 * VarioField roles — Fase 5
 *
 * - operario (default): camino feliz, perfiles Wi‑Fi/MQTT editables, sin CLI/simulado
 * - tecnico: CLI, simulado, log crudo, URL API, baud, topic_prefix
 *
 * Unlock: PIN (default 2580) or EXPO_PUBLIC_DEV_TOOLS=1
 * Product decision: operator MAY edit plant profiles with clear instructions.
 */

export type AppRole = "operario" | "tecnico";

const KEY_ROLE = "variofield_role";
const KEY_PIN = "variofield_tech_pin";
const KEY_LEGACY_DEV = "variofield_dev_tools";

/** Default technician PIN (changeable in modo técnico). */
export const DEFAULT_TECH_PIN = "2580";

export function getRole(): AppRole {
  try {
    const r = localStorage?.getItem(KEY_ROLE);
    if (r === "tecnico" || r === "operario") return r;
    // Migrate legacy unlock flag
    if (localStorage?.getItem(KEY_LEGACY_DEV) === "1") return "tecnico";
  } catch {
    /* ignore */
  }
  // Build-time force
  try {
    const flag =
      typeof process !== "undefined" ? process.env?.EXPO_PUBLIC_DEV_TOOLS : undefined;
    if (flag === "1" || flag === "true") return "tecnico";
    const env =
      typeof process !== "undefined" ? process.env?.EXPO_PUBLIC_ENV : undefined;
    if (env === "development" || env === "dev") return "tecnico";
  } catch {
    /* ignore */
  }
  return "operario";
}

export function setRole(role: AppRole): void {
  try {
    localStorage?.setItem(KEY_ROLE, role);
    // Keep legacy key in sync for older code paths
    if (role === "tecnico") localStorage?.setItem(KEY_LEGACY_DEV, "1");
    else localStorage?.removeItem(KEY_LEGACY_DEV);
  } catch {
    /* ignore */
  }
}

export function isTechnician(): boolean {
  return getRole() === "tecnico";
}

export function isOperator(): boolean {
  return getRole() === "operario";
}

export function getTechPin(): string {
  try {
    const p = localStorage?.getItem(KEY_PIN);
    if (p && p.length >= 4) return p;
  } catch {
    /* ignore */
  }
  return DEFAULT_TECH_PIN;
}

export function setTechPin(pin: string): void {
  const clean = String(pin || "").trim();
  if (clean.length < 4) throw new Error("El PIN debe tener al menos 4 dígitos");
  try {
    localStorage?.setItem(KEY_PIN, clean);
  } catch {
    /* ignore */
  }
}

export function verifyTechPin(input: string): boolean {
  return String(input || "").trim() === getTechPin();
}

/** Unlock technician mode if PIN matches. */
export function unlockTechnician(pin: string): boolean {
  if (!verifyTechPin(pin)) return false;
  setRole("tecnico");
  return true;
}

export function lockToOperator(): void {
  setRole("operario");
}

export function roleLabel(role?: AppRole): string {
  const r = role ?? getRole();
  return r === "tecnico" ? "Técnico" : "Operario";
}
