/** Textos de interfaz — español operativo (operarios de campo). */

export const t = {
  appName: "VarioField",
  tagline: "Recetas y enlace a variadores en campo",

  // Tabs
  tabHome: "Inicio",
  tabConnect: "Equipo",
  tabParams: "Recetas",
  tabMore: "Más",
  tabEdge: "Red del equipo",
  tabHelp: "Ayuda",

  // Home — 4 big steps
  homeTitle: "¿Qué quieres hacer?",
  homeSubtitle: "Sigue los pasos en orden. Puedes saltar al que necesites.",
  step1Title: "1 · Conectar el módulo",
  step1Body: "Cable USB, red Wi‑Fi o Bluetooth. Sin esto no se habla con el variador.",
  step1Cta: "Ir a conectar",
  step1Done: "Módulo conectado",
  step2Title: "2 · Elegir la receta",
  step2Body: "Abre o edita la lista de parámetros que quieres en el variador.",
  step2Cta: "Ir a recetas",
  step2Done: (n: number) => `Receta lista (${n} parámetros)`,
  step3Title: "3 · Comprobar el variador",
  step3Body: "Verifica que responde y compara la receta con lo que hay instalado.",
  step3CtaCheck: "Comprobar enlace",
  step3CtaCompare: "Comparar receta",
  step3Done: "Comprobación hecha",
  step4Title: "4 · Enviar la receta",
  step4Body: "Escribe los valores en el variador. Puedes enviar sin comparar; te avisaremos.",
  step4Cta: "Enviar al variador",
  step4Done: "Último envío OK",
  stepNeedConnect: "Conecta el módulo antes (paso 1).",
  stepNeedRecipe: "Elige o crea una receta (paso 2).",
  homeLive: "Lectura en vivo",
  homeMoreNetwork: "Configurar red del módulo (Wi‑Fi / MQTT)",
  homeMoreHelp: "Ayuda y tutorial",

  // Connection status
  statusReady: "Listo",
  statusWorking: "Trabajando…",
  statusOffline: "Sin conexión al equipo",
  statusOnline: "Equipo conectado",
  statusServiceError: "No se pudo iniciar el servicio. Reinicia la aplicación.",
  statusLinkError: "Problema de comunicación interna. Reinicia la app.",

  // Modes (operator-facing)
  modeMqtt: "Por red (Wi‑Fi)",
  modeUsb: "Por cable USB",
  modeBle: "Bluetooth (pantalla)",
  modeBt: "Bluetooth",
  modeDummy: "Prueba sin equipo",

  connect: "Conectar",
  disconnect: "Desconectar",
  scanBt: "Buscar equipos",
  refreshPorts: "Actualizar cables",
  portLabel: "Cable / puerto",
  baudLabel: "Velocidad (solo si te lo indica el técnico)",
  mqttProfileLabel: "Perfil de red / broker",
  brokerSetup: "Preparar broker local (Mosquitto)",
  brokerChecking: "Comprobando broker…",
  brokerOk: "Broker local listo en este PC",
  brokerNeedSudo: "Hace falta instalar Mosquitto con permisos de administrador",
  btDeviceLabel: "Equipo Bluetooth",

  // Telemetry
  telTitle: "Lectura en vivo",
  telFreq: "Frecuencia",
  telAmp: "Corriente",
  telVdc: "Tensión bus",
  telVout: "Tensión salida",
  telPfb: "Presión real",
  telPset: "Consigna",
  telStatus: "Estado",

  // Quick actions (no raw CLI names)
  actCheckDrive: "Comprobar variador",
  actLiveOn: "Activar lectura en vivo",
  actLiveOff: "Pausar lectura en vivo",
  actStart: "Marcha",
  actStop: "Paro",
  actWifiInfo: "Estado Wi‑Fi del equipo",
  actMqttInfo: "Estado de red del equipo",
  actBtInfo: "Estado Bluetooth",
  actHelpAdvanced: "Ayuda técnica (avanzado)",

  activity: "Actividad",
  activityEmpty: "Aquí verás lo que va haciendo la app…",
  cmdPlaceholder: "Comando técnico (solo avanzado)…",
  send: "Enviar",

  // Drive model (multi-VDF)
  driveModelTitle: "Modelo de variador",
  driveModelHint:
    "Elige el modelo conectado al módulo. Las recetas y el mapa de parámetros dependen de esto.",
  driveModelRecipes: "Recetas de este modelo",
  driveModelAllRecipes: "Todas las recetas",
  driveModelApplied: (name: string) => `Modelo activo: ${name}`,
  driveModelEdgeOk: (name: string) => `Módulo configurado para ${name}`,
  driveModelMismatch:
    "La receta es de otro modelo. Cambia el modelo o elige otra receta.",
  driveModelFilter: "Filtrar recetas por modelo",
  catalogColName: "Nombre (manual)",
  catalogLoading: "Cargando catálogo del modelo…",
  catalogReady: (n: number) => `Catálogo: ${n} parámetros del manual`,
  catalogMissing: "Sin nombre en catálogo",
  catalogUnit: "Unidad",

  // Recipes
  recipesTitle: "Receta de parámetros",
  recipesServer: "Recetas en este PC",
  openJson: "Abrir archivo…",
  saveAs: "Guardar como…",
  saveServer: "Guardar en el PC",
  exportBoth: "Guardar como + en el PC",
  sendToDrive: "Enviar al variador",
  compareDrive: "Comparar con el variador",
  cancelOp: "Cancelar",
  editor: "Editar parámetro",
  addUpdate: "Añadir / actualizar",
  remove: "Quitar",
  manualFlag: "Solo manual (no se envía al variador por cable)",
  indexLabel: "Número (0–47)",
  valueLabel: "Valor",
  notesLabel: "Descripción / notas",
  groupLabel: "Grupo",

  // Edge / network
  edgeTitle: "Red del módulo de campo",
  edgeWifiHint:
    "Usa un perfil Wi‑Fi guardado para que el módulo se una a la red de la planta. " +
    "El SSID y la contraseña no deben llevar espacios.",
  edgeMqttHint:
    "Indica al módulo la dirección del broker MQTT de esta planta " +
    "(normalmente la IP del PC o del servidor, no “localhost” desde el módulo).",
  applyWifi: "Enviar Wi‑Fi al módulo",
  applyMqtt: "Enviar red MQTT al módulo",
  editProfiles: "Crear o editar perfiles…",
  reloadProfiles: "Actualizar lista de perfiles",

  // Profiles modal
  profilesTitle: "Perfiles de esta planta",
  profilesMqttHelp:
    "Perfil MQTT: host = IP o nombre del broker alcanzable desde el módulo. " +
    "Puerto habitual 1883. El “prefijo de temas” solo cámbialo si te lo indica el técnico.",
  profilesWifiHelp:
    "Perfil Wi‑Fi: nombre libre (ej. Planta-1), SSID exacto de la red, contraseña. " +
    "Sin espacios en SSID ni contraseña. Luego usa “Enviar Wi‑Fi al módulo”.",
  saveMqttProfile: "Guardar perfil de red",
  saveWifiProfile: "Guardar perfil Wi‑Fi",
  close: "Cerrar",

  // Sync confirm
  syncTitle: "Enviar receta al variador",
  syncBody: (n: number, skipped: number) =>
    `Se van a enviar ${n} parámetro(s) al variador.\n` +
    (skipped ? `Se omiten ${skipped} marcados como “solo manual”.\n\n` : "\n") +
    "Recomendación: compara antes con el variador para ver diferencias.\n" +
    "¿Enviar de todos modos?",
  syncRecommendCompare: "Comparar primero (recomendado)",
  syncSendAnyway: "Enviar sin comparar",
  syncCancel: "Cancelar",

  // Tutorial
  tutorialTitle: "Bienvenido a VarioField",
  tutorialSkip: "Saltar",
  tutorialNext: "Siguiente",
  tutorialPrev: "Anterior",
  tutorialFinish: "Empezar a trabajar",
  tutorialAgain: "Ver tutorial otra vez",
  tutorialSteps: [
    {
      title: "¿Qué es VarioField?",
      body:
        "Es la app de campo para conectar con el módulo junto al variador, " +
        "ver lecturas en vivo y gestionar recetas de parámetros.\n\n" +
        "No está atada a una sola marca: el objetivo es trabajar con distintos variadores " +
        "a través del mismo módulo Edge.",
    },
    {
      title: "Conectar el equipo",
      body:
        "Elige cómo hablas con el módulo:\n" +
        "· Cable USB — puesta en marcha y diagnóstico\n" +
        "· Red (Wi‑Fi) — trabajo habitual en planta\n" +
        "· Bluetooth — sin cables cuando el módulo lo permite\n\n" +
        "Pulsa Conectar. La app activará sola la lectura en vivo.",
    },
    {
      title: "Recetas de parámetros",
      body:
        "Una receta es la lista de valores que quieres en el variador.\n\n" +
        "Puedes abrir un archivo JSON, usar una receta guardada en el PC, " +
        "editar valores y guardar.\n\n" +
        "Los marcados “solo manual” no se envían por el bus de campo.",
    },
    {
      title: "Comparar y enviar",
      body:
        "Comparar: lee el variador y marca qué no coincide con la receta.\n" +
        "Enviar: escribe la receta en el variador.\n\n" +
        "Puedes enviar sin comparar, pero es más seguro comparar antes. " +
        "La app te lo recordará sin bloquearte.",
    },
    {
      title: "Red del módulo",
      body:
        "Si el módulo debe unirse al Wi‑Fi de planta o al broker MQTT, " +
        "usa la pestaña “Red del equipo”.\n\n" +
        "Sigue las instrucciones de cada perfil (SSID sin espacios, IP del broker " +
        "vista desde el módulo, no desde “localhost”).\n\n" +
        "Puedes volver a este tutorial en Ayuda en cualquier momento.",
    },
  ],

  about: "Acerca de",
  diagnostics: "Diagnóstico (técnicos)",
  diagnosticsUnlock: "Modo técnico (PIN)",
  diagnosticsLock: "Volver a modo operario",
  roleOperator: "Operario",
  roleTech: "Técnico",
  roleBadgeOp: "Modo operario",
  roleBadgeTech: "Modo técnico",
  pinTitle: "Acceso técnico",
  pinHint:
    "Introduce el PIN de técnico para ver CLI, simulado, log crudo y opciones avanzadas.\n" +
    "El modo operario sigue pudiendo editar perfiles Wi‑Fi/MQTT de planta.",
  pinPlaceholder: "PIN (4+ dígitos)",
  pinOk: "Entrar como técnico",
  pinCancel: "Cancelar",
  pinWrong: "PIN incorrecto",
  pinChange: "Cambiar PIN de técnico",
  pinChanged: "PIN actualizado",
  exportProfiles: "Exportar plantilla de perfiles (planta)",
  importProfiles: "Importar plantilla de perfiles",
  profilesTemplateOk: "Plantilla de perfiles aplicada",
  profilesTemplateHint:
    "Guarda o carga un JSON con perfiles Wi‑Fi y MQTT de esta planta " +
    "(útil para clonar configuración entre PCs).",
} as const;
