/** Lightweight prefs (web + Electron webview = localStorage). */

const KEY_TUTORIAL_DONE = "variofield_tutorial_done";
const KEY_DRIVE_PROFILE = "variofield_drive_profile_id";

export function isTutorialDone(): boolean {
  try {
    return localStorage?.getItem(KEY_TUTORIAL_DONE) === "1";
  } catch {
    return false;
  }
}

export function setTutorialDone(done: boolean): void {
  try {
    if (done) localStorage?.setItem(KEY_TUTORIAL_DONE, "1");
    else localStorage?.removeItem(KEY_TUTORIAL_DONE);
  } catch {
    /* ignore */
  }
}

export function getLastDriveProfileId(): string | null {
  try {
    return localStorage?.getItem(KEY_DRIVE_PROFILE) || null;
  } catch {
    return null;
  }
}

export function setLastDriveProfileId(id: string): void {
  try {
    if (id) localStorage?.setItem(KEY_DRIVE_PROFILE, id);
  } catch {
    /* ignore */
  }
}
