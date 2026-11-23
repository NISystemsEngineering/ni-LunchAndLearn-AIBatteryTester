"""AA battery health checker GUI (NiMH and Li-ion with BMS) using an NI PXIe-4082 DMM.

Run with:  run.bat  (or python -m example_python_battery_checker)
"""
import queue
import tkinter as tk
from collections import deque
from tkinter import filedialog, messagebox, ttk

import numpy as np
from matplotlib.backends.backend_tkagg import FigureCanvasTkAgg, NavigationToolbar2Tk
from matplotlib.figure import Figure

from .analysis import (BAD, CHARGE, CHECK, GOOD, NO_OUTPUT, PRESENT_V, Assessment,
                       Measurement, Thresholds)
from .measure import MAX_SCOPE_RATE, TestSettings, write_csv
from .worker import DmmWorker

HEALTH_COLORS = {GOOD: "#1e8e3e", CHARGE: "#e37400", CHECK: "#1a73e8",
                 BAD: "#d93025", NO_OUTPUT: "#5f6368"}
IDLE_COLOR = "#5f6368"
WAVE_WINDOW_S = 0.05
SMOOTH_S = 20e-6              # moving-average overlay on high-rate ripple plots
LIVE_STABLE_V = 0.010         # consecutive live readings must agree this closely...
LIVE_STABLE_COUNT = 3         # ...over this many readings before a battery counts as connected


def _rate_text(rate: float) -> str:
    return f"{rate / 1e6:g} MS/s" if rate >= 1e6 else f"{rate / 1e3:g} kS/s"


SCOPE_RATES = {_rate_text(r): r for r in (100e3, 500e3, MAX_SCOPE_RATE)}

ABOUT = ("Measures open-circuit voltage, its stability, and AC ripple with the DMM. "
         "Ripple from the built-in regulator identifies 1.5 V Li-ion cells; NiMH cells "
         "have none.\n\nNo load is applied, so capacity and internal resistance "
         "are not measured.")


