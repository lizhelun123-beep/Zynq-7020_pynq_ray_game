"""Strict offline checks for THIS template's ABI;no PYNQ import."""
import hashlib
import json
from pathlib import Path
import re
from xml.etree import ElementTree as ET
from .core import OFFSETS

VLNV = "example.org:hls:add_bias:1.0"
MACROS = {"ctrl": "AP_CTRL", "gie": "GIE", "ier": "IER", "isr": "ISR",
          "x": "X_DATA", "bias": "BIAS_DATA", "y": "Y_DATA"}
FILES = {"scalar.bit", "scalar.hwh", "registers.h", "inputs.json", "gate.json"}


def digest(data):
    return hashlib.sha256(data).hexdigest()


def check_header(text):
    for name, suffix in MACROS.items():
        values = re.findall(r"^\s*#define\s+XADD_BIAS_CONTROL_ADDR_" + suffix + r"\s+(0[xX][0-9a-fA-F]+|[0-9]+)\s*$", text, re.M)
        if len(values) != 1 or int(values[0], 0) != OFFSETS[name]:
            raise ValueError("generated header ABI mismatch: " + name)


def check_hwh(data, ip_name):
    if len(data) > 8 * 1024 * 1024:
        raise ValueError("HWH too large")
    text = data.decode("utf-8-sig")
    if "\x00" in text or "<!DOCTYPE" in text.upper() or "<!ENTITY" in text.upper():
        raise ValueError("unsupported XML encoding/declarations")
    root = ET.fromstring(text)
    if root.tag != "SYSTEM" or not re.fullmatch(r"[A-Za-z0-9_]+(?:/[A-Za-z0-9_]+)*", ip_name):
        raise ValueError("unsupported HWH root/IP path")
    modules = [m for m in root.iter("MODULE") if m.get("FULLNAME", "").lstrip("/") == ip_name]
    if len(modules) != 1 or modules[0].get("VLNV") != VLNV:
        raise ValueError("unique template IP not found")
    module = modules[0]
    registers = {}
    for reg in module.iter("REGISTER"):
        offset = int(reg.get("ADDRESS_OFFSET", ""), 0)
        if offset in registers or int(reg.get("SIZE", "0"), 0) != 32:
            raise ValueError("duplicate/non32bit register")
        registers[offset] = reg
    if not set(OFFSETS.values()).issubset(registers):
        raise ValueError("required register offsets absent")
    for name in ("x", "bias", "y"):
        if registers[OFFSETS[name]].get("NAME", "").lower() != name:
            raise ValueError("data register name/offset mismatch")
    fields = {f.get("NAME"): f for f in registers[0].iter("FIELD")}
    for name, bit in (("AP_START", 0), ("AP_DONE", 1), ("AP_IDLE", 2)):
        field = fields.get(name)
        if field is None or field.get("BIT_OFFSET") != str(bit) or field.get("BIT_WIDTH") != "1":
            raise ValueError("ap_ctrl_hs field mismatch: " + name)
    return dict(ip_name=ip_name, vlnv=VLNV, offsets=dict(OFFSETS))


def validate_description(description):
    if description.get("type") != VLNV:
        raise ValueError("unexpected VLNV")
    address, span = description.get("phys_addr"), description.get("addr_range")
    if type(address) is not int or type(span) is not int or address <= 0 or address % 4 or span < 0x28 or address + span > 1 << 32:
        raise ValueError("invalid declared MMIO range")


def validate_bundle(directory):
    directory = Path(directory).resolve()
    manifest = json.loads((directory / "manifest.json").read_text(encoding="utf-8"))
    if manifest.get("schema") != "scalar-demo-bundle-v1" or set(manifest.get("files", {})) != FILES:
        raise ValueError("unknown bundle schema/inventory")
    for name, row in manifest["files"].items():
        path = (directory / name).resolve()
        if path.parent != directory or not path.is_file():
            raise ValueError("file leaves bundle")
        data = path.read_bytes()
        if len(data) != row["size"] or digest(data) != row["sha256"]:
            raise ValueError("bundle file changed: " + name)
    check_header((directory / "registers.h").read_text(encoding="utf-8"))
    check_hwh((directory / "scalar.hwh").read_bytes(), manifest["ip_name"])
    manifest["directory"] = str(directory)
    manifest["file_identity"] = digest((directory / "manifest.json").read_bytes())
    return manifest
