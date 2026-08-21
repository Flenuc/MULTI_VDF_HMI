/**
 * Cross-platform confirm overlay (Electron/Web-safe).
 * Prefer this over Alert.alert when there are multiple action buttons.
 */
import React, { useCallback, useRef, useState } from "react";
import { Pressable, StyleSheet, Text, View } from "react-native";

import { colors, font, radius, space, touchMin } from "../theme";

export type ConfirmChoice = "primary" | "secondary" | "cancel";

export type ConfirmOptions = {
  title: string;
  body: string;
  primaryLabel: string;
  /** Optional middle / alternate action */
  secondaryLabel?: string;
  cancelLabel?: string;
  /** Style primary as danger (e.g. discard / marcha) */
  primaryDanger?: boolean;
  secondaryDanger?: boolean;
};

type Pending = ConfirmOptions & {
  resolve: (c: ConfirmChoice) => void;
};

type Props = {
  pending: Pending | null;
  onChoose: (c: ConfirmChoice) => void;
};

/** Presentational overlay — use with useConfirmDialog(). */
export function ConfirmDialogView({ pending, onChoose }: Props) {
  if (!pending) return null;
  return (
    <View
      style={styles.overlay}
      pointerEvents="box-none"
      accessibilityViewIsModal
      accessibilityRole="summary"
      accessibilityLabel={pending.title}
    >
      <View style={styles.backdrop}>
        <View style={styles.card}>
          <Text style={styles.title} accessibilityRole="header">
            {pending.title}
          </Text>
          <Text style={styles.body}>{pending.body}</Text>
          <Pressable
            style={[
              pending.primaryDanger ? styles.btnDanger : styles.btnPri,
              styles.btnLarge,
              { marginTop: space.sm },
            ]}
            onPress={() => onChoose("primary")}
            accessibilityRole="button"
            accessibilityLabel={pending.primaryLabel}
          >
            <Text style={styles.btnTextLarge}>{pending.primaryLabel}</Text>
          </Pressable>
          {pending.secondaryLabel ? (
            <Pressable
              style={[
                pending.secondaryDanger ? styles.btnDanger : styles.btnSec,
                { marginTop: space.md },
              ]}
              onPress={() => onChoose("secondary")}
              accessibilityRole="button"
              accessibilityLabel={pending.secondaryLabel}
            >
              <Text style={styles.btnText}>{pending.secondaryLabel}</Text>
            </Pressable>
          ) : null}
          <Pressable
            style={[styles.btnSec, { marginTop: space.md }]}
            onPress={() => onChoose("cancel")}
            accessibilityRole="button"
            accessibilityLabel={pending.cancelLabel || "Cancelar"}
          >
            <Text style={styles.btnText}>{pending.cancelLabel || "Cancelar"}</Text>
          </Pressable>
        </View>
      </View>
    </View>
  );
}

export function useConfirmDialog() {
  const [pending, setPending] = useState<Pending | null>(null);
  const pendingRef = useRef<Pending | null>(null);

  const onChoose = useCallback((c: ConfirmChoice) => {
    const p = pendingRef.current;
    pendingRef.current = null;
    setPending(null);
    p?.resolve(c);
  }, []);

  const confirm = useCallback((opts: ConfirmOptions) => {
    return new Promise<ConfirmChoice>((resolve) => {
      const next: Pending = { ...opts, resolve };
      pendingRef.current = next;
      setPending(next);
    });
  }, []);

  const dialog = (
    <ConfirmDialogView pending={pending} onChoose={onChoose} />
  );

  return { confirm, dialog, open: !!pending };
}

const styles = StyleSheet.create({
  overlay: {
    ...StyleSheet.absoluteFill,
    zIndex: 11000,
    elevation: 11000,
  },
  backdrop: {
    flex: 1,
    backgroundColor: "rgba(0, 0, 0, 0.82)",
    justifyContent: "center",
    padding: space.lg,
  },
  card: {
    backgroundColor: colors.bg,
    borderRadius: radius.xl,
    padding: space.xl,
    borderWidth: 1,
    borderColor: colors.border,
  },
  title: {
    color: colors.text,
    fontSize: font.h2,
    fontWeight: font.weightBlack,
    marginBottom: space.md,
  },
  body: {
    color: colors.textSecondary,
    fontSize: font.body,
    lineHeight: 22,
    marginBottom: space.sm,
  },
  btnPri: {
    backgroundColor: colors.primary,
    paddingHorizontal: space.lg,
    paddingVertical: space.md,
    borderRadius: radius.md,
    minHeight: touchMin,
    justifyContent: "center",
  },
  btnDanger: {
    backgroundColor: colors.danger,
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
