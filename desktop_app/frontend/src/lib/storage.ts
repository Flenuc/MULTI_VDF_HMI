/**
 * Tiny key/value storage that works on Web/Electron and native RN.
 * - Web/Electron: localStorage
 * - Native (Android/iOS): in-memory Map (smoke APK; not persistent across restarts)
 *
 * For persistent native prefs later: @react-native-async-storage/async-storage.
 */

const memory = new Map<string, string>();

function hasLocalStorage(): boolean {
  try {
    return typeof globalThis !== "undefined" && "localStorage" in globalThis && !!globalThis.localStorage;
  } catch {
    return false;
  }
}

export function storageGet(key: string): string | null {
  try {
    if (hasLocalStorage()) return globalThis.localStorage.getItem(key);
  } catch {
    /* fall through */
  }
  return memory.has(key) ? memory.get(key)! : null;
}

export function storageSet(key: string, value: string): void {
  try {
    if (hasLocalStorage()) {
      globalThis.localStorage.setItem(key, value);
      return;
    }
  } catch {
    /* fall through */
  }
  memory.set(key, value);
}

export function storageRemove(key: string): void {
  try {
    if (hasLocalStorage()) {
      globalThis.localStorage.removeItem(key);
      return;
    }
  } catch {
    /* fall through */
  }
  memory.delete(key);
}
