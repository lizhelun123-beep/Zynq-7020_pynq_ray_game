"""Read-only preparation followed by writing a NEW external build directory."""
import argparse
import hashlib
import json
from pathlib import Path
import re
import shutil
import sys
import uuid

ASSETS = Path(__file__).resolve().parents[1] / "assets/scalar-demo"


def digest(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def tcl_word(value):
    text = str(value)
    for old, new in (("\\", "\\\\"), ('"', '\\"'), ("$", "\\$"),
                     ("[", "\\["), ("]", "\\]"), ("\n", "\\n"), ("\r", "\\r")):
        text = text.replace(old, new)
    return '"' + text + '"'


def prepare(profile_path, output, flow="hls"):
    if flow not in ("hls", "rtl"):
        raise ValueError("flow must be hls or rtl")
    assets = ASSETS if flow == "hls" else ASSETS.parent / "rtl-demo"
    profile_path = Path(profile_path).resolve()
    output = Path(output).resolve()
    profile = json.loads(profile_path.read_text(encoding="utf-8"))
    if not re.fullmatch(r"xc7z[0-9a-z-]+", profile.get("part", "")):
        raise ValueError("provide actual Zynq-7000 part;other families need a new PS flow")
    if not isinstance(profile.get("board_label"), str) or not profile["board_label"].strip():
        raise ValueError("provide actual board_label")
    if not re.fullmatch(r"20[0-9]{2}\.[0-9]+", profile.get("tool_version", "")):
        raise ValueError("provide exact tool release")
    mhz = profile.get("clock_mhz")
    if type(mhz) not in (int, float) or not 1 <= mhz <= 250:
        raise ValueError("provide a supported requested FCLK frequency")
    preset = Path(profile.get("ps_preset_tcl", ""))
    preset = (profile_path.parent / preset).resolve() if not preset.is_absolute() else preset.resolve()
    if not preset.is_file() or preset.suffix.lower() != ".tcl":
        raise ValueError("provide trusted board-specific PS7 preset Tcl")
    if output.exists() or output == assets.resolve() or assets.resolve() in output.parents:
        raise ValueError("build output must be a new directory outside template assets")
    sources = [f for f in assets.rglob("*") if f.is_file() and "__pycache__" not in f.parts]
    sources += [preset, profile_path, Path(__file__).resolve(), Path(__file__).with_name("verify_inputs.py"), Path(__file__).with_name("gate.py")]
    if flow == "rtl":
        sources += [Path(__file__).with_name("run_rtl.py")]
    receipt = {"schema": "pynq-demo-inputs-v1", "flow": flow, "build_id": str(uuid.uuid4()),
               "profile": profile, "files": {str(f.resolve()): digest(f) for f in sources},
               "scope": "FILE_PREPARATION_ONLY_VENDOR_TOOLS_NOT_RUN"}
    values = {"DEMO_PART": profile["part"], "DEMO_TOOL_VERSION": profile["tool_version"],
              "DEMO_CLOCK_MHZ": mhz, "DEMO_PS_PRESET": preset.as_posix(),
              "DEMO_BUILD": output.as_posix(), "DEMO_SOURCE": assets.resolve().as_posix(),
              "DEMO_PYTHON": Path(sys.executable).as_posix(),
              "DEMO_VERIFY": Path(__file__).with_name("verify_inputs.py").resolve().as_posix(),
              "DEMO_GATE": Path(__file__).with_name("gate.py").resolve().as_posix()}
    output.mkdir(parents=True)
    if flow == "rtl":
        # Stage this small template only;never copy a user's FPGA project.
        shutil.copytree(assets, output / "source", ignore=shutil.ignore_patterns("__pycache__"))
        shutil.copyfile(preset, output / "ps7_preset.tcl")
        values["DEMO_SOURCE"] = (output / "source").as_posix()
        values["DEMO_PS_PRESET"] = (output / "ps7_preset.tcl").as_posix()
        for f in [output / "ps7_preset.tcl"] + sorted((output / "source").rglob("*")):
            if f.is_file():
                receipt["files"][str(f.resolve())] = digest(f)
    config = "\n".join("set {} {}".format(k, tcl_word(v)) for k, v in values.items()) + "\n"
    receipt["config_sha256"] = hashlib.sha256(config.encode("utf-8")).hexdigest()
    (output / "inputs.json").write_text(json.dumps(receipt, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    with (output / "config.tcl").open("w", encoding="utf-8", newline="\n") as stream:
        stream.write(config)
    return receipt


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("profile", type=Path)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--flow", choices=("hls", "rtl"), default="hls")
    args = parser.parse_args()
    print(json.dumps(prepare(args.profile, args.output, args.flow), ensure_ascii=False))
