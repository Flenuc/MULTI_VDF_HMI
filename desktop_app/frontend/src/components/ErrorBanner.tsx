/**
 * Banner de error de campo: título, mensaje, reintentar, descartar.
 */
import { Pressable, StyleSheet, Text, View } from "react-native";

import type { AppError } from "../lib/errors";
import { colors, font, radius, space, touchMin } from "../theme";

type Props = {
  error: AppError | null;
  onDismiss: () => void;
  onRetry?: () => void;
};

export function ErrorBanner({ error, onDismiss, onRetry }: Props) {
  if (!error) return null;
  const canRetry =
    !!error.retry &&
    error.retry !== "none" &&
    typeof onRetry === "function" &&
    !!error.retryLabel;

  return (
    <View
      style={styles.wrap}
      accessibilityRole="alert"
      accessibilityLiveRegion="assertive"
    >
      <View style={styles.head}>
        <Text style={styles.title}>{error.title}</Text>
        <Pressable
          onPress={onDismiss}
          hitSlop={12}
          accessibilityLabel="Cerrar aviso"
          style={styles.dismiss}
        >
          <Text style={styles.dismissText}>✕</Text>
        </Pressable>
      </View>
      <Text style={styles.body}>{error.message}</Text>
      {error.technical ? (
        <Text style={styles.tech} numberOfLines={2}>
          Detalle: {error.technical}
        </Text>
      ) : null}
      <View style={styles.actions}>
        {canRetry ? (
          <Pressable
            style={styles.btnRetry}
            onPress={onRetry}
            accessibilityRole="button"
            accessibilityLabel={error.retryLabel}
          >
            <Text style={styles.btnRetryText}>{error.retryLabel}</Text>
          </Pressable>
        ) : null}
        <Pressable style={styles.btnOk} onPress={onDismiss} accessibilityRole="button">
          <Text style={styles.btnOkText}>Entendido</Text>
        </Pressable>
      </View>
    </View>
  );
}

const styles = StyleSheet.create({
  wrap: {
    backgroundColor: colors.dangerBg,
    borderColor: colors.danger,
    borderWidth: 1,
    borderRadius: radius.lg,
    padding: space.md,
    marginHorizontal: space.lg,
    marginTop: space.sm,
  },
  head: {
    flexDirection: "row",
    alignItems: "center",
    justifyContent: "space-between",
    marginBottom: space.sm,
  },
  title: {
    color: colors.text,
    fontSize: font.lg,
    fontWeight: font.weightBlack,
    flex: 1,
  },
  dismiss: {
    minWidth: 36,
    minHeight: 36,
    alignItems: "center",
    justifyContent: "center",
  },
  dismissText: { color: colors.textMuted, fontSize: 18, fontWeight: font.weightBold },
  body: {
    color: colors.textSecondary,
    fontSize: font.body,
    lineHeight: 20,
    marginBottom: space.md,
  },
  tech: {
    color: colors.textDim,
    fontSize: font.xs,
    fontFamily: "monospace",
    marginBottom: space.sm,
  },
  actions: { flexDirection: "row", flexWrap: "wrap", gap: space.sm },
  btnRetry: {
    backgroundColor: colors.primary,
    paddingHorizontal: space.lg,
    paddingVertical: space.md,
    borderRadius: radius.md,
    minHeight: touchMin,
    justifyContent: "center",
  },
  btnRetryText: {
    color: "#fff",
    fontWeight: font.weightBold,
    fontSize: font.body,
  },
  btnOk: {
    backgroundColor: colors.surfaceHover,
    paddingHorizontal: space.lg,
    paddingVertical: space.md,
    borderRadius: radius.md,
    minHeight: touchMin,
    justifyContent: "center",
  },
  btnOkText: {
    color: colors.text,
    fontWeight: font.weightSemi,
    fontSize: font.body,
  },
});
