/**
 * MULTI_VDF_HMI — Electron shell
 *
 * 1) Spawns embedded Python backend (packaged binary, embed CPython, or dev)
 * 2) Waits for GET /health
 * 3) Opens BrowserWindow → http://127.0.0.1:8765 (API + static UI)
 */
const { app, BrowserWindow, shell, dialog, ipcMain } = require("electron");
const { spawn } = require("child_process");
const http = require("http");
const path = require("path");
const fs = require("fs");
const fsp = fs.promises;

const HOST = process.env.MULTI_VDF_HOST || "127.0.0.1";
const PORT = parseInt(process.env.MULTI_VDF_PORT || "8765", 10);
const HEALTH_URL = `http://${HOST}:${PORT}/health`;

let mainWindow = null;
let backendProc = null;
let quitting = false;
let healthReady = false;
let backendLog = "";
let backendLogPath = "";

function isPackaged() {
  return app.isPackaged;
}

function logLine(msg) {
  const line = `[electron] ${msg}`;
  console.log(line);
  try {
    if (backendLogPath) {
      fs.appendFileSync(backendLogPath, line + "\n", "utf8");
    }
  } catch (_) {
    /* ignore */
  }
}

/**
 * Resolve resources/ robustly (packaged Electron win/linux, NSIS layout, dev).
 * Prefer a directory that actually contains backend bits.
 */
function resourcesDir() {
  const candidates = [];
  if (process.resourcesPath) candidates.push(process.resourcesPath);
  // Next to VarioField.exe / electron binary
  try {
    candidates.push(path.join(path.dirname(process.execPath), "resources"));
  } catch (_) {
    /* ignore */
  }
  // resources/app → parent is resources/
  candidates.push(path.join(__dirname, ".."));
  // Dev: electron/resources
  candidates.push(path.join(__dirname, "resources"));

  const looksGood = (dir) => {
    if (!dir || !fs.existsSync(dir)) return false;
    return (
      fs.existsSync(path.join(dir, "pyapp", "run_variofield.py")) ||
      fs.existsSync(path.join(dir, "ui", "index.html")) ||
      fs.existsSync(path.join(dir, "backend", "multi_vdf_backend.exe")) ||
      fs.existsSync(path.join(dir, "backend", "multi_vdf_backend")) ||
      fs.existsSync(path.join(dir, "python", "python.exe"))
    );
  };

  for (const c of candidates) {
    if (looksGood(c)) return c;
  }
  // Fallback
  if (isPackaged() && process.resourcesPath) return process.resourcesPath;
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
  return path.join(__dirname, "..");
}

function embeddedPythonPaths() {
  const res = resourcesDir();
  const pyDir = path.join(res, "python");
  const pyapp = path.join(res, "pyapp");
  const pyExe =
    process.platform === "win32"
      ? path.join(pyDir, "python.exe")
      : path.join(pyDir, "bin", "python3");
  const runScript = path.join(pyapp, "run_variofield.py");
  return { res, pyDir, pyExe, pyapp, runScript };
}

function initLogFile() {
  try {
    const dir = app.getPath("userData");
    fs.mkdirSync(dir, { recursive: true });
    backendLogPath = path.join(dir, "backend.log");
    fs.writeFileSync(
      backendLogPath,
      `=== VarioField backend log ${new Date().toISOString()} ===\n` +
        `execPath=${process.execPath}\n` +
        `resourcesPath=${process.resourcesPath}\n` +
        `resourcesDir=${resourcesDir()}\n` +
        `isPackaged=${isPackaged()}\n` +
        `__dirname=${__dirname}\n\n`,
      "utf8"
    );
  } catch (e) {
    backendLogPath = "";
    console.error("cannot create backend log", e);
  }
}

