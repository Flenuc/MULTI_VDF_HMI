/**
 * VarioField design system — tokens only.
 * Use these instead of hard-coded hex in new UI.
 */
export const colors = {
  bg: "#0b1220",
  bgElevated: "#0f172a",
  surface: "#1e293b",
  surfaceHover: "#334155",
  border: "#334155",
  borderFocus: "#60a5fa",

  text: "#f8fafc",
  textSecondary: "#cbd5e1",
  textMuted: "#94a3b8",
  /** Secondary labels (telemetry, notes). ≥4.5:1 on bg/surface (WCAG AA). */
  textDim: "#8592a8",
  /** Form placeholders — prefer over raw #6b7280 */
  textPlaceholder: "#8592a8",

  primary: "#2563eb",
  primaryHover: "#1d4ed8",
  primarySoft: "#1e3a5f",
  accent: "#3b82f6",
  accentSoft: "#93c5fd",

  success: "#16a34a",
  successBg: "#14532d",
  successSoft: "#14532d33",
  warning: "#fbbf24",
  warningBg: "#b45309",
  warningSoft: "#422006",
  danger: "#b91c1c",
  dangerBg: "#7f1d1d",
  dangerSoft: "#7f1d1d",

  infoBg: "#172554",
  infoBorder: "#1e3a8a",
  infoText: "#bfdbfe",

  live: "#22c55e",
  offline: "#ef4444",
} as const;

export const space = {
  xs: 4,
  sm: 8,
  md: 12,
  lg: 16,
  xl: 20,
  xxl: 24,
  xxxl: 32,
} as const;

export const radius = {
  sm: 8,
  md: 12,
  lg: 14,
  xl: 16,
  pill: 999,
  full: 9999,
} as const;

/** Minimum touch target (WCAG / platform guidelines) */
export const touchMin = 48;

export const font = {
  xs: 10,
  sm: 12,
  md: 13,
  body: 14,
  lg: 15,
  xl: 16,
  title: 17,
  h2: 20,
  h1: 22,
  display: 18,
  weightRegular: "400" as const,
  weightSemi: "600" as const,
  weightBold: "700" as const,
  weightBlack: "800" as const,
};

export const shadow = {
  card: {
    shadowColor: "#000",
    shadowOffset: { width: 0, height: 4 },
    shadowOpacity: 0.25,
    shadowRadius: 8,
    elevation: 4,
  },
};

export const theme = { colors, space, radius, touchMin, font, shadow };
export type Theme = typeof theme;