class BatteryGui(tk.Tk):
    def __init__(self, dmm_resource: str = "PXI1Slot3"):
        super().__init__()
        self.title("AA Battery Health Checker")
        self.geometry("1240x820")
        self.minsize(1040, 700)

        self.history: list[tuple[str, Assessment, Measurement]] = []
        self.events: queue.Queue = queue.Queue()
        self.worker = DmmWorker(dmm_resource, self.events)
        self._busy = False
        self._armed = True          # auto-test fires on the next battery detected
        self._live: deque[float] = deque(maxlen=LIVE_STABLE_COUNT)

        self._build_vars(dmm_resource)
        self._build_layout()
        self.protocol("WM_DELETE_WINDOW", self._on_close)

        self.worker.start()
        self.worker.set_monitoring(True)
        self.after(50, self._poll_events)

    # ---------------------------------------------------------------- layout
    def _build_vars(self, dmm_resource):
        t, s = Thresholds(), TestSettings()
        self.v_monitor = tk.BooleanVar(value=True)
        self.v_auto = tk.BooleanVar(value=True)
        self.v_readings = tk.StringVar(value=str(s.dc_readings))
        self.v_digits = tk.StringVar(value=f"{s.dc_digits:g}")
        self.v_scope_rate = tk.StringVar(value=_rate_text(s.scope_rate))
        self.v_ripple = tk.StringVar(value=f"{t.ripple_switching * 1e3:g}")
        self.v_noise = tk.StringVar(value=f"{t.max_noise * 1e3:g}")
        self.v_drift = tk.StringVar(value=f"{t.max_drift * 1e3:g}")
        self.v_dmm = tk.StringVar(value=dmm_resource)
        self.v_status = tk.StringVar(value="Starting…")

    def _build_layout(self):
        root = ttk.Frame(self, padding=10)
        root.pack(fill="both", expand=True)
        root.columnconfigure(1, weight=1)
        root.rowconfigure(0, weight=1)
        self._build_left(root).grid(row=0, column=0, sticky="nsw", padx=(0, 12))

        right = ttk.Frame(root)
        right.grid(row=0, column=1, sticky="nsew")
        right.columnconfigure(0, weight=1)
        right.rowconfigure(1, weight=3)
        right.rowconfigure(2, weight=2)
        self._build_result(right).grid(row=0, column=0, sticky="ew")
        self._build_plot(right).grid(row=1, column=0, sticky="nsew", pady=8)
        self._build_history(right).grid(row=2, column=0, sticky="nsew")

        ttk.Label(self, textvariable=self.v_status, anchor="w", relief="sunken",
                  padding=(8, 2)).pack(fill="x", side="bottom")

    def _entry_row(self, parent, r, label, var, unit=""):
        ttk.Label(parent, text=label).grid(row=r, column=0, sticky="w", pady=2)
        ttk.Entry(parent, textvariable=var, width=9).grid(row=r, column=1, sticky="ew", pady=2)
        ttk.Label(parent, text=unit).grid(row=r, column=2, sticky="w", padx=(4, 0))

    def _build_left(self, parent):
        f = ttk.Frame(parent, width=290)

        live = ttk.LabelFrame(f, text="Live voltage", padding=8)
        live.pack(fill="x")
        self.lbl_live = ttk.Label(live, text="—", font=("Segoe UI", 24, "bold"))
        self.lbl_live.pack(anchor="w")
        self.lbl_presence = ttk.Label(live, text="", foreground=IDLE_COLOR)
        self.lbl_presence.pack(anchor="w")
        ttk.Checkbutton(live, text="Live monitor", variable=self.v_monitor,
                        command=self._on_monitor_toggle).pack(anchor="w", pady=(6, 0))
        ttk.Checkbutton(live, text="Auto-test when a battery is connected",
                        variable=self.v_auto).pack(anchor="w")

        self.btn_test = ttk.Button(f, text="Test battery", command=self._start_test)
        self.btn_test.pack(fill="x", pady=10, ipady=6)

        st = ttk.LabelFrame(f, text="Settings", padding=8)
        st.pack(fill="x")
        st.columnconfigure(1, weight=1)
        self._entry_row(st, 0, "DC readings", self.v_readings)
        ttk.Label(st, text="Resolution").grid(row=1, column=0, sticky="w", pady=2)
        ttk.Combobox(st, textvariable=self.v_digits, values=["5.5", "6.5", "7.5"],
                     state="readonly", width=7).grid(row=1, column=1, sticky="ew", pady=2)
        ttk.Label(st, text="digits").grid(row=1, column=2, sticky="w", padx=(4, 0))
        self._entry_row(st, 2, "Regulator ripple ≥", self.v_ripple, "mV rms")
        self._entry_row(st, 3, "Max noise", self.v_noise, "mV rms")
        self._entry_row(st, 4, "Max |drift|", self.v_drift, "mV/s")
        ttk.Label(st, text="Ripple plot rate").grid(row=5, column=0, sticky="w", pady=2)
        ttk.Combobox(st, textvariable=self.v_scope_rate, values=list(SCOPE_RATES),
                     state="readonly", width=9).grid(row=5, column=1, columnspan=2, sticky="ew", pady=2)
        ttk.Label(st, text="DMM").grid(row=6, column=0, sticky="w", pady=2)
        ttk.Entry(st, textvariable=self.v_dmm, width=12).grid(row=6, column=1, sticky="ew", pady=2)
        ttk.Button(st, text="Apply", width=6, command=self._apply_resource).grid(
            row=6, column=2, padx=(4, 0))

        about = ttk.LabelFrame(f, text="About the measurement", padding=8)
        about.pack(fill="x", pady=(10, 0))
        ttk.Label(about, text=ABOUT, wraplength=260, foreground=IDLE_COLOR,
                  justify="left").pack(anchor="w")
        return f

    def _build_result(self, parent):
        f = ttk.Frame(parent)
        f.columnconfigure(1, weight=1)
        self.lbl_health = tk.Label(f, text="—", width=9, font=("Segoe UI", 22, "bold"),
                                   fg="white", bg=IDLE_COLOR, padx=6, pady=10)
        self.lbl_health.grid(row=0, column=0, rowspan=3, sticky="nw")

        head = ttk.Frame(f, padding=(14, 0, 0, 0))
        head.grid(row=0, column=1, sticky="ew")
        self.lbl_chem = ttk.Label(head, text="No test yet", font=("Segoe UI", 17, "bold"))
        self.lbl_chem.pack(anchor="w")
        self.lbl_conf = ttk.Label(head, text="", foreground=IDLE_COLOR)
        self.lbl_conf.pack(anchor="w")
        self.lbl_summary = ttk.Label(head, text="Connect a battery or press Test battery.")
        self.lbl_summary.pack(anchor="w", fill="x")

        stats = ttk.Frame(f, padding=(14, 6, 0, 0))
        stats.grid(row=1, column=1, sticky="ew")
        self.stat_labels = {}
        for i, key in enumerate(("OCV", "Charge", "Ripple", "Noise", "Drift")):
            ttk.Label(stats, text=key, foreground=IDLE_COLOR).grid(row=0, column=i, sticky="w", padx=(0, 16))
            lbl = ttk.Label(stats, text="—", font=("Segoe UI", 11, "bold"))
            lbl.grid(row=1, column=i, sticky="w", padx=(0, 16))
            self.stat_labels[key] = lbl
        self.soc_bar = ttk.Progressbar(stats, length=150, maximum=100)
        self.soc_bar.grid(row=2, column=1, sticky="w", pady=(2, 0))

        self.lbl_details = ttk.Label(f, text="", foreground=IDLE_COLOR, justify="left",
                                     padding=(14, 6, 0, 0))
        self.lbl_details.grid(row=2, column=1, sticky="ew")
        f.bind("<Configure>", lambda e: [lbl.configure(wraplength=max(e.width - 230, 200))
                                         for lbl in (self.lbl_summary, self.lbl_details)])
        return f

    def _build_plot(self, parent):
        f = ttk.Frame(parent)
        self.fig = Figure(figsize=(7, 3), dpi=100, layout="constrained")
        self.ax_dc, self.ax_wave = self.fig.subplots(1, 2)
        self.canvas = FigureCanvasTkAgg(self.fig, master=f)
        # Zoom/pan toolbar, mainly for inspecting individual ripple bursts.
        toolbar = NavigationToolbar2Tk(self.canvas, f, pack_toolbar=False)
        toolbar.update()
        toolbar.pack(side="bottom", fill="x")
        self.canvas.get_tk_widget().pack(fill="both", expand=True)
        self._draw(None)
        return f

    def _build_history(self, parent):
        f = ttk.Frame(parent)
        f.columnconfigure(0, weight=1)
        f.rowconfigure(0, weight=1)
        cols = ("time", "chem", "health", "ocv", "ripple", "soc", "summary")
        heads = ("Time", "Type", "Health", "OCV (V)", "Ripple (mV)", "Charge", "Summary")
        widths = (155, 225, 100, 80, 90, 65, 400)
        self.tree = ttk.Treeview(f, columns=cols, show="headings", height=6)
        for c, h, w in zip(cols, heads, widths):
            self.tree.heading(c, text=h)
            self.tree.column(c, width=w, anchor="e" if c in ("ocv", "ripple", "soc") else "w",
                             stretch=(c == "summary"))
        for h, color in HEALTH_COLORS.items():
            self.tree.tag_configure(h, foreground=color)
        self.tree.bind("<<TreeviewSelect>>", self._on_select)
        self.tree.grid(row=0, column=0, sticky="nsew")
        sb = ttk.Scrollbar(f, orient="vertical", command=self.tree.yview)
        sb.grid(row=0, column=1, sticky="ns")
        self.tree.configure(yscrollcommand=sb.set)
        bar = ttk.Frame(f)
        bar.grid(row=1, column=0, columnspan=2, sticky="ew", pady=(6, 0))
        ttk.Button(bar, text="Clear", command=self._clear).pack(side="right")
        ttk.Button(bar, text="Export CSV…", command=self._export).pack(side="right", padx=(0, 6))
        return f

    # ------------------------------------------------------------- actions
    def _read_settings(self) -> tuple[TestSettings, Thresholds] | None:
        try:
            n = int(self.v_readings.get())
            if not 3 <= n <= 1000:
                raise ValueError("DC readings must be between 3 and 1000")
            vals = {}
            for name, var in (("Regulator ripple", self.v_ripple), ("Max noise", self.v_noise),
                              ("Max drift", self.v_drift)):
                try:
                    vals[name] = float(var.get()) / 1e3
                except ValueError:
                    raise ValueError(f"{name} must be a number")
                if vals[name] <= 0:
                    raise ValueError(f"{name} must be greater than 0")
        except ValueError as e:
            msg = str(e) if "must" in str(e) else "DC readings must be a whole number"
            messagebox.showerror("Invalid setting", msg, parent=self)
            return None
        return (TestSettings(dc_readings=n, dc_digits=float(self.v_digits.get()),
                             scope_rate=SCOPE_RATES[self.v_scope_rate.get()]),
                Thresholds(ripple_switching=vals["Regulator ripple"],
                           max_noise=vals["Max noise"], max_drift=vals["Max drift"]))

    def _start_test(self):
        if self._busy:
            return
        cfg = self._read_settings()
        if cfg:
            self._set_busy(True)
            self.worker.test(*cfg)

    def _on_monitor_toggle(self):
        self.worker.set_monitoring(self.v_monitor.get())
        if not self.v_monitor.get():
            self.lbl_live.configure(text="—")
            self.lbl_presence.configure(text="Live monitor off")

    def _apply_resource(self):
        self.worker.set_resource(self.v_dmm.get().strip())
        self.v_status.set(f"DMM set to {self.v_dmm.get().strip()}")

    def _set_busy(self, busy: bool):
        self._busy = busy
        self.btn_test.configure(state="disabled" if busy else "normal",
                                text="Testing…" if busy else "Test battery")
        if busy:
            self.lbl_health.configure(text="…", bg=IDLE_COLOR)

    # ------------------------------------------------------------- events
    def _poll_events(self):
        try:
            while True:
                ev = self.events.get_nowait()
                kind = ev[0]
                if kind == "status":
                    self.v_status.set(ev[1])
                elif kind == "live":
                    self._on_live(ev[1])
                elif kind == "busy":
                    self._set_busy(ev[1])
                elif kind == "result":
                    self._on_result(*ev[1:])
                elif kind == "error":
                    self.v_status.set(f"Error: {ev[1]}")
                    self.v_monitor.set(False)
                    self.lbl_presence.configure(text="Live monitor stopped by error")
                    messagebox.showerror("DMM error", ev[1], parent=self)
        except queue.Empty:
            pass
        self.after(50, self._poll_events)

    def _on_live(self, v: float):
        if not self.v_monitor.get():
            return
        self._live.append(v)
        stable = (len(self._live) == self._live.maxlen
                  and max(self._live) - min(self._live) <= LIVE_STABLE_V)
        self.lbl_live.configure(text=f"{v:+.4f} V")
        if not stable:
            # Open leads wander by tenths of a volt; don't mistake that for a battery.
            self._armed = True
            self.lbl_presence.configure(text="Unstable: leads open or bad contact")
        elif abs(v) >= PRESENT_V:
            self.lbl_presence.configure(text="Battery detected" + (" (reversed)" if v < 0 else ""))
        else:
            self._armed = True
            self.lbl_presence.configure(text="No battery or no output")
        # Stable means the last few readings agree, so a battery being inserted has settled.
        present = stable and abs(v) >= PRESENT_V
        if present and self._armed and self.v_auto.get() and not self._busy:
            self._armed = False
            self._start_test()

    def _on_result(self, stamp: str, m: Measurement, a: Assessment):
        self.history.append((stamp, a, m))
        i = len(self.history) - 1
        soc = "n/a" if a.soc_pct is None else f"{a.soc_pct:.0f}%"
        ripple = "" if a.ripple_rms is None else f"{a.ripple_rms * 1e3:.3f}"
        self.tree.insert("", "end", iid=str(i), tags=(a.health,), values=(
            stamp, a.chemistry, a.health, f"{a.voltage:+.4f}", ripple, soc, a.summary))
        self.tree.see(str(i))
        self._show(a, m)

    def _on_select(self, _):
        sel = self.tree.selection()
        if sel:
            _, a, m = self.history[int(sel[0])]
            self._show(a, m)

    # ------------------------------------------------------------ display
    def _show(self, a: Assessment, m: Measurement):
        self.lbl_health.configure(text=a.health, bg=HEALTH_COLORS.get(a.health, IDLE_COLOR))
        self.lbl_chem.configure(text=a.chemistry)
        self.lbl_conf.configure(text=f"Type identified with {a.confidence} confidence"
                                if a.confidence != "-" else "")
        self.lbl_summary.configure(text=a.summary)
        s = self.stat_labels
        s["OCV"].configure(text=f"{a.voltage:+.4f} V")
        if a.soc_pct is None:
            s["Charge"].configure(text="n/a")
            self.soc_bar.configure(value=0)
        else:
            s["Charge"].configure(text=f"≈{a.soc_pct:.0f}%")
            self.soc_bar.configure(value=a.soc_pct)
        if a.ripple_rms is None:
            s["Ripple"].configure(text="—")
        else:
            f = f" @ {a.ripple_freq:.0f} Hz" if a.ripple_freq else ""
            s["Ripple"].configure(text=f"{a.ripple_rms * 1e3:.2f} mV{f}")
        s["Noise"].configure(text=f"{a.noise * 1e3:.3f} mV")
        s["Drift"].configure(text=f"{a.drift * 1e3:+.3f} mV/s")
        lines = []
        if a.soc_note:
            lines.append(f"Charge: {a.soc_note}")
        lines += [f"• {e}" for e in a.evidence]
        lines += [f"⚠ {n}" for n in a.notes]
        self.lbl_details.configure(text="\n".join(lines))
        self._draw(m)

    def _draw(self, m: Measurement | None):
        ax, aw = self.ax_dc, self.ax_wave
        ax.clear()
        aw.clear()
        ax.set_title("DC readings", fontsize=10)
        ax.set_xlabel("Time (s)")
        ax.set_ylabel("Voltage (V)")
        ax.ticklabel_format(axis="y", useOffset=False)
        aw.set_title("Ripple (AC part of waveform)", fontsize=10)
        aw.set_xlabel("Time (ms)")
        aw.set_ylabel("Ripple (mV)")
        for a in (ax, aw):
            a.grid(True, alpha=0.3)
        if m is not None:
            ax.plot(m.times, m.volts, "o-", ms=4, lw=1, color="#1a73e8")
            lo, hi = m.volts.min(), m.volts.max()
            pad = max((hi - lo) * 0.2, 0.0002)
            ax.set_ylim(lo - pad, hi + pad)
            # Prefer the high-rate capture; older results only have the 10 kS/s one.
            wave, rate = ((m.scope, m.scope_rate) if m.scope is not None and m.scope_rate
                          else (m.wave, m.wave_rate))
            if wave is not None and rate:
                n = min(len(wave), int(WAVE_WINDOW_S * rate))
                w = (wave[:n] - wave[:n].mean()) * 1e3
                t = np.arange(n) / rate * 1e3
                k = int(SMOOTH_S * rate)
                if k >= 3:
                    # At high rates the DMM's resolution drops to ~1 mV steps; draw the raw
                    # trace faintly and a short moving average over it to show the shape.
                    aw.plot(t, w, lw=0.3, color="#e37400", alpha=0.35, label=f"raw {_rate_text(rate)}")
                    sm = np.convolve(w, np.ones(k) / k, mode="valid")
                    aw.plot(t[k // 2:k // 2 + len(sm)], sm, lw=1.2, color="#b06000",
                            label=f"{SMOOTH_S * 1e6:.0f} µs average")
                    aw.legend(loc="upper right", fontsize=8)
                else:
                    aw.plot(t, w, lw=0.8, color="#e37400")
                aw.set_title(f"Ripple (AC part of waveform, {_rate_text(rate)})", fontsize=10)
            else:
                aw.text(0.5, 0.5, "Not measured (no voltage)", ha="center", va="center",
                        transform=aw.transAxes, color=IDLE_COLOR)
        self.canvas.draw()

    def _clear(self):
        self.history.clear()
        self.tree.delete(*self.tree.get_children())

    def _export(self):
        if not self.history:
            messagebox.showinfo("Export CSV", "There are no results to export yet.", parent=self)
            return
        path = filedialog.asksaveasfilename(parent=self, defaultextension=".csv",
                                            filetypes=[("CSV files", "*.csv")],
                                            initialfile="battery_results.csv")
        if path:
            write_csv(path, [(stamp, a) for stamp, a, _ in self.history])
            self.v_status.set(f"Exported {len(self.history)} results to {path}")

    def _on_close(self):
        self.worker.quit()
        self.worker.join(timeout=15)  # lets a running test finish and the DMM session close
        self.destroy()


def main():
    try:
        import ctypes
        ctypes.windll.shcore.SetProcessDpiAwareness(1)
    except Exception:
        pass
    BatteryGui().mainloop()


if __name__ == "__main__":
    main()