function appendBackendChunk(chunk) {
  const s = String(chunk);
  backendLog += s;
  if (backendLog.length > 80000) {
    backendLog = backendLog.slice(-60000);
  }
  process.stdout.write(`[backend] ${s}`);
  try {
    if (backendLogPath) fs.appendFileSync(backendLogPath, s, "utf8");
  } catch (_) {
    /* ignore */
  }
}

function attachBackendLogs(proc) {
  proc.stdout?.on("data", (d) => appendBackendChunk(d));
  proc.stderr?.on("data", (d) => appendBackendChunk(d));
  proc.on("error", (err) => {
    appendBackendChunk(`spawn error: ${err}\n`);
    logLine(`backend spawn error: ${err}`);
  });
  proc.on("exit", (code, signal) => {
    logLine(`backend exited code=${code} signal=${signal}`);
    backendProc = null;
    if (!quitting && mainWindow && healthReady) {
      dialog.showErrorBox(
        "VarioField",
        "El servicio de comunicación se detuvo. Cierra la app e inténtalo de nuevo." +
          (backendLogPath ? `\n\nLog: ${backendLogPath}` : "")
      );
    }
  });
}

function startBackend() {
  const res = resourcesDir();
  const ui = uiDir();
  const scriptsDir = path.join(res, "scripts");
  logLine(`startBackend resourcesDir=${res}`);
  logLine(`uiDir=${ui} exists=${fs.existsSync(ui)}`);
  logLine(`scriptsDir=${scriptsDir} exists=${fs.existsSync(scriptsDir)}`);

  const env = {
    ...process.env,
    MULTI_VDF_HOST: HOST,
    MULTI_VDF_PORT: String(PORT),
    MULTI_VDF_UI_DIR: ui,
    MULTI_VDF_RESOURCES: res,
    MULTI_VDF_SCRIPTS_DIR: fs.existsSync(scriptsDir) ? scriptsDir : "",
    PYTHONUNBUFFERED: "1",
    VARIOFIELD_EMBED: "1",
  };

  const spawnOptsBase = {
    stdio: ["ignore", "pipe", "pipe"],
    windowsHide: true,
  };

  // 1) PyInstaller one-file binary
  const exe = backendExecutable();
  logLine(`backend binary path=${exe} exists=${fs.existsSync(exe)}`);
  if (fs.existsSync(exe)) {
    logLine(`starting packaged backend binary`);
    backendProc = spawn(exe, [], {
      ...spawnOptsBase,
      env,
      cwd: path.dirname(exe),
    });
    attachBackendLogs(backendProc);
    return;
  }

  // 2) Embedded CPython + pyapp (Windows NSIS from Linux)
  const { pyDir, pyExe, pyapp, runScript } = embeddedPythonPaths();
  logLine(`embed pyExe=${pyExe} exists=${fs.existsSync(pyExe)}`);
  logLine(`embed runScript=${runScript} exists=${fs.existsSync(runScript)}`);
  if (fs.existsSync(pyExe) && fs.existsSync(runScript)) {
    const pathSep = process.platform === "win32" ? ";" : ":";
    const embedEnv = {
      ...env,
      // PYTHONPATH often ignored with python*._pth; still set for good measure
      PYTHONPATH: pyapp,
      // Help Windows load native .pyd deps (msvcp140, etc.)
      PATH: `${pyDir}${pathSep}${env.PATH || ""}`,
    };
    logLine(`starting embedded Python backend`);
    backendProc = spawn(pyExe, [runScript], {
      ...spawnOptsBase,
      env: embedEnv,
      cwd: pyapp,
    });
    attachBackendLogs(backendProc);
    return;
  }

  // 3) Dev only — never silent-fail to bare "python" when packaged layout was expected
  if (isPackaged()) {
    const detail =
      `No se encontró el backend empaquetado.\n\n` +
      `Buscado:\n- ${exe}\n- ${pyExe}\n- ${runScript}\n\n` +
      `resourcesDir=${res}\n` +
      (backendLogPath ? `Log: ${backendLogPath}\n` : "");
    throw new Error(detail);
  }

  const root = desktopAppRoot();
  const venvPy =
    process.platform === "win32"
      ? path.join(root, ".venv", "Scripts", "python.exe")
      : path.join(root, ".venv", "bin", "python");
  const py = fs.existsSync(venvPy)
    ? venvPy
    : process.platform === "win32"
      ? "python"
      : "python3";
  logLine(`starting dev backend with ${py}`);
  backendProc = spawn(
    py,
    ["-m", "uvicorn", "backend.main:app", "--host", HOST, "--port", String(PORT)],
    {
      ...spawnOptsBase,
      env: { ...env, PYTHONPATH: root },
      cwd: root,
    }
  );
  attachBackendLogs(backendProc);
}

