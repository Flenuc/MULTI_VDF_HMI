/**
 * Preload — bridge for native JSON open/save + desktop flag.
 * UI still talks to the Python backend via HTTP/WS on localhost.
 */
const { contextBridge, ipcRenderer } = require("electron");

contextBridge.exposeInMainWorld("multiVdfDesktop", {
  isDesktop: true,
  platform: process.platform,
  openJsonFile: () => ipcRenderer.invoke("dialog:openJson"),
  saveJsonFile: (opts) => ipcRenderer.invoke("dialog:saveJson", opts),
});
