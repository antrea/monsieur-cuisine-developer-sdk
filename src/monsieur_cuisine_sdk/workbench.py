"""Native workbench panels sharing the operational SDK APIs, with bounded jobs."""
from __future__ import annotations

import json
from pathlib import Path
import queue
import threading


class JobPanel:
    """One worker job at a time. Worker callbacks never access Tk objects."""
    def __init__(self, parent, title, description):
        import tkinter as tk
        from tkinter import ttk
        self.parent, self.tk, self.ttk = parent, tk, ttk
        self.busy = self.closed = False
        self.messages = queue.Queue(maxsize=4)
        self.cancelled = threading.Event()
        self.buttons = []
        self.last_result = None
        self.status = tk.StringVar(master=parent, value="Ready; no device operation is automatic.")
        ttk.Label(parent, text=title, font=("TkDefaultFont", 14, "bold")).pack(anchor="w")
        ttk.Label(parent, text=description, wraplength=950).pack(anchor="w", pady=5)
        self.fields = ttk.Frame(parent); self.fields.pack(fill="x")
        self.actions = ttk.Frame(parent); self.actions.pack(fill="x", pady=6)
        ttk.Label(parent, textvariable=self.status, wraplength=950).pack(anchor="w")
        self.output = tk.Text(parent, height=10, wrap="word", state="disabled")
        self.output.pack(fill="both", expand=True)
        self.after = parent.after(50, self.poll)

    def field(self, row, title, default="", *, choose=None):
        variable = self.tk.StringVar(master=self.parent, value=default)
        self.ttk.Label(self.fields, text=title).grid(row=row, column=0, sticky="w", padx=3, pady=2)
        self.ttk.Entry(self.fields, textvariable=variable).grid(row=row, column=1, sticky="ew", padx=3)
        self.fields.columnconfigure(1, weight=1)
        if choose:
            self.ttk.Button(self.fields, text="Choose", command=lambda: choose(variable)).grid(row=row, column=2)
        return variable

    def button(self, title, command):
        button = self.ttk.Button(self.actions, text=title, command=command)
        button.pack(side="left", padx=2)
        self.buttons.append(button)
        return button

    def start_job(self, job):
        if self.busy or self.closed:
            return
        self.busy = True
        self.last_result = None
        self.cancelled = threading.Event()
        self.status.set("Working in background; close does not erase a pending transaction journal.")
        for button in self.buttons:
            button.configure(state="disabled")
        inbox = self.messages
        def worker():
            try:
                inbox.put(("done", job()), timeout=1)
            except Exception as error:
                inbox.put(("error", {"completed": False, "error": str(error)}), timeout=1)
        threading.Thread(target=worker, daemon=True, name="sdk-workbench").start()

    def poll(self):
        if self.closed:
            return
        try:
            kind, value = self.messages.get_nowait()
        except queue.Empty:
            pass
        else:
            self.busy = False
            self.last_result = value
            self.status.set("Completed." if kind == "done" else "Operation failed; review result and any pending journal.")
            self.output.configure(state="normal")
            self.output.delete("1.0", "end")
            self.output.insert("end", json.dumps(value, indent=2))
            self.output.configure(state="disabled")
            for button in self.buttons:
                button.configure(state="normal")
        self.after = self.parent.after(50, self.poll)

    def close(self):
        self.closed = True
        self.cancelled.set()
        self.parent.after_cancel(self.after)


def choose_file(variable):
    from tkinter import filedialog
    selected = filedialog.askopenfilename()
    if selected:
        variable.set(selected)


class ConformancePanel(JobPanel):
    def __init__(self, parent):
        super().__init__(parent, "Recorded-reference conformance", "Compares real reference bytes with the SDK, without Digital Twin physics. Dataset origin needs separate provenance.")
        self.dataset = self.field(0, "Reference JSONL", choose=choose_file)
        self.button("Compare", self.compare)

    def compare(self):
        from .conformance import compare_reference
        dataset = self.dataset.get()
        self.start_job(lambda: compare_reference(dataset))


