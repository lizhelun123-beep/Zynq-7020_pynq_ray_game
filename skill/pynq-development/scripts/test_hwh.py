"""Offline HWH declaration extraction, failure and read-only CLI behavior."""
import hashlib
import io
from pathlib import Path
import tempfile
import unittest
from contextlib import redirect_stderr, redirect_stdout
from inspect_hwh import inspect, main, MAX_BYTES

EXAMPLE = Path(__file__).resolve().parents[1] / "examples/synthetic.hwh"


class HwhTests(unittest.TestCase):
    def data(self):
        return EXAMPLE.read_bytes()

    def test_module_parameters_and_range_are_declarations_only(self):
        data = self.data()
        result = inspect(data, "/demo_dma")
        self.assertEqual(result["scope"], "OFFLINE_DECLARATIONS_ONLY")
        self.assertEqual(result["sha256"], hashlib.sha256(data).hexdigest())
        module = result["modules"][0]
        self.assertEqual(module["vlnv"], "xilinx.com:ip:axi_dma:7.1")
        self.assertEqual(module["parameters"]["C_INCLUDE_SG"], "0")
        self.assertEqual(module["address_ranges"][0]["span"], 65536)
        self.assertTrue(result["not_proven"])

    def test_missing_exact_ip_and_unsupported_schema_rejected(self):
        for data, ip in [(self.data(), "wrong"), (b"<OTHER/>", None),
                          (b"<SYSTEM/>", None)]:
            with self.subTest(ip=ip), self.assertRaises(ValueError):
                inspect(data, ip)

    def test_duplicates_and_invalid_ranges_rejected(self):
        original = self.data()
        module = original.split(b"<MODULE INSTANCE", 1)[1].split(b"</MODULE>", 1)[0]
        duplicate = original.replace(b"</MODULES>", b"<MODULE INSTANCE" + module + b"</MODULE></MODULES>")
        for data in [duplicate, original.replace(b'VALUE="0"', b'VALUE="0"/><PARAMETER NAME="C_INCLUDE_SG" VALUE="1"', 1),
                     original.replace(b"0x4000ffff", b"0x00000001")]:
            with self.subTest(data=data[:30]), self.assertRaises(ValueError):
                inspect(data)

    def test_multiple_windows_preserved_not_guessed(self):
        extra = b'<MEMRANGE INSTANCE="demo_dma" BASEVALUE="0x50000000" HIGHVALUE="0x5000ffff"/>'
        result = inspect(self.data().replace(b"</MEMRANGES>", extra + b"</MEMRANGES>"))
        self.assertEqual(len(result["modules"][0]["address_ranges"]), 2)

    def test_dtd_utf16_and_oversize_rejected(self):
        for data in [b'<!DOCTYPE SYSTEM [<!ENTITY x "x">]><SYSTEM/>',
                     "<SYSTEM/>".encode("utf-16"), b" " * (MAX_BYTES + 1)]:
            with self.subTest(size=len(data)), self.assertRaises((ValueError, UnicodeError)):
                inspect(data)

    def test_cli_reads_input_without_changes_and_reports_missing_file(self):
        before = self.data()
        with redirect_stdout(io.StringIO()):
            self.assertEqual(main([str(EXAMPLE), "--ip", "demo_dma"]), 0)
        self.assertEqual(before, self.data())
        with tempfile.TemporaryDirectory() as tmp, redirect_stderr(io.StringIO()):
            self.assertEqual(main([str(Path(tmp) / "absent.hwh")]), 1)


if __name__ == "__main__":
    unittest.main()
