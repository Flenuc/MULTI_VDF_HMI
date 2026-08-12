"""
SAJ Edge Configurator — CustomTkinter GUI.

Concurrency model
-----------------
* All serial/WS I/O runs on background threads inside CommsClient subclasses.
* Inbound data is enqueued as CommsEvent objects.
* The Tk main loop drains the queue every POLL_MS via ``after()`` — never blocks
  on network or Modbus round-trips.
* Long multi-step ops (sync / compare) run on a dedicated worker thread and
  only touch widgets through ``self.after(0, ...)``.
"""

from __future__ import annotations

import threading
import time
import tkinter as tk
from pathlib import Path
from tkinter import filedialog, messagebox
import re
from typing import Dict, List, Optional, Tuple

import customtkinter as ctk

from comms import (
    BleNusClient,
    BluetoothClient,
    CommsClient,
    CommsEvent,
    ConnectionState,
    DummyClient,
    MqttClient,
    SerialClient,
    list_ble_nus_devices,
    list_bluetooth_devices,
)
from models import Parameter, ParameterList, parse_dump_csv_line
from profiles import (
    ConnectionStore,
    MqttProfile,
    WifiProfile,
    get_mqtt,
    get_wifi,
    load_store,
    save_store,
    upsert_mqtt,
    upsert_wifi,
)
from storage import load_json, save_json

try:
    from serial.tools import list_ports
except Exception:  # pragma: no cover
    list_ports = None

ctk.set_appearance_mode("Dark")
ctk.set_default_color_theme("blue")

POLL_MS = 40
APP_DIR = Path(__file__).resolve().parents[1]
LISTS_DIR = APP_DIR / "param_lists"

COLOR_OK = "#1b4332"
COLOR_BAD = "#9d0208"
COLOR_MANUAL = "#5c5420"
COLOR_ROW = "#2b2b2b"
FAULT_STATUSES = frozenset({"run", "stop", "rev", "unknown", "?"})


class TelemetryPanel(ctk.CTkFrame):
    """Large live indicators fed by JSON stream."""

    def __init__(self, master, **kwargs):
        super().__init__(master, **kwargs)
        self._last_rx_mono: float = 0.0
        self._rx_count: int = 0

        header = ctk.CTkFrame(self, fg_color="transparent")
        header.pack(fill="x", padx=12, pady=(12, 4))
        title = ctk.CTkLabel(
            header, text="Telemetría en vivo", font=ctk.CTkFont(size=16, weight="bold")
        )
        title.pack(side="left")
        self.lbl_live = ctk.CTkLabel(
            header,
            text="sin datos",
            text_color="#9ca3af",
            font=ctk.CTkFont(size=12),
        )
        self.lbl_live.pack(side="right")

        grid = ctk.CTkFrame(self, fg_color="transparent")
        grid.pack(fill="x", padx=8, pady=8)
        for i in range(7):
            grid.grid_columnconfigure(i, weight=1)

        self._cards: Dict[str, ctk.CTkLabel] = {}
        specs = [
            ("freq", "Frecuencia", "— Hz"),
            ("amp", "Corriente", "— A"),
            ("vdc", "V bus", "— V"),
            ("vout", "V out", "— V"),
            ("pfb", "P real", "— bar"),   # feedback / sensor (what matters)
            ("pset", "P consigna", "— bar"),
            ("status", "Estado", "—"),
        ]
        for col, (key, name, placeholder) in enumerate(specs):
            card = ctk.CTkFrame(grid, corner_radius=10)
            card.grid(row=0, column=col, padx=4, pady=4, sticky="nsew")
            ctk.CTkLabel(card, text=name, text_color="#9ca3af").pack(pady=(10, 0))
            val = ctk.CTkLabel(
                card, text=placeholder, font=ctk.CTkFont(size=22, weight="bold")
            )
            val.pack(pady=(4, 12))
            self._cards[key] = val

        self.fault_banner = ctk.CTkLabel(
            self,
            text="",
            font=ctk.CTkFont(size=14, weight="bold"),
            text_color="#fecaca",
            fg_color="transparent",
        )
        self.fault_banner.pack(fill="x", padx=12, pady=(0, 10))

        # Age ticker so frozen-looking zeros still prove the stream is alive
        self.after(500, self._tick_live_age)

    def _tick_live_age(self) -> None:
        if self._last_rx_mono <= 0:
            self.lbl_live.configure(text="sin datos · ¿stream on?", text_color="#9ca3af")
        else:
            import time as _time

            age = _time.monotonic() - self._last_rx_mono
            if age < 2.5:
                self.lbl_live.configure(
                    text=f"EN VIVO · {self._rx_count} msg · {age:.1f}s",
                    text_color="#86efac",
                )
            elif age < 8.0:
                self.lbl_live.configure(
                    text=f"lento · último hace {age:.0f}s",
                    text_color="#fbbf24",
                )
            else:
                self.lbl_live.configure(
                    text=f"sin actualizar · {age:.0f}s (revisar MQTT/stream)",
                    text_color="#fca5a5",
                )
        self.after(500, self._tick_live_age)

    def update_telemetry(self, data: dict) -> None:
        import time as _time

        self._last_rx_mono = _time.monotonic()
        self._rx_count += 1

        freq = data.get("freq")
        amp = data.get("amp")
        vdc = data.get("vdc")
        vout = data.get("vout")
        pset = data.get("pset")
        pfb = data.get("pfb")
        status = str(data.get("status", "—"))

        if freq is not None:
            self._cards["freq"].configure(text=f"{float(freq):.2f} Hz")
        if amp is not None:
            self._cards["amp"].configure(text=f"{float(amp):.2f} A")
        if vdc is not None:
            self._cards["vdc"].configure(text=f"{float(vdc):.1f} V")
        if vout is not None:
            self._cards["vout"].configure(text=f"{float(vout):.0f} V")
        if pfb is not None:
            self._cards["pfb"].configure(text=f"{float(pfb):.1f} bar")
        if pset is not None:
            self._cards["pset"].configure(text=f"{float(pset):.1f} bar")
        self._cards["status"].configure(text=status.upper())

        st = status.lower()
        if st not in FAULT_STATUSES and st not in ("", "—"):
            # e.g. E-04, fault codes
            self.fault_banner.configure(
                text=f"⚠ FALLO EN VDF — status={status}",
                fg_color="#7f1d1d",
            )
            self._cards["status"].configure(text_color="#fca5a5")
        else:
            self.fault_banner.configure(text="", fg_color="transparent")
            color = "#86efac" if st == "run" else "#e5e7eb"
            self._cards["status"].configure(text_color=color)


