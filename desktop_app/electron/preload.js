/**
 * Preload — keep minimal; UI talks to backend via HTTP/WS on localhost.
 */
const { contextBridge } = require("electron");

contextBridge.exposeInMainWorld("multiVdfDesktop", {
  platform: process.platform,
  isDesktop: true,
});
