#!/usr/bin/env bash
# Install + configure Mosquitto for VarioField (local MQTT broker).
# Safe to re-run. Prefer: sudo ./setup_mosquitto.sh
#
# Default: authentication REQUIRED (auditoría P0).
# Anonymous lab only: sudo VARIOFIELD_MQTT_ANON=1 ./setup_mosquitto.sh
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
CONF_SRC="$SCRIPT_DIR/mosquitto-variofield.conf"
ACL_SRC="$SCRIPT_DIR/mosquitto-variofield.acl.example"
PORT="${VARIOFIELD_MQTT_PORT:-1883}"
MQTT_USER="${VARIOFIELD_MQTT_USER:-variofield}"
MQTT_PASS="${VARIOFIELD_MQTT_PASS:-}"
ANON="${VARIOFIELD_MQTT_ANON:-0}"

PASSWD_FILE="/etc/mosquitto/variofield.passwd"
ACL_FILE="/etc/mosquitto/variofield.acl"

log() { echo "[variofield-mosquitto] $*"; }
die() { echo "[variofield-mosquitto] ERROR: $*" >&2; exit 1; }

need_root() {
  if [[ "${EUID:-$(id -u)}" -ne 0 ]]; then
    if command -v sudo >/dev/null 2>&1; then
      log "Requiere privilegios — reejecutando con sudo…"
      exec sudo -E env "PATH=$PATH" \
        "VARIOFIELD_MQTT_PORT=$PORT" \
        "VARIOFIELD_MQTT_USER=$MQTT_USER" \
        "VARIOFIELD_MQTT_PASS=$MQTT_PASS" \
        "VARIOFIELD_MQTT_ANON=$ANON" \
        bash "$0" "$@"
    fi
    die "Ejecutá como root o con sudo: sudo $0"
  fi
}

port_open() {
  local host="${1:-127.0.0.1}"
  if command -v ss >/dev/null 2>&1; then
    ss -lnt 2>/dev/null | grep -qE ":${PORT}\\b" && return 0
  fi
  timeout 1 bash -c "echo >/dev/tcp/${host}/${PORT}" 2>/dev/null && return 0
  return 1
}

install_packages() {
  if command -v mosquitto >/dev/null 2>&1; then
    log "Mosquitto ya instalado: $(command -v mosquitto)"
    return 0
  fi
  log "Instalando mosquitto…"
  if command -v apt-get >/dev/null 2>&1; then
    export DEBIAN_FRONTEND=noninteractive
    apt-get update -qq
    apt-get install -y -qq mosquitto mosquitto-clients
  elif command -v dnf >/dev/null 2>&1; then
    dnf install -y mosquitto
  elif command -v yum >/dev/null 2>&1; then
    yum install -y mosquitto
  elif command -v pacman >/dev/null 2>&1; then
    pacman -Sy --noconfirm mosquitto
  else
    die "No hay gestor de paquetes conocido. Instalá Mosquitto a mano."
  fi
  command -v mosquitto >/dev/null 2>&1 || die "mosquitto no quedó en PATH"
}

ensure_credentials() {
  if [[ "$ANON" == "1" ]]; then
    log "WARN: VARIOFIELD_MQTT_ANON=1 — broker ANÓNIMO (solo lab). No usar en planta."
    return 0
  fi
  if [[ -z "$MQTT_PASS" ]]; then
    if [[ -f "$PASSWD_FILE" ]]; then
      log "Usando password_file existente: $PASSWD_FILE (VARIOFIELD_MQTT_PASS vacío)"
      return 0
    fi
    # Generate a one-time pass and print it
    MQTT_PASS="$(openssl rand -base64 18 2>/dev/null | tr -d '/+=' | head -c 20 || true)"
    if [[ -z "$MQTT_PASS" ]]; then
      MQTT_PASS="variofield-$(date +%s)"
    fi
    log "Generado password para user '${MQTT_USER}' (guardalo; no se vuelve a mostrar):"
    log "  USER=${MQTT_USER}"
    log "  PASS=${MQTT_PASS}"
  fi
  if ! command -v mosquitto_passwd >/dev/null 2>&1; then
    die "mosquitto_passwd no está en PATH"
  fi
  touch "$PASSWD_FILE"
  chown mosquitto:mosquitto "$PASSWD_FILE" 2>/dev/null || true
  chmod 640 "$PASSWD_FILE" 2>/dev/null || true
  mosquitto_passwd -b "$PASSWD_FILE" "$MQTT_USER" "$MQTT_PASS"
  log "password_file actualizado: $PASSWD_FILE (user=$MQTT_USER)"
}

