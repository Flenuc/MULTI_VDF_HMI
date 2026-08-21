/** Parameter list / plant recipe domain (mirrors desktop_app/models.py). */

export type Parameter = {
  /** Canonical id preferred: P0-00 / F0.00 / D0.00 … */
  id?: string;
  group: number;
  index: number;
  value: number;
  notes: string;
  manual_only: boolean;
  live_value?: number | null;
  mismatch?: boolean;
};

export type ParameterList = {
  name: string;
  description: string;
  /** Multi-VDF target catalog (default saj.pdm30). */
  drive_profile_id?: string;
  parameters: Parameter[];
};

const PARAM_ID_RE =
  /^(P[01]|F[0-9A-E]|D0|E0)[.\-](\d{1,3})$/i;

export function normalizeParamId(raw: string): string | null {
  if (!raw) return null;
  const s = raw.trim().toUpperCase().replace(/\s+/g, "");
  const m = s.match(PARAM_ID_RE);
  if (!m) return null;
  const head = m[1].toUpperCase();
  const idx = parseInt(m[2], 10);
  if (head.startsWith("P")) {
    if (idx > 47) return null;
    return `${head}-${String(idx).padStart(2, "0")}`;
  }
  if (idx > 255) return null;
  return `${head}.${String(idx).padStart(2, "0")}`;
}

export function paramId(p: Parameter): string {
  if (p.id) {
    const n = normalizeParamId(p.id);
    if (n) return n;
    return p.id;
  }
  return `P${p.group}-${String(p.index).padStart(2, "0")}`;
}

/** CLI write line for active edge (profile-aware). Always pset by id. */
export function cliPsetLine(p: Parameter): string {
  return `pset ${paramId(p)} ${Number(p.value)}`;
}

export function cliPgetLine(p: Parameter): string {
  return `pget ${paramId(p)}`;
}

export function emptyList(
  name = "Nueva lista",
  drive_profile_id = "saj.pdm30"
): ParameterList {
  return { name, description: "", drive_profile_id, parameters: [] };
}

export function sortParams(pl: ParameterList): ParameterList {
  const parameters = [...pl.parameters].sort((a, b) => {
    const ia = paramId(a);
    const ib = paramId(b);
    const pa = ia.startsWith("P") && ia.includes("-");
    const pb = ib.startsWith("P") && ib.includes("-");
    if (pa && pb) return a.group - b.group || a.index - b.index;
    if (pa && !pb) return -1;
    if (!pa && pb) return 1;
    return ia.localeCompare(ib);
  });
  return { ...pl, parameters };
}

export function upsertParam(pl: ParameterList, p: Parameter): ParameterList {
  const key = paramId(p);
  const parameters = [...pl.parameters];
  const i = parameters.findIndex((x) => paramId(x) === key);
  if (i >= 0) {
    p.live_value = parameters[i].live_value;
    p.mismatch = parameters[i].mismatch;
    parameters[i] = { ...p, id: key };
  } else {
    parameters.push({ ...p, id: key });
  }
  return sortParams({ ...pl, parameters });
}

export function removeParam(pl: ParameterList, p: Parameter): ParameterList {
  const key = paramId(p);
  return {
    ...pl,
    parameters: pl.parameters.filter((x) => paramId(x) !== key),
  };
}

export function writable(pl: ParameterList): Parameter[] {
  return pl.parameters.filter((p) => !p.manual_only);
}

export function clearCompare(pl: ParameterList): ParameterList {
  return {
    ...pl,
    parameters: pl.parameters.map((p) => ({
      ...p,
      live_value: null,
      mismatch: false,
    })),
  };
}

export type DumpParsed = {
  id: string;
  /** PDM legacy; -1 when id-only (F/D/E). */
  group: number;
  index: number;
  eng: number | null;
};

/**
 * Parse firmware dump CSV:
 *   CSV:P0-03,0x0003,10,100,bar
 *   CSV:F0.00,0xF000,2.6,26,
 */
export function parseDumpCsvLine(line: string): DumpParsed | null {
  let s = line.trim();
  // USB CLI may leave a prompt glued as "> CSV:…"
  if (s.startsWith(">")) s = s.slice(1).trim();
  if (!s.startsWith("CSV:")) return null;
  if (s.startsWith("CSV:param") || s.startsWith("CSV:END")) return null;
  const body = s.slice(4);
  const parts = body.split(",");
  if (parts.length < 3) return null;
  const rawPid = parts[0].trim();
  const id = normalizeParamId(rawPid) || rawPid.toUpperCase();
  let eng: number | null = null;
  const engS = parts[2].trim();
  if (engS !== "ERROR") {
    const v = parseFloat(engS);
    eng = Number.isNaN(v) ? null : v;
  }
  let group = -1;
  let index = 0;
  if (id.startsWith("P") && id.includes("-")) {
    const [gs, is] = id.slice(1).split("-", 2);
    group = parseInt(gs, 10);
    index = parseInt(is, 10);
  } else if (id.includes(".")) {
    index = parseInt(id.split(".")[1] || "0", 10);
  }
  return { id, group, index, eng };
}

/** dumpMap keys are canonical param ids (P0-00 / F0.00). */
export function applyCompare(
  pl: ParameterList,
  dumpMap: Record<string, number>
): { list: ParameterList; mismatches: number } {
  const tol = 1e-3;
  let mismatches = 0;
  const parameters = pl.parameters.map((p) => {
    const key = paramId(p);
    const live = dumpMap[key];
    const has = live !== undefined;
    const live_value = has ? live : null;
    // Monitors / manual_only: show live value but do not fail the plant compare
    if (p.manual_only) {
      return { ...p, live_value, mismatch: false };
    }
    let mismatch = false;
    if (!has) {
      mismatch = true;
      mismatches += 1;
    } else {
      const thr = Math.max(tol, Math.abs(p.value) * 1e-4);
      mismatch = Math.abs(live - p.value) > thr;
      if (mismatch) mismatches += 1;
    }
    return { ...p, live_value, mismatch };
  });
  return { list: { ...pl, parameters }, mismatches };
}

export function validateParam(p: Parameter): void {
  const id = paramId(p);
  if (!normalizeParamId(id)) {
    throw new Error(
      `ID no válido: «${id}». Usá formato F0.00 (PDH) o P0-00 (PDM).`
    );
  }
  if (id.startsWith("P") && id.includes("-")) {
    if (p.group !== 0 && p.group !== 1) {
      throw new Error("El grupo PDM debe ser 0 o 1 (P0-xx / P1-xx).");
    }
    if (p.index < 0 || p.index > 47) {
      throw new Error("El índice PDM debe estar entre 0 y 47.");
    }
  }
  if (Number.isNaN(p.value)) {
    throw new Error("El valor no es un número válido.");
  }
}

export function isPdhProfile(driveProfileId?: string): boolean {
  const s = (driveProfileId || "saj.pdm30").toLowerCase();
  return s.includes("pdh");
}

export function isPdmProfile(driveProfileId?: string): boolean {
  return !isPdhProfile(driveProfileId);
}
