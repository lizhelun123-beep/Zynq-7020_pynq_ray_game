"""Target-only module;Overlay download requires current-task authorization."""
from pynq import DefaultIP, Overlay
from .core import Session
from .artifacts import VLNV, validate_bundle


class Add32IP(DefaultIP):
    bindto = [VLNV]

    def __init__(self, description):
        address, span = description.get('phys_addr'), description.get('addr_range')
        if description.get('type') != VLNV or type(address) is not int or type(span) is not int or address <= 0 or address % 4 or span < 32 or address + span > 1 << 32:
            raise ValueError('unsupported IP identity/address range')
        super().__init__(description=description)
        self.session = Session(self, getattr(self, 'interrupt', None))

    def add(self, a, b, timeout=.1):
        return self.session.add(a, b, timeout)

    async def add_async(self, a, b, timeout=.1):
        return await self.session.add_async(a, b, timeout)


_owner = None
_load_uncertain = False


def open_board(directory):
    global _owner, _load_uncertain
    bundle = validate_bundle(directory)
    key = (bundle['directory'], bundle['file_identity'])
    if _load_uncertain:
        raise RuntimeError('previous load uncertain;re-establish exclusive PL ownership before retry')
    if _owner is not None and _owner[2].session.state != 'closed':
        if _owner[0] != key:
            raise RuntimeError('close previous owner before changing Overlay')
        return _owner[2]
    _load_uncertain = True
    overlay = Overlay(bundle['directory'] + '/system.bit')
    _owner = (key, overlay, None)
    ip = overlay.add32_0
    if not isinstance(ip, Add32IP):
        raise RuntimeError('DefaultIP binding mismatch')
    _owner = (key, overlay, ip)
    _load_uncertain = False
    return ip
