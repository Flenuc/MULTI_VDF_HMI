"""
CustomTkinter GUI — SAJ PDM-30 parameter list manager.

Presentation layer only: serial I/O goes through Esp32Client on worker threads.
"""

from __future__ import annotations

import shutil
import sys
import threading
import tkinter as tk
from pathlib import Path
from tkinter import filedialog, messagebox
from typing import List, Optional

import customtkinter as ctk

from models import Parameter, ParameterList
from serial_client import Esp32Client, SerialResult, list_serial_ports
from storage import load_any, save_any

# Theme
ctk.set_appearance_mode("Dark")
ctk.set_default_color_theme("blue")

APP_TITLE = "SAJ PDM-30 — Gestor de Parámetros"


def _app_base_dir() -> Path:
    """Project dir (dev) or folder next to the frozen executable."""
    if getattr(sys, "frozen", False):
        # PyInstaller onefile extracts to _MEIPASS; keep user lists next to the binary
        return Path(sys.executable).resolve().parent
    return Path(__file__).resolve().parent


def _bundled_lists_dir() -> Path:
    if getattr(sys, "frozen", False) and hasattr(sys, "_MEIPASS"):
        return Path(sys._MEIPASS) / "param_lists"  # type: ignore[attr-defined]
    return _app_base_dir() / "param_lists"


DEFAULT_LISTS = _app_base_dir() / "param_lists"

# Row colors (tk/ctk compatible hex)
COLOR_OK = ("#1b4332", "#2d6a4f")       # match
COLOR_MISMATCH = ("#6a040f", "#9d0208")  # red highlight
COLOR_MANUAL = ("#3d3a1f", "#5c5420")    # manual only
COLOR_NORMAL = ("#2b2b2b", "#333333")
COLOR_HEADER = ("#1f2937", "#111827")


class ParamRow(ctk.CTkFrame):
    """One visual row in the parameter table."""

    def __init__(self, master, param: Parameter, on_select, **kwargs):
        super().__init__(master, corner_radius=6, **kwargs)
        self.param = param
        self.on_select = on_select
        self._selected = False

        self.grid_columnconfigure(2, weight=1)

        self.lbl_id = ctk.CTkLabel(self, text=param.param_id(), width=70, anchor="w")
        self.lbl_id.grid(row=0, column=0, padx=8, pady=6, sticky="w")

        self.lbl_val = ctk.CTkLabel(self, text=str(param.value), width=70, anchor="e")
        self.lbl_val.grid(row=0, column=1, padx=4, pady=6)

        notes = param.notes if param.notes else "—"
        if len(notes) > 48:
            notes = notes[:45] + "…"
        self.lbl_notes = ctk.CTkLabel(self, text=notes, anchor="w")
        self.lbl_notes.grid(row=0, column=2, padx=8, pady=6, sticky="ew")

        manual_txt = "Manual" if param.manual_only else "RS485"
        self.lbl_manual = ctk.CTkLabel(self, text=manual_txt, width=70)
        self.lbl_manual.grid(row=0, column=3, padx=4, pady=6)

        live = "—" if param.live_value is None else str(param.live_value)
        self.lbl_live = ctk.CTkLabel(self, text=live, width=70, anchor="e")
        self.lbl_live.grid(row=0, column=4, padx=8, pady=6)

        for w in (self, self.lbl_id, self.lbl_val, self.lbl_notes, self.lbl_manual, self.lbl_live):
            w.bind("<Button-1>", self._click)

        self.refresh_style()

    def _click(self, _event=None):
        self.on_select(self)

    def set_selected(self, selected: bool):
        self._selected = selected
        self.refresh_style()

    def refresh_style(self):
        p = self.param
        if p.mismatch:
            fg = COLOR_MISMATCH
        elif p.manual_only:
            fg = COLOR_MANUAL
        elif p.live_value is not None and not p.mismatch:
            fg = COLOR_OK
        else:
            fg = COLOR_NORMAL
        if self._selected:
            # slight border via thicker look
            self.configure(fg_color=fg, border_width=2, border_color="#60a5fa")
        else:
            self.configure(fg_color=fg, border_width=0)

        self.lbl_id.configure(text=p.param_id())
        self.lbl_val.configure(text=str(p.value))
        notes = p.notes if p.notes else "—"
        if len(notes) > 48:
            notes = notes[:45] + "…"
        self.lbl_notes.configure(text=notes)
        self.lbl_manual.configure(text="Manual" if p.manual_only else "RS485")
        live = "—" if p.live_value is None else str(p.live_value)
        self.lbl_live.configure(text=live)


