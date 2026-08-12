# Variante: Guition JC-ESP32P4-M3-DEV

Firmware Edge para la placa **Guition JC-ESP32P4-M3-DEV** (módulo JC-ESP32P4-M3-C6).

## Hardware relevante

| Recurso | Detalle |
|---------|---------|
| MCU | ESP32-P4 (RISC-V dual) + coprocesor **ESP32-C6** (Wi‑Fi 6 / BT) |
| Flash / PSRAM | 16 MB / OPI |
| RS485 | Onboard **MAX485** — `TX1=GPIO26`, `RX1=GPIO27` |
| Ethernet | IP101 — MDC=31, MDIO=52, PWR=51, CLK=50 |
| USB | CDC on boot (USB Serial/JTAG) |

Fuentes de pines: demo IDF `uart_echo_rs485` (sdkconfig TXD=26 RXD=27) y esquemático del módulo (GPIO26=TX1, GPIO27=RX1).

## Compilar / flashear

```bash
cd firmware/saj_pdm30_edge

# Solo esta placa
../.pio-venv/bin/pio run -e guition_jc_esp32p4_m3

# Flashear (puerto USB de la Guition)
../.pio-venv/bin/pio run -e guition_jc_esp32p4_m3 -t upload --upload-port /dev/ttyACM0
../.pio-venv/bin/pio device monitor -e guition_jc_esp32p4_m3 -b 115200
```

La plataforma **pioarduino** se descarga en el primer build (Arduino-esp32 3.3.x con soporte P4).

## Red en esta placa

1. **Ethernet (recomendado para MQTT)**  
   Conecta el RJ45 a la LAN del broker. DHCP automático.  
   Luego por Serial:
   ```text
   mqtt set <IP_BROKER> 1883
   mqtt enable
   mqtt status
   ```

2. **Wi‑Fi**  
   El radio está en el **C6** (SDIO hosted). El stack Arduino “hosted” puede requerir firmware del C6 al día.  
   Si Wi‑Fi no asocia, usa Ethernet o Serial.

3. **AP `SAJ_Diag_Tool`**  
   Solo si el stack Wi‑Fi del hosted está activo (misma CLI que en ESP32 clásico).

## Diferencias vs `esp32dev`

| | ESP32 DevKit | Guition P4 |
|--|--------------|------------|
| RS485 | GPIO14/25/27 externo | 26/27 onboard, DE auto |
| Red | Wi‑Fi STA/AP | Ethernet + Wi‑Fi hosted (C6) |
| LED actividad | GPIO2 | desactivado (−1) |
| Env PIO | `esp32dev` | `guition_jc_esp32p4_m3` |

## Archivos de la variante

```
include/boards/board_guition_jc_esp32p4_m3.h   # pines
boards/guition_jc_esp32p4_m3.json              # board JSON (referencia)
platformio.ini  → [env:guition_jc_esp32p4_m3]
```

## Cableado VDF

Usar el **bloque RS485** de la placa (A/B), no hace falta MAX485 externo salvo que se use un header GPIO libre.
