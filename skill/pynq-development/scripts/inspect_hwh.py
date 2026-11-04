"""Extract common HWH declarations without PYNQ/device initialization."""
import argparse
import hashlib
import json
from pathlib import Path
import sys
from xml.etree import ElementTree as ET

MAX_BYTES = 8 * 1024 * 1024


def inspect(data, ip=None):
    if len(data) > MAX_BYTES:
        raise ValueError("HWH exceeds 8 MiB limit")
    text = data.decode("utf-8-sig")
    if "<!DOCTYPE" in text.upper() or "<!ENTITY" in text.upper():
        raise ValueError("DTD/entities not accepted")
    root = ET.fromstring(text)
    if root.tag != "SYSTEM":
        raise ValueError("unsupported HWH root; expected unnamespaced SYSTEM")
    modules, instances = {}, {}
    for element in root.findall(".//MODULE"):
        name = element.get("FULLNAME", "").lstrip("/")
        instance, vlnv = element.get("INSTANCE"), element.get("VLNV")
        if not name or not instance or not vlnv or name in modules:
            raise ValueError("missing or duplicate module identity")
        parameters = {}
        for parameter in element.findall("./PARAMETERS/PARAMETER"):
            key, value = parameter.get("NAME"), parameter.get("VALUE")
            if not key or value is None or key in parameters:
                raise ValueError("invalid or duplicate parameter: " + name)
            parameters[key] = value
        modules[name] = dict(name=name, instance=instance, vlnv=vlnv,
                             parameters=parameters, address_ranges=[])
        instances.setdefault(instance, []).append(name)
    if not modules:
        raise ValueError("no MODULE declarations")
    if ip is not None and ip.lstrip("/") not in modules:
        raise ValueError("requested FULLNAME not found: " + ip)
    unknown_ranges = 0
    for element in root.findall(".//MEMRANGE"):
        names = instances.get(element.get("INSTANCE"), [])
        if not names:
            unknown_ranges += 1
            continue
        if len(names) != 1:
            raise ValueError("ambiguous MEMRANGE INSTANCE")
        base = int(element.attrib["BASEVALUE"], 16)
        high = int(element.attrib["HIGHVALUE"], 16)
        if not 0 <= base <= high < 2 ** 64:
            raise ValueError("invalid MEMRANGE address interval")
        modules[names[0]]["address_ranges"].append(dict(
            base=base, high=high, span=high - base + 1,
            master_bus=element.get("MASTERBUSINTERFACE"),
            slave_bus=element.get("SLAVEBUSINTERFACE")))
    chosen = [modules[ip.lstrip("/")]] if ip is not None else list(modules.values())
    return dict(scope="OFFLINE_DECLARATIONS_ONLY", sha256=hashlib.sha256(data).hexdigest(),
                modules=chosen, unmapped_memranges=unknown_ranges,
                not_proven=["BIT/HWH build pairing and loaded device identity",
                            "PS-visible address selection, clocks, resets and interrupts",
                            "Driver compatibility, DMA/cache behavior or hardware performance"])


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("hwh", type=Path)
    parser.add_argument("--ip", help="Exact FULLNAME, not a guessed leaf name")
    args = parser.parse_args(argv)
    try:
        with args.hwh.open("rb") as stream:
            data = stream.read(MAX_BYTES + 1)
        result = inspect(data, args.ip)
    except (OSError, ValueError, KeyError, UnicodeError, ET.ParseError) as error:
        print("HWH rejected: " + str(error), file=sys.stderr)
        return 1
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    sys.exit(main())
