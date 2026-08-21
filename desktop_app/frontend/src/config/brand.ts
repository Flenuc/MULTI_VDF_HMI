/**
 * Identidad comercial — multi-marca, sin atarse a un fabricante.
 *
 * VarioField = “variadores en campo”: recetas, enlace y telemetría
 * para cualquier VDF compatible con el módulo Edge.
 */
export const BRAND = {
  name: "VarioField",
  tagline: "Recetas y enlace a variadores en campo",
  fullName: "VarioField — gestor de campo multi-variador",
  version: "0.3.9",
  /** Bump when Electron packaging UI must be distinguished from browser dev */
  buildId: "20260821-sprint-b-a11y",
  /** Código interno / repo (solo diagnóstico) */
  codename: "MULTI_VDF_HMI",
} as const;
