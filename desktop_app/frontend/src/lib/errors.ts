/**
 * Catálogo de errores de campo — código interno + texto para el operario + acción.
 */

export type ErrorCode =
  | "SERVICE_DOWN"
  | "SERVICE_LINK"
  | "NO_USB"
  | "USB_OPEN"
  | "NO_MQTT_PROFILE"
  | "MQTT_CONNECT"
  | "MQTT_HOST_LOCAL"
  | "NO_BT_DEVICE"
  | "BT_SCAN"
  | "BT_CONNECT"
  | "DRIVE_NO_LINK"
  | "DRIVE_OK"
  | "COMPARE_FAIL"
  | "COMPARE_TIMEOUT"
  | "SYNC_FAIL"
  | "SYNC_EMPTY"
  | "NOT_CONNECTED"
  | "RECIPE_EMPTY"
  | "WIFI_PROFILE"
  | "WIFI_SPACES"
  | "MQTT_PROFILE"
  | "SAVE_FAIL"
  | "LOAD_FAIL"
  | "IMPORT_FAIL"
  | "EXPORT_FAIL"
  | "GENERIC";

export type RetryAction =
  | "reconnect"
  | "refresh_ports"
  | "scan_bt"
  | "retry_compare"
  | "retry_sync"
  | "retry_ping"
  | "open_profiles"
  | "go_connect"
  | "go_recipes"
  | "none";

export type AppError = {
  code: ErrorCode;
  /** Short title for alert / banner */
  title: string;
  /** What happened + what to do */
  message: string;
  retry?: RetryAction;
  retryLabel?: string;
  /** Keep technical detail for diagnostics */
  technical?: string;
};

const CATALOG: Record<
  ErrorCode,
  Omit<AppError, "code" | "technical">
