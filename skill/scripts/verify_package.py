"""Offline skill-package validation with standard library only, Python 3.8+."""

import argparse
import hashlib
import json
import os
import re
import subprocess
import sys
from pathlib import Path
from urllib.parse import unquote


SKILLS = ("pynq-development", "ray-game-integration", "pynq-dma-contract", "stream-perf-analysis",
          "fpga-verification-gates", "xilinx-project-flow", "pynq-accelerator-flow")


def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def source_files(root):
    return sorted(path for path in root.rglob("*") if path.is_file()
                  and "__pycache__" not in path.parts and path.suffix != ".pyc")


def require(condition, message):
    if not condition:
        raise ValueError(message)


def check_documents(root, files):
    allowed = re.compile(r"^[a-z0-9_-]+(?:\.[a-z0-9_-]+)*$")
    for path in files:
        require(not path.is_symlink(), "symlink not allowed: " + str(path))
        for part in path.relative_to(root).parts:
            require(part in ("README.md", "SKILL.md") or allowed.fullmatch(part),
                    "invalid package name: " + part)
        if path.suffix != ".md" or path.name == "package-root-readme.md":
            # This file is a template rendered one directory above skill/.
            continue
        fenced = False
        for line in path.read_text(encoding="utf-8").splitlines():
            if line.lstrip().startswith("```"):
                fenced = not fenced
                continue
            if fenced:
                continue
            for target in re.findall(r"\[[^\]]*\]\(([^)]+)\)", line):
                if target.startswith(("https://", "http://", "mailto:", "#")):
                    continue
                target = unquote(target.split("#", 1)[0])
                destination = (path.parent / target).resolve()
                require(destination == root or root in destination.parents,
                        "link leaves standalone skill package: " + target)
                require(destination.exists(), "broken link: " + str(path) + " -> " + target)
    found = {path.parent.name for path in root.glob("*/SKILL.md")}
    require(found == set(SKILLS), "missing or unregistered skill entry")
    for name in SKILLS:
        folder = root / name
        body = (folder / "SKILL.md").read_text(encoding="utf-8")
        front = re.match(r"^---\n(.*?)\n---\n", body, re.S)
        require(front is not None, "invalid frontmatter: " + name)
        fields = dict(re.findall(r"^([a-z-]+):\s*(.+)$", front.group(1), re.M))
        require(fields.get("name") == name, "name mismatch: " + name)
        require(bool(fields.get("description", "").strip()), "missing description: " + name)
        require("[TODO:" not in body, "unfinished scaffold: " + name)
        interface_path = folder / "agents" / "openai.yaml"
        if interface_path.is_file():
            interface = interface_path.read_text(encoding="utf-8")
            require("$" + name in interface, "default prompt lacks invocation: " + name)
    print("PASS metadata={} local_links=all filenames=english".format(len(SKILLS)))


def run_python(args, expected=0):
    env = dict(os.environ, PYTHONDONTWRITEBYTECODE="1", PYTHONUTF8="1")
    process = subprocess.run([sys.executable, "-B", *map(str, args)], env=env,
                             capture_output=True, text=True, encoding="utf-8", timeout=90)
    require(process.returncode == expected,
            "command failed: {}\n{}\n{}".format(args, process.stdout, process.stderr))
    return process


