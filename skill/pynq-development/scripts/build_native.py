"""Build with an EXISTING GCC/Clang C99 compiler;never downloads or installs."""
import argparse
import os
from pathlib import Path
import shutil
import subprocess


def compiler():
    return shutil.which("gcc") or shutil.which("clang")


def build(output, cc=None):
    output = Path(output).resolve()
    cc = cc or compiler()
    if not cc:
        raise RuntimeError("NOT_RUN: existing GCC/Clang compiler not found")
    if output.exists():
        raise FileExistsError("choose a new build directory")
    source = Path(__file__).resolve().parents[1] / "examples/native/bgr_reverse.c"
    output.mkdir(parents=True)
    library = output / ("bgr_reverse.dll" if os.name == "nt" else "libbgr_reverse.so")
    command = [cc, "-std=c99", "-O2", "-Wall", "-Wextra", "-Werror", "-shared"]
    if os.name != "nt":
        command.append("-fPIC")
    subprocess.run(command + [str(source), "-o", str(library)], check=True, timeout=60)
    return library


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--cc", help="existing compatible compiler executable")
    args = parser.parse_args()
    print(build(args.output, args.cc))
