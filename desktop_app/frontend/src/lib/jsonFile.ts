/**
 * Import / export parameter list JSON.
 * - Electron desktop: native open/save dialogs via preload bridge
 * - Web / Expo: FileReader + download blob
 */

import type { ParameterList } from "./params";
import { sortParams } from "./params";

export type DesktopBridge = {
  isDesktop?: boolean;
  platform?: string;
  openJsonFile?: () => Promise<{ path: string; text: string } | null>;
  saveJsonFile?: (opts: {
    defaultPath?: string;
    content: string;
  }) => Promise<{ path: string } | null>;
};

declare global {
  interface Window {
    multiVdfDesktop?: DesktopBridge;
  }
}

export function isDesktopShell(): boolean {
  return typeof window !== "undefined" && !!window.multiVdfDesktop?.isDesktop;
}

export function parseParamListJson(text: string): ParameterList {
  const data = JSON.parse(text);
  if (!data || typeof data !== "object") {
    throw new Error("JSON inválido");
  }
  const pl: ParameterList = {
    name: String(data.name || "Lista"),
    description: String(data.description || ""),
    drive_profile_id: String(
      data.drive_profile_id || data.driveProfileId || "saj.pdm30"
    ),
    parameters: Array.isArray(data.parameters)
      ? data.parameters.map((item: Record<string, unknown>) => {
          const rawId = item.id ?? item.param_id;
          let group =
            item.group !== undefined && item.group !== null
              ? Number(item.group)
              : 0;
          let index =
            item.index !== undefined && item.index !== null
              ? Number(item.index)
              : 0;
          let id: string | undefined;
          if (rawId != null) {
            id = String(rawId).trim().toUpperCase();
            // P0.00 / P0-00 → group/index
            const pMatch = id.match(/^P([01])[.\-](\d{1,2})$/i);
            if (pMatch) {
              group = parseInt(pMatch[1], 10);
              index = parseInt(pMatch[2], 10);
              id = `P${group}-${String(index).padStart(2, "0")}`;
            } else {
              // F0.00 / FD.01 / D0.00
              const fMatch = id.match(/^([FDE][0-9A-E]?)[.\-](\d{1,3})$/i);
              if (fMatch) {
                const head = fMatch[1].toUpperCase();
                index = parseInt(fMatch[2], 10);
                id = `${head}.${String(index).padStart(2, "0")}`;
                group = 0;
              }
            }
          } else if (!Number.isNaN(group) && !Number.isNaN(index)) {
            id = `P${group}-${String(index).padStart(2, "0")}`;
          }
          return {
            id,
            group: Number.isNaN(group) ? 0 : group,
            index: Number.isNaN(index) ? 0 : index,
            value: Number(item.value),
            notes: String(item.notes ?? ""),
            manual_only: Boolean(item.manual_only),
          };
        })
      : [],
  };
  return sortParams(pl);
}

export function serializeParamList(pl: ParameterList): string {
  return JSON.stringify(
    {
      name: pl.name,
      description: pl.description,
      drive_profile_id: pl.drive_profile_id || "saj.pdm30",
      parameters: pl.parameters.map((p) => {
        const id =
          p.id ||
          `P${p.group}-${String(p.index).padStart(2, "0")}`;
        const row: Record<string, unknown> = {
          id,
          value: p.value,
          notes: p.notes,
          manual_only: p.manual_only,
        };
        if (id.startsWith("P") && id.includes("-")) {
          row.group = p.group;
          row.index = p.index;
        }
        return row;
      }),
    },
    null,
    2
  );
}

/** Download arbitrary JSON (web) or native save (Electron). */
export async function exportJsonFile(
  filename: string,
  data: unknown
): Promise<string | null> {
  const text = JSON.stringify(data, null, 2);
  const bridge = typeof window !== "undefined" ? window.multiVdfDesktop : undefined;
  if (bridge?.saveJsonFile) {
    const res = await bridge.saveJsonFile({ defaultPath: filename, content: text });
    return res?.path ?? null;
  }
  // Browser download
  const blob = new Blob([text], { type: "application/json" });
  const url = URL.createObjectURL(blob);
  const a = document.createElement("a");
  a.href = url;
  a.download = filename.endsWith(".json") ? filename : `${filename}.json`;
  a.click();
  URL.revokeObjectURL(url);
  return a.download;
}

/** Open JSON file and parse as object. */
export async function importJsonObject(): Promise<unknown | null> {
  const bridge = typeof window !== "undefined" ? window.multiVdfDesktop : undefined;
  if (bridge?.openJsonFile) {
    const res = await bridge.openJsonFile();
    if (!res?.text) return null;
    return JSON.parse(res.text);
  }
  return new Promise((resolve, reject) => {
    const input = document.createElement("input");
    input.type = "file";
    input.accept = "application/json,.json";
    input.onchange = async () => {
      const file = input.files?.[0];
      if (!file) {
        resolve(null);
        return;
      }
      try {
        const text = await file.text();
        resolve(JSON.parse(text));
      } catch (e) {
        reject(e);
      }
    };
    input.click();
  });
}

/** Open a JSON file from disk (Electron dialog or browser file picker). */
export async function importParamListJson(): Promise<{
  list: ParameterList;
  filename: string;
  path?: string;
} | null> {
  const desk = typeof window !== "undefined" ? window.multiVdfDesktop : undefined;
  if (desk?.openJsonFile) {
    const r = await desk.openJsonFile();
    if (!r) return null;
    const list = parseParamListJson(r.text);
    const filename = r.path.split(/[/\\]/).pop() || "import.json";
    if (!list.name || list.name === "Lista") {
      list.name = filename.replace(/\.json$/i, "");
    }
    return { list, filename, path: r.path };
  }

  // Browser / Expo web
  return new Promise((resolve, reject) => {
    const input = document.createElement("input");
    input.type = "file";
    input.accept = "application/json,.json";
    input.onchange = async () => {
      const file = input.files?.[0];
      if (!file) {
        resolve(null);
        return;
      }
      try {
        const text = await file.text();
        const list = parseParamListJson(text);
        if (!list.name || list.name === "Lista") {
          list.name = file.name.replace(/\.json$/i, "");
        }
        resolve({ list, filename: file.name });
      } catch (e) {
        reject(e);
      }
    };
    input.click();
  });
}

/** Save JSON to disk (Electron save dialog or browser download). */
export async function exportParamListJson(
  pl: ParameterList,
  defaultName?: string
): Promise<{ path?: string; downloaded?: boolean } | null> {
  const content = serializeParamList(pl);
  const defaultPath =
    defaultName ||
    `${(pl.name || "lista").replace(/[^\w .\-()]/g, "_")}.json`;

  const desk = typeof window !== "undefined" ? window.multiVdfDesktop : undefined;
  if (desk?.saveJsonFile) {
    const r = await desk.saveJsonFile({ defaultPath, content });
    if (!r) return null;
    return { path: r.path };
  }

  // Browser download
  if (typeof document === "undefined") {
    throw new Error("Export no disponible en este entorno");
  }
  const blob = new Blob([content], { type: "application/json;charset=utf-8" });
  const url = URL.createObjectURL(blob);
  const a = document.createElement("a");
  a.href = url;
  a.download = defaultPath.endsWith(".json") ? defaultPath : `${defaultPath}.json`;
  a.click();
  URL.revokeObjectURL(url);
  return { downloaded: true };
}