def check_examples(root):
    perf = root / "stream-perf-analysis"
    dma = root / "pynq-dma-contract"
    development = root / "pynq-development"
    accelerator = root / "pynq-accelerator-flow"
    for label, folder, pattern in (("performance", perf, "test_analyze.py"),
                                    ("dma-layout", dma, "test_check_layout.py"),
                                    ("dma-lifecycle", dma, "test_lifecycle.py"),
                                    ("hwh", development, "test_hwh.py"),
                                    ("ps-native", development, "test_native_array.py"),
                                    ("real-c-abi", development, "test_native_library.py"),
                                    ("accelerator-core", accelerator, "test_core.py"),
                                    ("accelerator-owner", accelerator, "test_board_owner.py"),
                                    ("accelerator-artifacts", accelerator, "test_artifacts.py"),
                                    ("accelerator-rtl", accelerator, "test_rtl.py")):
        result = run_python(["-m", "unittest", "discover", "-s", folder / "scripts", "-p", pattern])
        count = re.search(r"Ran (\d+) tests?", result.stderr)
        require(count is not None, "unit-test runner produced no count")
        require(int(count.group(1)) > 0, "empty test suite: " + label)
        skipped = re.search(r"skipped=(\d+)", result.stderr)
        skip_count = int(skipped.group(1)) if skipped else 0
        require(skip_count == 0 or label in ("ps-native", "real-c-abi"),
                "required suite skipped tests: " + label)
        status = "SKIP" if skip_count == int(count.group(1)) else "PASS"
        print("{} suite={} tests={} skipped={}".format(status, label, count.group(1), skip_count))
        if label == "ps-native" and status == "PASS":
            native = json.loads(run_python([development / "examples" / "native_array.py"]).stdout)
            require(native["scope"] == "MOCK_NATIVE_ONLY" and native["input_unchanged"],
                    "native array example mismatch")
    hwh = json.loads(run_python([development / "scripts" / "inspect_hwh.py",
                                development / "examples" / "synthetic.hwh", "--ip", "demo_dma"]).stdout)
    require(hwh["scope"] == "OFFLINE_DECLARATIONS_ONLY"
            and hwh["modules"][0]["address_ranges"][0]["span"] == 65536,
            "HWH declaration example mismatch")
    lifecycle = json.loads(run_python([dma / "examples" / "lifecycle.py"]).stdout)
    require(lifecycle["scope"] == "MOCK_LIFECYCLE_ONLY" and lifecycle["released"],
            "DMA lifecycle example mismatch")
    print("PASS pynq_examples=hwh_declarations,mock_lifecycle ps_native=optional_numpy")
    template = json.loads(run_python([accelerator / "scripts/validate_template.py"]).stdout)
    require(template["scope"] == "HOST_SOURCE_SYNTAX_ONLY" and template["hardware"] == "NOT_RUN",
            "accelerator template scope mismatch")
    print("PASS template_syntax python={} notebook_cells={} tcl={} vendor_tools=NOT_RUN".format(
        template["python_files"], template["notebook_code_cells"], template["tcl_files"]))
    original = json.loads(run_python([
        perf / "scripts" / "analyze.py", perf / "examples" / "performance.jsonl",
        "--contract", perf / "references" / "project-perf-contract.json"]).stdout)
    require(original["valid_windows"] == 1 and original["last_window"]["from_report"] == 24
            and original["last_window"]["to_report"] == 25
            and len(original["last_window"]["stages"]) == 25,
            "historical cumulative example mismatch")
    audio = json.loads(run_python([
        perf / "scripts" / "analyze.py", perf / "examples" / "audio-performance.jsonl",
        "--contract", perf / "examples" / "audio-contract.json"]).stdout)
    require(audio["valid_windows"] == 1 and all(
        stage["mean_ms"] == 3.0 for stage in audio["last_window"]["stages"].values()),
        "audio transfer example mismatch")
    layout = json.loads(run_python([
        dma / "scripts" / "check_layout.py", dma / "examples" / "layout.json"]).stdout)
    require(layout["status"] == "PASS_STATIC_DESCRIPTION" and layout["buffers"] == 3,
            "DMA example mismatch")
    print("PASS fixtures=3 historical_25_nonmeta_stages=1 audio_transfer=1 padded_dma_layout=1")


def check_manifest(root):
    manifest = root.parent / "manifest.json"
    if not manifest.is_file():
        print("SKIP manifest (source-tree mode)")
        return
    data = json.loads(manifest.read_text(encoding="utf-8"))
    require(data.get("schema") == "skill-package-manifest-v1", "unknown manifest schema")
    actual = {path.relative_to(root.parent).as_posix(): path
              for path in source_files(root.parent) if path != manifest}
    declared = {row["path"]: row for row in data["files"]}
    require(len(declared) == len(data["files"]), "duplicate manifest paths")
    require(set(actual) == set(declared), "manifest inventory mismatch")
    for name, path in actual.items():
        row = declared[name]
        require(row["size"] == path.stat().st_size and row["sha256"] == digest(path),
                "manifest checksum mismatch: " + name)
    print("PASS manifest_files=" + str(len(actual)))


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("skill", nargs="?", type=Path, default=Path(__file__).resolve().parents[1])
    args = parser.parse_args(argv)
    root = args.skill.resolve()
    try:
        require(root.is_dir() and (root / "README.md").is_file(), "skill root not found")
        files = source_files(root)
        before = {path.relative_to(root).as_posix(): digest(path) for path in files}
        check_documents(root, files)
        check_examples(root)
        check_manifest(root)
        after = {path.relative_to(root).as_posix(): digest(path) for path in source_files(root)}
        require(before == after, "self-check modified package inputs")
        print("PASS input_files_unchanged=1 scope=offline_skill_package")
    except (OSError, ValueError, KeyError, TypeError) as error:
        print("FAIL: " + str(error), file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
