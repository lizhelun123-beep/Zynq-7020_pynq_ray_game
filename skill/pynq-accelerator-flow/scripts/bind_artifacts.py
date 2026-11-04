"""Bind one XSA's BIT/HWH,generated ABI header and reviewed build receipts."""
import argparse
import hashlib
import json
from pathlib import Path
import sys
import zipfile

PYTHON_SOURCE = Path(__file__).resolve().parents[1] / "assets/scalar-demo/python"
sys.path.insert(0, str(PYTHON_SOURCE))
from pynq_scalar_demo.bundle import check_header, check_hwh, validate_bundle
from verify_inputs import verify as verify_inputs
from gate import verify as verify_gate


def bind(xsa, header, receipt, gate, output, ip_name="add_bias_0"):
    xsa, header, receipt, gate, output = map(Path, (xsa, header, receipt, gate, output))
    inputs = verify_inputs(receipt)
    verify_gate(receipt, gate)
    header_data = header.read_bytes()
    check_header(header_data.decode("utf-8"))
    with zipfile.ZipFile(xsa) as archive:
        entries = archive.infolist()
        bits = [e for e in entries if e.filename.lower().endswith(".bit")]
        hwhs = [e for e in entries if e.filename.lower().endswith(".hwh")]
        if len(bits) != 1 or len(hwhs) != 1 or any(e.file_size > 32 * 1024 * 1024 for e in bits + hwhs):
            raise ValueError("require a unique bounded BIT/HWH pair in XSA")
        bit_data, hwh_data = archive.read(bits[0]), archive.read(hwhs[0])
    check_hwh(hwh_data, ip_name)
    if not bit_data or output.exists():
        raise ValueError("empty BIT or existing bundle output")
    files = {"scalar.bit": bit_data, "scalar.hwh": hwh_data,
             "registers.h": header_data, "inputs.json": receipt.read_bytes(), "gate.json": gate.read_bytes()}
    manifest = {"schema": "scalar-demo-bundle-v1", "scope": "FILE_BINDING_ONLY_NOT_BOARD_QUALIFICATION",
                "build_id": inputs["build_id"], "profile": inputs["profile"], "ip_name": ip_name,
                "xsa_sha256": hashlib.sha256(xsa.read_bytes()).hexdigest(),
                "files": {name: {"size": len(data), "sha256": hashlib.sha256(data).hexdigest()} for name, data in files.items()}}
    output.mkdir(parents=True)
    for name, data in files.items():
        (output / name).write_bytes(data)
    (output / "manifest.json").write_text(json.dumps(manifest, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return validate_bundle(output)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    for name in ("xsa", "header", "receipt", "gate", "output"):
        parser.add_argument("--" + name, required=True, type=Path)
    parser.add_argument("--ip", default="add_bias_0")
    args = parser.parse_args()
    print(json.dumps(bind(args.xsa, args.header, args.receipt, args.gate, args.output, args.ip), ensure_ascii=False))
