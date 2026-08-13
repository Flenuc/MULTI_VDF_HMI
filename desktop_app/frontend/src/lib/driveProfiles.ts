/** Drive profile (VFD model) helpers for multi-VDF UI. */

export type DriveProfileInfo = {
  id: string;
  vendor?: string;
  family?: string;
  model?: string;
  status?: string;
  param_count?: number;
  version?: string;
};

/** One catalog entry from drive_profiles profile.json */
export type CatalogParam = {
  id: string;
  name: string;
  unit: string;
  scale?: number;
  access?: string;
  notes?: string;
  register?: string;
};

export type CatalogIndex = Record<string, CatalogParam>;

/** Built-in list when API `/drive-profiles` is unavailable. */
export const FALLBACK_DRIVE_PROFILES: DriveProfileInfo[] = [
  {
    id: "saj.pdm30",
    vendor: "SAJ",
    family: "PDM",
    model: "PDM-30",
    status: "production",
    param_count: 96,
  },
  {
    id: "saj.pdh30",
    vendor: "SAJ",
    family: "PDH",
    model: "PDH-30",
    status: "field_mapped",
    param_count: 150,
  },
];

export function normalizeDriveProfileId(id?: string | null): string {
  const s = (id || "saj.pdm30").trim().toLowerCase();
  if (s === "pdm" || s === "pdm30") return "saj.pdm30";
  if (s === "pdh" || s === "pdh30") return "saj.pdh30";
  return s || "saj.pdm30";
}

/** Short chip label for operators. */
export function driveProfileShortLabel(p: DriveProfileInfo | string): string {
  if (typeof p === "string") {
    const id = normalizeDriveProfileId(p);
    if (id.includes("pdh")) return "SAJ PDH-30";
    if (id.includes("pdm")) return "SAJ PDM-30";
    return id;
  }
  if (p.model) {
    const v = p.vendor ? `${p.vendor} ` : "";
    return `${v}${p.model}`.trim();
  }
  return driveProfileShortLabel(p.id);
}

/** Secondary hint under the selector. */
export function driveProfileHint(p: DriveProfileInfo | undefined, id: string): string {
  const nid = normalizeDriveProfileId(id);
  if (p?.status) {
    const st =
      p.status === "production"
        ? "producción"
        : p.status === "field_mapped"
          ? "mapeado en campo"
          : p.status;
    const n = p.param_count != null ? ` · ${p.param_count} params` : "";
    return `${driveProfileShortLabel(p)} (${st}${n})`;
  }
  if (nid.includes("pdh")) {
    return "IDs F0.00 / D0.00 · mapa F-style";
  }
  return "IDs P0-xx / P1-xx · mapa PDM";
}

export function isSameDriveFamily(a?: string, b?: string): boolean {
  return normalizeDriveProfileId(a) === normalizeDriveProfileId(b);
}

/** Build id → catalog entry map from full profile JSON. */
export function buildCatalogIndex(profile: {
  parameters?: Array<Record<string, unknown>>;
}): CatalogIndex {
  const out: CatalogIndex = {};
  const list = profile.parameters || [];
  for (const raw of list) {
    const idRaw = String(raw.id || raw.param_id || "").trim();
    if (!idRaw) continue;
    // Normalize P0.00 → P0-00 where applicable
    let id = idRaw.toUpperCase();
    const pMatch = id.match(/^P([01])[.\-](\d{1,2})$/);
    if (pMatch) {
      id = `P${pMatch[1]}-${String(parseInt(pMatch[2], 10)).padStart(2, "0")}`;
    } else {
      const fMatch = id.match(/^([FDE][0-9A-E]?)[.\-](\d{1,3})$/i);
      if (fMatch) {
        id = `${fMatch[1].toUpperCase()}.${String(parseInt(fMatch[2], 10)).padStart(2, "0")}`;
      }
    }
    out[id] = {
      id,
      name: String(raw.name || "").trim(),
      unit: String(raw.unit || "").trim(),
      scale:
        raw.scale != null && raw.scale !== ""
          ? Number(raw.scale)
          : undefined,
      access: raw.access != null ? String(raw.access) : undefined,
      notes: raw.notes != null ? String(raw.notes) : undefined,
      register: raw.register != null ? String(raw.register) : undefined,
    };
  }
  return out;
}

export function catalogLookup(
  index: CatalogIndex | null | undefined,
  paramIdStr: string
): CatalogParam | undefined {
  if (!index) return undefined;
  const key = paramIdStr.trim().toUpperCase();
  if (index[key]) return index[key];
  // try alternate P0.00 form
  const alt = key.replace(".", "-");
  if (index[alt]) return index[alt];
  const alt2 = key.replace("-", ".");
  if (index[alt2]) return index[alt2];
  return undefined;
}

/** Display line: "Pre-set pressure" or fallback empty. */
export function catalogDisplayName(
  index: CatalogIndex | null | undefined,
  paramIdStr: string
): string {
  return catalogLookup(index, paramIdStr)?.name || "";
}

export function catalogUnit(
  index: CatalogIndex | null | undefined,
  paramIdStr: string
): string {
  return catalogLookup(index, paramIdStr)?.unit || "";
}

/** Value + unit for compact UI cells. */
export function formatEngWithUnit(
  value: number | null | undefined,
  unit: string
): string {
  if (value == null || Number.isNaN(value as number)) return "—";
  const v =
    typeof value === "number"
      ? Math.abs(value) >= 100
        ? String(Math.round(value * 1000) / 1000)
        : String(Number(value.toPrecision(6)))
      : String(value);
  return unit ? `${v} ${unit}` : v;
}