function waitForHealth(timeoutMs = 60000) {
  const start = Date.now();
  return new Promise((resolve, reject) => {
    const fail = (reason) => {
      const tail = backendLog.trim().slice(-2500);
      const msg =
        `${reason}\n\n` +
        (backendLogPath ? `Log completo: ${backendLogPath}\n\n` : "") +
        (tail ? `--- salida backend ---\n${tail}` : "(sin salida del backend)");
      reject(new Error(msg));
    };

    const tryOnce = () => {
      // Fail fast if process already died
      if (!backendProc && !healthReady) {
        return fail(
          `El proceso del backend se cerró antes de responder (${HEALTH_URL}).`
        );
      }
      const req = http.get(HEALTH_URL, (res) => {
        let body = "";
        res.on("data", (c) => (body += c));
        res.on("end", () => {
          if (res.statusCode === 200) {
            healthReady = true;
            return resolve(body);
          }
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
        return fail(`Backend no respondió en ${timeoutMs}ms (${HEALTH_URL}).`);
      }
      // If process died mid-wait, fail with log instead of spinning
      if (!backendProc && !healthReady) {
        return fail(
          `El proceso del backend se cerró antes de responder (${HEALTH_URL}).`
        );
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
    title: "VarioField",
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

function registerIpc() {
  ipcMain.handle("dialog:openJson", async () => {
    const win = BrowserWindow.getFocusedWindow() || mainWindow;
    const res = await dialog.showOpenDialog(win || undefined, {
      title: "VarioField — Abrir receta JSON",
      filters: [
        { name: "JSON", extensions: ["json"] },
        { name: "Todos", extensions: ["*"] },
      ],
      properties: ["openFile"],
    });
    if (res.canceled || !res.filePaths?.[0]) return null;
    const filePath = res.filePaths[0];
    const text = await fsp.readFile(filePath, "utf8");
    return { path: filePath, text };
  });

  ipcMain.handle("dialog:saveJson", async (_evt, opts = {}) => {
    const win = BrowserWindow.getFocusedWindow() || mainWindow;
    const defaultPath = opts.defaultPath || "lista.json";
    const res = await dialog.showSaveDialog(win || undefined, {
      title: "VarioField — Guardar receta JSON",
      defaultPath: defaultPath.endsWith(".json")
        ? defaultPath
        : `${defaultPath}.json`,
      filters: [
        { name: "JSON", extensions: ["json"] },
        { name: "Todos", extensions: ["*"] },
      ],
    });
    if (res.canceled || !res.filePath) return null;
    let out = res.filePath;
    if (!out.toLowerCase().endsWith(".json")) out += ".json";
    await fsp.writeFile(out, String(opts.content ?? ""), "utf8");
    return { path: out };
  });
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
      initLogFile();
      registerIpc();
      const ui = uiDir();
      if (!fs.existsSync(ui)) {
        // Don't create empty ui that hides a packaging bug in production
        if (!isPackaged()) {
          fs.mkdirSync(ui, { recursive: true });
        }
      }
      startBackend();
      await waitForHealth();
      createWindow();
    } catch (e) {
      console.error(e);
      const msg = String(e.message || e);
      dialog.showErrorBox("VarioField — error de arranque", msg);
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
