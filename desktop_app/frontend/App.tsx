/**
 * MULTI_VDF_HMI — React Native UI (Expo)
 *
 * Talks only to the local Python backend (USB / MQTT / BT / BLE).
 * Run backend:  cd desktop_app && ./run_backend.sh
 * Run UI:       cd desktop_app/frontend && npm run web
 */
import { StatusBar } from "expo-status-bar";
import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import {
  ActivityIndicator,
  Platform,
  Pressable,
  SafeAreaView,
  ScrollView,
  StyleSheet,
  Text,
  TextInput,
  View,
} from "react-native";

import { api, apiBase, openEventSocket } from "./src/api/client";
import type {
  BtDevice,
  PortInfo,
  Telemetry,
  Transport,
} from "./src/api/types";

const TRANSPORTS: { id: Transport; label: string }[] = [
  { id: "dummy", label: "Simulado" },
  { id: "serial", label: "USB" },
  { id: "mqtt", label: "MQTT" },
  { id: "bluetooth", label: "BT SPP" },
  { id: "ble", label: "BLE NUS" },
];

const QUICK_CMDS = ["help", "ping", "wifi status", "mqtt status", "bt status", "stream on", "stream off"];

export default function App() {
  const [backendOk, setBackendOk] = useState<boolean | null>(null);
  const [wsState, setWsState] = useState<"open" | "close" | "error" | "idle">("idle");
  const [connected, setConnected] = useState(false);
  const [statusMsg, setStatusMsg] = useState("desconectado");
  const [transport, setTransport] = useState<Transport>("dummy");
  const [ports, setPorts] = useState<PortInfo[]>([]);
  const [port, setPort] = useState("");
  const [host, setHost] = useState("127.0.0.1");
  const [mqttPort, setMqttPort] = useState("1883");
  const [btDevices, setBtDevices] = useState<BtDevice[]>([]);
  const [btAddress, setBtAddress] = useState("");
  const [scanning, setScanning] = useState(false);
  const [busy, setBusy] = useState(false);
  const [telemetry, setTelemetry] = useState<Telemetry>({});
  const [log, setLog] = useState<string[]>([]);
  const [cmd, setCmd] = useState("");
  const logRef = useRef<ScrollView>(null);
  const wsRef = useRef<WebSocket | null>(null);

  const pushLog = useCallback((line: string) => {
    setLog((prev) => {
      const next = [...prev, line];
      return next.length > 400 ? next.slice(-400) : next;
    });
  }, []);

  // Health + WebSocket
  useEffect(() => {
    let cancelled = false;
    (async () => {
      try {
        await api.health();
        if (!cancelled) setBackendOk(true);
      } catch {
        if (!cancelled) setBackendOk(false);
      }
    })();

    const ws = openEventSocket(
      (ev) => {
        if (ev.type === "line" && typeof ev.payload === "string") {
          pushLog(ev.payload);
        } else if (ev.type === "json" && ev.payload && typeof ev.payload === "object") {
          setTelemetry(ev.payload as Telemetry);
        } else if (ev.type === "status") {
          const st = String(ev.payload || "");
          const msg = String((ev.meta && ev.meta.message) || "");
          setConnected(st === "connected");
          if (msg) setStatusMsg(msg);
          else setStatusMsg(st);
        } else if (ev.type === "error") {
          pushLog(`ERR: ${String(ev.payload)}`);
        } else if (ev.type === "hello") {
          pushLog("WS: backend conectado");
        }
      },
      (s) => setWsState(s)
    );
    wsRef.current = ws;
    return () => {
      cancelled = true;
      ws.close();
    };
  }, [pushLog]);

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
    if (transport === "serial") refreshPorts();
  }, [transport, refreshPorts]);

  const scanBt = async () => {
    setScanning(true);
    pushLog(transport === "ble" ? "Escaneando BLE…" : "Escaneando BT Classic…");
    try {
      const devs =
        transport === "ble" ? await api.btBle(8) : await api.btClassic(10);
      setBtDevices(devs);
      if (devs.length) {
        const saj = devs.find((d) => /SAJ|PDM/i.test(d.name)) || devs[0];
        setBtAddress(saj.address);
        pushLog(`BT: ${devs.length} dispositivo(s)`);
      } else {
        pushLog("BT: ninguno encontrado");
      }
    } catch (e) {
      pushLog(`BT scan: ${e}`);
    } finally {
      setScanning(false);
    }
  };

  const doConnect = async () => {
    setBusy(true);
    try {
      const body =
        transport === "serial"
          ? { transport, port: port || "/dev/ttyACM0", baud: 115200 }
          : transport === "mqtt"
            ? {
                transport,
                host,
                mqtt_port: parseInt(mqttPort || "1883", 10),
                topic_prefix: "saj/pdm30/saj-pdm30",
              }
            : transport === "bluetooth" || transport === "ble"
              ? { transport, address: btAddress, pair: true }
              : { transport: "dummy" as Transport };
      const r = await api.connect(body);
      pushLog(`OK ${r.detail}`);
      setConnected(true);
    } catch (e) {
      pushLog(`Connect: ${e}`);
      setConnected(false);
    } finally {
      setBusy(false);
    }
  };

  const doDisconnect = async () => {
    setBusy(true);
    try {
      await api.disconnect();
      setConnected(false);
      setStatusMsg("disconnected");
      pushLog("Desconectado");
    } catch (e) {
      pushLog(`Disconnect: ${e}`);
    } finally {
      setBusy(false);
    }
  };

  const sendCmd = async (line?: string) => {
    const text = (line ?? cmd).trim();
    if (!text) return;
    pushLog(`>>> ${text}`);
    try {
      await api.command(text);
      if (!line) setCmd("");
    } catch (e) {
      pushLog(`cmd: ${e}`);
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
      <ScrollView contentContainerStyle={styles.pad} keyboardShouldPersistTaps="handled">
        <Text style={styles.title}>MULTI_VDF_HMI</Text>
        <Text style={styles.sub}>
          React Native UI · backend Python @ {apiBase()}
        </Text>

        <View style={styles.row}>
          <Badge
            ok={backendOk === true}
            label={
              backendOk === null
                ? "API…"
                : backendOk
                  ? "API OK"
                  : "API off — ./run_backend.sh"
            }
          />
          <Badge ok={wsState === "open"} label={`WS ${wsState}`} />
          <Badge ok={connected} label={connected ? "Link" : "Offline"} />
        </View>
        <Text style={styles.muted}>{statusMsg}</Text>

        <Text style={styles.section}>Transporte</Text>
        <View style={styles.chips}>
          {TRANSPORTS.map((t) => (
            <Chip
              key={t.id}
              active={transport === t.id}
              label={t.label}
              onPress={() => setTransport(t.id)}
              disabled={connected}
            />
          ))}
        </View>

        {transport === "serial" && (
          <View style={styles.block}>
            <Text style={styles.label}>Puerto USB</Text>
            <View style={styles.row}>
              <TextInput
                style={[styles.input, { flex: 1 }]}
                value={port}
                onChangeText={setPort}
                placeholder="/dev/ttyACM0 o COMx"
                placeholderTextColor="#6b7280"
                editable={!connected}
              />
              <Pressable style={styles.btnSecondary} onPress={refreshPorts}>
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
          </View>
        )}

        {transport === "mqtt" && (
          <View style={styles.block}>
            <Text style={styles.label}>Broker MQTT</Text>
            <TextInput
              style={styles.input}
              value={host}
              onChangeText={setHost}
              placeholder="host"
              placeholderTextColor="#6b7280"
              editable={!connected}
            />
            <TextInput
              style={styles.input}
              value={mqttPort}
              onChangeText={setMqttPort}
              placeholder="1883"
              placeholderTextColor="#6b7280"
              keyboardType="numeric"
              editable={!connected}
            />
          </View>
        )}

        {(transport === "bluetooth" || transport === "ble") && (
          <View style={styles.block}>
            <View style={styles.row}>
              <Text style={[styles.label, { flex: 1 }]}>Dispositivo</Text>
              <Pressable
                style={styles.btnSecondary}
                onPress={scanBt}
                disabled={scanning || connected}
              >
                {scanning ? (
                  <ActivityIndicator color="#fff" />
                ) : (
                  <Text style={styles.btnText}>Escanear</Text>
                )}
              </Pressable>
            </View>
            <TextInput
              style={styles.input}
              value={btAddress}
              onChangeText={setBtAddress}
              placeholder="AA:BB:CC:DD:EE:FF"
              placeholderTextColor="#6b7280"
              autoCapitalize="characters"
              editable={!connected}
            />
            {btDevices.map((d) => (
              <Pressable key={d.address} onPress={() => setBtAddress(d.address)}>
                <Text
                  style={[
                    styles.hint,
                    d.address === btAddress && styles.hintActive,
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
              style={[styles.btnPrimary, busy && styles.btnDisabled]}
              onPress={doConnect}
              disabled={busy}
            >
              <Text style={styles.btnText}>Conectar</Text>
            </Pressable>
          ) : (
            <Pressable
              style={[styles.btnDanger, busy && styles.btnDisabled]}
              onPress={doDisconnect}
              disabled={busy}
            >
              <Text style={styles.btnText}>Desconectar</Text>
            </Pressable>
          )}
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
                    ? c.v.toFixed(c.k === "status" ? 0 : 2)
                    : String(c.v)}
                {c.u ? ` ${c.u}` : ""}
              </Text>
            </View>
          ))}
        </View>

        <Text style={styles.section}>CLI</Text>
        <View style={styles.chips}>
          {QUICK_CMDS.map((c) => (
            <Chip
              key={c}
              label={c}
              onPress={() => sendCmd(c)}
              disabled={!connected}
            />
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
              <Text style={styles.muted}>Sin mensajes aún…</Text>
            ) : (
              log.map((l, i) => (
                <Text key={`${i}-${l.slice(0, 12)}`} style={styles.logLine}>
                  {l}
                </Text>
              ))
            )}
          </ScrollView>
        </View>
        <View style={styles.row}>
          <TextInput
            style={[styles.input, { flex: 1 }]}
            value={cmd}
            onChangeText={setCmd}
            placeholder="comando CLI…"
            placeholderTextColor="#6b7280"
            onSubmitEditing={() => sendCmd()}
            editable={connected}
          />
          <Pressable
            style={[styles.btnPrimary, !connected && styles.btnDisabled]}
            onPress={() => sendCmd()}
            disabled={!connected}
          >
            <Text style={styles.btnText}>Enviar</Text>
          </Pressable>
        </View>

        <Text style={styles.footer}>
          Plataforma: {Platform.OS} · CTk legacy sigue en desktop_app/gui
        </Text>
      </ScrollView>
    </SafeAreaView>
  );
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
      style={[
        styles.chip,
        active && styles.chipActive,
        disabled && styles.btnDisabled,
      ]}
    >
      <Text style={styles.chipText}>{label}</Text>
    </Pressable>
  );
}

const styles = StyleSheet.create({
  root: { flex: 1, backgroundColor: "#0f172a" },
  pad: { padding: 16, paddingBottom: 48 },
  title: {
    color: "#f8fafc",
    fontSize: 22,
    fontWeight: "700",
  },
  sub: { color: "#94a3b8", marginTop: 4, marginBottom: 12, fontSize: 12 },
  section: {
    color: "#e2e8f0",
    fontSize: 15,
    fontWeight: "600",
    marginTop: 18,
    marginBottom: 8,
  },
  row: { flexDirection: "row", alignItems: "center", gap: 8, marginVertical: 6 },
  chips: { flexDirection: "row", flexWrap: "wrap", gap: 8 },
  chip: {
    backgroundColor: "#1e293b",
    paddingHorizontal: 12,
    paddingVertical: 8,
    borderRadius: 999,
    borderWidth: 1,
    borderColor: "#334155",
  },
  chipActive: { backgroundColor: "#1d4ed8", borderColor: "#3b82f6" },
  chipText: { color: "#f1f5f9", fontSize: 13 },
  block: { marginTop: 8 },
  label: { color: "#cbd5e1", marginBottom: 6 },
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
  btnPrimary: {
    backgroundColor: "#2563eb",
    paddingHorizontal: 18,
    paddingVertical: 12,
    borderRadius: 10,
  },
  btnSecondary: {
    backgroundColor: "#334155",
    paddingHorizontal: 14,
    paddingVertical: 12,
    borderRadius: 10,
  },
  btnDanger: {
    backgroundColor: "#b91c1c",
    paddingHorizontal: 18,
    paddingVertical: 12,
    borderRadius: 10,
  },
  btnDisabled: { opacity: 0.45 },
  btnText: { color: "#fff", fontWeight: "600" },
  badge: {
    paddingHorizontal: 10,
    paddingVertical: 4,
    borderRadius: 8,
  },
  badgeOk: { backgroundColor: "#14532d" },
  badgeBad: { backgroundColor: "#7f1d1d" },
  badgeText: { color: "#f8fafc", fontSize: 11 },
  muted: { color: "#64748b", fontSize: 12, marginBottom: 4 },
  hint: { color: "#94a3b8", fontSize: 12, marginBottom: 4 },
  hintActive: { color: "#93c5fd" },
  telGrid: { flexDirection: "row", flexWrap: "wrap", gap: 8 },
  telCard: {
    backgroundColor: "#1e293b",
    borderRadius: 12,
    padding: 12,
    minWidth: 96,
    flexGrow: 1,
  },
  telLabel: { color: "#94a3b8", fontSize: 11 },
  telValue: { color: "#f8fafc", fontSize: 18, fontWeight: "700", marginTop: 4 },
  logBox: {
    backgroundColor: "#020617",
    borderRadius: 12,
    borderWidth: 1,
    borderColor: "#1e293b",
    height: 200,
    padding: 10,
    marginBottom: 8,
  },
  logLine: {
    color: "#cbd5e1",
    fontFamily: Platform.OS === "ios" ? "Menlo" : "monospace",
    fontSize: 11,
    marginBottom: 2,
  },
  footer: { color: "#475569", fontSize: 11, marginTop: 20, textAlign: "center" },
});
