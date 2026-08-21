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
import { useConfirmDialog } from "./ConfirmDialog";
import { colors, font, radius, space, touchMin } from "../theme";

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
  const { confirm, dialog: confirmDialog } = useConfirmDialog();


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
    const choice = await confirm({
      title: "Aplicar variante",
      body: `¿Copiar ${source} → active (overlay usuario)?`,
      primaryLabel: "Aplicar",
      cancelLabel: "Cancelar",
    });
    if (choice !== "primary") return;
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
            style={(state) => [
                styles.chip,
                profileId === p.id && styles.chipOn,
                (state as any).focused && styles.focusRing,
              ]}
            onPress={async () => {
              if (dirty) {
                const choice = await confirm({
                  title: "Cambios sin guardar",
                  body: "¿Descartar y cambiar de perfil?",
                  primaryLabel: "Descartar",
                  cancelLabel: "Cancelar",
                  primaryDanger: true,
                });
                if (choice === "primary") setProfileId(p.id);
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
              style={(state) => [
                  styles.chip,
                  variant === v && styles.chipOn,
                  missing && styles.chipDisabled,
                  (state as any).focused && styles.focusRing,
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
        placeholderTextColor={colors.textPlaceholder}
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
                placeholderTextColor={colors.textPlaceholder}
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
                placeholderTextColor={colors.textPlaceholder}
              />
              <View style={[styles.colMap, styles.mapChips]}>
                {MAP_STATUSES.map((st) => (
                  <Pressable
                    key={st}
                    style={(state) => [
                        styles.mapChip,
                        r.map_status === st && styles.mapChipOn,
                        (state as any).focused && styles.focusRing,
                      ]}
                    onPress={() => updateRow(r.id, { map_status: st })}
                    hitSlop={4}
                    accessibilityRole="button"
                    accessibilityLabel={`map_status ${st}`}
                    accessibilityState={{ selected: r.map_status === st }}
                  >
                    <Text style={styles.mapChipText}>{st === "missing" ? "miss" : st}</Text>
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
      {confirmDialog}
    </View>
  );
}

const styles = StyleSheet.create({
  section: {
    color: colors.text,
    fontSize: font.xl,
    fontWeight: font.weightBold,
    marginTop: space.sm,
    marginBottom: space.sm,
  },
  label: {
    color: colors.textMuted,
    marginTop: space.md,
    marginBottom: space.xs,
    fontSize: font.md,
  },
  hint: {
    color: colors.textDim,
    fontSize: font.md,
    marginBottom: space.sm,
    lineHeight: 18,
  },
  meta: { color: colors.accentSoft, fontSize: font.sm, marginVertical: space.sm },
  err: { color: colors.danger, marginVertical: space.sm },
  chips: { flexDirection: "row", flexWrap: "wrap", gap: space.sm },
  chip: {
    backgroundColor: colors.surface,
    paddingHorizontal: space.md,
    paddingVertical: space.sm,
    borderRadius: radius.sm,
    borderWidth: 1,
    borderColor: colors.border,
    minHeight: touchMin,
    justifyContent: "center",
  },
  chipOn: {
    borderColor: colors.borderFocus,
    backgroundColor: colors.primarySoft,
  },
  chipDisabled: { opacity: 0.35 },
  chipText: { color: colors.text, fontSize: font.sm, fontWeight: font.weightSemi },
  focusRing: { borderColor: colors.borderFocus, borderWidth: 2 },
  row: { flexDirection: "row", flexWrap: "wrap", gap: space.sm, marginTop: space.md },
  btn: {
    backgroundColor: colors.surfaceHover,
    paddingHorizontal: space.md,
    paddingVertical: space.md,
    borderRadius: radius.sm,
    minHeight: touchMin,
    justifyContent: "center",
  },
  btnPri: {
    backgroundColor: colors.primary,
    paddingHorizontal: space.md,
    paddingVertical: space.md,
    borderRadius: radius.sm,
    minHeight: touchMin,
    justifyContent: "center",
  },
  btnSec: {
    backgroundColor: colors.surface,
    paddingHorizontal: space.md,
    paddingVertical: space.md,
    borderRadius: radius.sm,
    borderWidth: 1,
    borderColor: colors.border,
    minHeight: touchMin,
    justifyContent: "center",
  },
  btnText: {
    color: colors.text,
    fontWeight: font.weightSemi,
    fontSize: font.md,
    textAlign: "center",
  },
  dis: { opacity: 0.4 },
  input: {
    backgroundColor: colors.bgElevated,
    borderColor: colors.border,
    borderWidth: 1,
    borderRadius: radius.sm,
    color: colors.text,
    paddingHorizontal: space.md,
    paddingVertical: space.sm,
    marginTop: space.sm,
    minHeight: touchMin,
  },
  tableWrap: { marginTop: space.md, maxHeight: 420 },
  tr: {
    flexDirection: "row",
    alignItems: "center",
    borderBottomWidth: StyleSheet.hairlineWidth,
    borderBottomColor: colors.border,
    minHeight: touchMin,
  },
  th: { backgroundColor: colors.surface },
  td: {
    color: colors.textSecondary,
    fontSize: font.sm,
    paddingHorizontal: space.xs,
  },
  tdInput: {
    color: colors.text,
    fontSize: font.sm,
    paddingHorizontal: space.xs,
    paddingVertical: space.xs,
    backgroundColor: colors.bgElevated,
    borderRadius: radius.sm,
    marginVertical: 2,
    minHeight: 40,
  },
  colId: { width: 72 },
  colName: { width: 160 },
  colScale: { width: 64 },
  colMap: { width: 168 },
  colLive: { width: 64 },
  colReg: { width: 72 },
  mapChips: { flexDirection: "row", gap: space.xs, flexWrap: "wrap" },
  mapChip: {
    minWidth: touchMin,
    minHeight: touchMin,
    paddingHorizontal: space.sm,
    borderRadius: radius.sm,
    backgroundColor: colors.surfaceHover,
    alignItems: "center",
    justifyContent: "center",
  },
  mapChipOn: { backgroundColor: colors.primary },
  mapChipText: {
    color: colors.text,
    fontSize: font.xs,
    fontWeight: font.weightBold,
  },
});

