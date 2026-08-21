/**
 * Technician catalog editor — table for name/scale/map_status + import/export/apply.
 */
import React, { useCallback, useEffect, useMemo, useState } from "react";
import {
  ActivityIndicator,
  Alert,
  Pressable,
  ScrollView,
  StyleSheet,
  Text,
  TextInput,
  View,
} from "react-native";
import {
  api,
  type DriveProfileDoc,
  type DriveProfileInfo,
  type DriveProfileParam,
  type DriveProfileVariantInfo,
} from "../api/client";
import { exportJsonFile, importJsonObject } from "../lib/jsonFile";
import { colors } from "../theme";

type Variant = "active" | "live_draft" | "merged";

const MAP_STATUSES = ["ok", "error", "missing"] as const;

type Props = {
  profiles: DriveProfileInfo[];
  initialId?: string;
  onLog?: (line: string) => void;
  onProfilesChanged?: () => void;
};

export default function CatalogEditor({
  profiles,
  initialId,
  onLog,
  onProfilesChanged,
}: Props) {
  const [profileId, setProfileId] = useState(
    initialId || profiles[0]?.id || "saj.pdh30"
  );
  const [variant, setVariant] = useState<Variant>("active");
  const [variants, setVariants] = useState<DriveProfileVariantInfo[]>([]);
  const [doc, setDoc] = useState<DriveProfileDoc | null>(null);
  const [rows, setRows] = useState<DriveProfileParam[]>([]);
  const [filter, setFilter] = useState("");
  const [busy, setBusy] = useState(false);
  const [dirty, setDirty] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const load = useCallback(async () => {
    if (!profileId) return;
    setBusy(true);
    setError(null);
    try {
      const v = await api.driveProfileVariants(profileId);
      setVariants(v.variants || []);
      const exists = (v.variants || []).find((x) => x.variant === variant)?.exists;
      const useVariant: Variant =
        exists || variant === "active" ? variant : "active";
      if (useVariant !== variant) setVariant(useVariant);
      const d = await api.driveProfile(profileId, useVariant);
      setDoc(d);
      setRows([...(d.parameters || [])]);
      setDirty(false);
      onLog?.(
        `Catálogo ${profileId} (${useVariant}) — ${(d.parameters || []).length} params`
      );
    } catch (e) {
      const msg = e instanceof Error ? e.message : String(e);
      setError(msg);
      setDoc(null);
      setRows([]);
      onLog?.(`Catálogo error: ${msg}`);
    } finally {
      setBusy(false);
    }
  }, [profileId, variant, onLog]);

  useEffect(() => {
    void load();
  }, [load]);

  const filtered = useMemo(() => {
    const q = filter.trim().toLowerCase();
    if (!q) return rows;
    return rows.filter(
      (r) =>
        String(r.id || "")
          .toLowerCase()
          .includes(q) ||
        String(r.name || "")
          .toLowerCase()
          .includes(q) ||
        String(r.map_status || "")
          .toLowerCase()
          .includes(q)
    );
  }, [rows, filter]);

  const stats = useMemo(() => {
    const c = { ok: 0, error: 0, missing: 0, other: 0 };
    for (const r of rows) {
      const s = String(r.map_status || "other");
      if (s in c) (c as Record<string, number>)[s] += 1;
      else c.other += 1;
    }
    return c;
  }, [rows]);

  const updateRow = (id: string, patch: Partial<DriveProfileParam>) => {
    setRows((prev) =>
      prev.map((r) => (r.id === id ? { ...r, ...patch } : r))
    );
    setDirty(true);
  };

  const save = async () => {
    if (!doc) return;
    setBusy(true);
    setError(null);
    try {
      const body: DriveProfileDoc = {
        ...doc,
        id: profileId,
        parameters: rows,
      };
      delete body._meta;
      const saved = await api.saveDriveProfile(profileId, body, variant);
      setDoc(saved);
      setRows([...(saved.parameters || [])]);
      setDirty(false);
      onLog?.(`Guardado ${profileId}/${variant} (overlay usuario)`);
      onProfilesChanged?.();
      Alert.alert("OK", `Perfil ${profileId} (${variant}) guardado.`);
    } catch (e) {
      const msg = e instanceof Error ? e.message : String(e);
      setError(msg);
      Alert.alert("Error", msg);
    } finally {
      setBusy(false);
    }
  };

  const doExport = async () => {
    if (!doc) return;
    try {
      const body = { ...doc, id: profileId, parameters: rows };
      delete body._meta;
      const name = `${profileId.replace(/\./g, "_")}_${variant}.json`;
      const path = await exportJsonFile(name, body);
      onLog?.(path ? `Export catálogo → ${path}` : `Export catálogo ${name}`);
    } catch (e) {
      Alert.alert("Error", String(e));
    }
  };

  const doImport = async () => {
    try {
      const data = await importJsonObject();
      if (!data || typeof data !== "object") return;
      const body = data as DriveProfileDoc;
      if (!Array.isArray(body.parameters) || !body.parameters.length) {
        throw new Error("El JSON no tiene parameters[]");
      }
      const id = String(body.id || profileId);
      setBusy(true);
      const saved = await api.saveDriveProfile(id, body, "active");
      setProfileId(id);
      setVariant("active");
      setDoc(saved);
      setRows([...(saved.parameters || [])]);
      setDirty(false);
      onLog?.(`Importado catálogo ${id}`);
      onProfilesChanged?.();
      Alert.alert("OK", `Importado ${id} (${saved.parameters?.length || 0} params)`);
    } catch (e) {
      Alert.alert("Error", String(e));
    } finally {
      setBusy(false);
    }
  };

  const applyVariant = async (source: "merged" | "live_draft") => {
    Alert.alert(
      "Aplicar variante",
      `¿Copiar ${source} → active (overlay usuario)?`,
      [
        { text: "Cancelar", style: "cancel" },
        {
          text: "Aplicar",
          onPress: async () => {
            setBusy(true);
            try {
              const saved = await api.applyDriveProfileVariant(profileId, source);
              setVariant("active");
              setDoc(saved);
              setRows([...(saved.parameters || [])]);
              setDirty(false);
              onLog?.(`Aplicado ${source} → active (${profileId})`);
              onProfilesChanged?.();
              Alert.alert("OK", `${source} aplicado como active.`);
            } catch (e) {
              Alert.alert("Error", String(e));
            } finally {
              setBusy(false);
            }
          },
        },
      ]
    );
  };

  return (
    <View>
      <Text style={styles.section}>Catálogo de variador (técnico)</Text>
      <Text style={styles.hint}>
        Editá nombre / escala / map_status. Importá o exportá JSON. Guardar escribe
        en overlay de usuario (no pisa el AppImage). Aplicá merged/live_draft cuando
        existan.
      </Text>

      <Text style={styles.label}>Perfil</Text>
      <View style={styles.chips}>
        {profiles.map((p) => (
          <Pressable
            key={p.id}
            style={[styles.chip, profileId === p.id && styles.chipOn]}
            onPress={() => {
              if (dirty) {
                Alert.alert("Cambios sin guardar", "¿Descartar y cambiar de perfil?", [
                  { text: "Cancelar", style: "cancel" },
                  {
                    text: "Descartar",
                    style: "destructive",
                    onPress: () => setProfileId(p.id),
                  },
                ]);
              } else setProfileId(p.id);
            }}
          >
            <Text style={styles.chipText}>{p.id}</Text>
          </Pressable>
        ))}
      </View>

      <Text style={styles.label}>Variante</Text>
      <View style={styles.chips}>
        {(["active", "live_draft", "merged"] as Variant[]).map((v) => {
          const info = variants.find((x) => x.variant === v);
          const missing = info && !info.exists;
          return (
            <Pressable
              key={v}
              style={[
                styles.chip,
                variant === v && styles.chipOn,
                missing && styles.chipDisabled,
              ]}
              disabled={!!missing}
              onPress={() => setVariant(v)}
            >
              <Text style={styles.chipText}>
                {v}
                {missing ? " ✗" : info?.exists ? "" : ""}
              </Text>
            </Pressable>
          );
        })}
      </View>

      <View style={styles.row}>
        <Pressable
          style={[styles.btn, busy && styles.dis]}
          onPress={() => void load()}
          disabled={busy}
        >
          <Text style={styles.btnText}>Recargar</Text>
        </Pressable>
        <Pressable
          style={[styles.btnPri, (busy || !dirty) && styles.dis]}
          onPress={() => void save()}
          disabled={busy || !dirty}
        >
          <Text style={styles.btnText}>Guardar</Text>
        </Pressable>
        <Pressable style={styles.btn} onPress={() => void doExport()} disabled={busy}>
          <Text style={styles.btnText}>Exportar</Text>
        </Pressable>
        <Pressable style={styles.btn} onPress={() => void doImport()} disabled={busy}>
          <Text style={styles.btnText}>Importar</Text>
        </Pressable>
      </View>

      <View style={styles.row}>
        <Pressable
          style={[
            styles.btnSec,
            !variants.find((v) => v.variant === "merged")?.exists && styles.dis,
          ]}
          disabled={!variants.find((v) => v.variant === "merged")?.exists || busy}
          onPress={() => void applyVariant("merged")}
        >
          <Text style={styles.btnText}>Aplicar merged → active</Text>
        </Pressable>
        <Pressable
          style={[
            styles.btnSec,
            !variants.find((v) => v.variant === "live_draft")?.exists && styles.dis,
          ]}
          disabled={
            !variants.find((v) => v.variant === "live_draft")?.exists || busy
          }
          onPress={() => void applyVariant("live_draft")}
        >
          <Text style={styles.btnText}>Aplicar live_draft → active</Text>
        </Pressable>
      </View>

      {busy && <ActivityIndicator color={colors.primary} style={{ marginVertical: 8 }} />}
      {error && <Text style={styles.err}>{error}</Text>}
      {doc && (
        <Text style={styles.meta}>
          status={String(doc.status || "?")} · params={rows.length} · ok={stats.ok}{" "}
          err={stats.error} miss={stats.missing}
          {dirty ? " · SIN GUARDAR" : ""}
          {doc._meta
            ? ` · ${(doc._meta as { source?: string }).source || ""}`
            : ""}
        </Text>
      )}

      <TextInput
        style={styles.input}
        value={filter}
        onChangeText={setFilter}
        placeholder="Filtrar id / nombre / map_status…"
        placeholderTextColor="#6b7280"
        autoCapitalize="none"
        autoCorrect={false}
      />

      <ScrollView horizontal style={styles.tableWrap}>
        <View>
          <View style={[styles.tr, styles.th]}>
            <Text style={[styles.td, styles.colId]}>id</Text>
            <Text style={[styles.td, styles.colName]}>name</Text>
            <Text style={[styles.td, styles.colScale]}>scale</Text>
            <Text style={[styles.td, styles.colMap]}>map_status</Text>
            <Text style={[styles.td, styles.colLive]}>live_eng</Text>
            <Text style={[styles.td, styles.colReg]}>register</Text>
          </View>
          {filtered.slice(0, 200).map((r) => (
            <View key={r.id} style={styles.tr}>
              <Text style={[styles.td, styles.colId]} numberOfLines={1}>
                {r.id}
              </Text>
              <TextInput
                style={[styles.tdInput, styles.colName]}
                value={String(r.name ?? "")}
                onChangeText={(t) => updateRow(r.id, { name: t })}
                placeholderTextColor="#6b7280"
              />
              <TextInput
                style={[styles.tdInput, styles.colScale]}
                value={r.scale == null ? "" : String(r.scale)}
                keyboardType="decimal-pad"
                onChangeText={(t) => {
                  const n = t.trim() === "" ? null : Number(t);
                  updateRow(r.id, {
                    scale: n != null && !Number.isNaN(n) ? n : null,
                  });
                }}
                placeholderTextColor="#6b7280"
              />
              <View style={[styles.colMap, styles.mapChips]}>
                {MAP_STATUSES.map((s) => (
                  <Pressable
                    key={s}
                    style={[
                      styles.mapChip,
                      r.map_status === s && styles.mapChipOn,
                    ]}
                    onPress={() => updateRow(r.id, { map_status: s })}
                  >
                    <Text style={styles.mapChipText}>{s[0]}</Text>
                  </Pressable>
                ))}
              </View>
              <Text style={[styles.td, styles.colLive]} numberOfLines={1}>
                {r.live_eng == null ? "—" : String(r.live_eng)}
              </Text>
              <Text style={[styles.td, styles.colReg]} numberOfLines={1}>
                {String(r.register || "—")}
              </Text>
            </View>
          ))}
          {filtered.length > 200 && (
            <Text style={styles.hint}>
              Mostrando 200 / {filtered.length} — usá el filtro.
            </Text>
          )}
        </View>
      </ScrollView>
    </View>
  );
}

