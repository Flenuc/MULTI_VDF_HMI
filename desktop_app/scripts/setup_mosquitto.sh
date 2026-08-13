#!/usr/bin/env bash
# Install + configure Mosquitto for VarioField (local MQTT broker).
# Safe to re-run. Prefer: sudo ./setup_mosquitto.sh
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
CONF_SRC="$SCRIPT_DIR/mosquitto-variofield.conf"
PORT="${VARIOFIELD_MQTT_PORT:-1883}"

log() { echo "[variofield-mosquitto] $*"; }
die() { echo "[variofield-mosquitto] ERROR: $*" >&2; exit 1; }

need_root() {
  if [[ "${EUID:-$(id -u)}" -ne 0 ]]; then
    if command -v sudo >/dev/null 2>&1; then
      log "Requiere privilegios — reejecutando con sudo…"
      exec sudo -E env "PATH=$PATH" bash "$0" "$@"
    fi
    die "Ejecutá como root o con sudo: sudo $0"
  fi
}

port_open() {
  local host="${1:-127.0.0.1}"
  if command -v ss >/dev/null 2>&1; then
    ss -lnt 2>/dev/null | grep -qE ":${PORT}\\b" && return 0
  fi
  # bash /dev/tcp
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
    die "No hay gestor de paquetes conocido (apt/dnf/yum/pacman). Instalá Mosquitto a mano."
  fi
  command -v mosquitto >/dev/null 2>&1 || die "mosquitto no quedó en PATH tras la instalación"
}

write_config() {
  local dest_dir="/etc/mosquitto/conf.d"
  local dest="$dest_dir/variofield.conf"
  if [[ ! -d "$dest_dir" ]]; then
    # some distros only have mosquitto.conf
    dest_dir="/etc/mosquitto"
    dest="$dest_dir/variofield.conf"
    mkdir -p "$dest_dir"
    if [[ -f /etc/mosquitto/mosquitto.conf ]] && ! grep -q "variofield.conf" /etc/mosquitto/mosquitto.conf 2>/dev/null; then
      echo "include_dir /etc/mosquitto" >> /etc/mosquitto/mosquitto.conf 2>/dev/null || true
    fi
  fi
  if [[ -f "$CONF_SRC" ]]; then
    cp -f "$CONF_SRC" "$dest"
  else
    cat > "$dest" <<EOF
listener ${PORT}
allow_anonymous true
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
  # Fallback: run in background if service unit missing
  if ! port_open; then
    log "Iniciando mosquitto en segundo plano…"
    if [[ -f /etc/mosquitto/conf.d/variofield.conf ]]; then
      mosquitto -c /etc/mosquitto/mosquitto.conf -d 2>/dev/null || mosquitto -d || true
    else
      mosquitto -d || true
    fi
    sleep 0.8
  fi
}

ensure_default_mqtt_profile_hint() {
  log "Listo. Perfil recomendado en VarioField:"
  log "  nombre: Local Mosquitto"
  log "  host:   127.0.0.1   (app en este PC)"
  log "  puerto: ${PORT}"
  log "  En el módulo Edge: mqtt set <IP_LAN_DE_ESTE_PC> ${PORT}"
  if command -v hostname >/dev/null 2>&1; then
    # best-effort LAN IPs
    hostname -I 2>/dev/null | tr ' ' '\n' | grep -v '^$' | head -5 | while read -r ip; do
      log "  IP de este PC (posible): $ip"
    done || true
  fi
}

main() {
  need_root "$@"
  install_packages
  write_config
  start_service
  if port_open 127.0.0.1; then
    log "OK — broker escuchando en 0.0.0.0:${PORT} (probado 127.0.0.1)"
  else
    die "Mosquitto instalado pero el puerto ${PORT} no responde. Revisá: journalctl -u mosquitto -e"
  fi
  ensure_default_mqtt_profile_hint
}

main "$@"
