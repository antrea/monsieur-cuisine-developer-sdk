"""Native local-file backup panel; bounded worker messages never touch Tk."""
import json
from pathlib import Path
import queue
import threading


class BackupPanel:
    def __init__(self, parent):
        import tkinter as tk
        from tkinter import ttk
        notebook = ttk.Notebook(parent)
        notebook.pack(fill="both", expand=True)
        files = ttk.Frame(notebook, padding=4)
        tools = ttk.Frame(notebook, padding=4)
        notebook.add(files, text="Private backup files")
        notebook.add(tools, text="Original external tool")
        self.tool_panel = ExternalToolPanel(tools)
        parent = files
        self.parent, self.tk = parent, tk
        self.folder = tk.StringVar(master=parent)
        self.second = tk.StringVar(master=parent)
        self.destination = tk.StringVar(master=parent)
        self.boot1 = tk.StringVar(master=parent)
        self.boot2 = tk.StringVar(master=parent)
        self.read_only_roots = ()
        self.status = tk.StringVar(master=parent, value="Select a local session. No hardware access.")
        self.messages = queue.Queue(maxsize=64)
        self.cancelled = threading.Event()
        self.busy = self.closed = False
        self.last_result = None
        ttk.Label(parent, text="Backup Manager: private local files", font=("TkDefaultFont", 14, "bold")).pack(anchor="w")
        ttk.Label(parent, text="Verify, compare or copy files into a NEW private folder. Stage reconstructs a missing full image for the original verifier. No device access.",
                  wraplength=800).pack(anchor="w", pady=6)
        row = ttk.Frame(parent); row.pack(fill="x")
        ttk.Entry(row, textvariable=self.folder).pack(side="left", fill="x", expand=True)
        ttk.Button(row, text="Choose session", command=self.choose).pack(side="left", padx=5)
        ttk.Button(row, text="ZIP / raw file", command=self.choose_file).pack(side="left", padx=5)
        for label, variable in (("Second session (Compare)", self.second),
                                ("New output folder (Import / Stage)", self.destination),
                                ("Boot1 / Boot2 (raw import only)", self.boot1)):
            row = ttk.Frame(parent); row.pack(fill="x", pady=2)
            ttk.Label(row, text=label, width=34).pack(side="left")
            ttk.Entry(row, textvariable=variable).pack(side="left", fill="x", expand=True)
            if variable is self.boot1:
                ttk.Entry(row, textvariable=self.boot2).pack(side="left", fill="x", expand=True)
        row = ttk.Frame(parent); row.pack(fill="x", pady=8)
        self.buttons = []
        for label, command in (("Verify", lambda: self.start("verify")),
                               ("Inventory", lambda: self.start("inventory")),
                               ("Compare", lambda: self.start("compare")),
                               ("Import", lambda: self.start("import")),
                               ("Stage full session", lambda: self.start("stage")),
                               ("Export report", self.export),
                               ("Discard output", self.discard)):
            button = ttk.Button(row, text=label, command=command); button.pack(side="left", padx=3)
            self.buttons.append(button)
        ttk.Button(row, text="Cancel", command=self.cancelled.set).pack(side="left", padx=3)
        self.progress = ttk.Progressbar(parent, mode="indeterminate"); self.progress.pack(fill="x")
        ttk.Label(parent, textvariable=self.status, wraplength=900).pack(anchor="w", pady=5)
        self.output = tk.Text(parent, height=8, wrap="word", state="disabled")
        self.output.pack(fill="both", expand=True)
        self.after = parent.after(50, self.poll)

    def choose(self):
        from tkinter import filedialog
        selected = filedialog.askdirectory(title="Select existing backup_session", parent=self.parent)
        if selected:
            self.folder.set(selected)

    def choose_file(self):
        from tkinter import filedialog
        selected = filedialog.askopenfilename(title="Select private backup ZIP or raw user-area image", parent=self.parent)
        if selected:
            self.folder.set(selected)

    def start(self, operation):
        if self.busy or self.closed:
            return
        if operation not in ("verify", "inventory", "compare", "import", "stage"):
            raise ValueError("unknown backup operation")
        folder = self.folder.get()
        if not folder:
            self.status.set("Choose an existing local session first."); return
        second, destination = self.second.get(), self.destination.get()
        boot1, boot2 = self.boot1.get() or None, self.boot2.get() or None
        if operation == "compare" and not second:
            self.status.set("Choose a second session to compare."); return
        if operation in ("import", "stage") and not destination:
            self.status.set("Choose a NEW private output folder."); return
        self.read_only_roots = tuple(Path(value).resolve() for value in (folder, second)
                                     if value and Path(value).is_dir())
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
                shared = {"progress": progress, "cancelled": event.is_set}
                if operation in ("verify", "inventory"):
                    report = verify_session(folder, **shared) if operation == "verify" else inventory_session(folder, **shared)
                    result = report.to_dict()
                elif operation == "compare":
                    from .compare import compare_sessions
                    result = compare_sessions(folder, second, **shared)
                elif operation == "stage":
                    from .importer import copy_session
                    result = copy_session(folder, destination, materialize=True, **shared)
                else:
                    from .importer import import_backup
                    result = import_backup(folder, destination, boot1=boot1, boot2=boot2, **shared)
                notify("done", result)
            except Exception:
                notify("error", "Cancelled or invalid backup input/output. Source files were not modified; partial imports retain their incomplete status.")
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
            if any(destination.is_relative_to(root) for root in self.read_only_roots):
                raise ValueError("source folder is read-only")
            with destination.open("x", encoding="utf-8") as handle:
                json.dump(self.last_result, handle, indent=2)
            self.status.set("Report exported.")
        except (ValueError, OSError):
            self.status.set("Export rejected: choose a new file outside the backup session.")

    def discard(self, *, confirm=None):
        """Delete the SDK-created output folder named in the output field after an explicit confirmation."""
        if self.busy or self.closed:
            return
        from .cleanup import describe_output, discard_output
        destination = self.destination.get()
        if not destination:
            self.status.set("Name the SDK output folder to discard in the output field."); return
        try:
            info = describe_output(destination)
        except (ValueError, OSError):
            self.status.set("Not an SDK import/stage/recovery output: nothing deleted."); return
        if info["complete"]:
            self.status.set("This output is complete; delete it with the CLI --include-complete option if intended."); return
        if confirm is None:
            from tkinter import messagebox
            confirm = messagebox.askyesno("Discard output", f"Delete the {info['status']} {info['kind']} output folder? "
                                          "Source sessions are not touched.", parent=self.parent)
        if not confirm:
            self.status.set("Discard cancelled."); return
        try:
            self.last_result = discard_output(destination)
            self.status.set("Output discarded. Source files were not modified.")
        except (ValueError, OSError, InterruptedError):
            self.last_result = None
            self.status.set("Discard refused or interrupted; remaining files were kept.")
            return
        self.output.configure(state="normal"); self.output.delete("1.0", "end")
        self.output.insert("end", json.dumps(self.last_result, indent=2)); self.output.configure(state="disabled")

    def close(self):
        self.closed = True; self.cancelled.set()
        self.tool_panel.close()
        self.parent.after_cancel(self.after)