const styles = StyleSheet.create({
  section: {
    color: "#e5e7eb",
    fontSize: 18,
    fontWeight: "700",
    marginTop: 8,
    marginBottom: 6,
  },
  label: { color: "#9ca3af", marginTop: 10, marginBottom: 4, fontSize: 13 },
  hint: { color: "#9ca3af", fontSize: 13, marginBottom: 8, lineHeight: 18 },
  meta: { color: "#a5b4fc", fontSize: 12, marginVertical: 6 },
  err: { color: "#fca5a5", marginVertical: 6 },
  chips: { flexDirection: "row", flexWrap: "wrap", gap: 8 },
  chip: {
    backgroundColor: "#1f2937",
    paddingHorizontal: 10,
    paddingVertical: 6,
    borderRadius: 8,
    borderWidth: 1,
    borderColor: "#374151",
  },
  chipOn: { borderColor: colors.primary, backgroundColor: "#1e3a5f" },
  chipDisabled: { opacity: 0.35 },
  chipText: { color: "#e5e7eb", fontSize: 12 },
  row: { flexDirection: "row", flexWrap: "wrap", gap: 8, marginTop: 10 },
  btn: {
    backgroundColor: "#374151",
    paddingHorizontal: 12,
    paddingVertical: 10,
    borderRadius: 8,
  },
  btnPri: {
    backgroundColor: colors.primary,
    paddingHorizontal: 12,
    paddingVertical: 10,
    borderRadius: 8,
  },
  btnSec: {
    backgroundColor: "#1f2937",
    paddingHorizontal: 12,
    paddingVertical: 10,
    borderRadius: 8,
    borderWidth: 1,
    borderColor: "#4b5563",
  },
  btnText: { color: "#fff", fontWeight: "600", fontSize: 13 },
  dis: { opacity: 0.4 },
  input: {
    backgroundColor: "#111827",
    borderColor: "#374151",
    borderWidth: 1,
    borderRadius: 8,
    color: "#e5e7eb",
    paddingHorizontal: 10,
    paddingVertical: 8,
    marginTop: 8,
  },
  tableWrap: { marginTop: 10, maxHeight: 420 },
  tr: {
    flexDirection: "row",
    alignItems: "center",
    borderBottomWidth: StyleSheet.hairlineWidth,
    borderBottomColor: "#374151",
    minHeight: 36,
  },
  th: { backgroundColor: "#1f2937" },
  td: { color: "#d1d5db", fontSize: 12, paddingHorizontal: 4 },
  tdInput: {
    color: "#e5e7eb",
    fontSize: 12,
    paddingHorizontal: 4,
    paddingVertical: 4,
    backgroundColor: "#0f172a",
    borderRadius: 4,
    marginVertical: 2,
  },
  colId: { width: 72 },
  colName: { width: 160 },
  colScale: { width: 56 },
  colMap: { width: 90 },
  colLive: { width: 64 },
  colReg: { width: 72 },
  mapChips: { flexDirection: "row", gap: 2 },
  mapChip: {
    width: 22,
    height: 22,
    borderRadius: 4,
    backgroundColor: "#374151",
    alignItems: "center",
    justifyContent: "center",
  },
  mapChipOn: { backgroundColor: colors.primary },
  mapChipText: { color: "#fff", fontSize: 10, fontWeight: "700" },
});