class App(ctk.CTk):
    def __init__(self):
        super().__init__()
        self.title(APP_TITLE)
        self.geometry("1180x720")
        self.minsize(960, 600)

        self.client = Esp32Client()
        self.plist = ParameterList(name="Nueva lista")
        self.current_path: Optional[Path] = None
        self._rows: List[ParamRow] = []
        self._selected_row: Optional[ParamRow] = None
        self._worker: Optional[threading.Thread] = None
        self._stop = False
        self._busy = False

        DEFAULT_LISTS.mkdir(parents=True, exist_ok=True)
        # Seed example lists next to the app if missing (frozen or first run)
        try:
            bundled = _bundled_lists_dir()
            if bundled.is_dir() and bundled.resolve() != DEFAULT_LISTS.resolve():
                for src in bundled.glob("*.json"):
                    dst = DEFAULT_LISTS / src.name
                    if not dst.exists():
                        shutil.copy2(src, dst)
        except Exception:
            pass

        self._build_ui()
        self._refresh_ports()
        self._reload_table()
        self._set_status("Listo. Conecta el ESP32 o activa modo simulado.")

    # ------------------------------------------------------------------ UI
    def _build_ui(self):
        self.grid_columnconfigure(0, weight=1)
        self.grid_rowconfigure(2, weight=1)

        # --- Connection bar ---
        top = ctk.CTkFrame(self, corner_radius=0)
        top.grid(row=0, column=0, sticky="ew")
        top.grid_columnconfigure(8, weight=1)

        ctk.CTkLabel(top, text="Puerto:").grid(row=0, column=0, padx=(12, 4), pady=10)
        self.port_var = ctk.StringVar(value="")
        self.port_menu = ctk.CTkOptionMenu(top, variable=self.port_var, values=["—"], width=160)
        self.port_menu.grid(row=0, column=1, padx=4, pady=10)

        ctk.CTkButton(top, text="↻", width=36, command=self._refresh_ports).grid(
            row=0, column=2, padx=2, pady=10
        )

        ctk.CTkLabel(top, text="Baud:").grid(row=0, column=3, padx=(12, 4), pady=10)
        self.baud_var = ctk.StringVar(value="115200")
        self.baud_menu = ctk.CTkOptionMenu(
            top,
            variable=self.baud_var,
            values=["9600", "19200", "38400", "57600", "115200"],
            width=100,
        )
        self.baud_menu.grid(row=0, column=4, padx=4, pady=10)

        self.btn_connect = ctk.CTkButton(top, text="Conectar", width=100, command=self._toggle_connect)
        self.btn_connect.grid(row=0, column=5, padx=8, pady=10)

        self.dummy_var = ctk.BooleanVar(value=False)
        self.chk_dummy = ctk.CTkCheckBox(
            top,
            text="Modo simulado (sin ESP32)",
            variable=self.dummy_var,
            command=self._on_dummy_toggle,
        )
        self.chk_dummy.grid(row=0, column=6, padx=12, pady=10)

        self.lbl_link = ctk.CTkLabel(top, text="● Desconectado", text_color="#ef4444")
        self.lbl_link.grid(row=0, column=7, padx=12, pady=10, sticky="e")

        # --- Toolbar ---
        bar = ctk.CTkFrame(self)
        bar.grid(row=1, column=0, sticky="ew", padx=12, pady=(8, 4))
        for i, (text, cmd) in enumerate(
            [
                ("Nueva lista", self._new_list),
                ("Abrir…", self._open_list),
                ("Guardar", self._save_list),
                ("Guardar como…", self._save_list_as),
                ("Enviar al VDF", self._send_to_vfd),
                ("Leer y comparar", self._read_compare),
                ("Ping", self._ping),
            ]
        ):
            ctk.CTkButton(bar, text=text, command=cmd, width=120).grid(
                row=0, column=i, padx=4, pady=8
            )

        self.progress = ctk.CTkProgressBar(bar, width=160)
        self.progress.grid(row=0, column=20, padx=12, pady=8)
        self.progress.set(0)
        self.lbl_progress = ctk.CTkLabel(bar, text="")
        self.lbl_progress.grid(row=0, column=21, padx=4, pady=8)

        # --- Main split: table | editor ---
        body = ctk.CTkFrame(self, fg_color="transparent")
        body.grid(row=2, column=0, sticky="nsew", padx=12, pady=4)
        body.grid_columnconfigure(0, weight=3)
        body.grid_columnconfigure(1, weight=1)
        body.grid_rowconfigure(0, weight=1)

        # Table panel
        table_panel = ctk.CTkFrame(body)
        table_panel.grid(row=0, column=0, sticky="nsew", padx=(0, 8))
        table_panel.grid_rowconfigure(1, weight=1)
        table_panel.grid_columnconfigure(0, weight=1)

        self.lbl_list_name = ctk.CTkLabel(
            table_panel, text="Lista: Nueva lista", font=ctk.CTkFont(size=16, weight="bold")
        )
        self.lbl_list_name.grid(row=0, column=0, sticky="w", padx=12, pady=(10, 4))

        header = ctk.CTkFrame(table_panel, corner_radius=6, fg_color=COLOR_HEADER[1])
        header.grid(row=1, column=0, sticky="ew", padx=8, pady=(4, 0))
        for col, (txt, w) in enumerate(
            [("ID", 70), ("Valor", 70), ("Notas", 0), ("Modo", 70), ("Leído", 70)]
        ):
            lbl = ctk.CTkLabel(
                header,
                text=txt,
                width=w if w else 200,
                anchor="w",
                font=ctk.CTkFont(weight="bold"),
            )
            lbl.grid(row=0, column=col, padx=8, pady=6, sticky="w")
        header.grid_columnconfigure(2, weight=1)

        self.scroll = ctk.CTkScrollableFrame(table_panel)
        self.scroll.grid(row=2, column=0, sticky="nsew", padx=8, pady=8)
        table_panel.grid_rowconfigure(2, weight=1)
        self.scroll.grid_columnconfigure(0, weight=1)

        # Editor panel
        ed = ctk.CTkFrame(body)
        ed.grid(row=0, column=1, sticky="nsew")
        ed.grid_columnconfigure(0, weight=1)

        ctk.CTkLabel(ed, text="Editor de parámetro", font=ctk.CTkFont(size=15, weight="bold")).grid(
            row=0, column=0, padx=12, pady=(12, 8), sticky="w"
        )

        ctk.CTkLabel(ed, text="Grupo").grid(row=1, column=0, padx=12, sticky="w")
        self.group_var = ctk.StringVar(value="P0")
        ctk.CTkOptionMenu(ed, variable=self.group_var, values=["P0", "P1"]).grid(
            row=2, column=0, padx=12, pady=4, sticky="ew"
        )

        ctk.CTkLabel(ed, text="Índice (0–47)").grid(row=3, column=0, padx=12, sticky="w")
        self.index_entry = ctk.CTkEntry(ed, placeholder_text="0")
        self.index_entry.grid(row=4, column=0, padx=12, pady=4, sticky="ew")

        ctk.CTkLabel(ed, text="Valor raw (0–65535)").grid(row=5, column=0, padx=12, sticky="w")
        self.value_entry = ctk.CTkEntry(ed, placeholder_text="ej. 10 = 1.0 bar en P0-00")
        self.value_entry.grid(row=6, column=0, padx=12, pady=4, sticky="ew")

        ctk.CTkLabel(ed, text="Notas / anotaciones").grid(row=7, column=0, padx=12, sticky="w")
        self.notes_box = ctk.CTkTextbox(ed, height=120)
        self.notes_box.grid(row=8, column=0, padx=12, pady=4, sticky="ew")

        self.manual_var = ctk.BooleanVar(value=False)
        ctk.CTkCheckBox(
            ed,
            text="No modificable por RS485\n(solo ajuste manual en el VDF)",
            variable=self.manual_var,
        ).grid(row=9, column=0, padx=12, pady=10, sticky="w")

        btn_row = ctk.CTkFrame(ed, fg_color="transparent")
        btn_row.grid(row=10, column=0, padx=12, pady=8, sticky="ew")
        ctk.CTkButton(btn_row, text="Añadir / Actualizar", command=self._add_or_update).pack(
            side="left", padx=4
        )
        ctk.CTkButton(
            btn_row, text="Eliminar", fg_color="#b91c1c", hover_color="#7f1d1d", command=self._delete_selected
        ).pack(side="left", padx=4)
        ctk.CTkButton(btn_row, text="Limpiar form.", command=self._clear_form, width=100).pack(
            side="left", padx=4
        )

        ctk.CTkLabel(
            ed,
            text=(
                "Leyenda colores:\n"
                "• Rojo = valor leído ≠ lista\n"
                "• Verde = coincide tras comparar\n"
                "• Amarillo = solo manual (no se envía)"
            ),
            justify="left",
            text_color="#9ca3af",
        ).grid(row=11, column=0, padx=12, pady=16, sticky="w")

        # Status bar
        self.status = ctk.CTkLabel(self, text="", anchor="w")
        self.status.grid(row=3, column=0, sticky="ew", padx=16, pady=(4, 10))

    # ------------------------------------------------------------------ helpers
    def _set_status(self, text: str):
        self.status.configure(text=text)

    def _set_link_ui(self, connected: bool, label: str = ""):
        if connected:
            self.lbl_link.configure(text=f"● {label or 'Conectado'}", text_color="#22c55e")
            self.btn_connect.configure(text="Desconectar")
        else:
            self.lbl_link.configure(text="● Desconectado", text_color="#ef4444")
            self.btn_connect.configure(text="Conectar")

    def _refresh_ports(self):
        ports = list_serial_ports()
        if not ports:
            ports = ["—"]
        self.port_menu.configure(values=ports)
        if self.port_var.get() not in ports:
            self.port_var.set(ports[0])

    def _on_dummy_toggle(self):
        if self.dummy_var.get():
            try:
                self.client.connect_dummy()
                self._set_link_ui(True, "Simulado")
                self._set_status("Modo simulado activo — respuestas dummy del VDF.")
            except Exception as e:
                messagebox.showerror("Error", str(e))
                self.dummy_var.set(False)
        else:
            self.client.disconnect()
            self._set_link_ui(False)
            self._set_status("Modo simulado desactivado.")

    def _toggle_connect(self):
        if self.client.connected and self.client.mode == "real":
            self.client.disconnect()
            self._set_link_ui(False)
            self._set_status("Desconectado.")
            return
        if self.dummy_var.get():
            messagebox.showinfo("Info", "Desactiva el modo simulado para conectar al puerto real.")
            return
        port = self.port_var.get()
        if not port or port == "—":
            messagebox.showwarning("Puerto", "Selecciona un puerto serial válido.")
            return
        try:
            baud = int(self.baud_var.get())
            self.client.connect_real(port, baud)
            self._set_link_ui(True, port)
            self._set_status(f"Conectado a {port} @ {baud}.")
        except Exception as e:
            messagebox.showerror("Conexión", f"No se pudo abrir el puerto:\n{e}")
            self._set_link_ui(False)

    def _reload_table(self):
        for row in self._rows:
            row.destroy()
        self._rows.clear()
        self._selected_row = None
        self.lbl_list_name.configure(text=f"Lista: {self.plist.name}  ({len(self.plist.parameters)} params)")

        for p in self.plist.parameters:
            row = ParamRow(self.scroll, p, on_select=self._on_row_select)
            row.grid(sticky="ew", padx=2, pady=2)
            self.scroll.grid_columnconfigure(0, weight=1)
            self._rows.append(row)

    def _on_row_select(self, row: ParamRow):
        if self._selected_row:
            self._selected_row.set_selected(False)
        self._selected_row = row
        row.set_selected(True)
        p = row.param
        self.group_var.set(f"P{p.group}")
        self.index_entry.delete(0, "end")
        self.index_entry.insert(0, str(p.index))
        self.value_entry.delete(0, "end")
        self.value_entry.insert(0, str(p.value))
        self.notes_box.delete("1.0", "end")
        self.notes_box.insert("1.0", p.notes)
        self.manual_var.set(p.manual_only)

    def _clear_form(self):
        self.index_entry.delete(0, "end")
        self.value_entry.delete(0, "end")
        self.notes_box.delete("1.0", "end")
        self.manual_var.set(False)
        if self._selected_row:
            self._selected_row.set_selected(False)
            self._selected_row = None

    def _form_to_param(self) -> Parameter:
        g = 0 if self.group_var.get() == "P0" else 1
        try:
            idx = int(self.index_entry.get().strip())
            val = int(self.value_entry.get().strip(), 0)
        except ValueError as e:
            raise ValueError("Índice y valor deben ser enteros (valor admite 0x..)") from e
        notes = self.notes_box.get("1.0", "end").strip()
        p = Parameter(
            group=g,
            index=idx,
            value=val,
            notes=notes,
            manual_only=bool(self.manual_var.get()),
        )
        p.validate()
        return p

    def _add_or_update(self):
        try:
            p = self._form_to_param()
        except ValueError as e:
            messagebox.showerror("Validación", str(e))
            return
        self.plist.add(p)
        self.plist.sort_by_id()
        self._reload_table()
        self._set_status(f"Parámetro {p.param_id()} guardado en la lista.")

    def _delete_selected(self):
        if not self._selected_row:
            messagebox.showinfo("Eliminar", "Selecciona un parámetro en la lista.")
            return
        p = self._selected_row.param
        self.plist.parameters = [
            x for x in self.plist.parameters if not (x.group == p.group and x.index == p.index)
        ]
        self._reload_table()
        self._clear_form()
        self._set_status(f"Eliminado {p.param_id()}.")

    # ------------------------------------------------------------------ file
    def _new_list(self):
        if self.plist.parameters and not messagebox.askyesno(
            "Nueva lista", "¿Descartar la lista actual no guardada?"
        ):
            return
        self.plist = ParameterList(name="Nueva lista")
        self.current_path = None
        self._reload_table()
        self._clear_form()
        self._set_status("Lista vacía creada.")

    def _open_list(self):
        path = filedialog.askopenfilename(
            title="Abrir lista de parámetros",
            initialdir=str(DEFAULT_LISTS),
            filetypes=[
                ("JSON", "*.json"),
                ("CSV", "*.csv"),
                ("Todos", "*.*"),
            ],
        )
        if not path:
            return
        try:
            self.plist = load_any(path)
            self.plist.sort_by_id()
            self.current_path = Path(path)
            self._reload_table()
            self._set_status(f"Cargado: {path}")
        except Exception as e:
            messagebox.showerror("Abrir", str(e))

    def _save_list(self):
        if self.current_path:
            try:
                save_any(self.plist, self.current_path)
                self._set_status(f"Guardado: {self.current_path}")
            except Exception as e:
                messagebox.showerror("Guardar", str(e))
        else:
            self._save_list_as()

    def _save_list_as(self):
        path = filedialog.asksaveasfilename(
            title="Guardar lista",
            initialdir=str(DEFAULT_LISTS),
            defaultextension=".json",
            filetypes=[("JSON", "*.json"), ("CSV", "*.csv")],
        )
        if not path:
            return
        try:
            # Update name from filename
            self.plist.name = Path(path).stem
            save_any(self.plist, path)
            self.current_path = Path(path)
            self._reload_table()
            self._set_status(f"Guardado: {path}")
        except Exception as e:
            messagebox.showerror("Guardar", str(e))

    # ------------------------------------------------------------------ serial ops
    def _ensure_connected(self) -> bool:
        if self.client.connected:
            return True
        messagebox.showwarning(
            "Sin conexión",
            "Conecta el puerto serial o activa «Modo simulado».",
        )
        return False

    def _set_busy(self, busy: bool):
        self._busy = busy
        state = "disabled" if busy else "normal"
        # CTk buttons use configure(state=...)
        # Soft-disable via progress feedback only if needed

    def _run_worker(self, target):
        if self._busy:
            messagebox.showinfo("Ocupado", "Espera a que termine la operación actual.")
            return
        self._stop = False
        self._busy = True
        self.progress.set(0)
        t = threading.Thread(target=target, daemon=True)
        self._worker = t
        t.start()

    def _ui(self, fn):
        """Marshal callable to UI thread."""
        self.after(0, fn)

    def _ping(self):
        if not self._ensure_connected():
            return

        def work():
            try:
                res = self.client.ping()
                self._ui(lambda: self._set_status("Ping OK" if res.ok else f"Ping FAIL: {res.message[:120]}"))
                if not res.ok:
                    self._ui(lambda: messagebox.showwarning("Ping", res.message[:500]))
            except Exception as e:
                self._ui(lambda: messagebox.showerror("Ping", str(e)))
            finally:
                self._busy = False

        self._run_worker(work)

    def _send_to_vfd(self):
        if not self._ensure_connected():
            return
        writable = self.plist.writable()
        if not writable:
            messagebox.showinfo("Enviar", "No hay parámetros enviables (todos manuales o lista vacía).")
            return
        skipped = len(self.plist.parameters) - len(writable)
        if not messagebox.askyesno(
            "Enviar al VDF",
            f"Se enviarán {len(writable)} parámetros por RS485.\n"
            f"Se omitirán {skipped} marcados como manuales.\n¿Continuar?",
        ):
            return

        def work():
            ok_n = 0
            fail_n = 0

            def on_prog(i, total, p, res: SerialResult):
                def upd():
                    self.progress.set(i / max(total, 1))
                    self.lbl_progress.configure(text=f"{i}/{total} {p.param_id()}")
                    if res.ok:
                        self._set_status(f"Escrito {p.param_id()} = {p.value}")
                    else:
                        self._set_status(f"Error {p.param_id()}: {res.message[:80]}")

                self._ui(upd)
                nonlocal ok_n, fail_n
                if res.ok:
                    ok_n += 1
                else:
                    fail_n += 1

            try:
                self.client.write_list(self.plist.parameters, on_progress=on_prog, stop_flag=lambda: self._stop)
                self._ui(
                    lambda: messagebox.showinfo(
                        "Envío terminado",
                        f"OK: {ok_n}\nErrores: {fail_n}\nOmitidos (manual): {skipped}",
                    )
                )
            except Exception as e:
                self._ui(lambda: messagebox.showerror("Enviar", str(e)))
            finally:
                self._busy = False
                self._ui(lambda: self.lbl_progress.configure(text=""))

        self._run_worker(work)

    def _read_compare(self):
        if not self._ensure_connected():
            return
        if not self.plist.parameters:
            messagebox.showinfo("Comparar", "La lista está vacía.")
            return

        def work():
            mismatches = 0

            def on_prog(i, total, p, res: SerialResult):
                nonlocal mismatches

                def upd():
                    self.progress.set(i / max(total, 1))
                    self.lbl_progress.configure(text=f"{i}/{total} {p.param_id()}")
                    if res.ok and res.value is not None:
                        p.live_value = res.value
                        p.mismatch = int(res.value) != int(p.value)
                    else:
                        p.live_value = None
                        p.mismatch = True
                    # refresh row styles
                    for row in self._rows:
                        if row.param is p:
                            row.refresh_style()
                            break
                    self._set_status(
                        f"Leído {p.param_id()}: live={p.live_value} lista={p.value}"
                        + (" ≠" if p.mismatch else " =")
                    )

                self._ui(upd)
                if res.ok and res.value is not None and int(res.value) != int(p.value):
                    mismatches += 1
                elif not res.ok:
                    mismatches += 1

            try:
                self.plist.clear_compare()
                self._ui(self._reload_table)
                # After reload, param objects are same references in plist
                self.client.read_list(self.plist.parameters, on_progress=on_prog, stop_flag=lambda: self._stop)
                # Final refresh
                def done():
                    for row in self._rows:
                        row.refresh_style()
                    messagebox.showinfo(
                        "Comparación",
                        f"Parámetros con diferencia o error: {mismatches} / {len(self.plist.parameters)}",
                    )

                self._ui(done)
            except Exception as e:
                self._ui(lambda: messagebox.showerror("Leer", str(e)))
            finally:
                self._busy = False
                self._ui(lambda: self.lbl_progress.configure(text=""))

        self._run_worker(work)


def run_app():
    app = App()
    app.mainloop()


if __name__ == "__main__":
    run_app()
