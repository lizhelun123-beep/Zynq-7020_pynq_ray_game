"""Offline artifact identity/metadata checks;never import PYNQ or touch MMIO."""
import hashlib
import json
from pathlib import Path
import xml.etree.ElementTree as ET

VLNV = "pynq.local:rtl:add32:1.0"
REGISTERS = {"CTRL": 0, "STATUS": 4, "IRQ_ENABLE": 8, "VERSION": 12,
             "A": 16, "B": 20, "RESULT": 24, "COUNT": 28}
FILES = ("system.bit", "system.hwh", "system.xsa", "inputs.json")


def digest(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def inspect_hwh(path):
    data = Path(path).read_bytes()
    if len(data) > 16 * 1024 * 1024 or b"<!DOCTYPE" in data.upper() or b"<!ENTITY" in data.upper():
        raise ValueError("unsupported HWH document")
    root = ET.fromstring(data)
    modules = [node for node in root.iter("MODULE") if node.get("VLNV") == VLNV]
    if len(modules) != 1 or modules[0].get("INSTANCE") != "add32_0":
        raise ValueError("expected exactly one add32_0 with the exact VLNV")
    module = modules[0]
    found = {}
    for node in module.iter("REGISTER"):
        properties = {prop.get("NAME"): prop.get("VALUE") for prop in node.findall("PROPERTY")}
        name = node.get("NAME")
        access = "read-only" if name in ("VERSION", "RESULT", "COUNT") else "read-write"
        if name in found or properties.get("SIZE") != "32" or properties.get("ACCESS") != access:
            raise ValueError("duplicate register or incompatible size/access")
        if "ADDRESS_OFFSET" not in properties:
            raise ValueError("register offset missing")
        found[name] = int(properties["ADDRESS_OFFSET"], 0)
    if found != REGISTERS:
        raise ValueError("HWH register map differs")
    ranges = [node for node in root.iter("MEMRANGE")
              if node.get("INSTANCE") == "add32_0"]
    if len(ranges) != 1:
        raise ValueError("unique PS address range missing")
    memory = ranges[0]
    base = int(memory.get("BASEVALUE"), 0)
    high = int(memory.get("HIGHVALUE"), 0)
    if base != 0x43c00000 or high - base + 1 != 4096:
        raise ValueError("HWH address window differs")
    return {"vlnv": VLNV, "registers": found, "base": base, "span": 4096}


def validate_bundle(directory):
    directory = Path(directory).resolve()
    manifest = json.loads((directory / "manifest.json").read_text(encoding="utf-8"))
    if manifest.get("schema") != "pynq-rtl-demo-bundle-v1" or manifest.get("files", {}).keys() != set(FILES):
        raise ValueError("unknown/incomplete bundle")
    for name in FILES:
        if digest(directory / name) != manifest["files"][name]:
            raise ValueError("artifact changed: " + name)
    receipt = json.loads((directory / "inputs.json").read_text(encoding="utf-8"))
    if receipt.get("build_id") != manifest.get("build_id") or receipt.get("flow") != "rtl":
        raise ValueError("build identity differs")
    metadata = inspect_hwh(directory / "system.hwh")
    if metadata != manifest.get("metadata"):
        raise ValueError("manifest metadata differs")
    return {"directory": str(directory), "file_identity": manifest["files"], "metadata": metadata}
