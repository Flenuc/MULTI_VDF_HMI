/**
 * VarioField — UI de producción (operarios de campo)
 * Backend local Python: USB / red / Bluetooth → variador
 */
import { StatusBar } from "expo-status-bar";
import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import {
  ActivityIndicator,
  Alert,
  Image,
  Modal,
  Platform,
  Pressable,
  SafeAreaView,
  ScrollView,
  StyleSheet,
  Switch,
  Text,
  TextInput,
  View,
} from "react-native";

import {
  api,
  apiBase,
  openEventSocket,
  type ParamFileInfo,
  type ProfilesStore,
} from "./src/api/client";
import type { BtDevice, PortInfo, Telemetry, Transport } from "./src/api/types";
import { ErrorBanner } from "./src/components/ErrorBanner";
import { BRAND } from "./src/config/brand";
import { isProductionUi, setDevToolsUnlocked, showDevTools } from "./src/config/env";
import { t } from "./src/i18n/es";
import {
  classifyError,
  classifyFromLine,
  type AppError,
  type RetryAction,
} from "./src/lib/errors";
import {
  exportParamListJson,
  importParamListJson,
  isDesktopShell,
} from "./src/lib/jsonFile";
import {
  applyCompare,
  clearCompare,
  emptyList,
  paramId,
  parseDumpCsvLine,
  removeParam,
  type Parameter,
  type ParameterList,
  upsertParam,
  validateParam,
  writable,
} from "./src/lib/params";
import { isTutorialDone, setTutorialDone } from "./src/lib/prefs";
import { colors, font, radius, space, touchMin } from "./src/theme";

type Tab = "home" | "connect" | "params" | "more";
type Mode = "mqtt" | "serial" | "bluetooth" | "ble" | "dummy";

const MODE_DEFS: {
  id: Mode;
  label: string;
  transport: Transport;
  prod: boolean;
}[] = [
  { id: "mqtt", label: t.modeMqtt, transport: "mqtt", prod: true },
  { id: "serial", label: t.modeUsb, transport: "serial", prod: true },
  { id: "ble", label: t.modeBle, transport: "ble", prod: true },
  { id: "bluetooth", label: t.modeBt, transport: "bluetooth", prod: true },
  { id: "dummy", label: t.modeDummy, transport: "dummy", prod: false },
];

function userLogLine(raw: string): string | null {
  const s = raw.trim();
  if (!s) return null;
  if (s.startsWith("CSV:")) return null; // dump noise
  if (s === "WS backend OK" || s.startsWith("WS:")) return null;
  if (s.startsWith("OK connected via")) {
    return "Equipo conectado.";
  }
  if (s.startsWith("→ stream on") || s === "stream on") return "Lectura en vivo activada.";
  if (s.startsWith("→ stream off")) return "Lectura en vivo en pausa.";
  if (s.startsWith("→ dump")) return "Leyendo parámetros del variador…";
  if (s.includes("Link OK")) return "El variador responde correctamente.";
  if (s.includes("PING FAIL") || s.includes("Timeout")) {
    return "El módulo responde, pero el variador no contesta (revisa el bus RS485).";
  }
  if (s.startsWith("ERR:")) return `Atención: ${s.replace(/^ERR:\s*/, "")}`;
  if (s.startsWith("→ w")) return `Enviando ${s.slice(2).trim()}…`;
  if (s.startsWith("→ ")) return s.slice(2);
  if (s.startsWith("Import JSON") || s.startsWith("Export JSON") || s.startsWith("Guardado")) {
    return s;
  }
  // Hide pure CLI dumps in production unless dev tools
  if (showDevTools()) return s;
  if (s.startsWith("help |") || s.startsWith("board=") || s.startsWith("mqtt enabled")) {
    return s.length > 120 ? s.slice(0, 117) + "…" : s;
  }
  if (s.startsWith("status=") || s.startsWith("freq=") || s.startsWith("P0-") || s.startsWith("P1-")) {
    return s;
  }
  if (s.startsWith("DUMP") || s.startsWith("stream ON") || s.startsWith("stream OFF")) {
    return s.includes("ON")
      ? "Lectura en vivo activada."
      : s.includes("OFF")
        ? "Lectura en vivo en pausa."
        : s;
  }
  return s.length > 160 ? s.slice(0, 157) + "…" : s;
}

