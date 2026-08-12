"""
MULTI_VDF_HMI — Firmware Flasher GUI

Descarga el firmware más reciente desde GitHub Releases y flashea
ESP32 / Guition con esptool.
"""

from __future__ import annotations

import threading
import tkinter as tk
from pathlib import Path
from tkinter import filedialog, messagebox
from typing import List, Optional

import customtkinter as ctk

from .flash_worker import flash_board, list_serial_ports
from .github_releases import (
    DEFAULT_REPO,
    BoardPackage,
    GithubFirmwareIndex,
    fetch_latest_firmware_index,
    load_local_manifest,
)

ctk.set_appearance_mode("dark")
ctk.set_default_color_theme("blue")


class FlasherApp(ctk.CTk):
    def __init__(self) -> None:
        super().__init__()
        self.title("MULTI_VDF_HMI — Flasheo de firmware")
        self.geometry("820x640")
        self.minsize(720, 520)

        self._index: Optional[GithubFirmwareIndex] = None
        self._busy = False

        self.grid_columnconfigure(0, weight=1)
        self.grid_rowconfigure(3, weight=1)

        # Header
        head = ctk.CTkFrame(self, corner_radius=0)
        head.grid(row=0, column=0, sticky="ew")
        ctk.CTkLabel(
            head,
            text="Flasheo de micros SAJ Edge",
            font=ctk.CTkFont(size=18, weight="bold"),
        ).pack(side="left", padx=16, pady=12)
        self.lbl_ver = ctk.CTkLabel(head, text="sin paquete", text_color="#9ca3af")
        self.lbl_ver.pack(side="right", padx=16, pady=12)

        # Repo / fetch
        row1 = ctk.CTkFrame(self)
        row1.grid(row=1, column=0, sticky="ew", padx=12, pady=8)
        row1.grid_columnconfigure(1, weight=1)
        ctk.CTkLabel(row1, text="Repo GitHub:").grid(row=0, column=0, padx=8, pady=8)
        self.repo_var = ctk.StringVar(value=DEFAULT_REPO)
        ctk.CTkEntry(row1, textvariable=self.repo_var, width=280).grid(
            row=0, column=1, padx=4, pady=8, sticky="w"
        )
        ctk.CTkButton(
            row1, text="Buscar último firmware", command=self._fetch_latest, width=180
        ).grid(row=0, column=2, padx=6, pady=8)
        ctk.CTkButton(
            row1,
            text="Carpeta local…",
            command=self._load_local,
            width=120,
            fg_color="#334155",
        ).grid(row=0, column=3, padx=6, pady=8)

        # Board + port
        row2 = ctk.CTkFrame(self)
        row2.grid(row=2, column=0, sticky="ew", padx=12, pady=4)
        row2.grid_columnconfigure(1, weight=1)
        row2.grid_columnconfigure(3, weight=1)

        ctk.CTkLabel(row2, text="Placa / firmware:").grid(row=0, column=0, padx=8, pady=8)
        self.board_var = ctk.StringVar(value="—")
        self.board_menu = ctk.CTkOptionMenu(
            row2, variable=self.board_var, values=["—"], width=320
        )
        self.board_menu.grid(row=0, column=1, padx=4, pady=8, sticky="w")

        ctk.CTkLabel(row2, text="Puerto:").grid(row=0, column=2, padx=8, pady=8)
        self.port_var = ctk.StringVar(value="—")
        self.port_menu = ctk.CTkOptionMenu(
            row2, variable=self.port_var, values=["—"], width=140
        )
        self.port_menu.grid(row=0, column=3, padx=4, pady=8, sticky="w")
        ctk.CTkButton(row2, text="↻", width=36, command=self._refresh_ports).grid(
            row=0, column=4, padx=4, pady=8
        )

        ctk.CTkLabel(row2, text="Baud flash:").grid(row=1, column=0, padx=8, pady=8)
        self.baud_var = ctk.StringVar(value="921600")
        ctk.CTkOptionMenu(
            row2,
            variable=self.baud_var,
            values=["115200", "460800", "921600"],
            width=120,
        ).grid(row=1, column=1, padx=4, pady=8, sticky="w")

        self.erase_var = ctk.BooleanVar(value=False)
        ctk.CTkCheckBox(
            row2, text="Borrar flash completa antes (erase)", variable=self.erase_var
        ).grid(row=1, column=2, columnspan=2, padx=8, pady=8, sticky="w")

        self.btn_flash = ctk.CTkButton(
            row2,
            text="Flashear",
            width=160,
            height=36,
            fg_color="#15803d",
            hover_color="#166534",
            command=self._flash,
        )
        self.btn_flash.grid(row=1, column=4, padx=8, pady=8)

        # Log
        logf = ctk.CTkFrame(self)
        logf.grid(row=3, column=0, sticky="nsew", padx=12, pady=8)
        logf.grid_rowconfigure(0, weight=1)
        logf.grid_columnconfigure(0, weight=1)
        self.log = ctk.CTkTextbox(logf, font=ctk.CTkFont(family="monospace", size=12))
        self.log.grid(row=0, column=0, sticky="nsew", padx=4, pady=4)

        # Status
        self.status = ctk.CTkLabel(self, text="Listo.", anchor="w")
        self.status.grid(row=4, column=0, sticky="ew", padx=16, pady=(0, 10))

        self._refresh_ports()
        self._log(
            "MULTI_VDF_HMI Flasher\n"
            f"Repo por defecto: {DEFAULT_REPO}\n"
            "1) Buscar último firmware  2) Elegir placa y puerto  3) Flashear\n"
            "Nota: Guition a veces necesita BOOT+EN si el upload falla.\n"
        )

    # ------------------------------------------------------------------ helpers
    def _log(self, text: str) -> None:
        self.log.insert("end", text + ("" if text.endswith("\n") else "\n"))
        self.log.see("end")

    def _set_status(self, text: str) -> None:
        self.status.configure(text=text)

    def _set_busy(self, busy: bool) -> None:
        self._busy = busy
        state = "disabled" if busy else "normal"
        self.btn_flash.configure(state=state)

    def _refresh_ports(self) -> None:
        ports = list_serial_ports() or ["—"]
        self.port_menu.configure(values=ports)
        if self.port_var.get() not in ports:
            self.port_var.set(ports[0])

    def _selected_board(self) -> Optional[BoardPackage]:
        if not self._index:
            return None
        label = self.board_var.get()
        for b in self._index.firmwares:
            if label.startswith(b.id) or b.name in label or label == b.name:
                return b
        # match "id — name"
        for b in self._index.firmwares:
            if b.id in label:
                return b
        return None

    def _apply_index(self, idx: GithubFirmwareIndex) -> None:
        self._index = idx
        labels = [f"{b.id}  —  {b.name}" for b in idx.firmwares] or ["—"]
        self.board_menu.configure(values=labels)
        self.board_var.set(labels[0])
        self.lbl_ver.configure(
            text=f"v{idx.version}  ·  {idx.release_tag}  ·  {idx.source}"
        )
        self._log(
            f"\n=== Firmware {idx.version} ===\n"
            f"repo={idx.repo}  tag={idx.release_tag}\n"
            f"built={idx.built_at}\n"
            f"placas={len(idx.firmwares)}\n"
        )
        for b in idx.firmwares:
            self._log(f"  • {b.id}  chip={b.chip}  flash={b.flash_size}")
        self._set_status(f"Paquete listo: v{idx.version}")

    # ------------------------------------------------------------------ actions
    def _fetch_latest(self) -> None:
        if self._busy:
            return
        repo = self.repo_var.get().strip() or DEFAULT_REPO
        self._set_busy(True)
        self._set_status(f"Consultando GitHub {repo}…")

        def work():
            try:
                def prog(done, total):
                    pct = 100 * done // total if total else 0
                    self.after(
                        0,
                        lambda: self._set_status(f"Descargando… {pct}% ({done}/{total})"),
                    )

                idx = fetch_latest_firmware_index(repo=repo, progress=prog)
                self.after(0, lambda: self._apply_index(idx))
            except Exception as e:
                self.after(
                    0,
                    lambda: messagebox.showerror("GitHub", str(e)),
                )
                self.after(0, lambda: self._set_status(f"Error: {e}"))
            finally:
                self.after(0, lambda: self._set_busy(False))

        threading.Thread(target=work, daemon=True).start()

    def _load_local(self) -> None:
        path = filedialog.askopenfilename(
            title="manifest.json del paquete local",
            filetypes=[("manifest.json", "manifest.json"), ("JSON", "*.json"), ("All", "*.*")],
        )
        if not path:
            # also allow directory
            d = filedialog.askdirectory(title="Carpeta dist/firmware/<version>")
            if not d:
                return
            man = Path(d) / "manifest.json"
            if not man.is_file():
                messagebox.showerror("Local", f"No hay manifest.json en {d}")
                return
            path = str(man)
        try:
            idx = load_local_manifest(Path(path))
            self._apply_index(idx)
        except Exception as e:
            messagebox.showerror("Local", str(e))

    def _flash(self) -> None:
        if self._busy:
            return
        board = self._selected_board()
        port = self.port_var.get()
        if not board:
            messagebox.showwarning("Flash", "Cargá un paquete de firmware y elegí placa.")
            return
        if not port or port == "—":
            messagebox.showwarning("Flash", "Seleccioná un puerto serial.")
            return
        if not messagebox.askyesno(
            "Confirmar flash",
            f"¿Flashear «{board.name}» ({board.chip}) en {port}?\n\n"
            f"Versión: {self._index.version if self._index else '?'}\n"
            f"Baud: {self.baud_var.get()}\n"
            f"Erase all: {self.erase_var.get()}",
        ):
            return

        self._set_busy(True)
        self._set_status("Flasheando…")
        baud = int(self.baud_var.get())
        erase = bool(self.erase_var.get())

        def work():
            try:
                self.after(0, lambda: self._log(f"\n--- Flash {board.id} → {port} ---"))
                flash_board(
                    board,
                    port,
                    baud=baud,
                    erase_all=erase,
                    log=lambda m: self.after(0, lambda: self._log(m)),
                )
                self.after(
                    0,
                    lambda: messagebox.showinfo(
                        "Flash", f"Firmware {board.id} grabado correctamente en {port}."
                    ),
                )
                self.after(0, lambda: self._set_status("Flash OK"))
            except Exception as e:
                self.after(0, lambda: messagebox.showerror("Flash", str(e)))
                self.after(0, lambda: self._set_status(f"Error flash: {e}"))
                self.after(0, lambda: self._log(f"ERROR: {e}"))
            finally:
                self.after(0, lambda: self._set_busy(False))

        threading.Thread(target=work, daemon=True).start()


def main() -> None:
    app = FlasherApp()
    app.mainloop()


if __name__ == "__main__":
    main()