class ParamRow(ctk.CTkFrame):
    def __init__(self, master, param: Parameter, on_select, **kwargs):
        super().__init__(master, corner_radius=6, **kwargs)
        self.param = param
        self.on_select = on_select
        self.grid_columnconfigure(2, weight=1)

        self.lbl_id = ctk.CTkLabel(self, text=param.param_id(), width=72, anchor="w")
        self.lbl_id.grid(row=0, column=0, padx=8, pady=6)
        self.lbl_val = ctk.CTkLabel(self, text=f"{param.value:g}", width=80, anchor="e")
        self.lbl_val.grid(row=0, column=1, padx=4, pady=6)
        notes = (param.notes[:42] + "…") if len(param.notes) > 43 else (param.notes or "—")
        self.lbl_notes = ctk.CTkLabel(self, text=notes, anchor="w")
        self.lbl_notes.grid(row=0, column=2, padx=8, pady=6, sticky="ew")
        self.lbl_mode = ctk.CTkLabel(self, text="Manual" if param.manual_only else "RS485", width=70)
        self.lbl_mode.grid(row=0, column=3, padx=4, pady=6)
        live = "—" if param.live_value is None else f"{param.live_value:g}"
        self.lbl_live = ctk.CTkLabel(self, text=live, width=80, anchor="e")
        self.lbl_live.grid(row=0, column=4, padx=8, pady=6)

        for w in (self, self.lbl_id, self.lbl_val, self.lbl_notes, self.lbl_mode, self.lbl_live):
            w.bind("<Button-1>", lambda e: self.on_select(self))
        self.refresh_style()

    def refresh_style(self) -> None:
        p = self.param
        if p.mismatch:
            fg = COLOR_BAD
        elif p.manual_only:
            fg = COLOR_MANUAL
        elif p.live_value is not None:
            fg = COLOR_OK
        else:
            fg = COLOR_ROW
        self.configure(fg_color=fg)
        self.lbl_id.configure(text=p.param_id())
        self.lbl_val.configure(text=f"{p.value:g}")
        notes = (p.notes[:42] + "…") if len(p.notes) > 43 else (p.notes or "—")
        self.lbl_notes.configure(text=notes)
        self.lbl_mode.configure(text="Manual" if p.manual_only else "RS485")
        live = "—" if p.live_value is None else f"{p.live_value:g}"
        self.lbl_live.configure(text=live)


