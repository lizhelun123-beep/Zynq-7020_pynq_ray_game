"""Run ONE requested native RTL stage. No board access or implicit later stages."""
import argparse
import json
from pathlib import Path
import re
import shutil
import subprocess
import sys
import zipfile

from verify_inputs import verify
import gate


def bind(build):
    package = build / "source/python"
    sys.path.insert(0, str(package))
    from pynq_rtl_demo.artifacts import digest, inspect_hwh, validate_bundle, FILES
    export = build / "export"
    xsa = export / "system.xsa"
    with zipfile.ZipFile(xsa) as archive:
        hwh = [name for name in archive.namelist() if name.lower().endswith(".hwh")]
        bits = [name for name in archive.namelist() if name.lower().endswith(".bit")]
        if len(hwh) != 1 or len(bits) != 1:
            raise ValueError("XSA must contain exactly one BIT and HWH")
        (export / "system.hwh").write_bytes(archive.read(hwh[0]))
        native_bit = build / "project/add32.runs/impl_1/system_wrapper.bit"
        if archive.read(bits[0]) != native_bit.read_bytes():
            raise ValueError("XSA bitstream differs from implemented bitstream")
        shutil.copyfile(native_bit, export / "system.bit")
    shutil.copyfile(build / "inputs.json", export / "inputs.json")
    receipt = json.loads((build / "inputs.json").read_text(encoding="utf-8"))
    result = {"schema": "pynq-rtl-demo-bundle-v1", "build_id": receipt["build_id"],
              "profile": receipt["profile"], "metadata": inspect_hwh(export / "system.hwh"),
              "gate_sha256": gate.sha(build / "gate.json"),
              "files": {name: digest(export / name) for name in FILES},
              "scope": "OFF_BOARD_ONLY;BOARD_AND_IRQ_DELIVERY_NOT_RUN"}
    (export / "manifest.json").write_text(json.dumps(result, indent=2) + "\n", encoding="utf-8")
    return validate_bundle(export)


def run(build, vivado, stage):
    build = Path(build).resolve()
    verify(build / "inputs.json")
    receipt = json.loads((build / "inputs.json").read_text(encoding="utf-8"))
    if receipt.get("flow") != "rtl":
        raise ValueError("use a --flow rtl preparation")
    if stage == "synth":
        functional = json.loads((build / "sim_pass.json").read_text(encoding="utf-8"))
        if functional.get("receipt_sha256") != gate.sha(build / "inputs.json") or functional.get("log_sha256") != gate.sha(build / "sim/sim.sim/sim_1/behav/xsim/simulate.log"):
            raise ValueError("functional evidence changed or belongs to another build")
    if stage == "export":
        gate.verify(build / "inputs.json", build / "gate.json")
    # Exclusive stage receipt prevents accidental launch retries/overwriting failed evidence.
    attempt = build / (stage + "_attempt.json")
    with attempt.open("x", encoding="utf-8") as stream:
        json.dump({"stage": stage, "status": "STARTED", "build_id": receipt["build_id"],
                   "launcher": str(Path(vivado).resolve()), "launcher_sha256": gate.sha(vivado)}, stream)
    log = build / (stage + ".log")
    command = [str(Path(vivado).resolve()), "-mode", "batch", "-notrace", "-source",
               str(build / "source/vivado/build.tcl"), "-tclargs", str(build / "config.tcl"), stage]
    with log.open("wb") as stream:
        completed = subprocess.run(command, cwd=str(build), stdout=stream, stderr=subprocess.STDOUT)
    native_receipt = build / (stage + "_native_pass.txt")
    passed = completed.returncode == 0 and native_receipt.is_file() and native_receipt.read_text().strip() == stage
    if stage == "sim":
        simulation_log = build / "sim/sim.sim/sim_1/behav/xsim/simulate.log"
        content = simulation_log.read_text(encoding="utf-8", errors="replace") if simulation_log.is_file() else ""
        matches = re.findall(r"RTL_DEMO_RESULT checks=(\d+) failures=(\d+)", content)
        passed = passed and len(matches) == 1 and int(matches[0][0]) >= 50 and matches[0][1] == "0" and "RTL_DEMO_PASS" in content and not re.search(r"FATAL|ERROR|RTL_DEMO_FAIL|RTL_DEMO_TIMEOUT", content)
        if passed:
            (build / "sim_pass.json").write_text(json.dumps({"checks": int(matches[0][0]), "log_sha256": gate.sha(simulation_log), "receipt_sha256": gate.sha(build / "inputs.json")}) + "\n", encoding="utf-8")
    result = {"stage": stage, "status": "PASS" if passed else "FAIL", "exit_code": completed.returncode, "log": str(log),
              "launcher": str(Path(vivado).resolve()), "launcher_sha256": gate.sha(vivado)}
    attempt.write_text(json.dumps(result, indent=2) + "\n", encoding="utf-8")
    if not passed:
        raise RuntimeError("Native stage failed;see " + str(log))
    if stage == "impl":
        result["gate"] = gate.collect_rtl(build / "inputs.json")
    if stage == "export":
        result["bundle"] = bind(build)
    return result


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("build", type=Path)
    parser.add_argument("--vivado", required=True, type=Path, help="existing verified launcher/executable")
    parser.add_argument("--stage", required=True, choices=("sim", "prepare", "synth", "impl", "export"))
    args = parser.parse_args()
    print(json.dumps(run(args.build, args.vivado, args.stage), ensure_ascii=False, indent=2))
