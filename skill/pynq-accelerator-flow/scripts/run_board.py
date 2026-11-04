"""Default validates files only;--hardware additionally downloads the Overlay."""
import argparse
import asyncio
import json
from pathlib import Path
import platform
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "assets/scalar-demo/python"))
from pynq_scalar_demo.bundle import validate_bundle


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("bundle", type=Path)
    parser.add_argument("--hardware", action="store_true")
    parser.add_argument("--irq", action="store_true")
    parser.add_argument("--output", type=Path)
    args = parser.parse_args(argv)
    manifest = validate_bundle(args.bundle)
    result = {"scope": "OFFLINE_FILE_BINDING_ONLY", "build_id": manifest["build_id"],
              "hardware": "NOT_RUN"}
    if args.hardware:
        if args.output is None:
            parser.error("--output required for hardware evidence")
        if args.output.exists():
            parser.error("evidence output already exists")
        ip = None
        result.update(scope="TARGET_BOARD_SCALAR_ONLY", hardware="FAIL", irq_requested=args.irq,
                      machine=platform.machine(), python=platform.python_version(),
                      manifest_sha256=manifest["file_identity"], vectors=[])
        try:
            from pynq_scalar_demo.board import open_board
            import pynq
            result["pynq_version"] = getattr(pynq, "__version__", "UNKNOWN")
            result["boot_id"] = Path("/proc/sys/kernel/random/boot_id").read_text().strip()
            ip = open_board(Path(manifest["directory"]) / "scalar.bit", manifest["ip_name"], manifest["file_identity"])
            for x, bias in ((0, 0), (3, 4), (0xffffffff, 1), (0x80000000, 0x80000000)):
                if args.irq:
                    loop = asyncio.get_event_loop()
                    value = loop.run_until_complete(ip.add_async(x, bias))
                else:
                    value = ip.add(x, bias)
                expected = (x + bias) & 0xffffffff
                result["vectors"].append({"x": x, "bias": bias, "value": value, "expected": expected})
                if value != expected:
                    raise RuntimeError("result differs from CPU oracle")
            result["irq_events"] = ip.session.irq_events
            if args.irq and result["irq_events"] < 4:
                raise RuntimeError("actual interrupt notification not observed")
            ip.session.close()
            result.update(hardware="PASS_SCALAR_VECTORS_ONLY", end_state=ip.session.state)
        except BaseException as exc:
            result.update(error=type(exc).__name__ + ": " + str(exc),
                          end_state=ip.session.state if ip else "UNKNOWN",
                          recovery_required=True)
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(result, ensure_ascii=False))
    return 0 if not args.hardware or result["hardware"] == "PASS_SCALAR_VECTORS_ONLY" else 2


if __name__ == "__main__":
    sys.exit(main())
