/** Lightweight prefs — Web/Electron (localStorage) or native smoke (memory). */

import { storageGet, storageRemove, storageSet } from "./storage";

const KEY_TUTORIAL_DONE = "variofield_tutorial_done";
const KEY_DRIVE_PROFILE = "variofield_drive_profile_id";

export function isTutorialDone(): boolean {
  return storageGet(KEY_TUTORIAL_DONE) === "1";
}

export function setTutorialDone(done: boolean): void {
  if (done) storageSet(KEY_TUTORIAL_DONE, "1");
  else storageRemove(KEY_TUTORIAL_DONE);
}

export function getLastDriveProfileId(): string | null {
  return storageGet(KEY_DRIVE_PROFILE);
}

export function setLastDriveProfileId(id: string): void {
  if (id) storageSet(KEY_DRIVE_PROFILE, id);
}