class EdgeConfiguratorApp(ctk.CTk):
    def __init__(self) -> None:
        super().__init__()
        self.title("SAJ Edge Configurator — PDM-30")
        self.geometry("1280x780")
        self.minsize(1024, 640)

        self.plist = ParameterList(name="Nueva lista")
        self.current_path: Optional[Path] = None
        self.client: Optional[CommsClient] = None
        self._rows: List[ParamRow] = []
        self._selected: Optional[ParamRow] = None
        self._busy = False
        self._op_name: str = ""
        self._op_deadline: float = 0.0  # monotonic seconds; 0 = no deadline
        self._worker: Optional[threading.Thread] = None
        self._log_lines: List[str] = []
        self._compare_finished = False

        # compare session
        self._dump_map: Dict[Tuple[int, int], float] = {}
        self._dump_active = False
        self._dump_lines_seen = 0
        self.conn_store: ConnectionStore = load_store()

        LISTS_DIR.mkdir(parents=True, exist_ok=True)
        self._build_ui()
        self._refresh_ports()
        self._reload_profile_menus()
        self._reload_table()
        self.after(POLL_MS, self._poll_comms)
        self._set_status("Selecciona Serial o MQTT y pulsa Conectar.")

    # ================================================================== UI
    def _build_ui(self) -> None:
        self.grid_columnconfigure(0, weight=1)
        self.grid_rowconfigure(2, weight=1)

        # --- Connection bar ---
        top = ctk.CTkFrame(self, corner_radius=0)
        top.grid(row=0, column=0, sticky="ew")
        top.grid_columnconfigure(10, weight=1)

        ctk.CTkLabel(top, text="Modo:", font=ctk.CTkFont(weight="bold")).grid(
            row=0, column=0, padx=(12, 4), pady=10
        )
        self.mode_var = ctk.StringVar(value=self.conn_store.last_mode or "MQTT")
        self.mode_menu = ctk.CTkOptionMenu(
            top,
            variable=self.mode_var,
            values=[
                "MQTT",
                "USB (Serial)",
                "Bluetooth LE (NUS)",
                "Bluetooth (SPP)",
                "Simulado (Dummy)",
            ],
            command=self._on_mode_change,
            width=160,
        )
        self.mode_menu.grid(row=0, column=1, padx=4, pady=10)

        # Serial widgets
        self.lbl_port = ctk.CTkLabel(top, text="Puerto:")
        self.port_var = ctk.StringVar(value=self.conn_store.last_serial_port or "")
        self.port_menu = ctk.CTkOptionMenu(top, variable=self.port_var, values=["—"], width=120)
        self.btn_refresh = ctk.CTkButton(top, text="↻", width=36, command=self._refresh_ports)
        self.lbl_baud = ctk.CTkLabel(top, text="Baud:")
        self.baud_var = ctk.StringVar(value=str(self.conn_store.last_serial_baud or 115200))
        self.baud_menu = ctk.CTkOptionMenu(
            top, variable=self.baud_var, values=["9600", "115200"], width=90
        )

        # Bluetooth widgets (SPP / Legacy)
        self.lbl_bt = ctk.CTkLabel(top, text="BT:")
        self.bt_var = ctk.StringVar(value="")
        self._bt_devices: List[dict] = []  # [{address,name,...}]
        self.bt_menu = ctk.CTkOptionMenu(top, variable=self.bt_var, values=["—"], width=200)
        self.btn_bt_scan = ctk.CTkButton(
            top, text="Escanear BT", width=90, command=self._refresh_bt_devices
        )

        # MQTT widgets
        self.lbl_mqtt = ctk.CTkLabel(top, text="Perfil MQTT:")
        self.mqtt_profile_var = ctk.StringVar(value=self.conn_store.last_mqtt or "")
        self.mqtt_profile_menu = ctk.CTkOptionMenu(
            top, variable=self.mqtt_profile_var, values=["—"], width=150
        )

        self.btn_connect = ctk.CTkButton(top, text="Conectar", width=100, command=self._toggle_connect)
        self.btn_connect.grid(row=0, column=8, padx=6, pady=10)
        self.btn_profiles = ctk.CTkButton(
            top, text="Perfiles…", width=90, command=self._profiles_dialog, fg_color="#334155"
        )
        self.btn_profiles.grid(row=0, column=9, padx=4, pady=10)
        self.btn_wifi = ctk.CTkButton(
            top, text="Wi‑Fi Edge…", width=100, command=self._wifi_dialog, fg_color="#334155"
        )
        self.btn_wifi.grid(row=0, column=10, padx=4, pady=10)
        self.lbl_link = ctk.CTkLabel(top, text="● Desconectado", text_color="#ef4444")
        self.lbl_link.grid(row=0, column=11, padx=8, pady=10)

        self._on_mode_change(self.mode_var.get())

        # --- Toolbar ---
        bar = ctk.CTkFrame(self)
        bar.grid(row=1, column=0, sticky="ew", padx=12, pady=6)
        actions = [
            ("Abrir JSON…", self._open),
            ("Guardar", self._save),
            ("Guardar como…", self._save_as),
            ("Sincronizar al VDF", self._sync_vfd),
            ("Comparar con VDF", self._compare_vfd),
            ("Start", lambda: self._quick_cmd("start")),
            ("Stop", lambda: self._quick_cmd("stop")),
            ("Stream on", lambda: self._quick_cmd("stream on")),
            ("Stream off", lambda: self._quick_cmd("stream off")),
            ("Wi‑Fi status", lambda: self._quick_cmd("wifi status")),
            ("MQTT status", lambda: self._quick_cmd("mqtt status")),
        ]
        for i, (txt, cmd) in enumerate(actions):
            ctk.CTkButton(bar, text=txt, command=cmd, width=120).grid(row=0, column=i, padx=3, pady=6)
        self.progress = ctk.CTkProgressBar(bar, width=140)
        self.progress.grid(row=0, column=20, padx=8, pady=6)
        self.progress.set(0)
        self.lbl_op = ctk.CTkLabel(bar, text="Libre", text_color="#86efac", width=100)
        self.lbl_op.grid(row=0, column=21, padx=4, pady=6)
        ctk.CTkButton(
            bar,
            text="Cancelar op.",
            width=100,
            fg_color="#b45309",
            hover_color="#92400e",
            command=self._cancel_operation,
        ).grid(row=0, column=22, padx=4, pady=6)

        # --- Body ---
        body = ctk.CTkFrame(self, fg_color="transparent")
        body.grid(row=2, column=0, sticky="nsew", padx=12, pady=4)
        body.grid_columnconfigure(0, weight=3)
        body.grid_columnconfigure(1, weight=1)
        body.grid_rowconfigure(0, weight=1)
        body.grid_rowconfigure(1, weight=0)

        # Table
        left = ctk.CTkFrame(body)
        left.grid(row=0, column=0, sticky="nsew", padx=(0, 8))
        left.grid_rowconfigure(2, weight=1)
        left.grid_columnconfigure(0, weight=1)
        self.lbl_list = ctk.CTkLabel(left, text="Lista: —", font=ctk.CTkFont(size=15, weight="bold"))
        self.lbl_list.grid(row=0, column=0, sticky="w", padx=10, pady=8)
        hdr = ctk.CTkFrame(left)
        hdr.grid(row=1, column=0, sticky="ew", padx=8)
        for col, t in enumerate(["ID", "Valor", "Notas", "Modo", "Leído VDF"]):
            ctk.CTkLabel(hdr, text=t, font=ctk.CTkFont(weight="bold")).grid(
                row=0, column=col, padx=8, pady=4, sticky="w"
            )
        hdr.grid_columnconfigure(2, weight=1)
        self.scroll = ctk.CTkScrollableFrame(left)
        self.scroll.grid(row=2, column=0, sticky="nsew", padx=8, pady=8)

        # Editor (scrollable — fits short screens)
        ed_shell = ctk.CTkFrame(body)
        ed_shell.grid(row=0, column=1, sticky="nsew")
        ed_shell.grid_rowconfigure(0, weight=1)
        ed_shell.grid_columnconfigure(0, weight=1)
        ed = ctk.CTkScrollableFrame(ed_shell, label_text="Editor")
        ed.grid(row=0, column=0, sticky="nsew", padx=2, pady=2)
        ed.grid_columnconfigure(0, weight=1)

        ctk.CTkLabel(ed, text="Grupo").pack(anchor="w", padx=12, pady=(8, 0))
        self.group_var = ctk.StringVar(value="P0")
        ctk.CTkOptionMenu(ed, variable=self.group_var, values=["P0", "P1"]).pack(
            fill="x", padx=12, pady=4
        )
        ctk.CTkLabel(ed, text="Índice 0–47").pack(anchor="w", padx=12)
        self.idx_entry = ctk.CTkEntry(ed)
        self.idx_entry.pack(fill="x", padx=12, pady=4)
        ctk.CTkLabel(ed, text="Valor (ingeniería, float)").pack(anchor="w", padx=12)
        self.val_entry = ctk.CTkEntry(ed, placeholder_text="ej. 1.5 bar, 50.0 Hz")
        self.val_entry.pack(fill="x", padx=12, pady=4)
        ctk.CTkLabel(ed, text="Notas").pack(anchor="w", padx=12)
        self.notes_box = ctk.CTkTextbox(ed, height=100)
        self.notes_box.pack(fill="x", padx=12, pady=4)
        self.manual_var = ctk.BooleanVar(value=False)
        ctk.CTkCheckBox(
            ed, text="Manual (ignorar en RS485 / sync)", variable=self.manual_var
        ).pack(anchor="w", padx=12, pady=8)
        bf = ctk.CTkFrame(ed, fg_color="transparent")
        bf.pack(fill="x", padx=8, pady=(8, 16))
        ctk.CTkButton(bf, text="Añadir / Actualizar", command=self._add_param).pack(
            side="left", padx=4
        )
        ctk.CTkButton(
            bf,
            text="Eliminar",
            fg_color="#b91c1c",
            hover_color="#7f1d1d",
            command=self._del_param,
        ).pack(side="left", padx=4)

        # Telemetry full width under
        self.telemetry = TelemetryPanel(body)
        self.telemetry.grid(row=1, column=0, columnspan=2, sticky="ew", pady=(8, 0))

        # Log + status
        self.log_box = ctk.CTkTextbox(self, height=90)
        self.log_box.grid(row=3, column=0, sticky="ew", padx=12, pady=4)
        self.status = ctk.CTkLabel(self, text="", anchor="w")
        self.status.grid(row=4, column=0, sticky="ew", padx=16, pady=(0, 8))

    def _on_mode_change(self, mode: str) -> None:
        # Hide all optional widgets first
        for w in (
            self.lbl_port,
            self.port_menu,
            self.btn_refresh,
            self.lbl_baud,
            self.baud_menu,
            self.lbl_bt,
            self.bt_menu,
            self.btn_bt_scan,
            self.lbl_mqtt,
            self.mqtt_profile_menu,
        ):
            try:
                w.grid_remove()
            except Exception:
                pass

        if mode.startswith("MQTT"):
            self.lbl_mqtt.grid(row=0, column=2, padx=(12, 4), pady=10)
            self.mqtt_profile_menu.grid(row=0, column=3, columnspan=3, padx=4, pady=10, sticky="w")
        elif "Bluetooth" in mode or mode.startswith("BT"):
            self.lbl_bt.grid(row=0, column=2, padx=(12, 4), pady=10)
            self.bt_menu.grid(row=0, column=3, columnspan=2, padx=4, pady=10, sticky="w")
            self.btn_bt_scan.grid(row=0, column=5, padx=4, pady=10)
            # Scan type depends on SPP vs LE NUS
            self.after(100, self._refresh_bt_devices)
        elif "Simulado" in mode:
            pass
        else:
            # USB Serial
            self.lbl_port.grid(row=0, column=2, padx=(12, 4), pady=10)
            self.port_menu.grid(row=0, column=3, padx=4, pady=10)
            self.btn_refresh.grid(row=0, column=4, padx=2, pady=10)
            self.lbl_baud.grid(row=0, column=5, padx=(8, 4), pady=10)
            self.baud_menu.grid(row=0, column=6, padx=4, pady=10)

    def _reload_profile_menus(self) -> None:
        mqtt_names = [p.name for p in self.conn_store.mqtt_profiles] or ["—"]
        self.mqtt_profile_menu.configure(values=mqtt_names)
        if self.conn_store.last_mqtt in mqtt_names:
            self.mqtt_profile_var.set(self.conn_store.last_mqtt)
        else:
            self.mqtt_profile_var.set(mqtt_names[0])

    # ================================================================== helpers
    def _set_status(self, text: str) -> None:
        self.status.configure(text=text)

    def _log(self, text: str) -> None:
        self.log_box.insert("end", text + "\n")
        self.log_box.see("end")

    def _begin_op(self, name: str, timeout_s: float = 120.0) -> bool:
        """Start a long operation. Returns False if another op is active."""
        if self._busy:
            msg = f"Operación en curso: «{self._op_name or 'desconocida'}»."
            if messagebox.askyesno(
                "Ocupado",
                f"{msg}\n\n¿Forzar cancelación y continuar?",
            ):
                self._end_op("Operación anterior cancelada por el usuario")
            else:
                return False
        self._busy = True
        self._op_name = name
        self._op_deadline = time.monotonic() + timeout_s if timeout_s > 0 else 0.0
        self.lbl_op.configure(text=f"⏳ {name}", text_color="#fbbf24")
        self._set_status(f"Operación: {name}…")
        return True

    def _end_op(self, status_msg: str = "") -> None:
        """Clear busy flag (always safe to call)."""
        self._busy = False
        self._op_name = ""
        self._op_deadline = 0.0
        self._dump_active = False
        self.lbl_op.configure(text="Libre", text_color="#86efac")
        self.progress.set(0)
        if status_msg:
            self._set_status(status_msg)

    def _cancel_operation(self) -> None:
        if not self._busy and not self._dump_active:
            self._set_status("No hay operación activa.")
            return
        name = self._op_name or "desconocida"
        self._end_op(f"Operación «{name}» cancelada manualmente")
        self._log(f"[app] canceló operación «{name}»")

    def _touch_op_deadline(self, extra_s: float = 45.0) -> None:
        """Sliding timeout: while data still arrives, keep the op alive."""
        if self._busy and extra_s > 0:
            self._op_deadline = time.monotonic() + extra_s

    def _check_op_timeout(self) -> None:
        if not self._busy or self._op_deadline <= 0:
            return
        if time.monotonic() < self._op_deadline:
            return
        name = self._op_name or "operación"
        self._log(f"[app] timeout de «{name}» — liberando UI")
        was_compare = self._dump_active
        dump_map = dict(self._dump_map) if was_compare else {}
        self._end_op(f"Timeout: «{name}» no terminó a tiempo (UI liberada)")
        if was_compare and dump_map:
            self._dump_map = dump_map
            self._apply_compare_results(show_dialog=True, partial=True)
        else:
            messagebox.showwarning(
                "Timeout",
                f"La operación «{name}» no respondió a tiempo.\n"
                "La interfaz se liberó para que puedas seguir trabajando.\n\n"
                "Si usas Wi‑Fi, reintenta: el dump se optimizó para no saturar el WebSocket.",
            )

    def _refresh_ports(self) -> None:
        ports = ["—"]
        if list_ports:
            found = [p.device for p in list_ports.comports()]
            if found:
                ports = found
        self.port_menu.configure(values=ports)
        self.port_var.set(ports[0])

    def _refresh_bt_devices(self) -> None:
        """Scan Bluetooth Classic and/or BLE NUS devices (background)."""
        mode = self.mode_var.get()
        is_ble = "LE" in mode or "NUS" in mode
        self._set_status(
            "Escaneando BLE NUS…" if is_ble else "Buscando Bluetooth Classic…"
        )

        def work():
            err = ""
            devs: List[dict] = []
            try:
                if is_ble:
                    devs = list_ble_nus_devices(scan_seconds=6.0)
                else:
                    devs = list_bluetooth_devices(scan_seconds=4.0)
            except Exception as e:
                err = str(e)

            def ui():
                self._bt_devices = devs
                if not devs:
                    if is_ble:
                        labels = ["— (ningún BLE / SAJ-PDM30-Edge)"]
                        hint = (
                            "No hay BLE. Guition con NUS debe anunciar "
                            "«SAJ-PDM30-Edge». pip install bleak"
                        )
                    else:
                        labels = ["— (ninguno / emparejá SAJ-PDM30-Edge)"]
                        hint = (
                            "No hay SPP. Emparejá «SAJ-PDM30-Edge» "
                            "(firmware esp32dev Classic)."
                        )
                    self.bt_menu.configure(values=labels)
                    self.bt_var.set(labels[0])
                    if err:
                        hint += f" ({err})"
                    self._set_status(hint)
                    return
                labels = []
                for d in devs:
                    tag = d["address"]
                    extra = ""
                    if d.get("paired"):
                        extra += " ✓"
                    if d.get("has_nus"):
                        extra += " NUS"
                    if d.get("rssi") is not None:
                        extra += f" {d['rssi']}dBm"
                    labels.append(f"{d['name']}  [{tag}]{extra}")
                self.bt_menu.configure(values=labels)
                last = (self.conn_store.last_bt_address or "").upper()
                chosen = labels[0]
                for lab, d in zip(labels, devs):
                    if str(d["address"]).upper() == last:
                        chosen = lab
                        break
                self.bt_var.set(chosen)
                kind = "BLE" if is_ble else "BT"
                self._set_status(f"{kind}: {len(devs)} dispositivo(s)")

            self.after(0, ui)

        threading.Thread(target=work, daemon=True).start()

    def _selected_bt_address(self) -> str:
        lab = self.bt_var.get() or ""
        m = re.search(r"\[([0-9A-Fa-f:]{17})\]", lab)
        if m:
            return m.group(1).upper()
        # fallback raw MAC
        if re.match(r"^[0-9A-Fa-f:]{17}$", lab.strip()):
            return lab.strip().upper()
        return ""

    def _set_link(self, connected: bool, label: str = "") -> None:
        if connected:
            self.lbl_link.configure(text=f"● {label or 'Conectado'}", text_color="#22c55e")
            self.btn_connect.configure(text="Desconectar")
        else:
            self.lbl_link.configure(text="● Desconectado", text_color="#ef4444")
            self.btn_connect.configure(text="Conectar")

    def _reload_table(self) -> None:
        for r in self._rows:
            r.destroy()
        self._rows.clear()
        self._selected = None
        self.lbl_list.configure(
            text=f"Lista: {self.plist.name}  ({len(self.plist.parameters)} params)"
        )
        for p in self.plist.parameters:
            row = ParamRow(self.scroll, p, on_select=self._select_row)
            row.pack(fill="x", padx=2, pady=2)
            self._rows.append(row)

    def _select_row(self, row: ParamRow) -> None:
        self._selected = row
        p = row.param
        self.group_var.set(f"P{p.group}")
        self.idx_entry.delete(0, "end")
        self.idx_entry.insert(0, str(p.index))
        self.val_entry.delete(0, "end")
        self.val_entry.insert(0, f"{p.value:g}")
        self.notes_box.delete("1.0", "end")
        self.notes_box.insert("1.0", p.notes)
        self.manual_var.set(p.manual_only)

    def _add_param(self) -> None:
        try:
            g = 0 if self.group_var.get() == "P0" else 1
            idx = int(self.idx_entry.get().strip())
            val = float(self.val_entry.get().strip().replace(",", "."))
            notes = self.notes_box.get("1.0", "end").strip()
            p = Parameter(g, idx, val, notes, bool(self.manual_var.get()))
            p.validate()
        except Exception as e:
            messagebox.showerror("Validación", str(e))
            return
        self.plist.add(p)
        self.plist.sort_by_id()
        self._reload_table()
        self._set_status(f"Guardado {p.param_id()} = {p.value:g}")

    def _del_param(self) -> None:
        if not self._selected:
            return
        p = self._selected.param
        self.plist.parameters = [
            x for x in self.plist.parameters if not (x.group == p.group and x.index == p.index)
        ]
        self._reload_table()

    # ================================================================== files
    def _open(self) -> None:
        path = filedialog.askopenfilename(
            initialdir=str(LISTS_DIR), filetypes=[("JSON", "*.json")]
        )
        if not path:
            return
        try:
            self.plist = load_json(path)
            self.plist.sort_by_id()
            self.current_path = Path(path)
            self._reload_table()
            self._set_status(f"Cargado {path}")
        except Exception as e:
            messagebox.showerror("Abrir", str(e))

    def _save(self) -> None:
        if self.current_path:
            save_json(self.plist, self.current_path)
            self._set_status(f"Guardado {self.current_path}")
        else:
            self._save_as()

    def _save_as(self) -> None:
        path = filedialog.asksaveasfilename(
            initialdir=str(LISTS_DIR),
            defaultextension=".json",
            filetypes=[("JSON", "*.json")],
        )
        if not path:
            return
        self.plist.name = Path(path).stem
        save_json(self.plist, path)
        self.current_path = Path(path)
        self._reload_table()
        self._set_status(f"Guardado {path}")

    # ================================================================== connection
    def _toggle_connect(self) -> None:
        if self.client and self.client.connected:
            try:
                self.client.send_line("stream off")
            except Exception:
                pass
            self.client.disconnect()
            self.client = None
            self._end_op("Desconectado")
            self._set_link(False)
            return

        mode = self.mode_var.get()
        self.conn_store.last_mode = mode

        def work():
            try:
                if "Simulado" in mode:
                    c: CommsClient = DummyClient()
                    c.connect()
                elif mode.startswith("MQTT"):
                    mp = get_mqtt(self.conn_store, self.mqtt_profile_var.get())
                    if not mp or not mp.host:
                        raise RuntimeError("Selecciona un perfil MQTT válido (Perfiles…)")
                    c = MqttClient()
                    c.connect(
                        host=mp.host,
                        port=mp.port,
                        topic_prefix=mp.topic_prefix,
                        username=mp.username,
                        password=mp.password,
                    )
                    self.conn_store.last_mqtt = mp.name
                    save_store(self.conn_store)
                elif "Bluetooth" in mode:
                    addr = self._selected_bt_address()
                    if not addr:
                        raise RuntimeError(
                            "Seleccioná un dispositivo (Escanear BT).\n"
                            "• BLE NUS → Guition (SAJ-PDM30-Edge)\n"
                            "• SPP Classic → ESP32 DevKit"
                        )
                    if "LE" in mode or "NUS" in mode:
                        c = BleNusClient()
                        c.connect(address=addr)
                    else:
                        c = BluetoothClient()
                        c.connect(address=addr, channel=1, pair=True)
                    self.conn_store.last_bt_address = addr
                    lab = self.bt_var.get() or ""
                    self.conn_store.last_bt_name = lab.split("[")[0].strip()
                    save_store(self.conn_store)
                else:
                    port = self.port_var.get()
                    if not port or port == "—":
                        raise RuntimeError("Selecciona un puerto serial")
                    c = SerialClient()
                    c.connect(port=port, baudrate=int(self.baud_var.get()))
                    self.conn_store.last_serial_port = port
                    self.conn_store.last_serial_baud = int(self.baud_var.get())
                    save_store(self.conn_store)

                def ok():
                    self.client = c
                    self._set_link(True, mode.split()[0])
                    self._set_status("Conectado — enviando stream on…")
                    try:
                        c.send_line("stream on")
                        self._log("→ stream on  (telemetría ~1 Hz)")
                    except Exception as e:
                        self._log(f"stream on failed: {e}")
                    if mode.startswith("MQTT"):
                        self._log(
                            "MQTT: el Edge debe apuntar al broker alcanzable "
                            "(p.ej. IP LAN de este PC, no 127.0.0.1 desde el ESP). "
                            "Usá Perfiles → Aplicar MQTT al Edge si hace falta."
                        )
                    if "LE" in mode or "NUS" in mode:
                        self._log(
                            "BLE NUS: mismo CLI que USB. Guition → "
                            "Nordic UART Service (SAJ-PDM30-Edge)."
                        )
                    elif "Bluetooth" in mode:
                        self._log(
                            "BT SPP: mismo CLI que USB. Firmware: env esp32dev."
                        )
                    self._log(f"Connected via {mode}")
                    # USB open may reset the MCU — delay stream on until CLI is alive
                    delay_ms = 800
                    if "erial" in mode or "USB" in mode or "ACM" in mode:
                        delay_ms = 2500
                    if "Bluetooth" in mode:
                        delay_ms = 1500
                    self.after(delay_ms, self._ensure_stream_on)

                self.after(0, ok)
            except Exception as e:
                self.after(0, lambda: messagebox.showerror("Conexión", str(e)))
                self.after(0, lambda: self._set_link(False))

        threading.Thread(target=work, daemon=True).start()

    def _require_client(self) -> Optional[CommsClient]:
        if not self.client or not self.client.connected:
            messagebox.showwarning("Sin conexión", "Conecta USB, Wi-Fi o modo simulado.")
            return None
        return self.client

    def _quick_cmd(self, cmd: str) -> None:
        c = self._require_client()
        if not c:
            return
        try:
            c.send_line(cmd)
            self._log(f"→ {cmd}")
        except Exception as e:
            messagebox.showerror("Comando", str(e))

    def _ensure_stream_on(self) -> None:
        """Best-effort: keep telemetry stream enabled after MQTT/serial connect."""
        c = self.client
        if not c or not c.connected:
            return
        try:
            c.send_line("stream on")
        except Exception:
            pass

    def _profiles_dialog(self) -> None:
        """Manage local Wi‑Fi + MQTT profiles (saved on this PC)."""
        dlg = ctk.CTkToplevel(self)
        dlg.title("Perfiles de conexión")
        dlg.geometry("520x520")
        dlg.transient(self)
        dlg.grab_set()

        tabs = ctk.CTkTabview(dlg)
        tabs.pack(fill="both", expand=True, padx=12, pady=12)
        tab_mqtt = tabs.add("MQTT")
        tab_wifi = tabs.add("Wi‑Fi (Edge)")

        # --- MQTT tab ---
        ctk.CTkLabel(tab_mqtt, text="Nombre perfil").pack(anchor="w", padx=8)
        m_name = ctk.CTkEntry(tab_mqtt, width=400)
        m_name.pack(padx=8, pady=2)
        ctk.CTkLabel(tab_mqtt, text="Broker host").pack(anchor="w", padx=8)
        m_host = ctk.CTkEntry(tab_mqtt, width=400)
        m_host.pack(padx=8, pady=2)
        m_host.insert(0, "127.0.0.1")
        ctk.CTkLabel(tab_mqtt, text="Puerto").pack(anchor="w", padx=8)
        m_port = ctk.CTkEntry(tab_mqtt, width=120)
        m_port.pack(padx=8, pady=2, anchor="w")
        m_port.insert(0, "1883")
        ctk.CTkLabel(tab_mqtt, text="Topic prefix").pack(anchor="w", padx=8)
        m_pref = ctk.CTkEntry(tab_mqtt, width=400)
        m_pref.pack(padx=8, pady=2)
        m_pref.insert(0, "saj/pdm30/saj-pdm30")
        ctk.CTkLabel(tab_mqtt, text="Usuario (opcional)").pack(anchor="w", padx=8)
        m_user = ctk.CTkEntry(tab_mqtt, width=400)
        m_user.pack(padx=8, pady=2)
        ctk.CTkLabel(tab_mqtt, text="Password MQTT (opcional)").pack(anchor="w", padx=8)
        m_pass = ctk.CTkEntry(tab_mqtt, width=400, show="*")
        m_pass.pack(padx=8, pady=2)

        def load_mqtt_into_form(name: str) -> None:
            p = get_mqtt(self.conn_store, name)
            if not p:
                return
            for e, v in (
                (m_name, p.name),
                (m_host, p.host),
                (m_port, str(p.port)),
                (m_pref, p.topic_prefix),
                (m_user, p.username),
                (m_pass, p.password),
            ):
                e.delete(0, "end")
                e.insert(0, v)

        def save_mqtt_profile() -> None:
            try:
                prof = MqttProfile(
                    name=m_name.get().strip() or "mqtt",
                    host=m_host.get().strip(),
                    port=int(m_port.get().strip() or "1883"),
                    username=m_user.get().strip(),
                    password=m_pass.get(),
                    topic_prefix=m_pref.get().strip() or "saj/pdm30/saj-pdm30",
                )
            except ValueError:
                messagebox.showerror("MQTT", "Puerto inválido", parent=dlg)
                return
            if not prof.host:
                messagebox.showwarning("MQTT", "Host obligatorio", parent=dlg)
                return
            upsert_mqtt(self.conn_store, prof)
            self.conn_store.last_mqtt = prof.name
            save_store(self.conn_store)
            self._reload_profile_menus()
            messagebox.showinfo("MQTT", f"Perfil «{prof.name}» guardado", parent=dlg)

        ctk.CTkButton(tab_mqtt, text="Guardar perfil MQTT", command=save_mqtt_profile).pack(
            pady=10
        )
        if self.conn_store.mqtt_profiles:
            load_mqtt_into_form(self.conn_store.last_mqtt or self.conn_store.mqtt_profiles[0].name)

        # --- WiFi tab ---
        ctk.CTkLabel(
            tab_wifi,
            text="Perfiles Wi‑Fi locales (para enviar al Edge por Serial/MQTT)",
            justify="left",
        ).pack(anchor="w", padx=8, pady=6)
        ctk.CTkLabel(tab_wifi, text="Nombre perfil").pack(anchor="w", padx=8)
        w_name = ctk.CTkEntry(tab_wifi, width=400)
        w_name.pack(padx=8, pady=2)
        ctk.CTkLabel(tab_wifi, text="SSID").pack(anchor="w", padx=8)
        w_ssid = ctk.CTkEntry(tab_wifi, width=400)
        w_ssid.pack(padx=8, pady=2)
        ctk.CTkLabel(tab_wifi, text="Password").pack(anchor="w", padx=8)
        w_pass = ctk.CTkEntry(tab_wifi, width=400, show="*")
        w_pass.pack(padx=8, pady=2)

        wifi_names = [p.name for p in self.conn_store.wifi_profiles] or ["—"]
        w_sel = ctk.StringVar(value=self.conn_store.last_wifi or wifi_names[0])
        ctk.CTkOptionMenu(
            tab_wifi,
            variable=w_sel,
            values=wifi_names,
            command=lambda n: _load_wifi(n),
            width=200,
        ).pack(padx=8, pady=8, anchor="w")

        def _load_wifi(name: str) -> None:
            p = get_wifi(self.conn_store, name)
            if not p:
                return
            for e, v in ((w_name, p.name), (w_ssid, p.ssid), (w_pass, p.password)):
                e.delete(0, "end")
                e.insert(0, v)

        def save_wifi_profile() -> None:
            prof = WifiProfile(
                name=w_name.get().strip() or "wifi",
                ssid=w_ssid.get().strip(),
                password=w_pass.get(),
            )
            if not prof.ssid:
                messagebox.showwarning("Wi‑Fi", "SSID obligatorio", parent=dlg)
                return
            upsert_wifi(self.conn_store, prof)
            self.conn_store.last_wifi = prof.name
            save_store(self.conn_store)
            messagebox.showinfo("Wi‑Fi", f"Perfil «{prof.name}» guardado en PC", parent=dlg)

        def push_to_edge() -> None:
            c = self._require_client()
            if not c:
                return
            name = w_name.get().strip() or "default"
            ssid = w_ssid.get().strip()
            pwd = w_pass.get() or '""'
            if " " in ssid or (pwd != '""' and " " in pwd):
                messagebox.showwarning(
                    "Wi‑Fi", "SSID/pass sin espacios (límite CLI)", parent=dlg
                )
                return
            # Save on PC + on device as named profile
            upsert_wifi(
                self.conn_store,
                WifiProfile(name=name, ssid=ssid, password=w_pass.get()),
            )
            save_store(self.conn_store)
            try:
                c.send_line(f"wifi profile save {name} {ssid} {pwd}")
                c.send_line(f"wifi profile use {name}")
                self._log(f"→ wifi profile save/use {name}")
                messagebox.showinfo(
                    "Wi‑Fi Edge",
                    f"Perfil «{name}» enviado al ESP32 y activado.\n"
                    "Espera la conexión STA y configura MQTT si hace falta.",
                    parent=dlg,
                )
            except Exception as e:
                messagebox.showerror("Wi‑Fi", str(e), parent=dlg)

        row = ctk.CTkFrame(tab_wifi, fg_color="transparent")
        row.pack(fill="x", padx=8, pady=10)
        ctk.CTkButton(row, text="Guardar en PC", command=save_wifi_profile).pack(
            side="left", padx=4
        )
        ctk.CTkButton(row, text="Enviar al Edge", command=push_to_edge).pack(
            side="left", padx=4
        )
        if self.conn_store.wifi_profiles:
            _load_wifi(self.conn_store.last_wifi or self.conn_store.wifi_profiles[0].name)

        ctk.CTkButton(dlg, text="Cerrar", command=dlg.destroy).pack(pady=8)

    def _wifi_dialog(self) -> None:
        """Quick apply saved Wi‑Fi profile to Edge + MQTT broker config."""
        dlg = ctk.CTkToplevel(self)
        dlg.title("Wi‑Fi / MQTT → Edge")
        dlg.geometry("480x420")
        dlg.transient(self)
        dlg.grab_set()

        ctk.CTkLabel(
            dlg,
            text="Aplica un perfil guardado al ESP32 (requiere conexión Serial o MQTT).",
            justify="left",
            wraplength=440,
        ).pack(anchor="w", padx=16, pady=12)

        wifi_names = [p.name for p in self.conn_store.wifi_profiles] or ["(ninguno)"]
        mqtt_names = [p.name for p in self.conn_store.mqtt_profiles] or ["(ninguno)"]
        w_var = ctk.StringVar(value=self.conn_store.last_wifi or wifi_names[0])
        m_var = ctk.StringVar(value=self.conn_store.last_mqtt or mqtt_names[0])

        ctk.CTkLabel(dlg, text="Perfil Wi‑Fi (PC)").pack(anchor="w", padx=16)
        ctk.CTkOptionMenu(dlg, variable=w_var, values=wifi_names, width=300).pack(
            padx=16, pady=4, anchor="w"
        )
        ctk.CTkLabel(dlg, text="Perfil MQTT broker (para el Edge)").pack(anchor="w", padx=16)
        ctk.CTkOptionMenu(dlg, variable=m_var, values=mqtt_names, width=300).pack(
            padx=16, pady=4, anchor="w"
        )

        def apply_wifi():
            c = self._require_client()
            if not c:
                return
            wp = get_wifi(self.conn_store, w_var.get())
            if not wp:
                messagebox.showwarning("Wi‑Fi", "Crea un perfil en Perfiles…", parent=dlg)
                return
            pwd = wp.password or '""'
            try:
                c.send_line(f"wifi profile save {wp.name} {wp.ssid} {pwd}")
                c.send_line(f"wifi profile use {wp.name}")
                self.conn_store.last_wifi = wp.name
                save_store(self.conn_store)
                self._log(f"→ wifi profile use {wp.name}")
                messagebox.showinfo("OK", f"Wi‑Fi «{wp.name}» enviado al Edge", parent=dlg)
            except Exception as e:
                messagebox.showerror("Error", str(e), parent=dlg)

        def apply_mqtt():
            c = self._require_client()
            if not c:
                return
            mp = get_mqtt(self.conn_store, m_var.get())
            if not mp:
                messagebox.showwarning("MQTT", "Crea un perfil MQTT en Perfiles…", parent=dlg)
                return
            try:
                c.send_line(f"mqtt set {mp.host} {mp.port}")
                if mp.username:
                    c.send_line(f"mqtt user {mp.username} {mp.password or '\"\"'}")
                c.send_line("mqtt enable")
                self.conn_store.last_mqtt = mp.name
                save_store(self.conn_store)
                self._log(f"→ mqtt set {mp.host}:{mp.port}")
                messagebox.showinfo(
                    "OK",
                    f"Broker «{mp.name}» configurado en el Edge.\n"
                    f"App → modo MQTT, perfil «{mp.name}».",
                    parent=dlg,
                )
            except Exception as e:
                messagebox.showerror("Error", str(e), parent=dlg)

        row = ctk.CTkFrame(dlg, fg_color="transparent")
        row.pack(fill="x", padx=12, pady=16)
        ctk.CTkButton(row, text="Aplicar Wi‑Fi al Edge", command=apply_wifi).pack(
            side="left", padx=4
        )
        ctk.CTkButton(row, text="Aplicar MQTT al Edge", command=apply_mqtt).pack(
            side="left", padx=4
        )
        ctk.CTkButton(row, text="wifi status", command=lambda: self._quick_cmd("wifi status")).pack(
            side="left", padx=4
        )
        ctk.CTkButton(dlg, text="Cerrar", command=dlg.destroy).pack(pady=8)

    # ================================================================== event pump
    def _poll_comms(self) -> None:
        self._check_op_timeout()
        if self.client:
            for ev in self.client.poll_events():
                self._handle_event(ev)
        self.after(POLL_MS, self._poll_comms)

    def _handle_event(self, ev: CommsEvent) -> None:
        if ev.kind == "status":
            st: ConnectionState = ev.payload
            msg = ev.meta.get("message", "")
            if st == ConnectionState.CONNECTED:
                self._set_link(True, msg or "OK")
            elif st in (ConnectionState.DISCONNECTED, ConnectionState.ERROR):
                self._set_link(False)
                # Never leave UI locked after link drop mid-dump/sync
                if self._busy:
                    self._end_op(f"Conexión perdida durante «{self._op_name}»")
            if not self._busy:
                self._set_status(f"{st.value}: {msg}")
        elif ev.kind == "json":
            data = ev.payload or {}
            self.telemetry.update_telemetry(data)
            # Occasional log so the console proves stream life without spam
            n = getattr(self, "_tel_log_n", 0) + 1
            self._tel_log_n = n
            if n == 1 or n % 10 == 0:
                self._log(
                    f"[tel #{n}] f={data.get('freq')} A={data.get('amp')} "
                    f"Vdc={data.get('vdc')} Vout={data.get('vout')} "
                    f"Preal={data.get('pfb')} Pset={data.get('pset')} "
                    f"{data.get('status')}"
                )
        elif ev.kind == "line":
            line = str(ev.payload)
            self._log(line)
            if self._dump_active:
                # Abort compare if ESP reports error instead of dump data
                if line.startswith("ERR:"):
                    self._end_op(f"Comparar abortado: {line}")
                    messagebox.showerror("Comparar", line)
                    return
                self._on_dump_line(line)
        elif ev.kind == "error":
            self._log(f"ERROR: {ev.payload}")
            if self._busy:
                # Transport error mid-op
                self._end_op(f"Error de transporte: {ev.payload}")

    def _on_dump_line(self, line: str) -> None:
        # Any dump traffic resets the sliding timeout (Wi‑Fi can be slow)
        if line.startswith("CSV:") or "DUMP" in line:
            self._touch_op_deadline(60.0)

        parsed = parse_dump_csv_line(line)
        if parsed:
            g, i, eng = parsed
            if eng is not None:
                self._dump_map[(g, i)] = eng
            self._dump_lines_seen += 1
            # ~96 params expected (P0+P1)
            self.progress.set(min(0.95, 0.1 + self._dump_lines_seen / 100.0))
            self.lbl_op.configure(
                text=f"⏳ compare {self._dump_lines_seen}/96",
                text_color="#fbbf24",
            )
        if "DUMP done" in line or line.startswith("CSV:END"):
            self._finish_compare()

    def _apply_compare_results(self, show_dialog: bool = True, partial: bool = False) -> int:
        tol = 1e-3
        mismatches = 0
        for p in self.plist.parameters:
            live = self._dump_map.get((p.group, p.index))
            p.live_value = live
            if live is None:
                p.mismatch = True
                mismatches += 1
            else:
                p.mismatch = abs(float(live) - float(p.value)) > max(tol, abs(p.value) * 1e-4)
                if p.mismatch:
                    mismatches += 1
        for row in self._rows:
            row.refresh_style()
        prefix = "Comparación parcial" if partial else "Comparación"
        self._set_status(
            f"{prefix}: {mismatches} diferencias / {len(self.plist.parameters)} "
            f"({len(self._dump_map)} leídos del VDF)"
        )
        if show_dialog:
            messagebox.showinfo(
                "Comparar con VDF",
                f"{prefix}: {mismatches} diferencias o no leídos / "
                f"{len(self.plist.parameters)}\n"
                f"Registros recibidos del dump: {len(self._dump_map)}",
            )
        return mismatches

    def _finish_compare(self) -> None:
        if self._compare_finished:
            return
        self._compare_finished = True
        self._dump_active = False
        self.progress.set(1.0)
        n = self._apply_compare_results(show_dialog=True, partial=False)
        self._end_op(
            f"Comparación: {n} diferencias / {len(self.plist.parameters)} "
            f"({len(self._dump_map)} leídos)"
        )

    # ================================================================== sync / compare
    def _sync_vfd(self) -> None:
        c = self._require_client()
        if not c:
            return
        items = self.plist.writable()
        if not items:
            messagebox.showinfo("Sync", "No hay parámetros enviables.")
            return
        skipped = len(self.plist.parameters) - len(items)
        if not messagebox.askyesno(
            "Sincronizar",
            f"Enviar {len(items)} parámetros (w0/w1 floats).\nOmitidos manuales: {skipped}",
        ):
            return
        # timeout scales with list size
        timeout_s = max(60.0, 0.5 * len(items) + 30.0)
        if not self._begin_op("sync", timeout_s=timeout_s):
            return
        self.progress.set(0)

        def work():
            try:
                total = len(items)
                for i, p in enumerate(items):
                    if not self._busy:
                        # cancelled
                        return
                    cmd = f"w{p.group} {p.index} {p.value:g}"
                    try:
                        c.send_line(cmd)
                    except Exception as e:
                        self.after(
                            0,
                            lambda e=e: (
                                messagebox.showerror("Sync", str(e)),
                                self._end_op(f"Sync error: {e}"),
                            ),
                        )
                        return
                    self.after(
                        0,
                        lambda i=i, total=total, cmd=cmd: (
                            self.progress.set((i + 1) / total),
                            self._set_status(f"Sync {i + 1}/{total}: {cmd}"),
                            self._log(f"→ {cmd}"),
                        ),
                    )
                    time.sleep(0.15)
                self.after(0, lambda: self._end_op("Sincronización enviada"))
            except Exception as e:
                self.after(
                    0,
                    lambda e=e: (
                        messagebox.showerror("Sync", str(e)),
                        self._end_op(f"Sync abortado: {e}"),
                    ),
                )

        threading.Thread(target=work, daemon=True).start()

    def _compare_vfd(self) -> None:
        c = self._require_client()
        if not c:
            return
        if not self.plist.parameters:
            messagebox.showinfo("Comparar", "Lista vacía.")
            return
        # Sliding timeout: initial 90s, refreshed on each CSV line (+60s)
        if not self._begin_op("compare", timeout_s=90.0):
            return
        self._compare_finished = False
        self._dump_active = True
        self._dump_map.clear()
        self._dump_lines_seen = 0
        self.plist.clear_compare()
        self._reload_table()
        self.progress.set(0.05)
        try:
            # Pause telemetry on the device path: dump also pauses stream in firmware
            try:
                c.send_line("stream off")
            except Exception:
                pass
            c.send_line("dump")
            self._log("→ stream off")
            self._log("→ dump")
            self._set_status("Comparando (dump en curso, Wi‑Fi puede tardar)…")
        except Exception as e:
            self._end_op(f"No se pudo iniciar dump: {e}")
            messagebox.showerror("Comparar", str(e))


def run_app() -> None:
    app = EdgeConfiguratorApp()
    app.mainloop()


if __name__ == "__main__":
    run_app()