export default function App() {
  const dev = showDevTools();
  const [devTick, setDevTick] = useState(0); // re-render when unlocking dev tools
  const [tab, setTab] = useState<Tab>("home");
  const [backendOk, setBackendOk] = useState<boolean | null>(null);
  const [wsState, setWsState] = useState<"open" | "close" | "error" | "idle">("idle");
  const [connected, setConnected] = useState(false);
  const [statusMsg, setStatusMsg] = useState<string>(t.statusOffline);
  const [mode, setMode] = useState<Mode>("mqtt");
  const [hasCompared, setHasCompared] = useState(false);
  const [hasSynced, setHasSynced] = useState(false);
  const [ports, setPorts] = useState<PortInfo[]>([]);
  const [port, setPort] = useState("");
  const [baud, setBaud] = useState("115200");
  const [btDevices, setBtDevices] = useState<BtDevice[]>([]);
  const [btAddress, setBtAddress] = useState("");
  const [scanning, setScanning] = useState(false);
  const [busy, setBusy] = useState(false);
  const [opName, setOpName] = useState("");
  const [progress, setProgress] = useState(0);
  const [telemetry, setTelemetry] = useState<Telemetry>({});
  const [log, setLog] = useState<string[]>([]);
  const [cmd, setCmd] = useState("");
  const [showAdvancedCmd, setShowAdvancedCmd] = useState(false);

  const [profiles, setProfiles] = useState<ProfilesStore | null>(null);
  const [mqttName, setMqttName] = useState("");
  const [wifiName, setWifiName] = useState("");

  const [plist, setPlist] = useState<ParameterList>(emptyList());
  const [listFile, setListFile] = useState("ejemplo_pdm30.json");
  const [listFiles, setListFiles] = useState<ParamFileInfo[]>([]);
  const [selectedKey, setSelectedKey] = useState<string | null>(null);
  const [edGroup, setEdGroup] = useState<"P0" | "P1">("P0");
  const [edIdx, setEdIdx] = useState("0");
  const [edVal, setEdVal] = useState("0");
  const [edNotes, setEdNotes] = useState("");
  const [edManual, setEdManual] = useState(false);
  const [recipeSearch, setRecipeSearch] = useState("");
  const [recipeFilter, setRecipeFilter] = useState<
    "all" | "diff" | "manual" | "ok"
  >("all");

  const [showProfiles, setShowProfiles] = useState(false);
  const [showTutorial, setShowTutorial] = useState(false);
  const [tutorialStep, setTutorialStep] = useState(0);
  const [showAbout, setShowAbout] = useState(false);
  const [moreSection, setMoreSection] = useState<"network" | "help">("help");
  const [appError, setAppError] = useState<AppError | null>(null);
  const [mForm, setMForm] = useState({
    name: "Local",
    host: "127.0.0.1",
    port: "1883",
    topic_prefix: "saj/pdm30/saj-pdm30",
    username: "",
    password: "",
  });
  const [wForm, setWForm] = useState({ name: "planta", ssid: "", password: "" });

  const dumpActive = useRef(false);
  const dumpMap = useRef<Record<string, number>>({});
  const dumpCount = useRef(0);
  const logRef = useRef<ScrollView>(null);
  const plistRef = useRef(plist);
  useEffect(() => {
    plistRef.current = plist;
  }, [plist]);

  const pushLog = useCallback((line: string) => {
    const pretty = userLogLine(line);
    if (pretty == null) return;
    setLog((prev) => {
      const next = [...prev, pretty];
      return next.length > 200 ? next.slice(-200) : next;
    });
  }, []);

  const reportError = useCallback(
    (
      err: unknown,
      context?:
        | "connect"
        | "usb"
        | "mqtt"
        | "bt"
        | "bt_scan"
        | "sync"
        | "compare"
        | "ping"
        | "save"
        | "load"
        | "import"
        | "export"
        | "wifi"
        | "profiles"
    ) => {
      const appErr = classifyError(err, context ? { context } : undefined);
      setAppError(appErr);
      pushLog(`${appErr.title}: ${appErr.message.split("\n")[0]}`);
      return appErr;
    },
    [pushLog]
  );

  const handleRetry = useCallback(() => {
    const action: RetryAction | undefined = appError?.retry;
    setAppError(null);
    if (!action || action === "none") return;
    switch (action) {
      case "go_connect":
        setTab("connect");
        break;
      case "go_recipes":
        setTab("params");
        break;
      case "open_profiles":
        setMoreSection("network");
        setTab("more");
        setShowProfiles(true);
        break;
      case "refresh_ports":
        setTab("connect");
        setMode("serial");
        void refreshPortsRef.current?.();
        break;
      case "scan_bt":
        setTab("connect");
        void scanBtRef.current?.();
        break;
      case "reconnect":
        setTab("connect");
        void doConnectRef.current?.();
        break;
      case "retry_compare":
        void compareVfdRef.current?.();
        break;
      case "retry_sync":
        void runSyncRef.current?.();
        break;
      case "retry_ping":
        void sendCmdRef.current?.("ping");
        break;
      default:
        break;
    }
  }, [appError]);

  const refreshPortsRef = useRef<(() => Promise<void>) | null>(null);
  const scanBtRef = useRef<(() => Promise<void>) | null>(null);
  const doConnectRef = useRef<(() => Promise<void>) | null>(null);
  const compareVfdRef = useRef<(() => Promise<void>) | null>(null);
  const runSyncRef = useRef<(() => Promise<void>) | null>(null);
  const sendCmdRef = useRef<((line?: string) => Promise<void>) | null>(null);

  const endOp = useCallback((msg?: string) => {
    setBusy(false);
    setOpName("");
    setProgress(0);
    dumpActive.current = false;
    if (msg) setStatusMsg(msg);
  }, []);

  const beginOp = useCallback(
    (name: string) => {
      if (busy) {
        Alert.alert("Ocupado", `Hay una operación en curso: ${opName}`);
        return false;
      }
      setBusy(true);
      setOpName(name);
      setProgress(0.05);
      setStatusMsg(`Trabajando: ${name}…`);
      return true;
    },
    [busy, opName]
  );

  useEffect(() => {
    let cancelled = false;
    (async () => {
      try {
        await api.health();
        if (!cancelled) setBackendOk(true);
        const pr = await api.profiles();
        if (!cancelled) {
          setProfiles(pr);
          if (pr.last_mqtt) setMqttName(pr.last_mqtt);
          if (pr.last_wifi) setWifiName(pr.last_wifi);
          if (pr.last_serial_port) setPort(pr.last_serial_port);
          if (pr.last_bt_address) setBtAddress(pr.last_bt_address);
          const m = (pr.last_mode || "").toLowerCase();
          if (m.includes("usb") || m.includes("serial") || m.includes("cable"))
            setMode("serial");
          else if (m.includes("ble") || m.includes("nus") || m.includes("pantalla"))
            setMode("ble");
          else if (m.includes("spp") || m.includes("bluetooth")) setMode("bluetooth");
          else if (m.includes("simul") || m.includes("dummy") || m.includes("prueba"))
            setMode(showDevTools() ? "dummy" : "mqtt");
          else setMode("mqtt");
        }
        const files = await api.paramListFiles();
        if (!cancelled) {
          setListFiles(files.files);
          const pref =
            files.files.find((f) => f.filename === "ejemplo_pdm30.json") ||
            files.files[0];
          if (pref) {
            setListFile(pref.filename);
            const loaded = await api.getParamList(pref.filename);
            setPlist(loaded.list);
          }
        }
      } catch {
        if (!cancelled) {
          setBackendOk(false);
          setStatusMsg(t.statusServiceError);
          setAppError(classifyError(new Error("failed to fetch")));
        }
      }
      if (!cancelled && !isTutorialDone()) {
        setShowTutorial(true);
        setTutorialStep(0);
      }
    })();

    const ws = openEventSocket(
      (ev) => {
        if (ev.type === "line" && typeof ev.payload === "string") {
          const line = ev.payload;
          pushLog(line);
          const lineErr = classifyFromLine(line);
          if (lineErr && lineErr.code === "DRIVE_NO_LINK") {
            setAppError(lineErr);
          } else if (lineErr && lineErr.code === "DRIVE_OK") {
            setAppError(null);
          }
          if (dumpActive.current) {
            if (line.startsWith("ERR:")) {
              dumpActive.current = false;
              endOp("No se pudo leer el variador.");
              setAppError(
                classifyError(line, { context: "compare" })
              );
              return;
            }
            const parsed = parseDumpCsvLine(line);
            if (parsed && parsed.eng != null) {
              dumpMap.current[`${parsed.group}:${parsed.index}`] = parsed.eng;
              dumpCount.current += 1;
              setProgress(Math.min(0.95, 0.1 + dumpCount.current / 100));
              setOpName(`Leyendo ${dumpCount.current}…`);
            }
            if (line.includes("DUMP done") || line.startsWith("CSV:END")) {
              dumpActive.current = false;
              const { list, mismatches } = applyCompare(
                plistRef.current,
                dumpMap.current
              );
              setPlist(list);
              setProgress(1);
              setHasCompared(true);
              endOp(
                mismatches === 0
                  ? "Receta y variador coinciden."
                  : `${mismatches} diferencia(s) respecto al variador.`
              );
              Alert.alert(
                "Comparación terminada",
                mismatches === 0
                  ? "Todo coincide con la receta."
                  : `Hay ${mismatches} diferencia(s) o valores sin lectura.\n` +
                      `Leídos del variador: ${Object.keys(dumpMap.current).length}.\n` +
                      "Las filas en rojo marcan problemas."
              );
            }
          }
        } else if (ev.type === "json" && ev.payload && typeof ev.payload === "object") {
          setTelemetry(ev.payload as Telemetry);
        } else if (ev.type === "status") {
          const st = String(ev.payload || "");
          const msg = String((ev.meta && ev.meta.message) || "");
          setConnected(st === "connected");
          if (st === "connected") setStatusMsg(msg || t.statusOnline);
          else if (msg) setStatusMsg(msg);
          else setStatusMsg(t.statusOffline);
          if (st !== "connected" && busy) endOp("Se perdió la conexión con el equipo.");
        } else if (ev.type === "error") {
          pushLog(`ERR: ${String(ev.payload)}`);
          if (busy) endOp("Error de comunicación.");
        }
      },
      (s) => {
        setWsState(s);
        if (s === "error" || s === "close") {
          if (isProductionUi() && !showDevTools()) {
            /* soft: backend badge handles it */
          }
        }
      }
    );
    return () => {
      cancelled = true;
      ws.close();
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [devTick]);

  const refreshPorts = useCallback(async () => {
    try {
      const list = await api.ports();
      setPorts(list);
      if (list.length === 1) setPort(list[0].device);
      else if (list.length && !port) setPort(list[0].device);
      else if (!list.length) {
        setAppError(classifyError(new Error("no cable"), { context: "usb" }));
      } else {
        setAppError(null);
      }
    } catch (e) {
      reportError(e, "usb");
    }
  }, [port, reportError]);
  refreshPortsRef.current = refreshPorts;

  useEffect(() => {
    if (mode === "serial") refreshPorts();
  }, [mode, refreshPorts]);

  const modesVisible = useMemo(
    () => MODE_DEFS.filter((m) => m.prod || dev),
    [dev]
  );

  const linkLabel = useMemo(() => {
    if (backendOk === false) return t.statusServiceError;
    if (wsState === "error") return t.statusLinkError;
    if (connected) return t.statusOnline;
    return t.statusOffline;
  }, [backendOk, wsState, connected]);

  const scanBt = async () => {
    setScanning(true);
    pushLog(
      mode === "ble"
        ? "Buscando equipos Bluetooth LE…"
        : "Buscando Bluetooth Classic (SPP)… En Windows deben estar emparejados en el sistema."
    );
    try {
      const devs = mode === "ble" ? await api.btBle(8) : await api.btClassic(10);
      setBtDevices(devs);
      if (devs.length) {
        const saj =
          devs.find((d) => /SAJ|PDM|VARIO|EDGE/i.test(d.name || "")) ||
          devs.find((d) => d.paired) ||
          devs[0];
        setBtAddress(saj.address);
        pushLog(
          `Encontrados ${devs.length} equipo(s). Preferido: ${saj.name || "?"} (${saj.address})`
        );
        setAppError(null);
      } else {
        setAppError(
          classifyError(
            new Error(
              mode === "bluetooth"
                ? "ningún dispositivo Classic: emparejá SAJ-PDM30-Edge en Configuración → Bluetooth y volvé a buscar"
                : "ningún dispositivo"
            ),
            { context: "bt" }
          )
        );
      }
    } catch (e) {
      reportError(e, "bt_scan");
    } finally {
      setScanning(false);
    }
  };
  scanBtRef.current = scanBt;

  const doConnect = async () => {
    setBusy(true);
    setOpName("Conectar");
    setAppError(null);
    try {
      const m = MODE_DEFS.find((x) => x.id === mode)!;
      let body: Parameters<typeof api.connect>[0];
      let ctx: "usb" | "mqtt" | "bt" | "connect" = "connect";
      if (mode === "serial") {
        ctx = "usb";
        if (!port || port === "—") {
          throw new Error("No hay cable detectado");
        }
        body = {
          transport: "serial",
          port,
          baud: parseInt(baud, 10) || 115200,
        };
        await api.patchLasts({
          last_mode: "USB (Serial)",
          last_serial_port: body.port,
          last_serial_baud: body.baud,
        });
      } else if (mode === "mqtt") {
        ctx = "mqtt";
        const pr = profiles || (await api.profiles());
        const mp =
          pr.mqtt_profiles.find((p) => p.name === mqttName) || pr.mqtt_profiles[0];
        if (!mp?.host) {
          throw new Error("Falta perfil de red");
        }
        body = {
          transport: "mqtt",
          host: mp.host,
          mqtt_port: mp.port,
          username: mp.username,
          password: mp.password,
          topic_prefix: mp.topic_prefix,
        };
        await api.patchLasts({ last_mode: "MQTT", last_mqtt: mp.name });
      } else if (mode === "bluetooth" || mode === "ble") {
        ctx = "bt";
        if (!btAddress) {
          throw new Error("Selecciona un dispositivo");
        }
        body = { transport: m.transport, address: btAddress, pair: true };
        await api.patchLasts({
          last_mode: mode === "ble" ? "Bluetooth LE (NUS)" : "Bluetooth (SPP)",
          last_bt_address: btAddress,
        });
      } else {
        body = { transport: "dummy" };
        await api.patchLasts({ last_mode: "Simulado (Dummy)" });
      }
      await api.connect(body);
      pushLog("OK connected via ok");
      setConnected(true);
      setStatusMsg(t.statusOnline);
      setAppError(null);
      const delay =
        mode === "serial" ? 2500 : mode === "bluetooth" || mode === "ble" ? 1500 : 800;
      setTimeout(async () => {
        try {
          await api.command("stream on");
          pushLog("→ stream on");
        } catch (e) {
          pushLog(`No se pudo activar la lectura en vivo: ${e}`);
        }
      }, delay);
    } catch (e) {
      const ctx =
        mode === "serial"
          ? "usb"
          : mode === "mqtt"
            ? "mqtt"
            : mode === "bluetooth" || mode === "ble"
              ? "bt"
              : "connect";
      reportError(e, ctx);
      setConnected(false);
    } finally {
      setBusy(false);
      setOpName("");
    }
  };
  doConnectRef.current = doConnect;

  const doDisconnect = async () => {
    try {
      try {
        await api.command("stream off");
      } catch {
        /* ignore */
      }
      await api.disconnect();
      setConnected(false);
      setStatusMsg(t.statusOffline);
      pushLog("Desconectado del equipo.");
    } catch (e) {
      pushLog(String(e));
    }
  };

  const sendCmd = async (line?: string) => {
    const text = (line ?? cmd).trim();
    if (!text) return;
    if (!connected) {
      setAppError(classifyError(new Error("sin conexión")));
      return;
    }
    pushLog(`→ ${text}`);
    try {
      await api.command(text);
      if (!line) setCmd("");
    } catch (e) {
      reportError(e, text === "ping" ? "ping" : "connect");
    }
  };
  sendCmdRef.current = sendCmd;

  const loadList = async (filename: string) => {
    try {
      const r = await api.getParamList(filename);
      setListFile(r.filename);
      setPlist(r.list);
      setSelectedKey(null);
      setStatusMsg(`Receta cargada: ${r.list.name || r.filename}`);
      setAppError(null);
    } catch (e) {
      reportError(e, "load");
    }
  };

  const saveList = async () => {
    try {
      const name = listFile || `${plist.name || "lista"}.json`;
      const r = await api.putParamList(name, plist);
      setListFile(r.filename);
      setPlist(r.list);
      setListFiles((await api.paramListFiles()).files);
      setStatusMsg(`Receta guardada en el PC: ${r.filename}`);
      pushLog(`Guardado ${r.filename}`);
      setAppError(null);
    } catch (e) {
      reportError(e, "save");
    }
  };

  const importJson = async () => {
    try {
      const r = await importParamListJson();
      if (!r) return;
      setPlist(r.list);
      setListFile(r.filename.endsWith(".json") ? r.filename : `${r.filename}.json`);
      setSelectedKey(null);
      setStatusMsg(`Archivo abierto: ${r.filename}`);
      pushLog(`Import JSON: ${r.filename} — ${r.list.parameters.length} parámetros`);
      setAppError(null);
    } catch (e) {
      reportError(e, "import");
    }
  };

  const exportJson = async (alsoServer = false) => {
    try {
      const defaultName =
        listFile || `${(plist.name || "lista").replace(/\s+/g, "_")}.json`;
      const r = await exportParamListJson(plist, defaultName);
      if (!r) return;
      if (r.path) {
        const base = r.path.split(/[/\\]/).pop() || defaultName;
        setListFile(base);
        setStatusMsg(`Guardado en: ${r.path}`);
        pushLog(`Export JSON → ${r.path}`);
      } else if (r.downloaded) {
        setStatusMsg(`Descarga iniciada: ${defaultName}`);
        pushLog(`Export JSON (descarga) ${defaultName}`);
      }
      if (alsoServer) {
        const name =
          (r.path && r.path.split(/[/\\]/).pop()) || listFile || defaultName;
        await api.putParamList(name, plist);
        setListFiles((await api.paramListFiles()).files);
        setListFile(name);
      }
      setAppError(null);
    } catch (e) {
      reportError(e, "export");
    }
  };

  const addParam = () => {
    try {
      const p: Parameter = {
        group: edGroup === "P0" ? 0 : 1,
        index: parseInt(edIdx, 10),
        value: parseFloat(edVal.replace(",", ".")),
        notes: edNotes,
        manual_only: edManual,
      };
      validateParam(p);
      setPlist((pl) => upsertParam(pl, p));
      setStatusMsg(`Parámetro ${paramId(p)} actualizado`);
    } catch (e) {
      Alert.alert("Dato no válido", String(e));
    }
  };

  const delParam = () => {
    if (!selectedKey) return;
    const [g, i] = selectedKey.split(":").map(Number);
    setPlist((pl) =>
      removeParam(pl, {
        group: g,
        index: i,
        value: 0,
        notes: "",
        manual_only: false,
      })
    );
    setSelectedKey(null);
  };

  const selectParam = (p: Parameter) => {
    setSelectedKey(`${p.group}:${p.index}`);
    setEdGroup(p.group === 0 ? "P0" : "P1");
    setEdIdx(String(p.index));
    setEdVal(String(p.value));
    setEdNotes(p.notes || "");
    setEdManual(!!p.manual_only);
  };

  const runSync = async () => {
    if (!connected) {
      setAppError(classifyError(new Error("sin conexión")));
      return;
    }
    const items = writable(plist);
    if (!items.length) {
      setAppError(classifyError(new Error("nada enviable"), { context: "sync" }));
      return;
    }
    if (!beginOp("Enviar receta")) return;
    setAppError(null);
    try {
      const total = items.length;
      for (let i = 0; i < total; i++) {
        const p = items[i];
        const c = `w${p.group} ${p.index} ${Number(p.value)}`;
        await api.command(c);
        pushLog(`→ ${c}`);
        setProgress((i + 1) / total);
        setStatusMsg(`Enviando ${i + 1} de ${total}…`);
        await sleep(150);
      }
      setHasSynced(true);
      endOp("Receta enviada al variador.");
      Alert.alert("Listo", "Los parámetros se enviaron al variador.");
    } catch (e) {
      endOp("El envío se interrumpió.");
      reportError(e, "sync");
    }
  };
  runSyncRef.current = runSync;

  /** Sync allowed without compare — soft recommendation dialog */
  const syncVfd = () => {
    if (!connected) {
      setAppError(classifyError(new Error("sin conexión")));
      return;
    }
    const items = writable(plist);
    if (!items.length) {
      setAppError(classifyError(new Error("nada enviable"), { context: "sync" }));
      return;
    }
    const skipped = plist.parameters.length - items.length;
    Alert.alert(t.syncTitle, t.syncBody(items.length, skipped), [
      { text: t.syncCancel, style: "cancel" },
      {
        text: t.syncRecommendCompare,
        onPress: () => {
          compareVfd();
        },
      },
      {
        text: t.syncSendAnyway,
        onPress: () => {
          runSync();
        },
      },
    ]);
  };

  const compareVfd = async () => {
    if (!connected) {
      setAppError(classifyError(new Error("sin conexión")));
      return;
    }
    if (!plist.parameters.length) {
      setAppError(classifyError(new Error("receta vacía")));
      return;
    }
    if (!beginOp("Comparar")) return;
    dumpActive.current = true;
    dumpMap.current = {};
    dumpCount.current = 0;
    setPlist((pl) => clearCompare(pl));
    setAppError(null);
    try {
      await api.command("stream off");
      pushLog("→ stream off");
      await api.command("dump");
      pushLog("→ dump");
      setStatusMsg("Leyendo el variador para comparar…");
      setTimeout(() => {
        if (dumpActive.current) {
          dumpActive.current = false;
          const { list, mismatches } = applyCompare(
            plistRef.current,
            dumpMap.current
          );
          setPlist(list);
          setHasCompared(true);
          endOp(
            `Comparación incompleta: ${mismatches} diferencia(s), ${Object.keys(dumpMap.current).length} leídos.`
          );
          setAppError(classifyError(new Error("timeout"), { context: "compare" }));
        }
      }, 120000);
    } catch (e) {
      dumpActive.current = false;
      endOp("No se pudo iniciar la comparación.");
      reportError(e, "compare");
    }
  };
  compareVfdRef.current = compareVfd;

  const applyWifiToEdge = async () => {
    if (!connected) {
      setAppError(classifyError(new Error("sin conexión")));
      return;
    }
    const pr = profiles || (await api.profiles());
    const wp = pr.wifi_profiles.find((p) => p.name === wifiName) || pr.wifi_profiles[0];
    if (!wp) {
      setAppError(classifyError(new Error("falta perfil wifi"), { context: "wifi" }));
      return;
    }
    if (/\s/.test(wp.ssid) || (wp.password && /\s/.test(wp.password))) {
      setAppError(classifyError(new Error("ssid con espacios"), { context: "wifi" }));
      return;
    }
    const pwd = wp.password || '""';
    try {
      await api.command(`wifi profile save ${wp.name} ${wp.ssid} ${pwd}`);
      await api.command(`wifi profile use ${wp.name}`);
      pushLog(`→ wifi profile use ${wp.name}`);
      await api.patchLasts({ last_wifi: wp.name });
      setAppError(null);
      Alert.alert(
        "Wi‑Fi enviado",
        `El módulo intentará unirse a “${wp.ssid}”.\nEspera unos segundos y revisa el estado Wi‑Fi.`
      );
    } catch (e) {
      reportError(e, "wifi");
    }
  };

  const applyMqttToEdge = async () => {
    if (!connected) {
      setAppError(classifyError(new Error("sin conexión")));
      return;
    }
    const pr = profiles || (await api.profiles());
    const mp = pr.mqtt_profiles.find((p) => p.name === mqttName) || pr.mqtt_profiles[0];
    if (!mp) {
      setAppError(classifyError(new Error("falta perfil"), { context: "profiles" }));
      return;
    }
    if (mp.host === "127.0.0.1" || mp.host === "localhost") {
      setAppError(classifyError(new Error("localhost"), { context: "mqtt" }));
      // still allow continue after user dismisses banner
    }
    try {
      await api.command(`mqtt set ${mp.host} ${mp.port}`);
      if (mp.username) {
        await api.command(`mqtt user ${mp.username} ${mp.password || '""'}`);
      }
      await api.command("mqtt enable");
      pushLog(`→ mqtt set ${mp.host}:${mp.port}`);
      await api.patchLasts({ last_mqtt: mp.name });
      if (mp.host !== "127.0.0.1" && mp.host !== "localhost") setAppError(null);
      Alert.alert(
        "Red MQTT enviada",
        `Broker “${mp.name}” (${mp.host}:${mp.port}) configurado en el módulo.\n` +
          "Luego puedes conectar la app en modo “Por red (Wi‑Fi)” con el mismo perfil."
      );
    } catch (e) {
      reportError(e, "mqtt");
    }
  };

  const saveMqttProfile = async () => {
    try {
      if (!mForm.host.trim()) {
        Alert.alert("Falta el host", "Indica la IP o nombre del broker.");
        return;
      }
      const pr = await api.upsertMqtt({
        name: mForm.name.trim() || "mqtt",
        host: mForm.host.trim(),
        port: parseInt(mForm.port, 10) || 1883,
        username: mForm.username,
        password: mForm.password,
        topic_prefix: mForm.topic_prefix || "saj/pdm30/saj-pdm30",
      });
      setProfiles(pr);
      setMqttName(mForm.name.trim() || "mqtt");
      Alert.alert("Perfil guardado", "Ya puedes usarlo al conectar o enviarlo al módulo.");
    } catch (e) {
      Alert.alert("No se pudo guardar", String(e));
    }
  };

  const saveWifiProfile = async () => {
    try {
      if (!wForm.ssid.trim()) {
        Alert.alert("Falta el SSID", "Indica el nombre exacto de la red Wi‑Fi.");
        return;
      }
      if (/\s/.test(wForm.ssid) || (wForm.password && /\s/.test(wForm.password))) {
        Alert.alert("Sin espacios", "SSID y contraseña no deben llevar espacios.");
        return;
      }
      const pr = await api.upsertWifi({
        name: wForm.name.trim() || "wifi",
        ssid: wForm.ssid.trim(),
        password: wForm.password,
      });
      setProfiles(pr);
      setWifiName(wForm.name.trim() || "wifi");
      Alert.alert("Perfil Wi‑Fi guardado", "Úsalo en “Enviar Wi‑Fi al módulo”.");
    } catch (e) {
      Alert.alert("No se pudo guardar", String(e));
    }
  };

  const openTutorial = () => {
    setTutorialStep(0);
    setShowTutorial(true);
  };

  const finishTutorial = (markDone: boolean) => {
    if (markDone) setTutorialDone(true);
    setShowTutorial(false);
  };

  const telCards = useMemo(
    () => [
      { k: "freq", label: t.telFreq, u: "Hz", v: telemetry.freq },
      { k: "amp", label: t.telAmp, u: "A", v: telemetry.amp },
      { k: "vdc", label: t.telVdc, u: "V", v: telemetry.vdc },
      { k: "vout", label: t.telVout, u: "V", v: telemetry.vout },
      { k: "pfb", label: t.telPfb, u: "bar", v: telemetry.pfb },
      { k: "pset", label: t.telPset, u: "bar", v: telemetry.pset },
      { k: "status", label: t.telStatus, u: "", v: telemetry.status },
    ],
    [telemetry]
  );

  const filteredParams = useMemo(() => {
    const q = recipeSearch.trim().toLowerCase();
    return plist.parameters.filter((p) => {
      if (recipeFilter === "diff" && !p.mismatch) return false;
      if (recipeFilter === "manual" && !p.manual_only) return false;
      if (recipeFilter === "ok" && (p.mismatch || p.manual_only)) return false;
      if (!q) return true;
      const id = paramId(p).toLowerCase();
      const notes = (p.notes || "").toLowerCase();
      const val = String(p.value);
      const live = p.live_value != null ? String(p.live_value) : "";
      return (
        id.includes(q) ||
        notes.includes(q) ||
        val.includes(q) ||
        live.includes(q) ||
        `p${p.group}`.includes(q) ||
        String(p.index).includes(q)
      );
    });
  }, [plist.parameters, recipeSearch, recipeFilter]);

  const quickActions = [
    { label: t.actCheckDrive, cmd: "ping" },
    { label: t.actLiveOn, cmd: "stream on" },
    { label: t.actLiveOff, cmd: "stream off" },
    { label: t.actStart, cmd: "start" },
    { label: t.actStop, cmd: "stop" },
    { label: t.actWifiInfo, cmd: "wifi status" },
    { label: t.actMqttInfo, cmd: "mqtt status" },
  ];

  // force re-read showDevTools after unlock
  void devTick;

  return (
    <SafeAreaView style={styles.root}>
      <StatusBar style="light" />
      <View style={styles.header}>
        <View style={styles.brandRow}>
          <Image
            source={require("./assets/icon.png")}
            style={styles.brandLogo}
            accessibilityLabel={BRAND.name}
          />
          <View style={{ flex: 1 }}>
            <Text style={styles.title}>{BRAND.name}</Text>
            <Text style={styles.tagline}>{BRAND.tagline}</Text>
          </View>
          <Pressable
            style={styles.helpBtn}
            onPress={() => {
              setMoreSection("help");
              setTab("more");
            }}
            accessibilityLabel="Ayuda"
          >
            <Text style={styles.helpBtnText}>?</Text>
          </Pressable>
        </View>

        <View style={styles.row}>
          <Badge
            ok={connected}
            warn={backendOk === false || wsState === "error"}
            label={
              connected
                ? "● Equipo conectado"
                : backendOk === false
                  ? "● Servicio no disponible"
                  : "● Sin conexión al equipo"
            }
          />
          {busy ? <Badge ok={false} warn label={`⏳ ${opName || "…"}`} /> : null}
        </View>
        <Text style={styles.statusLine} numberOfLines={2}>
          {statusMsg || linkLabel}
        </Text>
        {dev ? (
          <Text style={styles.devHint}>
            Diagnóstico: {apiBase()} · WS {wsState}
          </Text>
        ) : null}

        {busy ? (
          <View style={styles.progressTrack}>
            <View
              style={[styles.progressFill, { width: `${Math.round(progress * 100)}%` }]}
            />
          </View>
        ) : null}

        <ErrorBanner
          error={appError}
          onDismiss={() => setAppError(null)}
          onRetry={handleRetry}
        />

        <View style={styles.tabs}>
          {(
            [
              ["home", t.tabHome],
              ["connect", t.tabConnect],
              ["params", t.tabParams],
              ["more", t.tabMore],
            ] as const
          ).map(([id, lab]) => (
            <Pressable
              key={id}
              onPress={() => setTab(id)}
              style={[styles.tab, tab === id && styles.tabOn]}
              accessibilityRole="tab"
              accessibilityState={{ selected: tab === id }}
            >
              <Text style={styles.tabText}>{lab}</Text>
            </Pressable>
          ))}
        </View>
      </View>

      <ScrollView
        style={{ flex: 1 }}
        contentContainerStyle={styles.pad}
        keyboardShouldPersistTaps="handled"
      >
        {tab === "home" && (
          <>
            <Text style={styles.section}>{t.homeTitle}</Text>
            <Text style={styles.hint}>{t.homeSubtitle}</Text>

            {/* Compact live strip */}
            <View style={styles.liveStrip}>
              <Text style={styles.liveStripTitle}>{t.homeLive}</Text>
              <View style={styles.liveStripRow}>
                {telCards.slice(0, 4).map((c) => (
                  <View key={c.k} style={styles.liveChip}>
                    <Text style={styles.liveChipLab}>{c.label}</Text>
                    <Text style={styles.liveChipVal}>
                      {c.v === undefined || c.v === null || c.v === ""
                        ? "—"
                        : typeof c.v === "number"
                          ? c.v.toFixed(1)
                          : String(c.v)}
                    </Text>
                  </View>
                ))}
              </View>
            </View>

            <StepCard
              done={connected}
              title={t.step1Title}
              body={t.step1Body}
              status={connected ? t.step1Done : t.statusOffline}
              primaryLabel={connected ? "Ver conexión" : t.step1Cta}
              onPrimary={() => setTab("connect")}
            />
            <StepCard
              done={plist.parameters.length > 0}
              title={t.step2Title}
              body={t.step2Body}
              status={
                plist.parameters.length > 0
                  ? t.step2Done(plist.parameters.length)
                  : "Ninguna receta cargada"
              }
              primaryLabel={t.step2Cta}
              onPrimary={() => setTab("params")}
            />
            <StepCard
              done={hasCompared}
              locked={!connected}
              title={t.step3Title}
              body={t.step3Body}
              status={
                !connected
                  ? t.stepNeedConnect
                  : hasCompared
                    ? t.step3Done
                    : "Aún no has comparado"
              }
              primaryLabel={t.step3CtaCheck}
              onPrimary={() => {
                if (!connected) {
                  Alert.alert("Paso 1", t.stepNeedConnect);
                  setTab("connect");
                  return;
                }
                sendCmd("ping");
              }}
              secondaryLabel={t.step3CtaCompare}
              onSecondary={() => {
                if (!connected) {
                  Alert.alert("Paso 1", t.stepNeedConnect);
                  setTab("connect");
                  return;
                }
                if (!plist.parameters.length) {
                  Alert.alert("Paso 2", t.stepNeedRecipe);
                  setTab("params");
                  return;
                }
                compareVfd();
              }}
            />
            <StepCard
              done={hasSynced}
              locked={!connected || !plist.parameters.length}
              title={t.step4Title}
              body={t.step4Body}
              status={
                !connected
                  ? t.stepNeedConnect
                  : !plist.parameters.length
                    ? t.stepNeedRecipe
                    : hasSynced
                      ? t.step4Done
                      : hasCompared
                        ? "Listo para enviar (ya comparaste)"
                        : "Puedes enviar; se recomienda comparar antes"
              }
              primaryLabel={t.step4Cta}
              onPrimary={() => {
                if (!connected) {
                  Alert.alert("Paso 1", t.stepNeedConnect);
                  setTab("connect");
                  return;
                }
                if (!plist.parameters.length) {
                  Alert.alert("Paso 2", t.stepNeedRecipe);
                  setTab("params");
                  return;
                }
                syncVfd();
              }}
            />

            <Text style={[styles.section, { marginTop: 8 }]}>Más opciones</Text>
            <Pressable
              style={styles.btnSec}
              onPress={() => {
                setMoreSection("network");
                setTab("more");
              }}
              accessibilityRole="button"
            >
              <Text style={styles.btnText}>{t.homeMoreNetwork}</Text>
            </Pressable>
            <Pressable
              style={styles.btnSec}
              onPress={() => {
                setMoreSection("help");
                setTab("more");
              }}
              accessibilityRole="button"
            >
              <Text style={styles.btnText}>{t.homeMoreHelp}</Text>
            </Pressable>
          </>
        )}

        {tab === "connect" && (
          <>
            <Text style={styles.section}>¿Cómo te conectas al módulo?</Text>
            <View style={styles.chips}>
              {modesVisible.map((m) => (
                <Chip
                  key={m.id}
                  label={m.label}
                  active={mode === m.id}
                  disabled={connected}
                  onPress={() => setMode(m.id)}
                />
              ))}
            </View>

            {mode === "serial" && (
              <View style={styles.block}>
                <Text style={styles.label}>{t.portLabel}</Text>
                <View style={styles.row}>
                  <TextInput
                    style={[styles.input, { flex: 1 }]}
                    value={port}
                    onChangeText={setPort}
                    placeholder="Se detecta solo si hay un cable"
                    placeholderTextColor="#6b7280"
                    editable={!connected}
                  />
                  <Pressable
                    style={styles.btnSec}
                    onPress={refreshPorts}
                    accessibilityLabel={t.refreshPorts}
                  >
                    <Text style={styles.btnText}>{t.refreshPorts}</Text>
                  </Pressable>
                </View>
                {ports.map((p) => (
                  <Pressable key={p.device} onPress={() => setPort(p.device)}>
                    <Text style={styles.hint}>
                      {p.device}
                      {p.description ? ` — ${p.description}` : ""}
                    </Text>
                  </Pressable>
                ))}
                {dev ? (
                  <>
                    <Text style={styles.label}>{t.baudLabel}</Text>
                    <View style={styles.chips}>
                      {["9600", "115200"].map((b) => (
                        <Chip
                          key={b}
                          label={b}
                          active={baud === b}
                          disabled={connected}
                          onPress={() => setBaud(b)}
                        />
                      ))}
                    </View>
                  </>
                ) : null}
              </View>
            )}

            {mode === "mqtt" && (
              <View style={styles.block}>
                <Text style={styles.label}>{t.mqttProfileLabel}</Text>
                <Text style={styles.hint}>
                  Elige el perfil de esta planta. Si no hay ninguno, créalo en “Red del equipo”.
                </Text>
                <View style={styles.chips}>
                  {(profiles?.mqtt_profiles || []).map((p) => (
                    <Chip
                      key={p.name}
                      label={p.name}
                      active={mqttName === p.name}
                      disabled={connected}
                      onPress={() => setMqttName(p.name)}
                    />
                  ))}
                </View>
              </View>
            )}

            {(mode === "bluetooth" || mode === "ble") && (
              <View style={styles.block}>
                <View style={styles.row}>
                  <Text style={[styles.label, { flex: 1 }]}>{t.btDeviceLabel}</Text>
                  <Pressable
                    style={styles.btnSec}
                    onPress={scanBt}
                    disabled={scanning || connected}
                  >
                    {scanning ? (
                      <ActivityIndicator color="#fff" />
                    ) : (
                      <Text style={styles.btnText}>{t.scanBt}</Text>
                    )}
                  </Pressable>
                </View>
                {dev ? (
                  <TextInput
                    style={styles.input}
                    value={btAddress}
                    onChangeText={setBtAddress}
                    placeholder="Dirección del equipo"
                    placeholderTextColor="#6b7280"
                    editable={!connected}
                    autoCapitalize="characters"
                  />
                ) : btAddress ? (
                  <Text style={styles.hint}>Seleccionado: {btAddress}</Text>
                ) : (
                  <Text style={styles.hint}>Pulsa “Buscar equipos” y elige uno de la lista.</Text>
                )}
                {btDevices.map((d) => {
                  const labelName =
                    d.name && d.name.toUpperCase() !== d.address.toUpperCase()
                      ? d.name
                      : "Sin nombre";
                  return (
                    <Pressable key={d.address} onPress={() => setBtAddress(d.address)}>
                      <Text
                        style={[styles.hint, d.address === btAddress && styles.hintOn]}
                      >
                        {labelName} · {d.address}
                        {d.paired ? " ✓" : ""}
                      </Text>
                    </Pressable>
                  );
                })}
              </View>
            )}

            <View style={styles.row}>
              {!connected ? (
                <Pressable
                  style={[styles.btnPri, styles.btnLarge, busy && styles.dis]}
                  onPress={doConnect}
                  disabled={busy}
                  accessibilityRole="button"
                >
                  <Text style={styles.btnTextLarge}>{t.connect}</Text>
                </Pressable>
              ) : (
                <Pressable
                  style={[styles.btnDanger, styles.btnLarge]}
                  onPress={doDisconnect}
                  accessibilityRole="button"
                >
                  <Text style={styles.btnTextLarge}>{t.disconnect}</Text>
                </Pressable>
              )}
            </View>

            <Text style={styles.section}>{t.telTitle}</Text>
            <View style={styles.telGrid}>
              {telCards.map((c) => (
                <View key={c.k} style={styles.telCard}>
                  <Text style={styles.telLabel}>{c.label}</Text>
                  <Text style={styles.telValue}>
                    {c.v === undefined || c.v === null || c.v === ""
                      ? "—"
                      : typeof c.v === "number"
                        ? c.v.toFixed(2)
                        : String(c.v)}
                    {c.u ? ` ${c.u}` : ""}
                  </Text>
                </View>
              ))}
            </View>

            <Text style={styles.section}>Acciones rápidas</Text>
            <View style={styles.chips}>
              {quickActions.map((a) => (
                <Chip
                  key={a.cmd}
                  label={a.label}
                  onPress={() => sendCmd(a.cmd)}
                  disabled={!connected}
                />
              ))}
            </View>

            <Text style={styles.section}>{t.activity}</Text>
            <View style={styles.logBox}>
              <ScrollView
                ref={logRef}
                onContentSizeChange={() =>
                  logRef.current?.scrollToEnd({ animated: true })
                }
              >
                {log.length === 0 ? (
                  <Text style={styles.muted}>{t.activityEmpty}</Text>
                ) : (
                  log.map((l, i) => (
                    <Text key={`${i}-${l.slice(0, 8)}`} style={styles.logLine}>
                      {l}
                    </Text>
                  ))
                )}
              </ScrollView>
            </View>

            {dev || showAdvancedCmd ? (
              <View style={styles.row}>
                <TextInput
                  style={[styles.input, { flex: 1, marginBottom: 0 }]}
                  value={cmd}
                  onChangeText={setCmd}
                  placeholder={t.cmdPlaceholder}
                  placeholderTextColor="#6b7280"
                  onSubmitEditing={() => sendCmd()}
                  editable={connected}
                />
                <Pressable
                  style={[styles.btnPri, !connected && styles.dis]}
                  onPress={() => sendCmd()}
                  disabled={!connected}
                >
                  <Text style={styles.btnText}>{t.send}</Text>
                </Pressable>
              </View>
            ) : (
              <Pressable onPress={() => setShowAdvancedCmd(true)}>
                <Text style={styles.linkMuted}>Mostrar comando técnico (avanzado)</Text>
              </Pressable>
            )}
          </>
        )}

        {tab === "params" && (
          <>
            <Text style={styles.section}>
              {t.recipesTitle}: {plist.name}{" "}
              <Text style={styles.sectionCount}>
                ({filteredParams.length}
                {filteredParams.length !== plist.parameters.length
                  ? ` de ${plist.parameters.length}`
                  : ""}
                )
              </Text>
            </Text>
            <Text style={styles.label}>{t.recipesServer}</Text>
            <View style={styles.chips}>
              {listFiles.map((f) => (
                <Chip
                  key={f.filename}
                  label={`${f.name || f.stem}`}
                  active={listFile === f.filename}
                  onPress={() => loadList(f.filename)}
                />
              ))}
            </View>
            <Text style={styles.hint}>
              {isDesktopShell()
                ? "Puedes abrir o guardar archivos JSON en tu PC."
                : "Puedes importar o descargar un archivo JSON de receta."}
            </Text>
            <View style={styles.row}>
              <Pressable style={styles.btnSec} onPress={importJson}>
                <Text style={styles.btnText}>{t.openJson}</Text>
              </Pressable>
              <Pressable style={styles.btnSec} onPress={() => exportJson(false)}>
                <Text style={styles.btnText}>{t.saveAs}</Text>
              </Pressable>
              <Pressable style={styles.btnSec} onPress={saveList}>
                <Text style={styles.btnText}>{t.saveServer}</Text>
              </Pressable>
            </View>
            <View style={styles.row}>
              <Pressable
                style={[styles.btnPri, styles.btnLarge, (!connected || busy) && styles.dis]}
                onPress={syncVfd}
                disabled={!connected || busy}
              >
                <Text style={styles.btnTextLarge}>{t.sendToDrive}</Text>
              </Pressable>
              <Pressable
                style={[styles.btnPri, (!connected || busy) && styles.dis]}
                onPress={compareVfd}
                disabled={!connected || busy}
              >
                <Text style={styles.btnText}>{t.compareDrive}</Text>
              </Pressable>
              {busy ? (
                <Pressable style={styles.btnWarn} onPress={() => endOp("Cancelado")}>
                  <Text style={styles.btnText}>{t.cancelOp}</Text>
                </Pressable>
              ) : null}
            </View>

            <Text style={styles.label}>Buscar en la receta</Text>
            <TextInput
              style={styles.input}
              value={recipeSearch}
              onChangeText={setRecipeSearch}
              placeholder="ID, valor o notas… (ej. P0-00, presión, 1.5)"
              placeholderTextColor={colors.textDim}
              accessibilityLabel="Buscar parámetros en la receta"
              clearButtonMode="while-editing"
            />
            <View style={styles.chips}>
              {(
                [
                  ["all", "Todos"],
                  ["diff", "Diferentes"],
                  ["ok", "Coinciden"],
                  ["manual", "Solo manual"],
                ] as const
              ).map(([id, lab]) => (
                <Chip
                  key={id}
                  label={lab}
                  active={recipeFilter === id}
                  onPress={() => setRecipeFilter(id)}
                />
              ))}
            </View>
            {recipeSearch || recipeFilter !== "all" ? (
              <Pressable
                onPress={() => {
                  setRecipeSearch("");
                  setRecipeFilter("all");
                }}
              >
                <Text style={styles.linkMuted}>Limpiar búsqueda y filtros</Text>
              </Pressable>
            ) : null}

            <View style={styles.tableHead}>
              <Text style={[styles.th, { flex: 1 }]}>ID</Text>
              <Text style={[styles.th, { flex: 1 }]}>Receta</Text>
              <Text style={[styles.th, { flex: 1 }]}>Variador</Text>
              <Text style={[styles.th, { flex: 2 }]}>Notas</Text>
            </View>
            {filteredParams.length === 0 ? (
              <Text style={styles.muted}>
                Ningún parámetro coincide con la búsqueda.
              </Text>
            ) : (
              filteredParams.map((p) => {
                const key = `${p.group}:${p.index}`;
                const sel = selectedKey === key;
                const bg = p.mismatch
                  ? colors.dangerBg
                  : p.manual_only
                    ? colors.warningSoft
                    : sel
                      ? colors.primarySoft
                      : colors.surface;
                return (
                  <Pressable
                    key={key}
                    onPress={() => selectParam(p)}
                    style={[styles.tr, { backgroundColor: bg }]}
                    accessibilityRole="button"
                    accessibilityLabel={`${paramId(p)} valor ${p.value}`}
                  >
                    <Text style={[styles.td, { flex: 1 }]}>{paramId(p)}</Text>
                    <Text style={[styles.td, { flex: 1 }]}>{p.value}</Text>
                    <Text style={[styles.td, { flex: 1 }]}>
                      {p.live_value == null ? "—" : p.live_value}
                    </Text>
                    <Text style={[styles.td, { flex: 2 }]} numberOfLines={1}>
                      {p.manual_only ? "Manual · " : ""}
                      {p.notes}
                    </Text>
                  </Pressable>
                );
              })
            )}

            <Text style={styles.section}>{t.editor}</Text>
            <View style={styles.chips}>
              <Chip label="Grupo 0" active={edGroup === "P0"} onPress={() => setEdGroup("P0")} />
              <Chip label="Grupo 1" active={edGroup === "P1"} onPress={() => setEdGroup("P1")} />
            </View>
            <Text style={styles.label}>{t.indexLabel}</Text>
            <TextInput
              style={styles.input}
              value={edIdx}
              onChangeText={setEdIdx}
              keyboardType="numeric"
              placeholderTextColor="#6b7280"
            />
            <Text style={styles.label}>{t.valueLabel}</Text>
            <TextInput
              style={styles.input}
              value={edVal}
              onChangeText={setEdVal}
              keyboardType="decimal-pad"
              placeholderTextColor="#6b7280"
            />
            <Text style={styles.label}>{t.notesLabel}</Text>
            <TextInput
              style={[styles.input, { minHeight: 64 }]}
              value={edNotes}
              onChangeText={setEdNotes}
              multiline
              placeholderTextColor="#6b7280"
            />
            <View style={styles.row}>
              <Switch value={edManual} onValueChange={setEdManual} />
              <Text style={styles.hint}>{t.manualFlag}</Text>
            </View>
            <View style={styles.row}>
              <Pressable style={styles.btnPri} onPress={addParam}>
                <Text style={styles.btnText}>{t.addUpdate}</Text>
              </Pressable>
              <Pressable style={styles.btnDanger} onPress={delParam}>
                <Text style={styles.btnText}>{t.remove}</Text>
              </Pressable>
            </View>
          </>
        )}

        {tab === "more" && (
          <>
            <View style={styles.chips}>
              <Chip
                label={t.tabEdge}
                active={moreSection === "network"}
                onPress={() => setMoreSection("network")}
              />
              <Chip
                label={t.tabHelp}
                active={moreSection === "help"}
                onPress={() => setMoreSection("help")}
              />
            </View>

            {moreSection === "network" && (
          <>
            <Text style={styles.section}>{t.edgeTitle}</Text>
            <View style={styles.cardInfo}>
              <Text style={styles.cardInfoText}>{t.edgeWifiHint}</Text>
            </View>
            <Text style={styles.label}>Perfil Wi‑Fi</Text>
            <View style={styles.chips}>
              {(profiles?.wifi_profiles || []).map((p) => (
                <Chip
                  key={p.name}
                  label={p.name}
                  active={wifiName === p.name}
                  onPress={() => setWifiName(p.name)}
                />
              ))}
            </View>
            <Pressable
              style={[styles.btnPri, styles.btnLarge, !connected && styles.dis]}
              onPress={applyWifiToEdge}
              disabled={!connected}
            >
              <Text style={styles.btnTextLarge}>{t.applyWifi}</Text>
            </Pressable>

            <View style={[styles.cardInfo, { marginTop: 20 }]}>
              <Text style={styles.cardInfoText}>{t.edgeMqttHint}</Text>
            </View>
            <Text style={styles.label}>Perfil de red (MQTT)</Text>
            <View style={styles.chips}>
              {(profiles?.mqtt_profiles || []).map((p) => (
                <Chip
                  key={p.name}
                  label={p.name}
                  active={mqttName === p.name}
                  onPress={() => setMqttName(p.name)}
                />
              ))}
            </View>
            <Pressable
              style={[styles.btnPri, styles.btnLarge, !connected && styles.dis]}
              onPress={applyMqttToEdge}
              disabled={!connected}
            >
              <Text style={styles.btnTextLarge}>{t.applyMqtt}</Text>
            </Pressable>

            <View style={styles.row}>
              <Chip
                label={t.actWifiInfo}
                onPress={() => sendCmd("wifi status")}
                disabled={!connected}
              />
              <Chip
                label={t.actMqttInfo}
                onPress={() => sendCmd("mqtt status")}
                disabled={!connected}
              />
            </View>

            <Pressable
              style={[styles.btnSec, { marginTop: 20 }]}
              onPress={() => setShowProfiles(true)}
            >
              <Text style={styles.btnText}>{t.editProfiles}</Text>
            </Pressable>
            <Pressable
              style={styles.btnSec}
              onPress={async () => setProfiles(await api.profiles())}
            >
              <Text style={styles.btnText}>{t.reloadProfiles}</Text>
            </Pressable>
          </>
            )}

            {moreSection === "help" && (
          <>
            <Text style={styles.section}>Ayuda</Text>
            <Pressable style={[styles.btnPri, styles.btnLarge]} onPress={openTutorial}>
              <Text style={styles.btnTextLarge}>{t.tutorialAgain}</Text>
            </Pressable>
            <View style={styles.cardInfo}>
              <Text style={styles.cardInfoText}>
                Camino recomendado (también en Inicio):{"\n"}
                1) Conectar el módulo{"\n"}
                2) Elegir la receta{"\n"}
                3) Comprobar / comparar{"\n"}
                4) Enviar al variador{"\n\n"}
                Puedes enviar sin comparar: la app te lo recordará.
              </Text>
            </View>
            <Pressable style={styles.btnSec} onPress={() => setShowAbout(true)}>
              <Text style={styles.btnText}>{t.about}</Text>
            </Pressable>
            <Pressable
              style={styles.btnSec}
              onPress={() => {
                const next = !showDevTools();
                setDevToolsUnlocked(next);
                setDevTick((x) => x + 1);
                Alert.alert(
                  t.diagnostics,
                  next
                    ? "Herramientas técnicas visibles (CLI, simulado, URL)."
                    : "Herramientas técnicas ocultas."
                );
              }}
            >
              <Text style={styles.btnText}>
                {showDevTools() ? t.diagnosticsLock : t.diagnosticsUnlock}
              </Text>
            </Pressable>
            <Pressable
              style={styles.btnSec}
              onPress={() => setTab("home")}
            >
              <Text style={styles.btnText}>Volver al inicio</Text>
            </Pressable>
          </>
            )}
          </>
        )}
      </ScrollView>

      {/* Profiles modal */}
      <Modal visible={showProfiles} animationType="slide" transparent>
        <View style={styles.modalBg}>
          <ScrollView style={styles.modalCard} contentContainerStyle={{ padding: 16 }}>
            <Text style={styles.title}>{t.profilesTitle}</Text>
            <View style={styles.cardInfo}>
              <Text style={styles.cardInfoText}>{t.profilesMqttHelp}</Text>
            </View>
            <Text style={styles.section}>Perfil de red (MQTT)</Text>
            {(
              [
                ["name", "Nombre del perfil (ej. Planta-1)"],
                ["host", "IP o nombre del broker"],
                ["port", "Puerto (1883)"],
                ["topic_prefix", "Prefijo de temas (técnico)"],
                ["username", "Usuario (opcional)"],
                ["password", "Contraseña (opcional)"],
              ] as const
            ).map(([k, lab]) => (
              <View key={k}>
                <Text style={styles.label}>{lab}</Text>
                <TextInput
                  style={styles.input}
                  value={mForm[k]}
                  onChangeText={(v) => setMForm((f) => ({ ...f, [k]: v }))}
                  secureTextEntry={k === "password"}
                  placeholderTextColor="#6b7280"
                />
              </View>
            ))}
            <Pressable style={styles.btnPri} onPress={saveMqttProfile}>
              <Text style={styles.btnText}>{t.saveMqttProfile}</Text>
            </Pressable>

            <View style={[styles.cardInfo, { marginTop: 16 }]}>
              <Text style={styles.cardInfoText}>{t.profilesWifiHelp}</Text>
            </View>
            <Text style={styles.section}>Perfil Wi‑Fi</Text>
            {(
              [
                ["name", "Nombre del perfil"],
                ["ssid", "Nombre de la red (SSID)"],
                ["password", "Contraseña Wi‑Fi"],
              ] as const
            ).map(([k, lab]) => (
              <View key={k}>
                <Text style={styles.label}>{lab}</Text>
                <TextInput
                  style={styles.input}
                  value={wForm[k]}
                  onChangeText={(v) => setWForm((f) => ({ ...f, [k]: v }))}
                  secureTextEntry={k === "password"}
                  placeholderTextColor="#6b7280"
                />
              </View>
            ))}
            <Pressable style={styles.btnPri} onPress={saveWifiProfile}>
              <Text style={styles.btnText}>{t.saveWifiProfile}</Text>
            </Pressable>
            <Pressable
              style={[styles.btnSec, { marginTop: 12, marginBottom: 24 }]}
              onPress={() => setShowProfiles(false)}
            >
              <Text style={styles.btnText}>{t.close}</Text>
            </Pressable>
          </ScrollView>
        </View>
      </Modal>

      {/* Tutorial */}
      <Modal visible={showTutorial} animationType="fade" transparent>
        <View style={styles.modalBg}>
          <View style={styles.tutorialCard}>
            <Text style={styles.tutorialKicker}>
              {tutorialStep + 1} / {t.tutorialSteps.length}
            </Text>
            <Text style={styles.tutorialTitle}>
              {t.tutorialSteps[tutorialStep].title}
            </Text>
            <Text style={styles.tutorialBody}>
              {t.tutorialSteps[tutorialStep].body}
            </Text>
            <View style={styles.row}>
              <Pressable
                style={styles.btnSec}
                onPress={() => finishTutorial(true)}
              >
                <Text style={styles.btnText}>{t.tutorialSkip}</Text>
              </Pressable>
              {tutorialStep > 0 ? (
                <Pressable
                  style={styles.btnSec}
                  onPress={() => setTutorialStep((s) => s - 1)}
                >
                  <Text style={styles.btnText}>{t.tutorialPrev}</Text>
                </Pressable>
              ) : null}
              {tutorialStep < t.tutorialSteps.length - 1 ? (
                <Pressable
                  style={styles.btnPri}
                  onPress={() => setTutorialStep((s) => s + 1)}
                >
                  <Text style={styles.btnText}>{t.tutorialNext}</Text>
                </Pressable>
              ) : (
                <Pressable
                  style={styles.btnPri}
                  onPress={() => finishTutorial(true)}
                >
                  <Text style={styles.btnText}>{t.tutorialFinish}</Text>
                </Pressable>
              )}
            </View>
          </View>
        </View>
      </Modal>

      {/* About */}
      <Modal visible={showAbout} animationType="fade" transparent>
        <View style={styles.modalBg}>
          <View style={styles.tutorialCard}>
            <Text style={styles.tutorialTitle}>{BRAND.fullName}</Text>
            <Text style={styles.tutorialBody}>
              Versión {BRAND.version}
              {"\n"}
              {BRAND.tagline}
              {"\n\n"}
              Multi-variador: el módulo de campo puede ampliarse a distintos equipos.
              {"\n\n"}
              {dev ? `Interno: ${BRAND.codename} · ${apiBase()}` : ""}
            </Text>
            <Pressable style={styles.btnPri} onPress={() => setShowAbout(false)}>
              <Text style={styles.btnText}>{t.close}</Text>
            </Pressable>
          </View>
        </View>
      </Modal>
    </SafeAreaView>
  );
}