> = {
  SERVICE_DOWN: {
    title: "Servicio no disponible",
    message:
      "No se pudo iniciar el servicio de comunicación de VarioField.\n" +
      "Cierra la aplicación por completo y ábrela de nuevo.",
    retry: "none",
  },
  SERVICE_LINK: {
    title: "Comunicación interna interrumpida",
    message:
      "La app perdió el enlace con el servicio local.\n" +
      "Reinicia VarioField. Si sigue fallando, reinicia el PC.",
    retry: "none",
  },
  NO_USB: {
    title: "No hay cable USB",
    message:
      "No se detecta ningún convertidor o módulo por USB.\n" +
      "1) Conecta el cable\n" +
      "2) Pulsa «Actualizar cables»\n" +
      "3) Vuelve a conectar",
    retry: "refresh_ports",
    retryLabel: "Actualizar cables",
  },
  USB_OPEN: {
    title: "No se pudo usar el puerto USB",
    message:
      "El cable está, pero no se pudo abrir el puerto.\n" +
      "Prueba otro puerto USB, cierra otros programas que usen el cable y reintenta.",
    retry: "reconnect",
    retryLabel: "Reintentar conexión",
  },
  NO_MQTT_PROFILE: {
    title: "Falta perfil de red",
    message:
      "Para conectar por Wi‑Fi hace falta un perfil de broker MQTT.\n" +
      "Ve a Más → Red del equipo y crea un perfil con la IP del PC o del servidor de planta.",
    retry: "open_profiles",
    retryLabel: "Crear perfil",
  },
  MQTT_CONNECT: {
    title: "No hay enlace por red",
    message:
      "No se pudo conectar al broker MQTT.\n" +
      "Comprueba que el PC tiene red, que Mosquitto (u otro broker) está en marcha " +
      "y que el perfil usa la IP correcta (no “localhost” si el módulo es el que se conecta).",
    retry: "reconnect",
    retryLabel: "Reintentar",
  },
  MQTT_HOST_LOCAL: {
    title: "Revisa la dirección del broker",
    message:
      "“localhost” o 127.0.0.1 desde el módulo apunta al propio módulo, no a este PC.\n" +
      "Usa la IP del PC en la red de planta (ej. 192.168.x.x).",
    retry: "open_profiles",
    retryLabel: "Editar perfil",
  },
  NO_BT_DEVICE: {
    title: "No hay equipo Bluetooth",
    message:
      "Pulsa «Buscar equipos» y elige el módulo en la lista.\n" +
      "Acerca el módulo, enciéndelo y asegúrate de que el Bluetooth del PC está activo.",
    retry: "scan_bt",
    retryLabel: "Buscar otra vez",
  },
  BT_SCAN: {
    title: "Búsqueda Bluetooth fallida",
    message:
      "No se pudo buscar equipos.\n" +
      "Activa el Bluetooth del PC e inténtalo de nuevo.",
    retry: "scan_bt",
    retryLabel: "Buscar otra vez",
  },
  BT_CONNECT: {
    title: "No se pudo enlazar por Bluetooth",
    message:
      "El equipo se vio, pero la conexión falló.\n" +
      "Acércalo, vuelve a buscar y selecciona el módulo. No hace falta emparejar a mano en el sistema.",
    retry: "reconnect",
    retryLabel: "Reintentar",
  },
  DRIVE_NO_LINK: {
    title: "El variador no responde",
    message:
      "El módulo está en línea, pero el variador no contesta por RS485.\n" +
      "Revisa el cable del bus, la polaridad A/B y que el variador tenga alimentación.",
    retry: "retry_ping",
    retryLabel: "Comprobar otra vez",
  },
  DRIVE_OK: {
    title: "Variador OK",
    message: "El variador responde correctamente.",
    retry: "none",
  },
  COMPARE_FAIL: {
    title: "No se pudo comparar",
    message:
      "Falló la lectura de parámetros del variador.\n" +
      "Mantén la conexión y reintenta. Si usas red, espera a tener buena señal.",
    retry: "retry_compare",
    retryLabel: "Reintentar comparación",
  },
  COMPARE_TIMEOUT: {
    title: "La comparación tardó demasiado",
    message:
      "La lectura no terminó a tiempo. Se pueden mostrar resultados parciales.\n" +
      "Reintenta con el módulo cerca (si es Bluetooth) o con buena red.",
    retry: "retry_compare",
    retryLabel: "Reintentar",
  },
  SYNC_FAIL: {
    title: "Envío interrumpido",
    message:
      "No se completó el envío de la receta.\n" +
      "No desconectes el cable. Reintenta el envío; los parámetros ya enviados pueden haberse aplicado.",
    retry: "retry_sync",
    retryLabel: "Reintentar envío",
  },
  SYNC_EMPTY: {
    title: "Nada que enviar",
    message:
      "La receta no tiene parámetros enviables (todos pueden estar marcados como “solo manual”).\n" +
      "Revisa la receta en el paso 2.",
    retry: "go_recipes",
    retryLabel: "Ir a recetas",
  },
  NOT_CONNECTED: {
    title: "Sin conexión al equipo",
    message: "Conecta el módulo primero (Inicio → paso 1, o pestaña Equipo).",
    retry: "go_connect",
    retryLabel: "Ir a conectar",
  },
  RECIPE_EMPTY: {
    title: "Receta vacía",
    message: "Abre o crea una receta antes de continuar.",
    retry: "go_recipes",
    retryLabel: "Ir a recetas",
  },
  WIFI_PROFILE: {
    title: "Falta perfil Wi‑Fi",
    message:
      "Crea un perfil Wi‑Fi (nombre, SSID y contraseña sin espacios) y luego envíalo al módulo.",
    retry: "open_profiles",
    retryLabel: "Crear perfil",
  },
  WIFI_SPACES: {
    title: "SSID o contraseña con espacios",
    message:
      "El nombre de la red y la contraseña no deben llevar espacios.\n" +
      "Edita el perfil y vuelve a enviarlo.",
    retry: "open_profiles",
    retryLabel: "Editar perfil",
  },
  MQTT_PROFILE: {
    title: "Falta perfil MQTT",
    message: "Crea un perfil de red con la IP del broker de esta planta.",
    retry: "open_profiles",
    retryLabel: "Crear perfil",
  },
  SAVE_FAIL: {
    title: "No se pudo guardar",
    message: "Comprueba el nombre del archivo y el espacio en disco, e inténtalo de nuevo.",
    retry: "none",
  },
  LOAD_FAIL: {
    title: "No se pudo abrir la receta",
    message: "El archivo puede estar dañado o no ser una receta válida de VarioField.",
    retry: "none",
  },
  IMPORT_FAIL: {
    title: "Importación fallida",
    message: "El JSON no tiene el formato de receta esperado (name + parameters).",
    retry: "none",
  },
  EXPORT_FAIL: {
    title: "No se pudo exportar",
    message: "No se pudo escribir el archivo. Elige otra carpeta e inténtalo de nuevo.",
    retry: "none",
  },
  GENERIC: {
    title: "Algo no ha ido bien",
    message: "Ha ocurrido un error. Revisa la conexión e inténtalo de nuevo.",
    retry: "none",
  },
};

export function makeError(
  code: ErrorCode,
  technical?: string
): AppError {
  const base = CATALOG[code];
  return { code, ...base, technical: technical || undefined };
}

/**
 * Map raw Error / string / HTTP detail → AppError for operators.
 */
