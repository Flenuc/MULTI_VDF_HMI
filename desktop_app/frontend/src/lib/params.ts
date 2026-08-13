/** Parameter list domain (mirrors desktop_app/models.py). */

export type Parameter = {
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
  parameters: Parameter[];
};

export function paramId(p: Parameter): string {
  return `P${p.group}-${String(p.index).padStart(2, "0")}`;
}

export function emptyList(name = "Nueva lista"): ParameterList {
  return { name, description: "", parameters: [] };
}

export function sortParams(pl: ParameterList): ParameterList {
  const parameters = [...pl.parameters].sort(
    (a, b) => a.group - b.group || a.index - b.index
  );
  return { ...pl, parameters };
}

export function upsertParam(pl: ParameterList, p: Parameter): ParameterList {
  const parameters = [...pl.parameters];
  const i = parameters.findIndex(
    (x) => x.group === p.group && x.index === p.index
  );
  if (i >= 0) {
    p.live_value = parameters[i].live_value;
    p.mismatch = parameters[i].mismatch;
    parameters[i] = p;
  } else {
    parameters.push(p);
  }
  return sortParams({ ...pl, parameters });
}

export function removeParam(pl: ParameterList, p: Parameter): ParameterList {
  return {
    ...pl,
    parameters: pl.parameters.filter(
      (x) => !(x.group === p.group && x.index === p.index)
    ),
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

export function parseDumpCsvLine(
  line: string
): { group: number; index: number; eng: number | null } | null {
  if (!line.startsWith("CSV:P")) return null;
  if (line.startsWith("CSV:param") || line.startsWith("CSV:END")) return null;
  const body = line.slice(4);
  const parts = body.split(",");
  if (parts.length < 3) return null;
  const pid = parts[0].trim().toUpperCase();
  if (!pid.startsWith("P") || !pid.includes("-")) return null;
  const [gs, is] = pid.slice(1).split("-", 2);
  const g = parseInt(gs, 10);
  const i = parseInt(is, 10);
  if (Number.isNaN(g) || Number.isNaN(i)) return null;
  let eng: number | null = null;
  try {
    eng = parseFloat(parts[2]);
    if (Number.isNaN(eng)) eng = null;
  } catch {
    eng = null;
  }
  return { group: g, index: i, eng };
}

export function applyCompare(
  pl: ParameterList,
  dumpMap: Record<string, number>
): { list: ParameterList; mismatches: number } {
  const tol = 1e-3;
  let mismatches = 0;
  const parameters = pl.parameters.map((p) => {
    const key = `${p.group}:${p.index}`;
    const live = dumpMap[key];
    const has = live !== undefined;
    const live_value = has ? live : null;
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
  if (p.group !== 0 && p.group !== 1) throw new Error("group must be 0 or 1");
  if (p.index < 0 || p.index > 47) throw new Error("index must be 0..47");
  if (Number.isNaN(p.value)) throw new Error("value invalid");
}
