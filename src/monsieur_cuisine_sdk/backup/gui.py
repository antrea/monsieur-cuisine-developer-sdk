"""Native local-file backup panel; bounded worker messages never touch Tk."""
import json
from pathlib import Path
import queue
import threading


class BackupPanel:
    def __init__(self, parent):
        import tkinter as tk
        from tkinter import ttk
        self.parent, self.tk = parent, tk
        self.folder = tk.StringVar(master=parent)
        self.status = tk.StringVar(master=parent, value="Select a local session. No hardware access.")
        self.messages = queue.Queue(maxsize=64)
        self.cancelled = threading.Event()
        self.busy = self.closed = False
        self.last_result = None
        ttk.Label(parent, text="Read-only Backup Manager", font=("TkDefaultFont", 14, "bold")).pack(anchor="w")
        ttk.Label(parent, text="Verify images or inventory system metadata. Personal userdata files are never browsed.",
                  wraplength=800).pack(anchor="w", pady=6)
        row = ttk.Frame(parent); row.pack(fill="x")
        ttk.Entry(row, textvariable=self.folder).pack(side="left", fill="x", expand=True)
        ttk.Button(row, text="Choose session", command=self.choose).pack(side="left", padx=5)
        row = ttk.Frame(parent); row.pack(fill="x", pady=8)
        self.buttons = []
        for label, command in (("Verify", lambda: self.start("verify")),
                               ("Inventory", lambda: self.start("inventory")),
                               ("Export report", self.export)):
            button = ttk.Button(row, text=label, command=command); button.pack(side="left", padx=3)
            self.buttons.append(button)
        ttk.Button(row, text="Cancel", command=self.cancelled.set).pack(side="left", padx=3)
        self.progress = ttk.Progressbar(parent, mode="indeterminate"); self.progress.pack(fill="x")
        ttk.Label(parent, textvariable=self.status, wraplength=900).pack(anchor="w", pady=5)
        self.output = tk.Text(parent, height=12, wrap="word", state="disabled")
        self.output.pack(fill="both", expand=True)
        self.after = parent.after(50, self.poll)

    def choose(self):
        from tkinter import filedialog
        selected = filedialog.askdirectory(title="Select existing backup_session", parent=self.parent)
        if selected:
            self.folder.set(selected)

    def start(self, operation):
        if self.busy:
            return
        if operation not in ("verify", "inventory"):
            raise ValueError("unknown backup operation")
        folder = self.folder.get()
        if not folder:
            self.status.set("Choose an existing local session first."); return
        self.busy = True; self.last_result = None
        self.cancelled = threading.Event()
        event, inbox = self.cancelled, self.messages
        for button in self.buttons:
            button.configure(state="disabled")
        self.progress.start(80)
        self.status.set("Reading local backup files; the source is never modified.")

        def notify(kind, value):
            try:
                inbox.put_nowait((kind, value))
            except queue.Full:
                if kind != "progress":
                    # A terminal result must not be lost behind progress updates.
                    while True:
                        try: inbox.get_nowait()
                        except queue.Empty: break
                    inbox.put_nowait((kind, value))

        def worker():
            from .inventory import inventory_session
            from .verify import verify_session
            try:
                progress = lambda text: notify("progress", text)
                report = (verify_session(folder, progress=progress, cancelled=event.is_set)
                          if operation == "verify" else
                          inventory_session(folder, progress=progress, cancelled=event.is_set))
                notify("done", report.to_dict())
            except Exception:
                notify("error", "Cancelled or invalid backup input; source files were not modified.")
        threading.Thread(target=worker, daemon=True, name="backup-local-reader").start()

    def poll(self):
        if self.closed:
            return
        while True:
            try: kind, value = self.messages.get_nowait()
            except queue.Empty: break
            if kind == "progress":
                self.status.set(value)
            else:
                self.busy = False; self.progress.stop()
                for button in self.buttons: button.configure(state="normal")
                self.last_result = value if kind == "done" else None
                self.status.set("Completed. Integrity and completeness do not prove restorability."
                                if kind == "done" else value)
                self.output.configure(state="normal"); self.output.delete("1.0", "end")
                self.output.insert("end", json.dumps(value, indent=2)); self.output.configure(state="disabled")
        self.after = self.parent.after(50, self.poll)

    def export(self):
        if self.last_result is None:
            self.status.set("Run verification or inventory before exporting."); return
        from tkinter import filedialog
        selected = filedialog.asksaveasfilename(parent=self.parent, title="Export a new backup report",
                                              defaultextension=".json")
        if not selected:
            return
        try:
            destination = Path(selected).resolve()
            if destination.is_relative_to(Path(self.folder.get()).resolve()):
                raise ValueError("source folder is read-only")
            with destination.open("x", encoding="utf-8") as handle:
                json.dump(self.last_result, handle, indent=2)
            self.status.set("Report exported.")
        except (ValueError, OSError):
            self.status.set("Export rejected: choose a new file outside the backup session.")

    def close(self):
        self.closed = True; self.cancelled.set()
        self.parent.after_cancel(self.after)
