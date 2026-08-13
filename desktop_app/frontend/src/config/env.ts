/**
 * Production vs development UI flags + role-based tools (Fase 5).
 */
import { isTechnician, setRole, type AppRole } from "../lib/roles";

export function isProductionUi(): boolean {
  const env =
    typeof process !== "undefined" ? process.env?.EXPO_PUBLIC_ENV : undefined;
  if (env === "development" || env === "dev") return false;
  if (env === "production" || env === "prod") return true;
  // Default: production-facing UI (safe for operators)
  return true;
}

/** Advanced tools: CLI, simulado, raw logs, API URL — technician role */
export function showDevTools(): boolean {
  if (!isProductionUi()) return true;
  return isTechnician();
}

export function setDevToolsUnlocked(on: boolean): void {
  setRole(on ? "tecnico" : "operario");
}

export function currentRole(): AppRole {
  return isTechnician() ? "tecnico" : "operario";
}
