/**
 * MULTI_VDF_HMI — React Native UI (parity with CustomTkinter)
 *
 * Backend: ./run_backend.sh  → http://127.0.0.1:8765
 */
import { StatusBar } from "expo-status-bar";
import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import {
  ActivityIndicator,
  Alert,
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

type Tab = "connect" | "params" | "edge";
type Mode = "mqtt" | "serial" | "bluetooth" | "ble" | "dummy";

const MODES: { id: Mode; label: string; transport: Transport }[] = [
  { id: "mqtt", label: "MQTT", transport: "mqtt" },
  { id: "serial", label: "USB", transport: "serial" },
  { id: "ble", label: "BLE NUS", transport: "ble" },
  { id: "bluetooth", label: "BT SPP", transport: "bluetooth" },
  { id: "dummy", label: "Simulado", transport: "dummy" },
];

const QUICK = [
  "help",
  "ping",
  "stream on",
  "stream off",
  "wifi status",
  "mqtt status",
  "bt status",
  "start",
  "stop",
];

export default function App() {
  const [tab, setTab] = useState<Tab>("connect");
  const [backendOk, setBackendOk] = useState<boolean | null>(null);
  const [wsState, setWsState] = useState<"open" | "close" | "error" | "idle">("idle");
  const [connected, setConnected] = useState(false);
  const [statusMsg, setStatusMsg] = useState("Desconectado");
  const [mode, setMode] = useState<Mode>("mqtt");
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

  // profiles
  const [profiles, setProfiles] = useState<ProfilesStore | null>(null);
  const [mqttName, setMqttName] = useState("");
  const [wifiName, setWifiName] = useState("");

  // param list
  const [plist, setPlist] = useState<ParameterList>(emptyList());
  const [listFile, setListFile] = useState("ejemplo_pdm30.json");
  const [listFiles, setListFiles] = useState<ParamFileInfo[]>([]);
  const [selectedKey, setSelectedKey] = useState<string | null>(null);
  const [edGroup, setEdGroup] = useState<"P0" | "P1">("P0");
  const [edIdx, setEdIdx] = useState("0");
  const [edVal, setEdVal] = useState("0");
  const [edNotes, setEdNotes] = useState("");
  const [edManual, setEdManual] = useState(false);

  // compare dump
  const dumpActive = useRef(false);
  const dumpMap = useRef<Record<string, number>>({});
  const dumpCount = useRef(0);
  const logRef = useRef<ScrollView>(null);

  // profile modal forms
  const [showProfiles, setShowProfiles] = useState(false);
  const [mForm, setMForm] = useState({
    name: "Local",
    host: "127.0.0.1",
    port: "1883",
    topic_prefix: "saj/pdm30/saj-pdm30",
    username: "",
    password: "",
  });
  const [wForm, setWForm] = useState({ name: "home", ssid: "", password: "" });

  const pushLog = useCallback((line: string) => {
    setLog((prev) => {
      const next = [...prev, line];
      return next.length > 500 ? next.slice(-500) : next;
    });
  }, []);

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
        Alert.alert("Ocupado", `Operación en curso: ${opName}`);
        return false;
      }
      setBusy(true);
      setOpName(name);
      setProgress(0.05);
      setStatusMsg(`Operación: ${name}…`);
      return true;
    },
    [busy, opName]
  );

  // --- backend + ws ---
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
          if (m.includes("usb") || m.includes("serial")) setMode("serial");
          else if (m.includes("ble") || m.includes("nus") || m.includes("le"))
            setMode("ble");
          else if (m.includes("spp") || m.includes("bluetooth")) setMode("bluetooth");
          else if (m.includes("simul") || m.includes("dummy")) setMode("dummy");
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
        if (!cancelled) setBackendOk(false);
      }
    })();

    const ws = openEventSocket(
      (ev) => {
        if (ev.type === "line" && typeof ev.payload === "string") {
          const line = ev.payload;
          pushLog(line);
          if (dumpActive.current) {
            if (line.startsWith("ERR:")) {
              dumpActive.current = false;
              endOp(`Comparar abortado: ${line}`);
              Alert.alert("Comparar", line);
              return;
            }
            const parsed = parseDumpCsvLine(line);
            if (parsed && parsed.eng != null) {
              dumpMap.current[`${parsed.group}:${parsed.index}`] = parsed.eng;
              dumpCount.current += 1;
              setProgress(Math.min(0.95, 0.1 + dumpCount.current / 100));
              setOpName(`compare ${dumpCount.current}/96`);
            }
            if (line.includes("DUMP done") || line.startsWith("CSV:END")) {
              dumpActive.current = false;
              const { list, mismatches } = applyCompare(plistRef.current, dumpMap.current);
              setPlist(list);
              setProgress(1);
              endOp(
                `Comparación: ${mismatches} dif. / ${list.parameters.length} (${Object.keys(dumpMap.current).length} leídos)`
              );
              Alert.alert(
                "Comparar con VDF",
                `${mismatches} diferencias o no leídos / ${list.parameters.length}\nRegistros dump: ${Object.keys(dumpMap.current).length}`
              );
            }
          }
        } else if (ev.type === "json" && ev.payload && typeof ev.payload === "object") {
          setTelemetry(ev.payload as Telemetry);
        } else if (ev.type === "status") {
          const st = String(ev.payload || "");
          const msg = String((ev.meta && ev.meta.message) || "");
          setConnected(st === "connected");
          if (msg) setStatusMsg(msg);
          if (st !== "connected" && busy) {
            endOp(`Conexión: ${st}`);
          }
        } else if (ev.type === "error") {
          pushLog(`ERR: ${String(ev.payload)}`);
          if (busy) endOp(`Error: ${ev.payload}`);
        } else if (ev.type === "hello") {
          pushLog("WS backend OK");
        }
      },
      (s) => setWsState(s)
    );
    return () => {
      cancelled = true;
      ws.close();
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  // keep latest plist for dump finish callback
  const plistRef = useRef(plist);
  useEffect(() => {
    plistRef.current = plist;
  }, [plist]);

  const refreshPorts = useCallback(async () => {
    try {
      const list = await api.ports();
      setPorts(list);
      if (list.length && !port) setPort(list[0].device);
    } catch (e) {
      pushLog(`ports: ${e}`);
    }
  }, [port, pushLog]);

  useEffect(() => {
    if (mode === "serial") refreshPorts();
  }, [mode, refreshPorts]);

  const scanBt = async () => {
    setScanning(true);
    pushLog(mode === "ble" ? "Escaneando BLE…" : "Escaneando BT Classic…");
    try {
      const devs = mode === "ble" ? await api.btBle(8) : await api.btClassic(10);
      setBtDevices(devs);
      if (devs.length) {
        const saj = devs.find((d) => /SAJ|PDM/i.test(d.name)) || devs[0];
        setBtAddress(saj.address);
        pushLog(`BT: ${devs.length} dispositivo(s)`);
      } else pushLog("BT: ninguno");
    } catch (e) {
      pushLog(`BT: ${e}`);
    } finally {
      setScanning(false);
    }
  };

  const doConnect = async () => {
    setBusy(true);
    setOpName("connect");
    try {
      const m = MODES.find((x) => x.id === mode)!;
      let body: Parameters<typeof api.connect>[0];
      if (mode === "serial") {
        body = {
          transport: "serial",
          port: port || "/dev/ttyACM0",
          baud: parseInt(baud, 10) || 115200,
        };
        await api.patchLasts({
          last_mode: "USB (Serial)",
          last_serial_port: body.port,
          last_serial_baud: body.baud,
        });
      } else if (mode === "mqtt") {
        const pr = profiles || (await api.profiles());
        const mp =
          pr.mqtt_profiles.find((p) => p.name === mqttName) || pr.mqtt_profiles[0];
        if (!mp?.host) throw new Error("Crea un perfil MQTT (pestaña Edge)");
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
        if (!btAddress) throw new Error("Escanea y elige un dispositivo BT");
        body = { transport: m.transport, address: btAddress, pair: true };
        await api.patchLasts({
          last_mode: mode === "ble" ? "Bluetooth LE (NUS)" : "Bluetooth (SPP)",
          last_bt_address: btAddress,
        });
      } else {
        body = { transport: "dummy" };
        await api.patchLasts({ last_mode: "Simulado (Dummy)" });
      }
      const r = await api.connect(body);
      pushLog(`OK ${r.detail}`);
      setConnected(true);
      setStatusMsg("Conectado — stream on…");
      // delayed stream on (USB may reset MCU)
      const delay =
        mode === "serial" ? 2500 : mode === "bluetooth" || mode === "ble" ? 1500 : 800;
      setTimeout(async () => {
        try {
          await api.command("stream on");
          pushLog("→ stream on");
        } catch (e) {
          pushLog(`stream on: ${e}`);
        }
      }, delay);
    } catch (e) {
      pushLog(`Connect: ${e}`);
      Alert.alert("Conexión", String(e));
      setConnected(false);
    } finally {
      setBusy(false);
      setOpName("");
    }
  };

  const doDisconnect = async () => {
    try {
      try {
        await api.command("stream off");
      } catch {
        /* ignore */
      }
      await api.disconnect();
      setConnected(false);
      setStatusMsg("Desconectado");
      pushLog("Desconectado");
    } catch (e) {
      pushLog(`Disconnect: ${e}`);
    }
  };

  const sendCmd = async (line?: string) => {
    const text = (line ?? cmd).trim();
    if (!text) return;
    if (!connected) {
      Alert.alert("Sin conexión", "Conecta primero.");
      return;
    }
    pushLog(`→ ${text}`);
    try {
      await api.command(text);
      if (!line) setCmd("");
    } catch (e) {
      pushLog(`cmd: ${e}`);
    }
  };

  const loadList = async (filename: string) => {
    try {
      const r = await api.getParamList(filename);
      setListFile(r.filename);
      setPlist(r.list);
      setSelectedKey(null);
      setStatusMsg(`Cargado ${r.filename}`);
    } catch (e) {
      Alert.alert("Abrir lista", String(e));
    }
  };

  const saveList = async () => {
    try {
      const name = listFile || `${plist.name || "lista"}.json`;
      const r = await api.putParamList(name, plist);
      setListFile(r.filename);
      setPlist(r.list);
      const files = await api.paramListFiles();
      setListFiles(files.files);
      setStatusMsg(`Guardado ${r.filename}`);
      pushLog(`Guardado ${r.filename}`);
    } catch (e) {
      Alert.alert("Guardar", String(e));
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
      setStatusMsg(`Guardado ${paramId(p)} = ${p.value}`);
    } catch (e) {
      Alert.alert("Validación", String(e));
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

  const syncVfd = async () => {
    if (!connected) {
      Alert.alert("Sync", "Sin conexión");
      return;
    }
    const items = writable(plist);
    if (!items.length) {
      Alert.alert("Sync", "No hay parámetros enviables");
      return;
    }
    if (!beginOp("sync")) return;
    try {
      const total = items.length;
      for (let i = 0; i < total; i++) {
        const p = items[i];
        const c = `w${p.group} ${p.index} ${Number(p.value)}`;
        await api.command(c);
        pushLog(`→ ${c}`);
        setProgress((i + 1) / total);
        setStatusMsg(`Sync ${i + 1}/${total}`);
        await sleep(150);
      }
      endOp("Sincronización enviada");
    } catch (e) {
      endOp(`Sync error: ${e}`);
      Alert.alert("Sync", String(e));
    }
  };

  const compareVfd = async () => {
    if (!connected) {
      Alert.alert("Comparar", "Sin conexión");
      return;
    }
    if (!plist.parameters.length) {
      Alert.alert("Comparar", "Lista vacía");
      return;
    }
    if (!beginOp("compare")) return;
    dumpActive.current = true;
    dumpMap.current = {};
    dumpCount.current = 0;
    setPlist((pl) => clearCompare(pl));
    try {
      await api.command("stream off");
      pushLog("→ stream off");
      await api.command("dump");
      pushLog("→ dump");
      setStatusMsg("Comparando (dump en curso)…");
      // safety timeout 120s
      setTimeout(() => {
        if (dumpActive.current) {
          dumpActive.current = false;
          const { list, mismatches } = applyCompare(plistRef.current, dumpMap.current);
          setPlist(list);
          endOp(
            `Timeout compare: ${mismatches} dif. / ${Object.keys(dumpMap.current).length} leídos`
          );
          Alert.alert(
            "Timeout",
            "El dump no terminó a tiempo. Se aplicó comparación parcial."
          );
        }
      }, 120000);
    } catch (e) {
      dumpActive.current = false;
      endOp(`No se pudo iniciar dump: ${e}`);
      Alert.alert("Comparar", String(e));
    }
  };

  const reloadProfiles = async () => {
    try {
      const pr = await api.profiles();
      setProfiles(pr);
    } catch (e) {
      pushLog(`profiles: ${e}`);
    }
  };

  const saveMqttProfile = async () => {
    try {
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
      Alert.alert("MQTT", "Perfil guardado");
    } catch (e) {
      Alert.alert("MQTT", String(e));
    }
  };

  const saveWifiProfile = async () => {
    try {
      const pr = await api.upsertWifi({
        name: wForm.name.trim() || "wifi",
        ssid: wForm.ssid.trim(),
        password: wForm.password,
      });
      setProfiles(pr);
      setWifiName(wForm.name.trim() || "wifi");
      Alert.alert("Wi‑Fi", "Perfil guardado en PC");
    } catch (e) {
      Alert.alert("Wi‑Fi", String(e));
    }
  };

  const applyWifiToEdge = async () => {
    if (!connected) {
      Alert.alert("Edge", "Conecta primero");
      return;
    }
    const pr = profiles || (await api.profiles());
    const wp = pr.wifi_profiles.find((p) => p.name === wifiName) || pr.wifi_profiles[0];
    if (!wp) {
      Alert.alert("Wi‑Fi", "Crea un perfil Wi‑Fi");
      return;
    }
    const pwd = wp.password || '""';
    try {
      await api.command(`wifi profile save ${wp.name} ${wp.ssid} ${pwd}`);
      await api.command(`wifi profile use ${wp.name}`);
      pushLog(`→ wifi profile use ${wp.name}`);
      await api.patchLasts({ last_wifi: wp.name });
      Alert.alert("OK", `Wi‑Fi «${wp.name}» enviado al Edge`);
    } catch (e) {
      Alert.alert("Error", String(e));
    }
  };

  const applyMqttToEdge = async () => {
    if (!connected) {
      Alert.alert("Edge", "Conecta primero");
      return;
    }
    const pr = profiles || (await api.profiles());
    const mp = pr.mqtt_profiles.find((p) => p.name === mqttName) || pr.mqtt_profiles[0];
    if (!mp) {
      Alert.alert("MQTT", "Crea un perfil MQTT");
      return;
    }
    try {
      await api.command(`mqtt set ${mp.host} ${mp.port}`);
      if (mp.username) {
        await api.command(`mqtt user ${mp.username} ${mp.password || '""'}`);
      }
      await api.command("mqtt enable");
      pushLog(`→ mqtt set ${mp.host}:${mp.port}`);
      await api.patchLasts({ last_mqtt: mp.name });
      Alert.alert("OK", `Broker «${mp.name}» en el Edge`);
    } catch (e) {
      Alert.alert("Error", String(e));
    }
  };

  const telCards = useMemo(
    () => [
      { k: "freq", label: "Freq", u: "Hz", v: telemetry.freq },
      { k: "amp", label: "I", u: "A", v: telemetry.amp },
      { k: "vdc", label: "Vbus", u: "V", v: telemetry.vdc },
      { k: "vout", label: "Vout", u: "V", v: telemetry.vout },
      { k: "pfb", label: "P real", u: "bar", v: telemetry.pfb },
      { k: "pset", label: "P set", u: "bar", v: telemetry.pset },
      { k: "status", label: "Estado", u: "", v: telemetry.status },
    ],
    [telemetry]
  );

  return (
    <SafeAreaView style={styles.root}>
      <StatusBar style="light" />
      <View style={styles.header}>
        <Text style={styles.title}>MULTI_VDF_HMI</Text>
        <Text style={styles.sub}>{apiBase()}</Text>
        <View style={styles.row}>
          <Badge ok={backendOk === true} label={backendOk ? "API" : "API off"} />
          <Badge ok={wsState === "open"} label={`WS ${wsState}`} />
          <Badge ok={connected} label={connected ? "Link" : "Offline"} />
          {busy ? <Badge ok={false} label={opName || "…"} /> : null}
        </View>
        <Text style={styles.muted}>{statusMsg}</Text>
        {busy ? (
          <View style={styles.progressTrack}>
            <View style={[styles.progressFill, { width: `${Math.round(progress * 100)}%` }]} />
          </View>
        ) : null}
        <View style={styles.tabs}>
          {(
            [
              ["connect", "Conexión"],
              ["params", "Parámetros"],
              ["edge", "Edge / Perfiles"],
            ] as const
          ).map(([id, lab]) => (
            <Pressable
              key={id}
              onPress={() => setTab(id)}
              style={[styles.tab, tab === id && styles.tabOn]}
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
        {tab === "connect" && (
          <>
            <Text style={styles.section}>Modo</Text>
            <View style={styles.chips}>
              {MODES.map((m) => (
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
                <Text style={styles.label}>Puerto / baud</Text>
                <View style={styles.row}>
                  <TextInput
                    style={[styles.input, { flex: 1 }]}
                    value={port}
                    onChangeText={setPort}
                    placeholder="/dev/ttyACM0"
                    placeholderTextColor="#6b7280"
                    editable={!connected}
                  />
                  <Pressable style={styles.btnSec} onPress={refreshPorts}>
                    <Text style={styles.btnText}>↻</Text>
                  </Pressable>
                </View>
                {ports.map((p) => (
                  <Pressable key={p.device} onPress={() => setPort(p.device)}>
                    <Text style={styles.hint}>
                      {p.device} — {p.description}
                    </Text>
                  </Pressable>
                ))}
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
              </View>
            )}

            {mode === "mqtt" && (
              <View style={styles.block}>
                <Text style={styles.label}>Perfil MQTT</Text>
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
                <Pressable style={styles.btnSec} onPress={() => setShowProfiles(true)}>
                  <Text style={styles.btnText}>Editar perfiles…</Text>
                </Pressable>
              </View>
            )}

            {(mode === "bluetooth" || mode === "ble") && (
              <View style={styles.block}>
                <View style={styles.row}>
                  <Text style={[styles.label, { flex: 1 }]}>Dispositivo</Text>
                  <Pressable
                    style={styles.btnSec}
                    onPress={scanBt}
                    disabled={scanning || connected}
                  >
                    {scanning ? (
                      <ActivityIndicator color="#fff" />
                    ) : (
                      <Text style={styles.btnText}>Escanear BT</Text>
                    )}
                  </Pressable>
                </View>
                <TextInput
                  style={styles.input}
                  value={btAddress}
                  onChangeText={setBtAddress}
                  placeholder="AA:BB:CC:DD:EE:FF"
                  placeholderTextColor="#6b7280"
                  editable={!connected}
                  autoCapitalize="characters"
                />
                {btDevices.map((d) => (
                  <Pressable key={d.address} onPress={() => setBtAddress(d.address)}>
                    <Text
                      style={[
                        styles.hint,
                        d.address === btAddress && styles.hintOn,
                      ]}
                    >
                      {d.name} [{d.address}]
                      {d.paired ? " ✓" : " (nuevo)"}
                    </Text>
                  </Pressable>
                ))}
              </View>
            )}

            <View style={styles.row}>
              {!connected ? (
                <Pressable
                  style={[styles.btnPri, busy && styles.dis]}
                  onPress={doConnect}
                  disabled={busy}
                >
                  <Text style={styles.btnText}>Conectar</Text>
                </Pressable>
              ) : (
                <Pressable style={styles.btnDanger} onPress={doDisconnect}>
                  <Text style={styles.btnText}>Desconectar</Text>
                </Pressable>
              )}
              <Pressable
                style={styles.btnSec}
                onPress={() => setShowProfiles(true)}
              >
                <Text style={styles.btnText}>Perfiles…</Text>
              </Pressable>
            </View>

            <Text style={styles.section}>Telemetría</Text>
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

            <Text style={styles.section}>CLI / acciones rápidas</Text>
            <View style={styles.chips}>
              {QUICK.map((c) => (
                <Chip key={c} label={c} onPress={() => sendCmd(c)} disabled={!connected} />
              ))}
            </View>
            <View style={styles.logBox}>
              <ScrollView
                ref={logRef}
                onContentSizeChange={() =>
                  logRef.current?.scrollToEnd({ animated: true })
                }
              >
                {log.length === 0 ? (
                  <Text style={styles.muted}>Sin mensajes…</Text>
                ) : (
                  log.map((l, i) => (
                    <Text key={`${i}-${l.slice(0, 8)}`} style={styles.logLine}>
                      {l}
                    </Text>
                  ))
                )}
              </ScrollView>
            </View>
            <View style={styles.row}>
              <TextInput
                style={[styles.input, { flex: 1, marginBottom: 0 }]}
                value={cmd}
                onChangeText={setCmd}
                placeholder="comando…"
                placeholderTextColor="#6b7280"
                onSubmitEditing={() => sendCmd()}
                editable={connected}
              />
              <Pressable
                style={[styles.btnPri, !connected && styles.dis]}
                onPress={() => sendCmd()}
                disabled={!connected}
              >
                <Text style={styles.btnText}>Enviar</Text>
              </Pressable>
            </View>
          </>
        )}

        {tab === "params" && (
          <>
            <Text style={styles.section}>
              Lista: {plist.name} ({plist.parameters.length})
            </Text>
            <Text style={styles.label}>Archivo en servidor (param_lists/)</Text>
            <View style={styles.chips}>
              {listFiles.map((f) => (
                <Chip
                  key={f.filename}
                  label={`${f.stem} (${f.count})`}
                  active={listFile === f.filename}
                  onPress={() => loadList(f.filename)}
                />
              ))}
            </View>
            <View style={styles.row}>
              <Pressable style={styles.btnSec} onPress={saveList}>
                <Text style={styles.btnText}>Guardar</Text>
              </Pressable>
              <Pressable
                style={styles.btnPri}
                onPress={syncVfd}
                disabled={!connected || busy}
              >
                <Text style={styles.btnText}>Sync → VDF</Text>
              </Pressable>
              <Pressable
                style={styles.btnPri}
                onPress={compareVfd}
                disabled={!connected || busy}
              >
                <Text style={styles.btnText}>Comparar</Text>
              </Pressable>
              {busy ? (
                <Pressable style={styles.btnWarn} onPress={() => endOp("Cancelado")}>
                  <Text style={styles.btnText}>Cancelar</Text>
                </Pressable>
              ) : null}
            </View>

            <View style={styles.tableHead}>
              <Text style={[styles.th, { flex: 1 }]}>ID</Text>
              <Text style={[styles.th, { flex: 1 }]}>Valor</Text>
              <Text style={[styles.th, { flex: 1 }]}>VDF</Text>
              <Text style={[styles.th, { flex: 2 }]}>Notas</Text>
            </View>
            {plist.parameters.map((p) => {
              const key = `${p.group}:${p.index}`;
              const sel = selectedKey === key;
              const bg = p.mismatch
                ? "#7f1d1d"
                : p.manual_only
                  ? "#422006"
                  : sel
                    ? "#1e3a5f"
                    : "#1e293b";
              return (
                <Pressable
                  key={key}
                  onPress={() => selectParam(p)}
                  style={[styles.tr, { backgroundColor: bg }]}
                >
                  <Text style={[styles.td, { flex: 1 }]}>{paramId(p)}</Text>
                  <Text style={[styles.td, { flex: 1 }]}>{p.value}</Text>
                  <Text style={[styles.td, { flex: 1 }]}>
                    {p.live_value == null ? "—" : p.live_value}
                  </Text>
                  <Text style={[styles.td, { flex: 2 }]} numberOfLines={1}>
                    {p.manual_only ? "MAN " : ""}
                    {p.notes}
                  </Text>
                </Pressable>
              );
            })}

            <Text style={styles.section}>Editor</Text>
            <View style={styles.chips}>
              <Chip label="P0" active={edGroup === "P0"} onPress={() => setEdGroup("P0")} />
              <Chip label="P1" active={edGroup === "P1"} onPress={() => setEdGroup("P1")} />
            </View>
            <Text style={styles.label}>Índice 0–47</Text>
            <TextInput
              style={styles.input}
              value={edIdx}
              onChangeText={setEdIdx}
              keyboardType="numeric"
              placeholderTextColor="#6b7280"
            />
            <Text style={styles.label}>Valor (ingeniería)</Text>
            <TextInput
              style={styles.input}
              value={edVal}
              onChangeText={setEdVal}
              keyboardType="decimal-pad"
              placeholderTextColor="#6b7280"
            />
            <Text style={styles.label}>Notas</Text>
            <TextInput
              style={[styles.input, { minHeight: 64 }]}
              value={edNotes}
              onChangeText={setEdNotes}
              multiline
              placeholderTextColor="#6b7280"
            />
            <View style={styles.row}>
              <Switch value={edManual} onValueChange={setEdManual} />
              <Text style={styles.hint}>Manual (ignorar en sync RS485)</Text>
            </View>
            <View style={styles.row}>
              <Pressable style={styles.btnPri} onPress={addParam}>
                <Text style={styles.btnText}>Añadir / Actualizar</Text>
              </Pressable>
              <Pressable style={styles.btnDanger} onPress={delParam}>
                <Text style={styles.btnText}>Eliminar</Text>
              </Pressable>
            </View>
          </>
        )}

        {tab === "edge" && (
          <>
            <Text style={styles.section}>Aplicar al Edge (Serial/MQTT/BT)</Text>
            <Text style={styles.label}>Perfil Wi‑Fi → Edge</Text>
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
              style={[styles.btnPri, !connected && styles.dis]}
              onPress={applyWifiToEdge}
              disabled={!connected}
            >
              <Text style={styles.btnText}>Aplicar Wi‑Fi al Edge</Text>
            </Pressable>

            <Text style={[styles.label, { marginTop: 16 }]}>Perfil MQTT → Edge</Text>
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
              style={[styles.btnPri, !connected && styles.dis]}
              onPress={applyMqttToEdge}
              disabled={!connected}
            >
              <Text style={styles.btnText}>Aplicar MQTT al Edge</Text>
            </Pressable>
            <View style={styles.row}>
              <Chip label="wifi status" onPress={() => sendCmd("wifi status")} disabled={!connected} />
              <Chip label="mqtt status" onPress={() => sendCmd("mqtt status")} disabled={!connected} />
            </View>

            <Pressable style={[styles.btnSec, { marginTop: 16 }]} onPress={() => setShowProfiles(true)}>
              <Text style={styles.btnText}>Crear / editar perfiles en PC…</Text>
            </Pressable>
            <Pressable style={styles.btnSec} onPress={reloadProfiles}>
              <Text style={styles.btnText}>Recargar perfiles</Text>
            </Pressable>
          </>
        )}

        <Text style={styles.footer}>
          Paridad CTk · {Platform.OS} · listas en backend/param_lists
        </Text>
      </ScrollView>

      <Modal visible={showProfiles} animationType="slide" transparent>
        <View style={styles.modalBg}>
          <ScrollView style={styles.modalCard} contentContainerStyle={{ padding: 16 }}>
            <Text style={styles.title}>Perfiles PC</Text>
            <Text style={styles.section}>MQTT</Text>
            {(
              [
                ["name", "Nombre"],
                ["host", "Host"],
                ["port", "Puerto"],
                ["topic_prefix", "Topic prefix"],
                ["username", "Usuario"],
                ["password", "Password"],
              ] as const
            ).map(([k, lab]) => (
              <View key={k}>
                <Text style={styles.label}>{lab}</Text>
                <TextInput
                  style={styles.input}
                  value={mForm[k]}
                  onChangeText={(t) => setMForm((f) => ({ ...f, [k]: t }))}
                  secureTextEntry={k === "password"}
                  placeholderTextColor="#6b7280"
                />
              </View>
            ))}
            <Pressable style={styles.btnPri} onPress={saveMqttProfile}>
              <Text style={styles.btnText}>Guardar perfil MQTT</Text>
            </Pressable>

            <Text style={styles.section}>Wi‑Fi (para enviar al Edge)</Text>
            {(
              [
                ["name", "Nombre"],
                ["ssid", "SSID"],
                ["password", "Password"],
              ] as const
            ).map(([k, lab]) => (
              <View key={k}>
                <Text style={styles.label}>{lab}</Text>
                <TextInput
                  style={styles.input}
                  value={wForm[k]}
                  onChangeText={(t) => setWForm((f) => ({ ...f, [k]: t }))}
                  secureTextEntry={k === "password"}
                  placeholderTextColor="#6b7280"
                />
              </View>
            ))}
            <Pressable style={styles.btnPri} onPress={saveWifiProfile}>
              <Text style={styles.btnText}>Guardar perfil Wi‑Fi</Text>
            </Pressable>
            <Pressable
              style={[styles.btnSec, { marginTop: 12 }]}
              onPress={() => setShowProfiles(false)}
            >
              <Text style={styles.btnText}>Cerrar</Text>
            </Pressable>
          </ScrollView>
        </View>
      </Modal>
    </SafeAreaView>
  );
}

function sleep(ms: number) {
  return new Promise((r) => setTimeout(r, ms));
}

function Badge({ ok, label }: { ok: boolean; label: string }) {
  return (
    <View style={[styles.badge, ok ? styles.badgeOk : styles.badgeBad]}>
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
    >
      <Text style={styles.chipText}>{label}</Text>
    </Pressable>
  );
}

const styles = StyleSheet.create({
  root: { flex: 1, backgroundColor: "#0f172a" },
  header: { paddingHorizontal: 16, paddingTop: 8, paddingBottom: 4 },
  pad: { padding: 16, paddingBottom: 48 },
  title: { color: "#f8fafc", fontSize: 20, fontWeight: "700" },
  sub: { color: "#94a3b8", fontSize: 11, marginBottom: 6 },
  section: {
    color: "#e2e8f0",
    fontSize: 15,
    fontWeight: "600",
    marginTop: 16,
    marginBottom: 8,
  },
  row: { flexDirection: "row", alignItems: "center", flexWrap: "wrap", gap: 8, marginVertical: 6 },
  chips: { flexDirection: "row", flexWrap: "wrap", gap: 8 },
  chip: {
    backgroundColor: "#1e293b",
    paddingHorizontal: 12,
    paddingVertical: 8,
    borderRadius: 999,
    borderWidth: 1,
    borderColor: "#334155",
  },
  chipOn: { backgroundColor: "#1d4ed8", borderColor: "#3b82f6" },
  chipText: { color: "#f1f5f9", fontSize: 12 },
  tabs: { flexDirection: "row", gap: 8, marginTop: 10 },
  tab: {
    flex: 1,
    paddingVertical: 10,
    borderRadius: 10,
    backgroundColor: "#1e293b",
    alignItems: "center",
  },
  tabOn: { backgroundColor: "#2563eb" },
  tabText: { color: "#f8fafc", fontWeight: "600", fontSize: 12 },
  block: { marginTop: 8 },
  label: { color: "#cbd5e1", marginBottom: 4, marginTop: 6, fontSize: 12 },
  input: {
    backgroundColor: "#1e293b",
    borderColor: "#334155",
    borderWidth: 1,
    borderRadius: 10,
    color: "#f8fafc",
    paddingHorizontal: 12,
    paddingVertical: 10,
    marginBottom: 8,
  },
  btnPri: {
    backgroundColor: "#2563eb",
    paddingHorizontal: 14,
    paddingVertical: 12,
    borderRadius: 10,
  },
  btnSec: {
    backgroundColor: "#334155",
    paddingHorizontal: 14,
    paddingVertical: 12,
    borderRadius: 10,
  },
  btnDanger: {
    backgroundColor: "#b91c1c",
    paddingHorizontal: 14,
    paddingVertical: 12,
    borderRadius: 10,
  },
  btnWarn: {
    backgroundColor: "#b45309",
    paddingHorizontal: 14,
    paddingVertical: 12,
    borderRadius: 10,
  },
  btnText: { color: "#fff", fontWeight: "600", fontSize: 13 },
  dis: { opacity: 0.45 },
  badge: { paddingHorizontal: 8, paddingVertical: 3, borderRadius: 6 },
  badgeOk: { backgroundColor: "#14532d" },
  badgeBad: { backgroundColor: "#7f1d1d" },
  badgeText: { color: "#f8fafc", fontSize: 10 },
  muted: { color: "#64748b", fontSize: 12 },
  hint: { color: "#94a3b8", fontSize: 12, marginBottom: 3 },
  hintOn: { color: "#93c5fd" },
  progressTrack: {
    height: 4,
    backgroundColor: "#1e293b",
    borderRadius: 2,
    marginTop: 6,
    overflow: "hidden",
  },
  progressFill: { height: 4, backgroundColor: "#fbbf24" },
  telGrid: { flexDirection: "row", flexWrap: "wrap", gap: 8 },
  telCard: {
    backgroundColor: "#1e293b",
    borderRadius: 12,
    padding: 10,
    minWidth: 88,
    flexGrow: 1,
  },
  telLabel: { color: "#94a3b8", fontSize: 10 },
  telValue: { color: "#f8fafc", fontSize: 16, fontWeight: "700", marginTop: 2 },
  logBox: {
    backgroundColor: "#020617",
    borderRadius: 12,
    borderWidth: 1,
    borderColor: "#1e293b",
    height: 160,
    padding: 8,
    marginVertical: 8,
  },
  logLine: {
    color: "#cbd5e1",
    fontFamily: Platform.OS === "ios" ? "Menlo" : "monospace",
    fontSize: 10,
  },
  tableHead: {
    flexDirection: "row",
    paddingVertical: 6,
    borderBottomWidth: 1,
    borderBottomColor: "#334155",
  },
  th: { color: "#94a3b8", fontWeight: "700", fontSize: 11 },
  tr: {
    flexDirection: "row",
    paddingVertical: 8,
    paddingHorizontal: 4,
    borderRadius: 6,
    marginTop: 3,
  },
  td: { color: "#e2e8f0", fontSize: 11 },
  modalBg: {
    flex: 1,
    backgroundColor: "rgba(0,0,0,0.7)",
    justifyContent: "center",
    padding: 16,
  },
  modalCard: {
    backgroundColor: "#0f172a",
    borderRadius: 16,
    maxHeight: "90%",
    borderWidth: 1,
    borderColor: "#334155",
  },
  footer: { color: "#475569", fontSize: 11, marginTop: 24, textAlign: "center" },
});
