/**
 * Production vs development UI flags.
 * Production build: hide API URL, WS badges, free CLI, simulado, etc.
 */
export function isProductionUi(): boolean {
  const env =
    typeof process !== "undefined" ? process.env?.EXPO_PUBLIC_ENV : undefined;
  if (env === "development" || env === "dev") return false;
  if (env === "production" || env === "prod") return true;
  // Default: production-facing UI (safe for operators)
  // Force dev chrome with EXPO_PUBLIC_ENV=development
  return true;
}

/** Advanced tools: CLI, simulado, raw logs, API URL */
export function showDevTools(): boolean {
  if (!isProductionUi()) return true;
  const flag =
    typeof process !== "undefined"
      ? process.env?.EXPO_PUBLIC_DEV_TOOLS
      : undefined;
  if (flag === "1" || flag === "true") return true;
  // Runtime unlock via localStorage (Diagnóstico)
  try {
    if (typeof localStorage !== "undefined") {
      return localStorage.getItem("variofield_dev_tools") === "1";
    }
  } catch {
    /* ignore */
  }
  return false;
}

export function setDevToolsUnlocked(on: boolean): void {
  try {
    if (typeof localStorage !== "undefined") {
      if (on) localStorage.setItem("variofield_dev_tools", "1");
      else localStorage.removeItem("variofield_dev_tools");
    }
  } catch {
    /* ignore */
  }
}
