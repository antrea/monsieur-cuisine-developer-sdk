"""One native, resizable Tk application for both explicit device profiles."""
from __future__ import annotations
from collections import deque
import json
import math
from pathlib import Path
import queue
import threading
import time

from .api import DeviceModel, DigitalTwin, replay
from .scenarios import SCENARIOS, run_scenario

MODELS = {"Monsieur Cuisine Connect (MCC)": DeviceModel.MCC,
          "Monsieur Cuisine Smart (MCS)": DeviceModel.MCS}


class DesktopApp:
    def __init__(self, root, twin=None, *, model=DeviceModel.MCC):
        import tkinter as tk
        from tkinter import ttk
        self.tk, self.ttk, self.root = tk, ttk, root
        # An interactive clock records every poll; a full recording is truncated
        # instead of stopping the motor after a few minutes.
        self.twin = twin or DigitalTwin(model, on_recording_full="continue")
        self._truncation_reported = False
        self._sensor_baseline = {}
        self.connection = None
        self.closed = False
        self.running = True
        self._after = None
        self._previous = time.monotonic()
        self._angle = 0.0
        self._job = 0
        self._cancel = threading.Event()
        self._results = queue.Queue(maxsize=8)
        self._connection_error = ""
        self._last_connection = {}
        self._console_generation = None
        self._console_size = 0
        self._tab_frames = {}
        root.title("Monsieur Cuisine Digital Twin — BlackStuff Labs")
        # Fit small/scaled work areas (e.g. 1280x720 logical at 150 %).
        width = min(1220, root.winfo_screenwidth() - 40)
        height = min(840, root.winfo_screenheight() - 80)
        root.geometry(f"{width}x{height}"); root.minsize(min(1000, width), min(720, height))
        root.configure(background="#edf2f7")
        root.protocol("WM_DELETE_WINDOW", self.close)
        style = ttk.Style(root)
        if "clam" in style.theme_names():
            style.theme_use("clam")
        style.configure("TFrame", background="#edf2f7")
        style.configure("TLabel", background="#edf2f7", foreground="#172b46", font=("TkDefaultFont", 10))
        style.configure("Title.TLabel", font=("TkDefaultFont", 21, "bold"))
        style.configure("Muted.TLabel", foreground="#52657d")
        style.configure("Value.TLabel", font=("TkDefaultFont", 18, "bold"), foreground="#087e8b")
        style.configure("TButton", padding=(10, 6))
        style.configure("Stop.TButton", foreground="#a32635", font=("TkDefaultFont", 10, "bold"))
        style.configure("TNotebook.Tab", padding=(9, 6))
        shell = ttk.Frame(root, padding=18); shell.pack(fill="both", expand=True)
        header = ttk.Frame(shell); header.pack(fill="x")
        ttk.Label(header, text="Monsieur Cuisine Digital Twin", style="Title.TLabel").pack(side="left")
        ttk.Label(header, text="BLACKSTUFF LABS  /  OFFLINE DEVELOPMENT", style="Muted.TLabel").pack(side="right")
        selector = ttk.Frame(shell); selector.pack(fill="x", pady=(12, 10))
        ttk.Label(selector, text="Device Model:").pack(side="left")
        self.model_var = tk.StringVar(value=next(k for k,v in MODELS.items() if v==self.twin.model))
        self.model_selector = ttk.Combobox(selector, textvariable=self.model_var, values=list(MODELS), state="readonly", width=36)
        self.model_selector.pack(side="left", padx=10)
        self.model_selector.bind("<<ComboboxSelected>>", self.change_model)
        self.format_var = tk.StringVar()
        ttk.Label(selector, textvariable=self.format_var, style="Muted.TLabel").pack(side="left", padx=10)
        self.owner_var = tk.StringVar(value="Owner: local")
        ttk.Label(selector, textvariable=self.owner_var).pack(side="right")
        control = ttk.Frame(shell); control.pack(fill="x", pady=(0, 10))
        self.speed = tk.StringVar(value="2"); self.direction = tk.StringVar(value="cw")
        self.temperature = tk.StringVar(value="0"); self.step_seconds = tk.StringVar(value="0.1")
        for title, variable, values, width in (("Speed",self.speed,list(range(11)),5),
            ("Direction",self.direction,["ccw","cw"],7), ("Heat °C",self.temperature,[],6)):
            ttk.Label(control,text=title).pack(side="left",padx=(0,4))
            combo=ttk.Combobox(control,textvariable=variable,values=values,width=width,state="readonly")
            combo.pack(side="left",padx=(0,12))
            if title=="Heat °C":self.heat_combo=combo
        self.start_button=ttk.Button(control,text="START / Apply",command=lambda:self.action(self.start_motor,sends=True))
        self.start_button.pack(side="left",padx=(0,6))
        ttk.Button(control,text="STOP",style="Stop.TButton",command=lambda:self.action(self.stop_motor,sends=True)).pack(side="left",padx=6)
        self.pause_button=ttk.Button(control,text="Pause",command=self.toggle_clock);self.pause_button.pack(side="left",padx=6)
        ttk.Entry(control,textvariable=self.step_seconds,width=6).pack(side="left",padx=(8,4))
        ttk.Button(control,text="Step seconds",command=lambda:self.action(lambda:self.twin.advance(float(self.step_seconds.get())))).pack(side="left")
        # Packed before the notebook so the only feedback line is never clipped.
        self.message=tk.StringVar(value="Synthetic physics. No appliance connected. Default startup opens no listener.")
        ttk.Label(shell,textvariable=self.message,style="Muted.TLabel",wraplength=1140).pack(side="bottom",fill="x",pady=(10,0))
        self.notebook=ttk.Notebook(shell);self.notebook.pack(fill="both",expand=True)
        names=("Dashboard","Motor","Temperature","Scale & Sensors","Errors","Protocol Monitor","Scenarios","Timeline","Android Connection","Settings","Protocol Information","Backup")
        for name in names:
            frame=ttk.Frame(self.notebook,padding=14);self.notebook.add(frame,text=name);self._tab_frames[name]=frame
        self.values={key:tk.StringVar() for key in ("speed","temperature","weight","lid","error","firmware","clock","direction")}
        self._dashboard();self._motor();self._temperature();self._sensors();self._faults()
        self._protocol();self._scenarios();self._timeline();self._android();self._settings();self._information()
        from .backup.gui import BackupPanel
        self.backup_panel=BackupPanel(self._tab_frames["Backup"])
        self._load_profile_controls();self.refresh();self._after=root.after(50,self.poll)

    def _card(self,parent,label,key):
        box=self.ttk.LabelFrame(parent,text=label,padding=12);box.pack(side="left",fill="both",expand=True,padx=5)
        self.ttk.Label(box,textvariable=self.values[key],style="Value.TLabel").pack(anchor="w")

    def _dashboard(self):
        f=self._tab_frames["Dashboard"]
        row=self.ttk.Frame(f);row.pack(fill="x")
        for title,key in (("Observed / target speed","speed"),("Temperature","temperature"),("Scale","weight"),("Lid / NTC","lid")):
            self._card(row,title,key)
        visuals=self.ttk.Frame(f);visuals.pack(fill="both",expand=True,pady=12)
        self.blades=self.tk.Canvas(visuals,width=280,height=280,background="#172b46",highlightthickness=0)
        self.blades.pack(side="left",fill="both",expand=True,padx=(0,12))
        self.chart=self.tk.Canvas(visuals,width=580,height=280,background="#ffffff",highlightthickness=0)
        self.chart.pack(side="left",fill="both",expand=True)
        row=self.ttk.Frame(f);row.pack(fill="x")
        for title,key in (("Direction","direction"),("Board error","error"),("Firmware (simulated)","firmware"),("Virtual clock","clock")):
            self._card(row,title,key)
        self.ttk.Label(f,text="One model instance drives the controls, animation, charts, original binary telemetry and optional Android session.",style="Muted.TLabel").pack(anchor="w",pady=(12,0))

    def _motor(self):
        f=self._tab_frames["Motor"]
        self.ttk.Label(f,text="Motor control",style="Title.TLabel").pack(anchor="w")
        self.ttk.Label(f,textvariable=self.values["speed"],style="Value.TLabel").pack(anchor="w",pady=15)
        self.ttk.Label(f,text="Use the common START/STOP controls above. Speed is a profile-specific UI level. MCC telemetry carries RPM; MCS carries a raw motor level. These values do not establish physical equivalence.",wraplength=950).pack(anchor="w")
        self.ttk.Label(f,text="Reversal and braking are synthetic model policies. STOP is a request; measured motion takes virtual time to decay.",wraplength=950).pack(anchor="w",pady=15)

    def _temperature(self):
        f=self._tab_frames["Temperature"]
        self.ttk.Label(f,text="Thermal model",style="Title.TLabel").pack(anchor="w")
        self.ttk.Label(f,textvariable=self.values["temperature"],style="Value.TLabel").pack(anchor="w",pady=15)
        self.ttk.Label(f,text="The Heat selector lists exact targets supported by the selected protocol. Heating/cooling coefficients are configurable synthetic assumptions; no real thermal mass, load or safety cutoff has been calibrated.",wraplength=950).pack(anchor="w")

    def _sensors(self):
        f=self._tab_frames["Scale & Sensors"]
        self.sensor_vars={"weight":self.tk.StringVar(value="0"),"temperature":self.tk.StringVar(value="25"),
                          "firmware":self.tk.StringVar(value="1"),"lid_open":self.tk.BooleanVar(value=False),
                          "ntc_present":self.tk.BooleanVar(value=True)}
        for index,key in enumerate(("weight","temperature","firmware")):
            self.ttk.Label(f,text={"weight":"Weight g","temperature":"Injected temperature °C","firmware":"Simulated firmware number"}[key]).grid(row=index,column=0,sticky="w",pady=8)
            self.ttk.Entry(f,textvariable=self.sensor_vars[key],width=15).grid(row=index,column=1,padx=12)
        for index,key in enumerate(("lid_open","ntc_present"),3):
            self.ttk.Checkbutton(f,text=key.replace("_"," "),variable=self.sensor_vars[key]).grid(row=index,column=0,columnspan=2,sticky="w",pady=8)
        self.ttk.Button(f,text="Inject sensor state",command=lambda:self.action(self.inject_sensors)).grid(row=5,column=0,pady=14,sticky="w")
        self.tare_button=self.ttk.Button(f,text="Tare",command=lambda:self.action(self.tare,sends=True));self.tare_button.grid(row=5,column=1,padx=12)
        self.ttk.Label(f,text="Sensor and fault controls remain available while Android owns motor commands.",style="Muted.TLabel").grid(row=6,column=0,columnspan=3,pady=15,sticky="w")

    def _faults(self):
        f=self._tab_frames["Errors"]
        self.error_var=self.tk.StringVar(value="0")
        self.ttk.Label(f,text="Injected board error code").grid(row=0,column=0,sticky="w",pady=10)
        self.ttk.Entry(f,textvariable=self.error_var,width=12).grid(row=0,column=1,padx=12)
        self.ttk.Button(f,text="Apply error",command=lambda:self.action(lambda:self.twin.set_sensors(error_code=int(self.error_var.get())))).grid(row=0,column=2)
        self.fault_vars={"delay_seconds":self.tk.StringVar(value="0"),"drop_next":self.tk.StringVar(value="0"),"corrupt_next":self.tk.StringVar(value="0"),"disconnected":self.tk.BooleanVar(value=False)}
        for row,key in enumerate(("delay_seconds","drop_next","corrupt_next"),2):
            self.ttk.Label(f,text=key.replace("_"," ")).grid(row=row,column=0,sticky="w",pady=10)
            self.ttk.Entry(f,textvariable=self.fault_vars[key],width=12).grid(row=row,column=1,padx=12)
        self.ttk.Checkbutton(f,text="Simulated link disconnected",variable=self.fault_vars["disconnected"]).grid(row=5,column=0,columnspan=2,sticky="w",pady=10)
        self.ttk.Button(f,text="Apply response faults",command=lambda:self.action(self.inject_faults)).grid(row=6,column=0,pady=12)
        self.ttk.Label(f,text="Faults affect the development model only. No unknown firmware guarantee or wire fault opcode is added.",wraplength=850,style="Muted.TLabel").grid(row=7,column=0,columnspan=4,pady=15,sticky="w")

    def _text(self,parent,height=12):
        frame=self.ttk.Frame(parent);frame.pack(fill="both",expand=True,pady=8)
        text=self.tk.Text(frame,height=height,wrap="none",font=("TkFixedFont",10),background="#ffffff",foreground="#172b46")
        sy=self.ttk.Scrollbar(frame,orient="vertical",command=text.yview)
        sx=self.ttk.Scrollbar(frame,orient="horizontal",command=text.xview)
        text.configure(yscrollcommand=sy.set,xscrollcommand=sx.set)
        text.grid(row=0,column=0,sticky="nsew");sy.grid(row=0,column=1,sticky="ns");sx.grid(row=1,column=0,sticky="ew")
        frame.rowconfigure(0,weight=1);frame.columnconfigure(0,weight=1)
        return text

    def _protocol(self):
        f=self._tab_frames["Protocol Monitor"]
        self.ttk.Label(f,text="Original binary TX / RX — no ACK wrapper, JSON or HTTP",style="Muted.TLabel").pack(anchor="w")
        self.hex_var=self.tk.StringVar()
        row=self.ttk.Frame(f);row.pack(fill="x",pady=8)
        self.ttk.Entry(row,textvariable=self.hex_var).pack(side="left",fill="x",expand=True,padx=(0,8))
        self.hex_button=self.ttk.Button(row,text="Send HEX",command=lambda:self.action(lambda:self.twin.feed(bytes.fromhex(self.hex_var.get())),sends=True));self.hex_button.pack(side="right")
        self.console=self._text(f)

    def _scenarios(self):
        f=self._tab_frames["Scenarios"]
        row=self.ttk.Frame(f);row.pack(fill="x")
        self.scenario=self.tk.StringVar(value="intermittent")
        self.ttk.Combobox(row,textvariable=self.scenario,values=SCENARIOS,state="readonly",width=24).pack(side="left")
        self.ttk.Button(row,text="Run bounded experiment",command=self.run_scenario).pack(side="left",padx=10)
        self.ttk.Button(row,text="Cancel",command=self.cancel_job).pack(side="left")
        self.ttk.Button(row,text="Verify current replay",command=self.verify_replay).pack(side="left",padx=10)
        self.ttk.Button(row,text="Verify saved replay",command=self.open_replay).pack(side="left")
        self.scenario_output=self._text(f)
        self.ttk.Label(f,text="Experiments run on a separate deterministic instance. A model switch invalidates and cancels old results.",style="Muted.TLabel").pack(anchor="w")

    def _timeline(self):
        self.timeline_text=self._text(self._tab_frames["Timeline"])

    def _android(self):
        f=self._tab_frames["Android Connection"]
        self.ttk.Label(f,text="Direct Android → virtual PowerBoard",style="Title.TLabel").pack(anchor="w")
        row=self.ttk.Frame(f);row.pack(fill="x",pady=15)
        self.host=self.tk.StringVar(value="127.0.0.1");self.port=self.tk.StringVar()
        self.ttk.Label(row,text="Loopback host").pack(side="left")
        self.host_entry=self.ttk.Entry(row,textvariable=self.host,width=17);self.host_entry.pack(side="left",padx=8)
        self.ttk.Label(row,text="Port").pack(side="left")
        self.port_entry=self.ttk.Entry(row,textvariable=self.port,width=8);self.port_entry.pack(side="left",padx=8)
        self.connection_button=self.ttk.Button(row,text="Enable Android Connection",command=lambda:self.action(self.toggle_connection));self.connection_button.pack(side="left",padx=8)
        self.connection_values={key:self.tk.StringVar() for key in ("status","model","address","clients","owner","tx_frames","rx_frames","last_command","last_error","last_disconnect")}
        grid=self.ttk.Frame(f);grid.pack(fill="x")
        for row,(key,var) in enumerate(self.connection_values.items()):
            self.ttk.Label(grid,text=key.replace("_"," ").title(),width=20).grid(row=row,column=0,sticky="w",pady=5)
            self.ttk.Label(grid,textvariable=var,wraplength=820).grid(row=row,column=1,sticky="w",pady=5)
        self.ttk.Label(f,text="Android Studio emulator: 10.0.2.2:<port>. Select the same model in the Android demo. One client owns commands; GUI sensors/faults stay available. Disconnect requests synthetic STOP; switching model closes the listener and starts a fresh isolated board.",wraplength=1040,style="Muted.TLabel").pack(anchor="w",pady=18)

    def _settings(self):
        f=self._tab_frames["Settings"]
        row=self.ttk.Frame(f);row.pack(fill="x")
        self.ttk.Button(row,text="Save recording",command=self.save_recording).pack(side="left")
        self.ttk.Button(row,text="New session",command=lambda:self.action(self.new_session)).pack(side="left",padx=10)
        self.ttk.Button(row,text="Apply physics as fresh session",command=lambda:self.action(self.apply_parameters)).pack(side="left")
        self.ttk.Label(f,text="JSON physics parameters belong to the selected profile. Applying them explicitly resets the model and closes Android Connection. All coefficients are synthetic.",wraplength=1000,style="Muted.TLabel").pack(anchor="w",pady=12)
        self.parameters=self._text(f)

    def _information(self):
        f=self._tab_frames["Protocol Information"]
        self.ttk.Label(f,text="Capabilities, units and evidence",style="Title.TLabel").pack(anchor="w")
        self.info=self._text(f)

    @staticmethod
    def _replace_text(widget,text,*,preserve_view=False):
        if preserve_view:
            # Live views: skip unchanged text, never clear an active selection,
            # keep the reader's position and follow the tail when at the bottom.
            if getattr(widget,"_rendered",None)==text or widget.tag_ranges("sel"):return
            first,last=widget.yview()
            if widget.winfo_ismapped():widget._follow=last>=.999  # hidden tabs keep their mode
            follow=getattr(widget,"_follow",True)
            if not follow and getattr(widget,"_rendered",None) is not None:return  # paused while reading
        widget.delete("1.0","end");widget.insert("1.0",text)
        if preserve_view:
            widget._rendered=text
            if follow:widget.see("end")

    def _load_profile_controls(self):
        temperatures = ([0,37,45,50,55,60,65,70,75,80,85,90,95,100,105,110,115,120,125,130]
                        if self.twin.model==DeviceModel.MCC else [0,37,40,45,50,55,60,65,70,75,80,85,90,95,100,105,110,115,120,125,130])
        self.heat_combo.configure(values=temperatures);self.temperature.set("0")
        state=self.twin.get_state()
        for key,value in (("weight",str(round(state.weight))),("temperature",str(round(state.temperature))),
                          ("firmware",str(state.firmware)),("lid_open",state.lid_open),("ntc_present",state.ntc_present)):
            self.sensor_vars[key].set(value)
        self._sensor_baseline={key:var.get() for key,var in self.sensor_vars.items()}
        self._truncation_reported=False
        self.port.set("8765" if self.twin.model==DeviceModel.MCC else "8766")
        self.format_var.set("MCC build292 · TX15 / RX27 · synthetic RPM" if self.twin.model==DeviceModel.MCC else "MCS 1.2.14.15 · TX39 / RX48 · raw level, RPM unknown")
        self._replace_text(self.parameters,json.dumps(self.twin.profile.parameters,indent=2))
        self._replace_text(self.info,json.dumps(self.twin.capabilities,indent=2))
        self._console_generation=None

    def action(self, callback, *, sends=False):
        twin,stream=self.twin,self.twin.stream
        generation,discarded,refused,accepted=twin.generation,stream.rejected,twin.rejected_commands,twin.command_count
        try:
            result=callback()
            # Report framing/profile refusals instead of claiming success.
            same=self.twin is twin and twin.generation==generation and twin.stream is stream
            if same and twin.rejected_commands>refused:
                reason=next((e.get("reason","") for e in reversed(twin.timeline) if e.get("event")=="rejected_command"),"")
                self.message.set("Command refused by the model: "+reason)
            elif same and sends and twin._faults.get("disconnected") and twin.command_count==accepted:
                self.message.set("Simulated link is disconnected: input was not delivered to the model.")
            elif same and stream.rejected>discarded:
                prefix="Some input bytes were discarded" if twin.command_count>accepted else "Input not executed"
                self.message.set(f"{prefix}: {stream.issues[-1]['reason']}. See Timeline.")
            elif same and twin.buffered_bytes and twin.command_count==accepted:
                self.message.set(f"Partial frame buffered ({twin.buffered_bytes} bytes); waiting for the rest.")
            else:
                self.message.set("Applied to the selected virtual model.")
            return result
        except (ValueError,TypeError,OSError) as exc:
            self.message.set(str(exc));return None
        finally:
            self.refresh()

    def start_motor(self):
        return self.twin.start_motor(int(self.speed.get()),self.direction.get(),int(self.temperature.get()))

    def stop_motor(self):
        if self.connection:self.connection.disconnect("desktop STOP")
        return self.twin.stop_motor()

    def tare(self):
        result=self.twin.tare()
        # The displayed weight is now zero: make a new weight entry count as an edit.
        self.sensor_vars["weight"].set("0");self._sensor_baseline["weight"]="0"
        return result

    def inject_sensors(self):
        # Inject only the fields edited since the last injection, so toggling the
        # lid does not also overwrite the evolving temperature or weight.
        changed={key for key,var in self.sensor_vars.items() if var.get()!=self._sensor_baseline.get(key)}
        if not changed:
            raise ValueError("No sensor field was edited since the last injection")
        values={key:(self.sensor_vars[key].get() if key in ("lid_open","ntc_present") else int(self.sensor_vars[key].get()))
                for key in changed}
        result=self.twin.set_sensors(**values)
        self._sensor_baseline={key:var.get() for key,var in self.sensor_vars.items()}
        return result

    def inject_faults(self):
        return self.twin.set_faults(delay_seconds=float(self.fault_vars["delay_seconds"].get()),
            drop_next=int(self.fault_vars["drop_next"].get()),corrupt_next=int(self.fault_vars["corrupt_next"].get()),
            disconnected=self.fault_vars["disconnected"].get())

    def toggle_clock(self):
        self.running=not self.running;self.pause_button.configure(text="Pause" if self.running else "Resume")

    def change_model(self,event=None):
        selected=MODELS[self.model_var.get()]
        self.cancel_job()
        self.action(lambda:self.twin.switch_model(selected))
        self.connection=None;self._last_connection={};self._connection_error=""
        self._load_profile_controls();self.refresh()

    def new_session(self):
        self.cancel_job();self.twin.new_session();self.connection=None;self._load_profile_controls()

    def apply_parameters(self):
        parameters=json.loads(self.parameters.get("1.0","end"))
        self.twin.new_session(parameters=parameters);self.connection=None;self._load_profile_controls()

    def enable_android(self, *, host=None, port=None):
        from .android_connection import AndroidConnection,ConnectionConfig
        if self.connection and self.connection.listener:
            return self.connection
        try:
            connection=AndroidConnection(self.twin,ConnectionConfig(host=host or self.host.get(),port=int(self.port.get()) if port is None else port)).start()
        except (ValueError,OSError) as exc:
            self._connection_error=str(exc);self.refresh();raise
        self.connection=connection;self._connection_error=""
        self.port.set(str(connection.address[1]));self.refresh();return connection

    def disable_android(self):
        if self.connection:
            self.connection.close();self._last_connection=self.connection.status();self.connection=None
        self._connection_error=""

    def toggle_connection(self):
        if self.connection and self.connection.listener:self.disable_android()
        else:self.enable_android()

    def cancel_job(self):
        self._cancel.set();self._job+=1

    def _run_job(self,work):
        self.cancel_job();self._cancel=threading.Event()
        token,generation,event=self._job,self.twin.generation,self._cancel
        inbox=self._results
        def worker():
            try:result=work(event.is_set)
            except Exception as exc:result={"error":str(exc)}
            if event.is_set():return
            try:inbox.put_nowait((token,generation,result))
            except queue.Full:pass
        threading.Thread(target=worker,daemon=True,name="mc-sdk-bounded-experiment").start()

    def run_scenario(self):
        model,name=self.twin.model,self.scenario.get()
        def execute(cancelled):
            result=run_scenario(model,name,cancelled=cancelled);result.pop("recording",None);return result
        self._run_job(execute)

    def verify_replay(self):
        recording=json.loads(json.dumps(self.twin.recording))
        self._run_job(lambda cancelled:{"PASS":True,"final_state":replay(recording,cancelled=cancelled).get_state().to_dict()})

    def open_replay(self):
        from tkinter import filedialog
        selected=filedialog.askopenfilename(title="Verify SDK recording",filetypes=[("JSON recordings","*.json")])
        if selected:self._run_job(lambda cancelled:{"PASS":True,"final_state":replay(Path(selected),cancelled=cancelled).get_state().to_dict()})

    def save_recording(self):
        from tkinter import filedialog
        selected=filedialog.asksaveasfilename(title="Save SDK recording",defaultextension=".json",filetypes=[("JSON recordings","*.json")])
        if selected:self.action(lambda:self.twin.save(Path(selected)))

    def refresh(self):
        if self.closed:return
        state=self.twin.get_state()
        label="RPM" if state.speed_unit=="rpm" else "raw level"
        values={"speed":f"{state.actual_speed:g} / {state.target_speed:g} {label}","temperature":f"{state.temperature:.1f} / {state.target_temperature:g} °C",
                "weight":f"{state.weight:g} g","lid":("OPEN" if state.lid_open else "Closed")+" / "+("NTC present" if state.ntc_present else "NTC absent"),
                "error":str(state.error_code),"firmware":str(state.firmware),"clock":f"{state.time:.2f} s", "direction":state.actual_direction.upper()}
        for key,value in values.items():self.values[key].set(value)
        self.owner_var.set("Owner: "+state.owner)
        for button in (self.start_button,self.tare_button,self.hex_button):button.configure(state="disabled" if state.owner=="remote" else "normal")
        if self.connection and self.connection.listener:status=self.connection.status()
        else:status={**self._last_connection,"status":"Error" if self._connection_error else "Disabled","model":state.model,"clients":0,"owner":state.owner,"last_error":self._connection_error}
        for key,var in self.connection_values.items():var.set(str(status.get(key,"—")))
        active=bool(self.connection and self.connection.listener)
        self.connection_button.configure(text="Disable Android Connection" if active else "Enable Android Connection")
        self.host_entry.configure(state="disabled" if active else "normal");self.port_entry.configure(state="disabled" if active else "normal")
        self._replace_text(self.console,"\n".join(f"{row['time']:9.3f} {row['model'].upper()} {row['direction']} {row['hex']}" for row in self.twin.frames),preserve_view=True)
        self._replace_text(self.timeline_text,"\n".join(json.dumps(event) for event in list(self.twin.timeline)[-200:])+"\n"+
            "\n".join("framing "+json.dumps(issue) for issue in list(self.twin.stream.issues)[-20:])+"\n"+
            "\n".join(f"{event['operation']} {event['input']}" for event in self.twin.recording["actions"][-60:]),preserve_view=True)
        self._draw(state)

    def _draw(self,state):
        c=self.blades;c.delete("all")
        w,h=max(c.winfo_width(),280),max(c.winfo_height(),250);cx,cy=w/2,h/2;r=min(w,h)*.30
        c.create_oval(cx-r,cy-r,cx+r,cy+r,outline="#4d6985",width=3)
        for angle in (self._angle,self._angle+math.pi/2):
            dx,dy=math.cos(angle)*r*.88,math.sin(angle)*r*.88
            c.create_line(cx-dx,cy-dy,cx+dx,cy+dy,fill="#4dd9c3",width=13,capstyle="round")
        c.create_oval(cx-12,cy-12,cx+12,cy+12,fill="#ffffff",outline="")
        c.create_text(cx,28,text=state.model.upper()+"  /  VIRTUAL POWERBOARD",fill="#ffffff",font=("TkDefaultFont",12,"bold"))
        c.create_text(cx,h-28,text=state.actual_direction.upper()+"  ·  SYNTHETIC MOTION",fill="#b9cfdf")
        c=self.chart;c.delete("all");w,h=max(c.winfo_width(),500),max(c.winfo_height(),250)
        points=list(self.twin.history);maximum=max([1]+[p[k] for p in points for k in ("actual","target")])
        left,right,top,bottom=65,w-20,40,h-40
        c.create_text(left,18,anchor="w",text="SPEED EVOLUTION  /  "+state.speed_unit,fill="#172b46",font=("TkDefaultFont",11,"bold"))
        for i in range(5):
            y=bottom-(bottom-top)*i/4;c.create_line(left,y,right,y,fill="#e0e8f0")
            c.create_text(left-8,y,anchor="e",text=f"{maximum*i/4:g}",fill="#52657d")
        if len(points)>1:
            for key,color in (("target","#eda63f"),("actual","#087e8b")):
                coords=[]
                for index,p in enumerate(points):coords.extend((left+(right-left)*index/(len(points)-1),bottom-(bottom-top)*p[key]/maximum))
                c.create_line(*coords,fill=color,width=2)
        c.create_text(left,bottom+24,anchor="w",text="virtual samples  ·  teal: observed  /  amber: target",fill="#52657d")

    def poll(self):
        if self.closed:return
        now=time.monotonic();elapsed=min(.1,max(0,now-self._previous));self._previous=now
        try:
            if self.connection:self.connection.poll()
            if self.running:
                self.twin.advance(elapsed)
                # MCC has no documented query opcode. MCS clients explicitly
                # poll0801; extra unsolicited samples would build stale status
                # behind every request and can starve fresh STOP observations.
                if self.twin.model==DeviceModel.MCC:self.twin.sample()
            if self.connection:self.connection.poll()
        except (ValueError,OSError) as exc:
            self.running=False;self.pause_button.configure(text="Resume");self.message.set(str(exc))
            if self.connection:self.disable_android()
        if self.twin.recording.get("truncated") and not self._truncation_reported:
            self._truncation_reported=True
            self.message.set("Recording capacity reached: the simulation continues unrecorded. "
                             "Save recording keeps the recorded part; New session starts a fresh recording.")
        state=self.twin.get_state()
        if state.actual_speed:
            self._angle+=(1 if state.actual_direction=="cw" else -1)*min(10,state.actual_speed)*elapsed
        while True:
            try:token,generation,result=self._results.get_nowait()
            except queue.Empty:break
            if token==self._job and generation==self.twin.generation:
                self._replace_text(self.scenario_output,json.dumps(result,indent=2))
        self.refresh();self._after=self.root.after(50,self.poll)

    def close(self):
        if self.closed:return
        self.backup_panel.close()
        self.cancel_job();self.disable_android();self.twin.disarm();self.closed=True
        if self._after:
            self.root.after_cancel(self._after);self._after=None
        self.root.destroy()


def launch(model=DeviceModel.MCC, *, smoke_test=False):
    import tkinter as tk
    root=tk.Tk();app=DesktopApp(root,model=model)
    result={}
    if smoke_test:
        def exercise():
            try:
                app.running=False;app.twin.start_motor(2);app.twin.advance(.2)
                moving=app.twin.get_state().actual_speed>0
                app.twin.stop_motor();app.twin.advance(3)
                app.twin.switch_model(DeviceModel.MCS if app.twin.model==DeviceModel.MCC else DeviceModel.MCC)
                app.refresh();result.update(PASS=moving and app.twin.get_state().requested_speed==0,model=app.twin.model.value)
            finally:app.close()
        root.after(100,exercise)
    root.mainloop();return result
