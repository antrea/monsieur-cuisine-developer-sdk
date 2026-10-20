"""Real binary E2E using the common Kotlin SDK or actual Android Activity.

Android mode assumes the developer explicitly prepared/installed the demo and
test APKs on an isolated emulator. This tool never installs an APK, selects a
physical device, or guesses an adb server. Default JVM mode needs only Java.
"""
import argparse
import json
from pathlib import Path
import queue
import subprocess
import sys
import threading
import tomllib
import time

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/"src"))


def verify(model, *, mode="jvm", java="java", jar=None, adb=None,
           adb_port=None, serial=None, gui=False, screenshot=None,
           periodic_telemetry=False):
    from monsieur_cuisine_sdk import DeviceModel,DigitalTwin,replay
    from monsieur_cuisine_sdk.android_connection import AndroidConnection,ConnectionConfig
    model=DeviceModel(model)
    twin=DigitalTwin(model)
    root=app=None
    if gui:
        import tkinter as tk
        from monsieur_cuisine_sdk.gui import DesktopApp
        root=tk.Tk();app=DesktopApp(root,twin);app.running=False
        connection=app.enable_android(port=0)
    else:
        connection=AndroidConnection(twin,ConnectionConfig(port=0)).start()
    port=connection.address[1]
    if mode=="android":
        if not adb or not adb_port or not serial or not serial.startswith("emulator-"):
            raise ValueError("Android test requires explicit adb path, private server port and emulator serial")
        command=[str(adb),"-P",str(adb_port),"-s",serial,"shell","am","instrument","-w","-r",
                 "-e","model",model.name,"-e","port",str(port),
                 "org.blackstufflabs.monsieurcuisine.demo.debug.test/org.blackstufflabs.monsieurcuisine.demo.BridgeInstrumentation"]
    else:
        version=tomllib.loads((ROOT/"pyproject.toml").read_text("utf-8"))["project"]["version"].replace(".dev", "-dev")
        jar=jar or ROOT/f"android/sdk/build/libs/sdk-{version}-host-tests.jar"
        command=[java,"-cp",str(jar),"org.blackstufflabs.monsieurcuisine.HostExercise",model.name,str(port)]
    lines=queue.Queue();trace=[];errors=[]
    process=subprocess.Popen(command,stdout=subprocess.PIPE,stderr=subprocess.PIPE,text=True,encoding="utf-8")
    def output():
        for line in process.stdout:lines.put(line.rstrip())
    def error():errors.append(process.stderr.read())
    out_thread=threading.Thread(target=output,daemon=True);err_thread=threading.Thread(target=error,daemon=True)
    out_thread.start();err_thread.start()
    deadline=time.monotonic()+60
    next_sample=0.0
    motion=False;error_injected=False;callback_errors=[]
    if root:
        root.report_callback_exception=lambda kind,value,tb:callback_errors.append(str(value))
    try:
        while time.monotonic()<deadline:
            connection.poll()
            twin.advance(.02)
            now=time.monotonic()
            if (model==DeviceModel.MCC or periodic_telemetry) and now>=next_sample:
                twin.sample();next_sample=now+.05
            connection.poll()
            motion|=twin.get_state().actual_speed>0
            if app:root.update()
            try:line=lines.get(timeout=.005)
            except queue.Empty:
                if process.poll() is not None and not out_thread.is_alive():break
                continue
            trace.append(line)
            if screenshot and mode=="android" and "stage=TELEMETRY" in line:
                capture=subprocess.run([str(adb),"-P",str(adb_port),"-s",serial,"exec-out","screencap","-p"],capture_output=True,timeout=10,check=True)
                if not capture.stdout.startswith(b"\x89PNG\r\n\x1a\n"):
                    raise ValueError("emulator screenshot is not PNG")
                screenshot.parent.mkdir(parents=True,exist_ok=True);screenshot.write_bytes(capture.stdout)
            if "AWAIT_HOST_ERROR" in line:
                twin.set_sensors(error_code=3);error_injected=True
        process.wait(timeout=5);out_thread.join(2);err_thread.join(2)
        while not lines.empty():trace.append(lines.get_nowait())
        for _ in range(4):connection.poll()
        joined="\n".join(trace)
        expected=("CONNECTED","STARTED","SPEED_CHANGED","TELEMETRY","STOPPED","ERROR_OBSERVED","DISCONNECTED","RECONNECTED_DISARMED")
        assert process.returncode==0, "child process failed: "+"".join(errors)[-2000:]
        assert all(stage in joined for stage in expected),joined[-6000:]
        if mode=="android":
            assert "passed=true" in joined and "INSTRUMENTATION_CODE: -1" in joined,joined[-6000:]
            assert all(stage in joined for stage in ("UI_MODEL_SWITCHED_BOTH_DIRECTIONS","CONNECTED_MODEL_SWITCH_DISARMED","BACKGROUND_DISCONNECTED"))
        assert motion and error_injected
        assert not callback_errors,callback_errors
        assert twin.get_state().requested_speed==0
        assert twin.owner=="local"
        replayed=replay(twin.recording)
        assert replayed.get_state()==twin.get_state()
        return {"PASS":True,"model":model.value,"mode":mode,
                "actual_activity_exercised":mode=="android","actual_tk_gui":gui,
                "same_twin_instance":app.twin is twin if app else True,
                "periodic_telemetry":model==DeviceModel.MCC or periodic_telemetry,
                "motion_observed":motion,"host_error_injected":error_injected,
                "connection":connection.status(),"recording_actions":len(twin.recording["actions"]),
                "replay":"PASS","callback_errors":callback_errors,"trace":trace,
                "final_state":twin.get_state().to_dict()}
    finally:
        if process.poll() is None:process.terminate();process.wait(timeout=5)
        out_thread.join(2);err_thread.join(2)
        if app:app.close()
        else:connection.close()


if __name__=="__main__":
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--model",choices=("mcc","mcs"),required=True)
    parser.add_argument("--mode",choices=("jvm","android"),default="jvm")
    parser.add_argument("--java",default="java");parser.add_argument("--jar",type=Path)
    parser.add_argument("--adb",type=Path);parser.add_argument("--adb-port",type=int);parser.add_argument("--serial")
    parser.add_argument("--gui",action="store_true");parser.add_argument("--report",type=Path)
    parser.add_argument("--screenshot",type=Path,help="optional actual emulator screenshot at telemetry stage")
    parser.add_argument("--periodic-telemetry",action="store_true",
                        help="also push MCS synthetic status every 50 ms to exercise unsolicited RX")
    args=parser.parse_args();report=args.report
    result=verify(**{k:v for k,v in vars(args).items() if k!="report"})
    rendered=json.dumps(result,indent=2)+"\n"
    if report:report.write_text(rendered,encoding="utf-8")
    print(rendered,end="")
