/**
 * Shared UI primitives extracted from App.tsx (Sprint D).
 */
import React from "react";
import { Pressable, StyleSheet, Text, View } from "react-native";

import { colors, font, radius, space, touchMin } from "../theme";

export function Badge({
  ok,
  warn,
  label,
}: {
  ok: boolean;
  warn?: boolean;
  label: string;
}) {
  const bg = warn ? colors.warningSoft : ok ? colors.successBg : colors.dangerBg;
  return (
    <View style={[styles.badge, { backgroundColor: bg }]}>
      <Text style={styles.badgeText}>{label}</Text>
    </View>
  );
}

export function Chip({
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
      style={(state) => [
        styles.chip,
        active && styles.chipOn,
        disabled && styles.dis,
        (state as any).focused && styles.focusRing,
      ]}
      accessibilityRole="button"
      accessibilityLabel={label}
      accessibilityState={{ selected: !!active, disabled: !!disabled }}
    >
      <Text style={styles.chipText}>{label}</Text>
    </Pressable>
  );
}

export function StepCard({
  title,
  body,
  status,
  done,
  locked,
  primaryLabel,
  onPrimary,
  secondaryLabel,
  onSecondary,
}: {
  title: string;
  body: string;
  status: string;
  done?: boolean;
  locked?: boolean;
  primaryLabel: string;
  onPrimary: () => void;
  secondaryLabel?: string;
  onSecondary?: () => void;
}) {
  return (
    <View
      style={[
        styles.stepCard,
        done && styles.stepCardDone,
        locked && styles.stepCardLocked,
      ]}
      accessibilityRole="summary"
    >
      <View style={styles.stepHeader}>
        <View
          style={[
            styles.stepBadge,
            done ? styles.stepBadgeDone : styles.stepBadgeTodo,
          ]}
        >
          <Text style={styles.stepBadgeText}>{done ? "✓" : "·"}</Text>
        </View>
        <Text style={styles.stepTitle}>{title}</Text>
      </View>
      <Text style={styles.stepBody}>{body}</Text>
      <Text style={styles.stepStatus}>{status}</Text>
      <View style={styles.row}>
        <Pressable
          style={[styles.btnPri, styles.btnLarge]}
          onPress={onPrimary}
          accessibilityRole="button"
          accessibilityLabel={primaryLabel}
        >
          <Text style={styles.btnTextLarge}>{primaryLabel}</Text>
        </Pressable>
        {secondaryLabel && onSecondary ? (
          <Pressable
            style={[styles.btnSec, locked && styles.dis]}
            onPress={onSecondary}
            accessibilityRole="button"
            accessibilityLabel={secondaryLabel}
          >
            <Text style={styles.btnText}>{secondaryLabel}</Text>
          </Pressable>
        ) : null}
      </View>
    </View>
  );
}

const styles = StyleSheet.create({
  badge: {
    paddingHorizontal: 10,
    paddingVertical: 4,
    borderRadius: radius.pill,
  },
  badgeText: {
    color: colors.text,
    fontSize: font.sm,
    fontWeight: font.weightSemi,
  },
  chip: {
    backgroundColor: colors.surface,
    paddingHorizontal: 14,
    paddingVertical: 10,
    borderRadius: radius.pill,
    borderWidth: 1,
    borderColor: colors.border,
    minHeight: 44,
    justifyContent: "center",
  },
  chipOn: {
    backgroundColor: colors.primaryHover,
    borderColor: colors.borderFocus,
  },
  chipText: {
    color: colors.text,
    fontSize: font.md,
    fontWeight: font.weightSemi,
  },
  focusRing: {
    borderColor: colors.borderFocus,
    borderWidth: 2,
  },
  dis: { opacity: 0.4 },
  row: {
    flexDirection: "row",
    alignItems: "center",
    flexWrap: "wrap",
    gap: space.sm,
    marginVertical: 6,
  },
  stepCard: {
    backgroundColor: colors.surface,
    borderRadius: radius.lg,
    padding: space.lg,
    marginBottom: space.md,
    borderWidth: 1,
    borderColor: colors.border,
  },
  stepCardDone: {
    borderColor: colors.live,
    backgroundColor: colors.successSoft,
  },
  stepCardLocked: { opacity: 0.92 },
  stepHeader: {
    flexDirection: "row",
    alignItems: "center",
    gap: space.sm,
    marginBottom: space.sm,
  },
  stepBadge: {
    width: 28,
    height: 28,
    borderRadius: 14,
    alignItems: "center",
    justifyContent: "center",
  },
  stepBadgeDone: { backgroundColor: colors.success },
  stepBadgeTodo: { backgroundColor: colors.surfaceHover },
  stepBadgeText: {
    color: "#fff",
    fontWeight: font.weightBlack,
    fontSize: font.xl,
  },
  stepTitle: {
    color: colors.text,
    fontSize: font.lg,
    fontWeight: font.weightBold,
    flex: 1,
  },
  stepBody: {
    color: colors.textSecondary,
    fontSize: font.md,
    lineHeight: 20,
    marginBottom: space.sm,
  },
  stepStatus: {
    color: colors.textMuted,
    fontSize: font.sm,
    fontWeight: font.weightSemi,
    marginBottom: space.md,
  },
  btnPri: {
    backgroundColor: colors.primary,
    paddingHorizontal: space.lg,
    paddingVertical: space.md,
    borderRadius: radius.md,
    minHeight: touchMin,
    justifyContent: "center",
  },
  btnSec: {
    backgroundColor: colors.surfaceHover,
    paddingHorizontal: 14,
    paddingVertical: space.md,
    borderRadius: radius.md,
    minHeight: touchMin,
    justifyContent: "center",
  },
  btnLarge: { paddingVertical: space.lg, minHeight: 56 },
  btnText: {
    color: "#fff",
    fontWeight: font.weightBold,
    fontSize: font.body,
    textAlign: "center",
  },
  btnTextLarge: {
    color: "#fff",
    fontWeight: font.weightBlack,
    fontSize: font.lg,
    textAlign: "center",
  },
});