from ..workbench import JobPanel, choose_file


class ExternalToolPanel(JobPanel):
    """Explicit known-release provisioning and original file-only verification."""
    def __init__(self, parent):
        import sys
        super().__init__(parent, "Original MCC Backup: file verifier", "Uses an owner-supplied pinned ZIP, never bundled GPL binaries. Provision creates a new folder; verification launches the original file-only script explicitly. No USB connection or driver installation.")
        self.archive = self.field(0, "Original tool ZIP", choose=choose_file)
        self.installation = self.field(1, "Tool source installation / new provision folder")
        self.session = self.field(2, "Staged session (must contain full image)")
        self.reports = self.field(3, "NEW private report directory")
        self.python = self.field(4, "Python interpreter", sys.executable, choose=choose_file)
        for label, operation in (("Inspect ZIP", "inspect"), ("Provision source", "provision"),
                                 ("Verify installation", "installation"), ("Run original file verifier", "verify")):
            self.button(label, lambda kind=operation: self.run(kind))
        self.ttk.Button(self.actions, text="Cancel", command=self.cancelled.set).pack(side="left", padx=2)

    def run(self, operation):
        from .runtime import MCCBackupRuntime
        selected = {"archive": self.archive.get(), "installation": self.installation.get(),
                    "session": self.session.get(), "reports": self.reports.get(), "python": self.python.get()}
        event = self.cancelled
        def job():
            tool = MCCBackupRuntime(selected["archive"])
            if operation == "inspect":
                return tool.inspect()
            if operation == "provision":
                return tool.provision(selected["installation"], kind="source", cancelled=event.is_set, progress=self.progress)
            if operation == "installation":
                return tool.verify_installation(selected["installation"], kind="source", cancelled=event.is_set)
            return tool.offline_verify(selected["installation"], selected["session"], selected["reports"],
                                       python=selected["python"], cancelled=event.is_set, progress=self.progress)
        self.start_job(job)