function sleep(ms: number) {
  return new Promise((r) => setTimeout(r, ms));
}

function Badge({
  ok,
  warn,
  label,
}: {
  ok: boolean;
  warn?: boolean;
  label: string;
}) {
  const bg = warn ? colors.warningSoft : ok ? colors.successBg : colors.dangerBg;
  return (
    <View style={[styles.badge, { backgroundColor: bg }]}>
      <Text style={styles.badgeText}>{label}</Text>
    </View>
  );
}

function Chip({
  label,
  onPress,
  active,
  disabled,
}: {
  label: string;
  onPress: () => void;
  active?: boolean;
  disabled?: boolean;
}) {
  return (
    <Pressable
      onPress={onPress}
      disabled={disabled}
      style={[styles.chip, active && styles.chipOn, disabled && styles.dis]}
      accessibilityRole="button"
      accessibilityState={{ selected: !!active, disabled: !!disabled }}
    >
      <Text style={styles.chipText}>{label}</Text>
    </Pressable>
  );
}

function StepCard({
  title,
  body,
  status,
  done,
  locked,
  primaryLabel,
  onPrimary,
  secondaryLabel,
  onSecondary,
}: {
  title: string;
  body: string;
  status: string;
  done?: boolean;
  locked?: boolean;
  primaryLabel: string;
  onPrimary: () => void;
  secondaryLabel?: string;
  onSecondary?: () => void;
}) {
  return (
    <View
      style={[
        styles.stepCard,
        done && styles.stepCardDone,
        locked && styles.stepCardLocked,
      ]}
      accessibilityRole="summary"
    >
      <View style={styles.stepHeader}>
        <View
          style={[styles.stepBadge, done ? styles.stepBadgeDone : styles.stepBadgeTodo]}
        >
          <Text style={styles.stepBadgeText}>{done ? "✓" : "·"}</Text>
        </View>
        <Text style={styles.stepTitle}>{title}</Text>
      </View>
      <Text style={styles.stepBody}>{body}</Text>
      <Text style={styles.stepStatus}>{status}</Text>
      <View style={styles.row}>
        <Pressable
          style={[styles.btnPri, styles.btnLarge]}
          onPress={onPrimary}
          accessibilityRole="button"
        >
          <Text style={styles.btnTextLarge}>{primaryLabel}</Text>
        </Pressable>
        {secondaryLabel && onSecondary ? (
          <Pressable
            style={[styles.btnSec, locked && styles.dis]}
            onPress={onSecondary}
            accessibilityRole="button"
          >
            <Text style={styles.btnText}>{secondaryLabel}</Text>
          </Pressable>
        ) : null}
      </View>
    </View>
  );
}