class AppManagerPanel(JobPanel):
    def __init__(self, parent):
        super().__init__(parent, "ADB App & Launcher Manager", "Select an exact authorized target. App changes are opt-in; rollback journals contain private device metadata. API 23 persistent HOME selection uses the system chooser.")
        self.adb = self.field(0, "ADB executable", "adb", choose=choose_file)
        self.aapt = self.field(1, "aapt executable", "aapt", choose=choose_file)
        self.serial = self.field(2, "Exact ADB target")
        self.port = self.field(3, "ADB server port", "5037")
        self.apk = self.field(4, "User APK", choose=choose_file)
        self.journal = self.field(5, "Private transaction directory")
        self.component = self.field(6, "Activity / HOME component")
        self.allow_changes = self.tk.BooleanVar(master=parent, value=False)
        self.ttk.Checkbutton(self.fields, text="Enable application/configuration changes for this selected target",
                             variable=self.allow_changes).grid(row=7, column=0, columnspan=3, sticky="w")
        for title, operation in (("Discover", "devices"), ("Device / apps", "info"), ("Inspect APK", "inspect"),
                                 ("Install new app", "install"), ("Start activity", "start"),
                                 ("HOME chooser", "chooser"), ("Set HOME", "home"), ("Rollback", "rollback")):
            self.button(title, lambda value=operation: self.run(value))

    def run(self, operation):
        from .adb import AdbClient, inspect_apk, metadata_dict
        from .transactions import AppTransaction
        try:
            selected = {"adb": self.adb.get(), "aapt": self.aapt.get(), "serial": self.serial.get(),
                        "port": int(self.port.get()), "apk": self.apk.get(), "journal": self.journal.get(),
                        "component": self.component.get(), "allow": self.allow_changes.get()}
            if operation in ("install", "home", "rollback") and not selected["allow"]:
                raise PermissionError("Enable application changes explicitly before this operation")
        except (ValueError, PermissionError) as error:
            self.status.set(str(error)); return

        def job():
            if operation == "devices":
                return {"devices": AdbClient.enumerate_devices(selected["adb"], server_port=selected["port"]),
                        "note": "Copy the chosen target into Exact ADB target; no device was selected automatically"}
            if operation == "inspect":
                return metadata_dict(inspect_apk(selected["apk"], aapt=selected["aapt"]))
            client = AdbClient(selected["adb"], serial=selected["serial"], server_port=selected["port"],
                               application_changes=selected["allow"])
            if operation == "info":
                return {"device": client.diagnose(), "user_apps": client.packages(kind="user"), "homes": client.home_preferences()}
            if operation == "start":
                return client.start_activity(selected["component"])
            if operation == "chooser":
                return client.home_chooser()
            if not selected["journal"]:
                raise ValueError("Select a private transaction directory")
            transaction = AppTransaction(client, selected["journal"])
            if operation == "rollback" or transaction.directory.exists():
                transaction.load()
            else:
                transaction.begin()
            if operation == "rollback":
                return transaction.rollback()
            if operation == "home":
                transaction.home(selected["component"])
                return {"home_changed": True, "component": selected["component"]}
            metadata = inspect_apk(selected["apk"], aapt=selected["aapt"])
            return transaction.install(selected["apk"], metadata)
        self.start_job(job)


class ToolkitPanel:
    def __init__(self, parent):
        from tkinter import ttk
        self.notebook = ttk.Notebook(parent)
        self.notebook.pack(fill="both", expand=True)
        self.panels = []
        for label, panel_type in (("App & Launcher", AppManagerPanel), ("Conformance", ConformancePanel)):
            frame = ttk.Frame(self.notebook, padding=8)
            self.notebook.add(frame, text=label)
            self.panels.append(panel_type(frame))

    def close(self):
        for panel in self.panels:
            panel.close()