write_acl() {
  if [[ "$ANON" == "1" ]]; then
    return 0
  fi
  if [[ -f "$ACL_SRC" ]]; then
    # Substitute username if different from example
    sed "s/^user variofield$/user ${MQTT_USER}/" "$ACL_SRC" > "$ACL_FILE"
  else
    cat > "$ACL_FILE" <<EOF
user ${MQTT_USER}
topic readwrite saj/pdm30/#
EOF
  fi
  chown mosquitto:mosquitto "$ACL_FILE" 2>/dev/null || true
  chmod 640 "$ACL_FILE" 2>/dev/null || true
  log "ACL escrita: $ACL_FILE"
}

write_config() {
  local dest_dir="/etc/mosquitto/conf.d"
  local dest="$dest_dir/variofield.conf"
  if [[ ! -d "$dest_dir" ]]; then
    dest_dir="/etc/mosquitto"
    dest="$dest_dir/variofield.conf"
    mkdir -p "$dest_dir"
    if [[ -f /etc/mosquitto/mosquitto.conf ]] && ! grep -q "variofield.conf" /etc/mosquitto/mosquitto.conf 2>/dev/null; then
      echo "include_dir /etc/mosquitto" >> /etc/mosquitto/mosquitto.conf 2>/dev/null || true
    fi
  fi

  if [[ "$ANON" == "1" ]]; then
    cat > "$dest" <<EOF
# VarioField — ANONYMOUS DEV MODE (VARIOFIELD_MQTT_ANON=1)
listener ${PORT}
allow_anonymous true
EOF
  elif [[ -f "$CONF_SRC" ]]; then
    # Rewrite listener port if needed
    sed -e "s/^listener .*/listener ${PORT}/" "$CONF_SRC" > "$dest"
  else
    cat > "$dest" <<EOF
listener ${PORT}
allow_anonymous false
password_file ${PASSWD_FILE}
acl_file ${ACL_FILE}
EOF
  fi
  log "Config escrita: $dest"
}

start_service() {
  if command -v systemctl >/dev/null 2>&1; then
    systemctl enable mosquitto 2>/dev/null || systemctl enable mosquitto.service 2>/dev/null || true
    systemctl restart mosquitto 2>/dev/null || systemctl restart mosquitto.service 2>/dev/null || true
    sleep 0.8
    if systemctl is-active --quiet mosquitto 2>/dev/null || systemctl is-active --quiet mosquitto.service 2>/dev/null; then
      log "Servicio mosquitto activo (systemd)"
      return 0
    fi
  fi
  if ! port_open; then
    log "Iniciando mosquitto en segundo plano…"
    mosquitto -c /etc/mosquitto/mosquitto.conf -d 2>/dev/null || mosquitto -d || true
    sleep 0.8
  fi
}

ensure_default_mqtt_profile_hint() {
  log "Listo. Perfil recomendado en VarioField:"
  log "  nombre: Local Mosquitto"
  log "  host:   127.0.0.1   (app en este PC)  /  IP LAN para el Edge"
  log "  puerto: ${PORT}"
  if [[ "$ANON" == "1" ]]; then
    log "  auth:   ANÓNIMO (solo lab)"
  else
    log "  user:   ${MQTT_USER}"
    log "  pass:   (el que configuraste / se imprimió arriba)"
    log "  Edge:   mqtt set <IP_LAN> ${PORT}"
    log "          mqtt user ${MQTT_USER} <pass>"
    log "          mqtt enable"
  fi
  if command -v hostname >/dev/null 2>&1; then
    hostname -I 2>/dev/null | tr ' ' '\n' | grep -v '^$' | head -5 | while read -r ip; do
      log "  IP de este PC (posible): $ip"
    done || true
  fi
  log "Ver docs/SECURITY.md"
}

main() {
  need_root "$@"
  install_packages
  ensure_credentials
  write_acl
  write_config
  start_service
  if port_open 127.0.0.1; then
    log "OK — broker escuchando en puerto ${PORT} (probado 127.0.0.1)"
  else
    die "Mosquitto instalado pero el puerto ${PORT} no responde. Revisá: journalctl -u mosquitto -e"
  fi
  ensure_default_mqtt_profile_hint
}

main "$@"
