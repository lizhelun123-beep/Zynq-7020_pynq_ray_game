"""Import this module only in the explicitly authorized target-board stage."""
from pynq import DefaultIP, Overlay
from .core import AddBiasSession
from .bundle import validate_description


class AddBiasDriver(DefaultIP):
    bindto = ["example.org:hls:add_bias:1.0"]

    def __init__(self, description):
        validate_description(description)
        super().__init__(description=description)
        self.session = AddBiasSession(self, getattr(self, "interrupt", None))

    def add(self, x, bias, timeout=1.0):
        return self.session.add(x, bias, timeout)

    async def add_async(self, x, bias, timeout=1.0):
        return await self.session.add_async(x, bias, timeout)


_active = None
_load_uncertain = False


def open_board(bitfile, ip_name, file_identity):
    """Caller first validates bundle/exclusive PL ownership and authorizes download."""
    global _active, _load_uncertain
    if _load_uncertain:
        raise RuntimeError("previous Overlay load uncertain;re-establish PL ownership before retry")
    key = (str(bitfile), ip_name, file_identity)
    if _active is not None and _active[2].session.state != "closed":
        if _active[0] != key:
            raise RuntimeError("close the existing owner before loading another Overlay")
        return _active[2]
    _load_uncertain = True
    overlay = Overlay(str(bitfile))
    _active = (key, overlay, None)
    ip = overlay
    for part in ip_name.strip("/").split("/"):
        ip = getattr(ip, part)
    if not isinstance(ip, AddBiasDriver):
        raise RuntimeError("VLNV driver binding mismatch")
    _active = (key, overlay, ip)
    _load_uncertain = False
    return ip