const styles = StyleSheet.create({
  root: { flex: 1, backgroundColor: colors.bg },
  header: {
    paddingHorizontal: space.lg,
    paddingTop: 10,
    paddingBottom: space.sm,
    borderBottomWidth: 1,
    borderBottomColor: colors.surface,
  },
  brandRow: { flexDirection: "row", alignItems: "center", gap: space.md },
  brandLogo: {
    width: 44,
    height: 44,
    borderRadius: radius.md,
    backgroundColor: colors.surface,
  },
  title: {
    color: colors.text,
    fontSize: font.h1,
    fontWeight: font.weightBlack,
    letterSpacing: 0.3,
  },
  tagline: { color: colors.textMuted, fontSize: font.sm, marginTop: 2 },
  helpBtn: {
    width: touchMin,
    height: touchMin,
    borderRadius: touchMin / 2,
    backgroundColor: colors.primarySoft,
    alignItems: "center",
    justifyContent: "center",
  },
  helpBtnText: { color: colors.textSecondary, fontSize: 20, fontWeight: font.weightBold },
  statusLine: { color: colors.textSecondary, fontSize: font.md, marginTop: 6 },
  devHint: {
    color: colors.textDim,
    fontSize: font.xs,
    marginTop: 4,
    fontFamily: "monospace",
  },
  pad: { padding: space.lg, paddingBottom: 56 },
  section: {
    color: colors.text,
    fontSize: font.xl,
    fontWeight: font.weightBold,
    marginTop: 18,
    marginBottom: 10,
  },
  sectionCount: { color: colors.textMuted, fontWeight: font.weightSemi, fontSize: font.body },
  row: {
    flexDirection: "row",
    alignItems: "center",
    flexWrap: "wrap",
    gap: space.sm,
    marginVertical: 6,
  },
  chips: { flexDirection: "row", flexWrap: "wrap", gap: space.sm },
  chip: {
    backgroundColor: colors.surface,
    paddingHorizontal: 14,
    paddingVertical: 10,
    borderRadius: radius.pill,
    borderWidth: 1,
    borderColor: colors.border,
    minHeight: 44,
    justifyContent: "center",
  },
  chipOn: { backgroundColor: colors.primaryHover, borderColor: colors.borderFocus },
  chipText: { color: colors.text, fontSize: font.md, fontWeight: font.weightSemi },
  tabs: { flexDirection: "row", gap: 6, marginTop: space.md },
  tab: {
    flex: 1,
    paddingVertical: space.md,
    borderRadius: radius.md,
    backgroundColor: colors.surface,
    alignItems: "center",
    minHeight: touchMin,
    justifyContent: "center",
  },
  tabOn: { backgroundColor: colors.primary },
  tabText: {
    color: colors.text,
    fontWeight: font.weightBold,
    fontSize: font.sm,
    textAlign: "center",
  },
  block: { marginTop: space.sm },
  label: {
    color: colors.textSecondary,
    marginBottom: 6,
    marginTop: space.sm,
    fontSize: font.md,
    fontWeight: font.weightSemi,
  },
  input: {
    backgroundColor: colors.surface,
    borderColor: colors.border,
    borderWidth: 1,
    borderRadius: radius.md,
    color: colors.text,
    paddingHorizontal: 14,
    paddingVertical: space.md,
    marginBottom: space.sm,
    minHeight: touchMin,
    fontSize: font.lg,
  },
  btnPri: {
    backgroundColor: colors.primary,
    paddingHorizontal: space.lg,
    paddingVertical: space.md,
    borderRadius: radius.md,
    minHeight: touchMin,
    justifyContent: "center",
  },
  btnLarge: { paddingVertical: space.lg, minHeight: 56 },
  btnSec: {
    backgroundColor: colors.surfaceHover,
    paddingHorizontal: 14,
    paddingVertical: space.md,
    borderRadius: radius.md,
    minHeight: touchMin,
    justifyContent: "center",
  },
  btnDanger: {
    backgroundColor: colors.danger,
    paddingHorizontal: space.lg,
    paddingVertical: space.md,
    borderRadius: radius.md,
    minHeight: touchMin,
    justifyContent: "center",
  },
  btnWarn: {
    backgroundColor: colors.warningBg,
    paddingHorizontal: 14,
    paddingVertical: space.md,
    borderRadius: radius.md,
    minHeight: touchMin,
    justifyContent: "center",
  },
  btnText: {
    color: "#fff",
    fontWeight: font.weightBold,
    fontSize: font.body,
    textAlign: "center",
  },
  btnTextLarge: {
    color: "#fff",
    fontWeight: font.weightBlack,
    fontSize: font.xl,
    textAlign: "center",
  },
  dis: { opacity: 0.4 },
  badge: { paddingHorizontal: 10, paddingVertical: 6, borderRadius: radius.sm },
  badgeText: { color: colors.text, fontSize: font.sm, fontWeight: font.weightSemi },
  muted: { color: colors.textDim, fontSize: font.md },
  hint: {
    color: colors.textMuted,
    fontSize: font.md,
    marginBottom: 4,
    lineHeight: 18,
  },
  hintOn: { color: colors.accentSoft, fontWeight: font.weightSemi },
  linkMuted: {
    color: colors.textDim,
    fontSize: font.sm,
    textDecorationLine: "underline",
    marginTop: space.sm,
  },
  progressTrack: {
    height: 5,
    backgroundColor: colors.surface,
    borderRadius: 3,
    marginTop: space.sm,
    overflow: "hidden",
  },
  progressFill: { height: 5, backgroundColor: colors.warning },
  telGrid: { flexDirection: "row", flexWrap: "wrap", gap: space.sm },
  telCard: {
    backgroundColor: colors.surface,
    borderRadius: radius.lg,
    padding: space.md,
    minWidth: 96,
    flexGrow: 1,
  },
  telLabel: { color: colors.textMuted, fontSize: 11, fontWeight: font.weightSemi },
  telValue: {
    color: colors.text,
    fontSize: font.display,
    fontWeight: font.weightBlack,
    marginTop: 4,
  },
  logBox: {
    backgroundColor: "#020617",
    borderRadius: radius.lg,
    borderWidth: 1,
    borderColor: colors.surface,
    height: 140,
    padding: 10,
    marginVertical: space.sm,
  },
  logLine: {
    color: colors.textSecondary,
    fontSize: font.sm,
    marginBottom: 3,
    lineHeight: 16,
  },
  tableHead: {
    flexDirection: "row",
    paddingVertical: space.sm,
    borderBottomWidth: 1,
    borderBottomColor: colors.border,
    marginTop: space.sm,
  },
  th: { color: colors.textMuted, fontWeight: font.weightBold, fontSize: 11 },
  tr: {
    flexDirection: "row",
    paddingVertical: space.md,
    paddingHorizontal: 6,
    borderRadius: radius.sm,
    marginTop: 4,
    minHeight: 44,
  },
  td: { color: colors.textSecondary, fontSize: font.sm },
  cardInfo: {
    backgroundColor: colors.infoBg,
    borderRadius: radius.md,
    padding: 14,
    borderWidth: 1,
    borderColor: colors.infoBorder,
    marginBottom: 10,
  },
  cardInfoText: { color: colors.infoText, fontSize: font.md, lineHeight: 20 },
  modalBg: {
    flex: 1,
    backgroundColor: "rgba(0,0,0,0.75)",
    justifyContent: "center",
    padding: space.lg,
  },
  modalCard: {
    backgroundColor: colors.bg,
    borderRadius: radius.xl,
    maxHeight: "92%",
    borderWidth: 1,
    borderColor: colors.border,
  },
  tutorialCard: {
    backgroundColor: colors.bg,
    borderRadius: radius.xl,
    padding: space.xl,
    borderWidth: 1,
    borderColor: colors.border,
  },
  tutorialKicker: {
    color: colors.borderFocus,
    fontWeight: font.weightBold,
    marginBottom: space.sm,
  },
  tutorialTitle: {
    color: colors.text,
    fontSize: font.h2,
    fontWeight: font.weightBlack,
    marginBottom: space.md,
  },
  tutorialBody: {
    color: colors.textSecondary,
    fontSize: font.lg,
    lineHeight: 22,
    marginBottom: space.xl,
  },
  stepCard: {
    backgroundColor: colors.surface,
    borderRadius: radius.xl,
    padding: space.lg,
    marginTop: space.md,
    borderWidth: 2,
    borderColor: colors.border,
  },
  stepCardDone: { borderColor: colors.live, backgroundColor: colors.successSoft },
  stepCardLocked: { opacity: 0.92 },
  stepHeader: {
    flexDirection: "row",
    alignItems: "center",
    gap: 10,
    marginBottom: space.sm,
  },
  stepBadge: {
    width: 32,
    height: 32,
    borderRadius: 16,
    alignItems: "center",
    justifyContent: "center",
  },
  stepBadgeDone: { backgroundColor: colors.success },
  stepBadgeTodo: { backgroundColor: colors.surfaceHover },
  stepBadgeText: { color: "#fff", fontWeight: font.weightBlack, fontSize: font.xl },
  stepTitle: {
    color: colors.text,
    fontSize: font.title,
    fontWeight: font.weightBlack,
    flex: 1,
  },
  stepBody: {
    color: colors.textSecondary,
    fontSize: font.body,
    lineHeight: 20,
    marginBottom: space.sm,
  },
  stepStatus: {
    color: colors.accentSoft,
    fontSize: font.md,
    fontWeight: font.weightSemi,
    marginBottom: space.md,
  },
  liveStrip: {
    backgroundColor: colors.bgElevated,
    borderRadius: radius.lg,
    borderWidth: 1,
    borderColor: colors.primarySoft,
    padding: space.md,
    marginTop: space.sm,
    marginBottom: 4,
  },
  liveStripTitle: {
    color: colors.textMuted,
    fontSize: font.sm,
    fontWeight: font.weightBold,
    marginBottom: space.sm,
  },
  liveStripRow: { flexDirection: "row", flexWrap: "wrap", gap: space.sm },
  liveChip: {
    backgroundColor: colors.surface,
    borderRadius: 10,
    paddingHorizontal: 10,
    paddingVertical: space.sm,
    minWidth: 72,
  },
  liveChipLab: { color: colors.textDim, fontSize: font.xs, fontWeight: font.weightSemi },
  liveChipVal: {
    color: colors.text,
    fontSize: font.lg,
    fontWeight: font.weightBlack,
    marginTop: 2,
  },
});
