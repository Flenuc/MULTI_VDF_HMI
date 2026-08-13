/** Lightweight prefs (web + Electron webview = localStorage). */

const KEY_TUTORIAL_DONE = "variofield_tutorial_done";

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
