"""Check prepared input bytes;does not claim actual tool preparation or hardware."""
import argparse
import hashlib
import json
from pathlib import Path


def verify(path):
    data = json.loads(Path(path).read_text(encoding="utf-8"))
    if data.get("schema") != "pynq-demo-inputs-v1" or not data.get("files"):
        raise ValueError("unknown or empty input receipt")
    config = Path(path).resolve().with_name("config.tcl")
    if hashlib.sha256(config.read_bytes()).hexdigest() != data.get("config_sha256"):
        raise ValueError("prepared tool configuration changed")
    for name, expected in data["files"].items():
        if hashlib.sha256(Path(name).read_bytes()).hexdigest() != expected:
            raise ValueError("input changed;prepare a new build: " + name)
    return data


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--receipt", required=True, type=Path)
    args = parser.parse_args()
    verify(args.receipt)
    print("PASS_INPUT_BYTES_ONLY")
