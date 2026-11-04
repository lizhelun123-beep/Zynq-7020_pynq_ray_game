"""Build a standalone deterministic skill package; Python 3.8+, standard library only."""

import argparse
import hashlib
import json
import shutil
import subprocess
import sys
import zipfile
from pathlib import Path


def sha256(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def files(root):
    return sorted(p for p in root.rglob("*") if p.is_file() and p.name != "manifest.json")


def write_manifest(package):
    rows = [{"path": p.relative_to(package).as_posix(), "size": p.stat().st_size,
             "sha256": sha256(p)} for p in files(package)]
    data = {"schema": "skill-package-manifest-v1", "package": "amd-camera-skill-package",
            "version": "2026-10-28", "files": rows}
    (package / "manifest.json").write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n",
                                            encoding="utf-8", newline="\n")


def run_verify(package):
    verifier = package / "skill" / "scripts" / "verify_package.py"
    return subprocess.run([sys.executable, "-B", str(verifier), str(package / "skill")],
                          capture_output=True, text=True, encoding="utf-8")


def build(source, destination):
    source = source.resolve()
    destination = destination.resolve()
    if destination == source or source in destination.parents:
        raise ValueError("destination must be outside the source skill directory")
    if destination.exists():
        shutil.rmtree(destination)
    destination.mkdir(parents=True)
    shutil.copytree(source, destination / "skill")
    template = source / "references" / "package-root-readme.md"
    if not template.is_file():
        raise ValueError("missing package-root-readme.md")
    (destination / "README.md").write_text(template.read_text(encoding="utf-8"),
                                             encoding="utf-8", newline="\n")
    (destination / "verification.txt").write_text("", encoding="utf-8", newline="\n")
    write_manifest(destination)
    for _ in range(4):
        result = run_verify(destination)
        if result.returncode:
            raise RuntimeError(result.stdout + result.stderr)
        current = (destination / "verification.txt").read_text(encoding="utf-8")
        if current == result.stdout:
            write_manifest(destination)
            final = run_verify(destination)
            if final.returncode or final.stdout != result.stdout:
                raise RuntimeError(final.stdout + final.stderr)
            break
        (destination / "verification.txt").write_text(result.stdout, encoding="utf-8", newline="\n")
        write_manifest(destination)
    else:
        raise RuntimeError("verification output did not stabilize")
    archive = destination.with_suffix(".zip")
    if archive.exists():
        archive.unlink()
    with zipfile.ZipFile(archive, "w", compression=zipfile.ZIP_DEFLATED, compresslevel=9) as output:
        for path in sorted(p for p in destination.rglob("*") if p.is_file()):
            info = zipfile.ZipInfo(path.relative_to(destination).as_posix(), (2026, 10, 28, 0, 0, 0))
            info.compress_type = zipfile.ZIP_DEFLATED
            info.external_attr = 0o644 << 16
            output.writestr(info, path.read_bytes())
    checksum = destination.with_suffix(".sha256")
    checksum.write_text("{}  {}\n".format(sha256(archive), archive.name), encoding="ascii", newline="\n")
    return archive, checksum, result.stdout


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source", type=Path, default=Path(__file__).resolve().parents[1])
    parser.add_argument("--destination", type=Path, required=True)
    args = parser.parse_args(argv)
    try:
        archive, checksum, output = build(args.source, args.destination)
    except (OSError, ValueError, RuntimeError) as error:
        print("FAIL: " + str(error), file=sys.stderr)
        return 1
    print("PACKAGE=" + str(args.destination.resolve()))
    print("ZIP=" + str(archive.resolve()))
    print("SHA256=" + sha256(archive))
    print(output, end="")
    print("CHECKSUM_FILE=" + str(checksum.resolve()))
    return 0


if __name__ == "__main__":
    sys.exit(main())
