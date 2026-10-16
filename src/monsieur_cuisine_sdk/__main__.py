"""Simple default native launch, with explicit headless CLI delegation."""
import json
import sys

def main(argv=None):
    arguments=list(sys.argv[1:] if argv is None else argv)
    gui_model="mcc"
    gui_arguments=list(arguments)
    if "--model" in gui_arguments:
        index=gui_arguments.index("--model")
        if index+1<len(gui_arguments):
            gui_model=gui_arguments[index+1];del gui_arguments[index:index+2]
    if not gui_arguments or gui_arguments==["--smoke-test"]:
        from .api import DeviceModel
        from .gui import launch
        result=launch(DeviceModel(gui_model),smoke_test=bool(gui_arguments))
        if gui_arguments:print(json.dumps(result));return 0 if result.get("PASS") else 1
        return 0
    if arguments==["--headless"]:
        from .api import DeviceModel
        from .scenarios import run_scenario
        results=[]
        for model in DeviceModel:
            result=run_scenario(model);result.pop("recording",None);results.append(result)
        print(json.dumps(results,indent=2));return 0 if all(r["PASS"] for r in results) else 1
    from .cli import main as cli
    return cli(arguments)

if __name__=="__main__":raise SystemExit(main())
