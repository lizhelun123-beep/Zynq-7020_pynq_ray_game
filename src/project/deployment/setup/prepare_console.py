"""在主机生成可复核的串口控制台迁移候选文件，不修改真实SD卡。"""
import hashlib
from pathlib import Path
import re
import shlex
import struct
import zlib

HEADER = struct.Struct('>7I4B32s')
ORIGINAL_SHA256 = '03e395686fe2e059f45b03ec072034915918c3caf16477e2f7868a1f274de6b7'
CMDLINE = ('root=/dev/mmcblk0p2 rw earlyprintk rootfstype=ext4 rootwait '
           'devtmpfs.mount=1 uio_pdrv_genirq.of_id="generic-uio" clk_ignore_unused')


def decode(raw):
    if len(raw) < HEADER.size + 8:
        raise ValueError('short legacy script')
    header = list(HEADER.unpack_from(raw))
    check = bytearray(raw[:HEADER.size])
    check[4:8] = b'\0' * 4
    if (header[0] != 0x27051956 or header[9] != 6 or
            zlib.crc32(check) & 0xffffffff != header[1]):
        raise ValueError('legacy script header/type/CRC mismatch')
    data = raw[HEADER.size:]
    if len(data) != header[3] or zlib.crc32(data) & 0xffffffff != header[6]:
        raise ValueError('legacy script payload length/CRC mismatch')
    size, end = struct.unpack_from('>II', data)
    if end != 0 or size != len(data) - 8:
        raise ValueError('only one complete script is supported')
    return header, data[8:].decode('utf-8')


def console_arguments(cmdline):
    # 保留已确认的根文件系统和驱动参数，只替换控制台及串口登录启动项。
    words = shlex.split(cmdline)
    if 'root=/dev/mmcblk0p2' not in words:
        raise ValueError('unexpected root filesystem')
    words = [w for w in words if not w.startswith(('console=', 'earlycon=', 'earlyprintk=',
                                                   'systemd.mask=serial-getty@ttyPS0'))
             and w not in ('earlycon', 'earlyprintk')]
    if any(not re.fullmatch(r'[A-Za-z0-9_./:@,=+\-]+', word) for word in words):
        raise ValueError('unreviewed kernel command-line characters')
    words += ['console=tty0', 'systemd.mask=serial-getty@ttyPS0.service']
    return ' '.join(words)


def patch(raw, cmdline):
    header, script = decode(raw)
    if script.count('\nfor boot_target in ') != 1 or re.search(r'^\s*setenv\s+bootargs\b', script, re.M):
        raise ValueError('unexpected boot script control flow')
    arguments = console_arguments(cmdline)
    script = script.replace('\nfor boot_target in ',
        '\nsetenv bootargs ' + shlex.quote(arguments) + ';\n\nfor boot_target in ', 1)
    body = script.encode('utf-8')
    payload = struct.pack('>II', len(body), 0) + body
    header[1], header[3], header[6] = 0, len(payload), zlib.crc32(payload) & 0xffffffff
    header[1] = zlib.crc32(HEADER.pack(*header)) & 0xffffffff
    result = HEADER.pack(*header) + payload
    decode(result)
    return result, script


def main():
    root = Path(__file__).resolve().parents[4]
    source = root / 'output/build/game_app/sd_autostart_1/sd_backup_20261025_1/boot.scr'
    raw = source.read_bytes()
    if hashlib.sha256(raw).hexdigest() != ORIGINAL_SHA256:
        raise ValueError('reference boot.scr changed')
    output = Path(__file__).resolve().parent
    updated, script = patch(raw, CMDLINE)
    for name, data in (('boot.scr.original', raw), ('boot.scr.candidate', updated),
                       ('boot_console.cmd', script.encode('utf-8'))):
        with (output / name).open('xb') as stream:
            stream.write(data)
    print('CANDIDATE_ONLY: original and candidate CRC verified; no board/SD writes')


if __name__ == '__main__':
    main()