export function classifyError(
  err: unknown,
  hint?: {
    context?:
      | "connect"
      | "usb"
      | "mqtt"
      | "bt"
      | "bt_scan"
      | "sync"
      | "compare"
      | "ping"
      | "save"
      | "load"
      | "import"
      | "export"
      | "wifi"
      | "profiles";
  }
): AppError {
  const raw =
    err instanceof Error
      ? err.message
      : typeof err === "string"
        ? err
        : JSON.stringify(err);
  const s = raw.toLowerCase();
  const ctx = hint?.context;

  if (
    s.includes("failed to fetch") ||
    s.includes("networkerror") ||
    s.includes("econnrefused") ||
    s.includes("network request failed")
  ) {
    return makeError("SERVICE_DOWN", raw);
  }

  if (ctx === "usb" || s.includes("serial") || s.includes("tty") || s.includes("com")) {
    if (
      s.includes("no hay cable") ||
      s.includes("no cable") ||
      s.includes("no se detecta") ||
      s.includes("selecciona un puerto") ||
      s.includes("port")
    ) {
      if (s.includes("no") || s.includes("select") || s.includes("detect")) {
        return makeError("NO_USB", raw);
      }
    }
    if (s.includes("open") || s.includes("permission") || s.includes("busy") || s.includes("access")) {
      return makeError("USB_OPEN", raw);
    }
  }

  if (ctx === "mqtt" || s.includes("mqtt") || s.includes("broker")) {
    if (s.includes("perfil") || s.includes("profile") || s.includes("host")) {
      if (s.includes("falta") || s.includes("crea") || s.includes("valid")) {
        return makeError("NO_MQTT_PROFILE", raw);
      }
    }
    if (s.includes("127.0.0.1") || s.includes("localhost")) {
      return makeError("MQTT_HOST_LOCAL", raw);
    }
    return makeError("MQTT_CONNECT", raw);
  }

  if (ctx === "bt_scan") {
    return makeError("BT_SCAN", raw);
  }
  if (ctx === "bt" || s.includes("bluetooth") || s.includes("rfcomm") || s.includes("spp")) {
    // Prefer connect errors over "no device" — long messages mention "dispositivo"
    if (
      s.includes("no se pudo abrir") ||
      s.includes("cannot allocate") ||
      s.includes("enomem") ||
      s.includes("errno 12") ||
      s.includes("conexión cerrada") ||
      s.includes("conexion cerrada") ||
      s.includes("peer")
    ) {
      return makeError("BT_CONNECT", raw);
    }
    if (
      s.includes("seleccioná") ||
      s.includes("selecciona") ||
      s.includes("ningún dispositivo") ||
      s.includes("ningun dispositivo")
    ) {
      return makeError("NO_BT_DEVICE", raw);
    }
    return makeError("BT_CONNECT", raw);
  }

  if (ctx === "sync") {
    if (s.includes("enviable") || s.includes("empty") || s.includes("nada")) {
      return makeError("SYNC_EMPTY", raw);
    }
    return makeError("SYNC_FAIL", raw);
  }

  if (ctx === "compare") {
    if (s.includes("timeout") || s.includes("tiempo")) {
      return makeError("COMPARE_TIMEOUT", raw);
    }
    return makeError("COMPARE_FAIL", raw);
  }

  if (ctx === "ping" || s.includes("ping fail") || s.includes("timeout")) {
    if (s.includes("link ok")) return makeError("DRIVE_OK", raw);
    return makeError("DRIVE_NO_LINK", raw);
  }

  if (ctx === "wifi" || s.includes("ssid") || s.includes("wifi")) {
    if (s.includes("espacio")) return makeError("WIFI_SPACES", raw);
    return makeError("WIFI_PROFILE", raw);
  }

  if (ctx === "profiles") return makeError("MQTT_PROFILE", raw);
  if (ctx === "save") return makeError("SAVE_FAIL", raw);
  if (ctx === "load") return makeError("LOAD_FAIL", raw);
  if (ctx === "import") return makeError("IMPORT_FAIL", raw);
  if (ctx === "export") return makeError("EXPORT_FAIL", raw);

  if (
    s.includes("sin conexión") ||
    s.includes("not connected") ||
    (s.includes("conecta") && s.includes("primero"))
  ) {
    return makeError("NOT_CONNECTED", raw);
  }
  if (
    s.includes("vacía") ||
    s.includes("vacia") ||
    s.includes("empty") ||
    s.includes("nada enviable") ||
    s.includes("ninguna receta")
  ) {
    return makeError(
      s.includes("enviable") || s.includes("manual") ? "SYNC_EMPTY" : "RECIPE_EMPTY",
      raw
    );
  }
  if (s.includes("no hay cable") || s.includes("no cable") || s.includes("detectado")) {
    return makeError("NO_USB", raw);
  }
  if (s.includes("selecciona un dispositivo") || s.includes("busca equipos")) {
    return makeError("NO_BT_DEVICE", raw);
  }
  if (s.includes("falta perfil")) {
    return makeError(
      s.includes("wifi") ? "WIFI_PROFILE" : "NO_MQTT_PROFILE",
      raw
    );
  }

  return makeError("GENERIC", raw);
}

export function classifyFromLine(line: string): AppError | null {
  if (line.includes("Link OK")) return makeError("DRIVE_OK", line);
  if (line.includes("PING FAIL") || (line.includes("Timeout") && line.toLowerCase().includes("ping"))) {
    return makeError("DRIVE_NO_LINK", line);
  }
  if (line.startsWith("ERR:")) {
    return makeError("GENERIC", line);
  }
  return null;
}
