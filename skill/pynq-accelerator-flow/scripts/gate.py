"""Validate declarations;RTL mode also parses the fixed Vivado 2023.1 reports."""
import argparse
import hashlib
import json
import math
from pathlib import Path
import re

REPORTS = ("timing", "cdc", "drc", "utilization", "clocks")


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def draft(receipt):
    receipt = Path(receipt).resolve()
    source = json.loads(receipt.read_text(encoding="utf-8"))
    return {"schema": "scalar-demo-gate-v1", "status": "NOT_RUN",
            "build_id": source["build_id"], "receipt_sha256": sha(receipt),
            "timing": dict.fromkeys(("WNS", "TNS", "WHS", "THS")),
            "critical_cdc": None, "unexplained_unconstrained": None,
            "drc_errors": None, "drc_critical": None,
            "resources_reviewed": False, "clock_reset_reviewed": False,
            "reviewed_by": "", "reports": {name: {"path": str(receipt.parent / "reports" / (name + ".rpt")), "sha256": None} for name in REPORTS}}


def verify(receipt, record):
    receipt, record = Path(receipt).resolve(), Path(record).resolve()
    source = json.loads(receipt.read_text(encoding="utf-8"))
    data = json.loads(record.read_text(encoding="utf-8"))
    if data.get("schema") != "scalar-demo-gate-v1" or data.get("status") != "PASS" or data.get("build_id") != source["build_id"] or data.get("receipt_sha256") != sha(receipt):
        raise ValueError("gate not passed or input identity differs")
    for name in ("WNS", "TNS", "WHS", "THS"):
        value = data.get("timing", {}).get(name)
        if type(value) not in (int, float) or not math.isfinite(value) or value < 0:
            raise ValueError("unknown/negative timing: " + name)
    for name in ("critical_cdc", "unexplained_unconstrained", "drc_errors", "drc_critical"):
        if type(data.get(name)) is not int or data[name] != 0:
            raise ValueError("unresolved gate: " + name)
    if data.get("resources_reviewed") is not True or data.get("clock_reset_reviewed") is not True or not data.get("reviewed_by", "").strip():
        raise ValueError("reviews missing")
    if set(data.get("reports", {})) != set(REPORTS):
        raise ValueError("report set incomplete")
    for row in data["reports"].values():
        path = Path(row["path"]).resolve()
        if receipt.parent not in path.parents or sha(path) != row.get("sha256"):
            raise ValueError("report outside build or changed")
    if source.get("flow") == "rtl":
        actual = collect_rtl_data(receipt)
        if actual["status"] != "PASS" or any(data.get(k) != actual[k] for k in ("timing", "critical_cdc", "unexplained_unconstrained", "drc_errors", "drc_critical", "parsed")):
            raise ValueError("RTL declaration differs from actual reports")
    return data


def parse_rtl_reports(directory, metrics):
    """Only the known 7-series report tables;missing/unknown/negative fails closed."""
    root = Path(directory)
    timing = {name: float(metrics[name]) for name in ("WNS", "TNS", "WHS", "THS")}
    if not all(math.isfinite(v) for v in timing.values()):
        raise ValueError("nonfinite timing")
    text = (root / "timing.rpt").read_text(encoding="utf-8", errors="replace")
    coverage = {}
    for key in ("no_clock", "unconstrained_internal_endpoints", "no_input_delay", "no_output_delay"):
        values = re.findall(r"checking\s+" + key + r"\s+\((\d+)\)", text)
        if not values or len(set(values)) != 1:
            raise ValueError("unknown timing coverage format: " + key)
        coverage[key] = int(values[0])
    cdc = (root / "cdc.rpt").read_text(encoding="utf-8", errors="replace")
    if "CDC Report" not in cdc or not re.search(r"ID\s+Severity\s+Count\s+Description", cdc):
        raise ValueError("unknown CDC summary format")
    cdc_rows = re.findall(r"^CDC-\d+\s+(Critical|Warning|Info)\s+(\d+)\s+", cdc, re.M)
    critical = sum(int(n) for severity, n in cdc_rows if severity == "Critical")
    warnings = sum(int(n) for severity, n in cdc_rows if severity == "Warning")
    utilization = (root / "utilization.rpt").read_text(encoding="utf-8", errors="replace")
    resources = {}
    for label, limit in {"Slice LUTs": .7, "Slice Registers": .7, "Slice": .75, "Block RAM Tile": .7, "DSPs": .7}.items():
        values = []
        for line in utilization.splitlines():
            cells = [s.strip() for s in line.split("|")[1:-1]]
            if len(cells) >= 6 and cells[0].rstrip("*") == label:
                used, available = float(cells[1].replace(",", "")), float(cells[-2].replace(",", ""))
                if not math.isfinite(used) or not math.isfinite(available) or used < 0 or available <= 0:
                    raise ValueError("invalid utilization number")
                values.append((used, available))
        if not values or len(set(values)) != 1:
            raise ValueError("unknown utilization row: " + label)
        used, available = values[0]
        resources[label] = {"used": used, "available": available, "fraction": used / available, "limit": limit}
    passed = all(v >= 0 for v in timing.values()) and not any(coverage.values()) and critical == 0 and warnings == 0 and all(v["fraction"] < v["limit"] for v in resources.values())
    return {"status": "PASS" if passed else "FAIL", "timing": timing, "coverage": coverage,
            "critical_cdc": critical, "cdc_warnings": warnings, "resources": resources}


def collect_rtl_data(receipt):
    receipt = Path(receipt).resolve()
    source = json.loads(receipt.read_text(encoding="utf-8"))
    if source.get("flow") != "rtl" or source["profile"]["tool_version"] != "2023.1":
        raise ValueError("RTL report parser validated only for Vivado 2023.1")
    metrics = dict(line.split("\t", 1) for line in (receipt.parent / "impl.txt").read_text().splitlines())
    parsed = parse_rtl_reports(receipt.parent / "reports", metrics)
    record = draft(receipt)
    record.update(status=parsed["status"], timing=parsed["timing"], critical_cdc=parsed["critical_cdc"],
                  unexplained_unconstrained=sum(parsed["coverage"].values()),
                  drc_errors=int(metrics["drc_errors"]), drc_critical=int(metrics["drc_critical"]),
                  resources_reviewed=True, clock_reset_reviewed=False,
                  reviewed_by="", parsed=parsed)
    # Parsed data alone never asserts that clock/reset topology has been reviewed.
    for row in record["reports"].values():
        row["sha256"] = sha(row["path"])
    if record["drc_errors"] or record["drc_critical"]:
        record["status"] = "FAIL"
    return record


def collect_rtl(receipt):
    record = collect_rtl_data(receipt)
    (Path(receipt).resolve().parent / "gate.json").write_text(json.dumps(record, indent=2) + "\n", encoding="utf-8")
    return record


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--receipt", required=True, type=Path)
    parser.add_argument("--record", type=Path)
    parser.add_argument("--verify", action="store_true")
    args = parser.parse_args()
    if args.verify:
        if args.record is None:
            parser.error("--record required")
        verify(args.receipt, args.record)
        print("PASS_REVIEW_DECLARATIONS_AND_REPORT_IDENTITIES_ONLY")
    else:
        print(json.dumps(draft(args.receipt), ensure_ascii=False, indent=2))
