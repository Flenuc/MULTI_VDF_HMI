/**
 * MULTI_VDF_HMI — Electron shell
 *
 * 1) Spawns embedded Python backend (packaged binary or dev uvicorn)
 * 2) Waits for GET /health
 * 3) Opens BrowserWindow → http://127.0.0.1:8765 (API + static UI)
 */
const { app, BrowserWindow, shell, dialog } = require("electron");
const { spawn } = require("child_process");
const http = require("http");
const path = require("path");
const fs = require("fs");

const HOST = process.env.MULTI_VDF_HOST || "127.0.0.1";
const PORT = parseInt(process.env.MULTI_VDF_PORT || "8765", 10);
const HEALTH_URL = `http://${HOST}:${PORT}/health`;

let mainWindow = null;
let backendProc = null;
let quitting = false;

function isPackaged() {
  return app.isPackaged;
}

function resourcesDir() {
  // Packaged: process.resourcesPath/…  Dev: electron/resources
  if (isPackaged()) return process.resourcesPath;
  return path.join(__dirname, "resources");
}

function backendExecutable() {
  const base = path.join(resourcesDir(), "backend");
  if (process.platform === "win32") {
    return path.join(base, "multi_vdf_backend.exe");
  }
  return path.join(base, "multi_vdf_backend");
}

function uiDir() {
  return path.join(resourcesDir(), "ui");
}

function desktopAppRoot() {
  // …/desktop_app/electron → …/desktop_app
  return path.join(__dirname, "..");
}

function startBackend() {
  const env = {
    ...process.env,
    MULTI_VDF_HOST: HOST,
    MULTI_VDF_PORT: String(PORT),
    MULTI_VDF_UI_DIR: uiDir(),
    PYTHONUNBUFFERED: "1",
  };

  const exe = backendExecutable();
  if (fs.existsSync(exe)) {
    console.log("[electron] starting packaged backend:", exe);
    backendProc = spawn(exe, [], {
      env,
      cwd: path.dirname(exe),
      stdio: ["ignore", "pipe", "pipe"],
      windowsHide: true,
    });
  } else {
    // Dev: run uvicorn from desktop_app venv / system python
    const root = desktopAppRoot();
    const venvPy =
      process.platform === "win32"
        ? path.join(root, ".venv", "Scripts", "python.exe")
        : path.join(root, ".venv", "bin", "python");
    const py = fs.existsSync(venvPy) ? venvPy : process.platform === "win32" ? "python" : "python3";
    console.log("[electron] starting dev backend with", py);
    backendProc = spawn(
      py,
      ["-m", "uvicorn", "backend.main:app", "--host", HOST, "--port", String(PORT)],
      {
        env: { ...env, PYTHONPATH: root },
        cwd: root,
        stdio: ["ignore", "pipe", "pipe"],
      }
    );
  }

  backendProc.stdout?.on("data", (d) => process.stdout.write(`[backend] ${d}`));
  backendProc.stderr?.on("data", (d) => process.stderr.write(`[backend] ${d}`));
  backendProc.on("exit", (code, signal) => {
    console.log(`[electron] backend exited code=${code} signal=${signal}`);
    backendProc = null;
    if (!quitting && mainWindow) {
      dialog.showErrorBox(
        "MULTI_VDF_HMI",
        "El backend Python se detuvo. Cierra la app e inténtalo de nuevo."
      );
    }
  });
}

function waitForHealth(timeoutMs = 45000) {
  const start = Date.now();
  return new Promise((resolve, reject) => {
    const tryOnce = () => {
      const req = http.get(HEALTH_URL, (res) => {
        let body = "";
        res.on("data", (c) => (body += c));
        res.on("end", () => {
          if (res.statusCode === 200) return resolve(body);
          retry();
        });
      });
      req.on("error", retry);
      req.setTimeout(1500, () => {
        req.destroy();
        retry();
      });
    };
    const retry = () => {
      if (Date.now() - start > timeoutMs) {
        return reject(new Error(`Backend no respondió en ${timeoutMs}ms (${HEALTH_URL})`));
      }
      setTimeout(tryOnce, 400);
    };
    tryOnce();
  });
}

function createWindow() {
  mainWindow = new BrowserWindow({
    width: 1100,
    height: 780,
    minWidth: 800,
    minHeight: 560,
    title: "MULTI_VDF_HMI",
    webPreferences: {
      preload: path.join(__dirname, "preload.js"),
      contextIsolation: true,
      nodeIntegration: false,
      sandbox: true,
    },
    show: false,
  });

  mainWindow.once("ready-to-show", () => mainWindow.show());
  mainWindow.loadURL(`http://${HOST}:${PORT}/`);

  mainWindow.webContents.setWindowOpenHandler(({ url }) => {
    shell.openExternal(url);
    return { action: "deny" };
  });

  mainWindow.on("closed", () => {
    mainWindow = null;
  });
}

function stopBackend() {
  if (!backendProc) return;
  try {
    if (process.platform === "win32") {
      spawn("taskkill", ["/pid", String(backendProc.pid), "/f", "/t"]);
    } else {
      backendProc.kill("SIGTERM");
      setTimeout(() => {
        try {
          backendProc?.kill("SIGKILL");
        } catch (_) {
          /* ignore */
        }
      }, 2000);
    }
  } catch (_) {
    /* ignore */
  }
  backendProc = null;
}

const gotLock = app.requestSingleInstanceLock();
if (!gotLock) {
  app.quit();
} else {
  app.on("second-instance", () => {
    if (mainWindow) {
      if (mainWindow.isMinimized()) mainWindow.restore();
      mainWindow.focus();
    }
  });

  app.whenReady().then(async () => {
    try {
      // Ensure UI dir exists for env (may be empty in pure-API dev)
      const ui = uiDir();
      if (!fs.existsSync(ui)) {
        fs.mkdirSync(ui, { recursive: true });
      }
      startBackend();
      await waitForHealth();
      createWindow();
    } catch (e) {
      console.error(e);
      dialog.showErrorBox("MULTI_VDF_HMI — error de arranque", String(e.message || e));
      stopBackend();
      app.quit();
    }
  });

  app.on("before-quit", () => {
    quitting = true;
    stopBackend();
  });

  app.on("window-all-closed", () => {
    quitting = true;
    stopBackend();
    app.quit();
  });
}
