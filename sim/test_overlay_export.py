"""Negative checks for source/artifact binding and software-facing metadata."""
import json
from pathlib import Path
import sys
import tempfile
import unittest
import struct
import zipfile

sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'build'))
import export_overlay as export


def hwh(base='0x43000000', width='64', revision='1'):
    return ('<EDKSYSTEM><MODULES><MODULE INSTANCE="axi_vdma_0"><PARAMETERS>'
            '<PARAMETER NAME="DATA_WIDTH" VALUE="'+width+'"/></PARAMETERS>'
            '<MEMRANGES><MEMRANGE BASEVALUE="'+base+'" HIGHVALUE="0x4300FFFF"/></MEMRANGES></MODULE>'
            '<MODULE INSTANCE="MIPI_CSI_2_RX_0"><PARAMETERS>'
            '<PARAMETER NAME="kVersionMinor" VALUE="'+revision+'"/></PARAMETERS></MODULE>'
            '</MODULES><EXTERNALPORTS><PORT NAME="cam_gpio_tri_o" DIR="O" LEFT="0" RIGHT="0"/>'
            '</EXTERNALPORTS></EDKSYSTEM>').encode()


class OverlayBindingTests(unittest.TestCase):
    def test_xsa_bit_timestamp_difference_is_preserved_and_delivered_byte_exact(self):
        def bit(time, payload):
            field=lambda data:struct.pack('>H',len(data))+data
            raw=field(b'\x0f\xf0')+field(b'a')
            raw+=field(b'system_wrapper\x00')+b'b'+field(b'7z020clg400\x00')
            raw+=b'c'+field(b'2026/11/03\x00')+b'd'+field(time.encode()+b'\x00')
            return raw+b'e'+struct.pack('>I',len(payload))+payload
        with tempfile.TemporaryDirectory() as temporary:
            directory=Path(temporary)
            initial,canonical=bit('05:32:36',b'actual_configuration'),bit('05:32:51',b'actual_configuration')
            (directory/'system_wrapper.bit').write_bytes(initial)
            with zipfile.ZipFile(directory/'system_wrapper.xsa','w') as archive:
                archive.writestr('system_wrapper.bit',canonical)
                archive.writestr('system.hwh','<EDKSYSTEM/>')
            preserved=directory/'initial_bitgen.bit'
            result=export.canonicalize_xsa_bit(directory,preserved)
            self.assertEqual((directory/'system_wrapper.bit').read_bytes(),canonical)
            self.assertEqual(preserved.read_bytes(),initial)
            self.assertEqual(result['configuration_payload_byte_identity'],'PASS')
            # A real configuration mismatch must never be hidden as metadata.
            (directory/'system_wrapper.bit').write_bytes(bit('05:32:51',b'different_configuration'))
            with self.assertRaisesRegex(ValueError,'configuration payload differs'):
                export.canonicalize_xsa_bit(directory,directory/'another.bit')

    def test_failed_parent_timing_cannot_export(self):
        with tempfile.TemporaryDirectory() as temporary:
            parent=Path(temporary)
            (parent/'build.json').write_text(json.dumps({'status':'REPORTS_COMPLETE','timing_status':'FAIL'}))
            with self.assertRaisesRegex(ValueError,'timing-passing'):
                export.validate_parent(parent,parent)

    def test_changed_parent_manifest_cannot_export(self):
        with tempfile.TemporaryDirectory() as temporary:
            parent=Path(temporary)
            (parent/'build.json').write_text(json.dumps({'status':'REPORTS_COMPLETE','timing_status':'PASS',
                                                       'input_manifest_sha256':'wrong'}))
            (parent/'input_manifest.tsv').write_text('modified')
            with self.assertRaisesRegex(ValueError,'Parent manifest changed'):
                export.validate_parent(parent,parent)

    def test_address_remap_is_rejected(self):
        with self.assertRaisesRegex(ValueError,'Address map'):
            export.compare_interfaces(hwh(),hwh(base='0x44000000'))

    def test_dma_data_width_change_is_rejected(self):
        with self.assertRaisesRegex(ValueError,'PS/VDMA'):
            export.compare_interfaces(hwh(),hwh(width='32'))

    def test_ip_parameter_change_is_reported_without_board_qualification(self):
        result=export.compare_interfaces(hwh(),hwh(revision='2'))
        self.assertEqual(result['parameter_differences']['MIPI_CSI_2_RX_0']['kVersionMinor'],
                         {'old':'1','new':'2'})
        self.assertIn('not register-semantics or board-functional qualification',result['scope'])


if __name__=='__main__':
    unittest.main()
