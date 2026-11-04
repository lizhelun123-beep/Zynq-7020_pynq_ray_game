"""以当前系统和实际隔离/加载/退休证据完成固定version14板端准入。"""
import argparse
import csv
import ctypes as C
import hashlib
import io
import json
import mmap
import os
from pathlib import Path
import platform
import signal
import stat
import struct
import sys
import time
import uuid
import zipfile

HARDWARE = 'output/build/game_app/pynq_beam_hardware_5'
ORIGINAL_GATE = '203868770d3b0829a628db870ff17faa4a90d4d08e87736dfb43c4f833387ce5'
VERSION = '20261102-v1-isolated-bootstrap'


def digest(data):
    return hashlib.sha256(data).hexdigest()


def require(condition, message):
    if not condition:
        raise RuntimeError(message)


def payload(name):
    with zipfile.ZipFile(str(Path(sys.argv[0]).resolve())) as archive:
        return archive.read(name)


def atomic_write(path, data, mode=0o600, owner=None):
    temporary = path.with_name('.' + path.name + '.' + uuid.uuid4().hex)
    descriptor = os.open(str(temporary), os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW, mode)
    try:
        with os.fdopen(descriptor, 'wb') as stream:
            stream.write(data)
            stream.flush()
            os.fsync(stream.fileno())
        os.chmod(str(temporary), mode)
        if owner is not None:
            os.chown(str(temporary), owner[0], owner[1])
        os.replace(str(temporary), str(path))
    except BaseException:
        if temporary.exists():
            temporary.unlink()
        raise


def protected_directory(path):
    path.mkdir(mode=0o700, parents=True, exist_ok=True)
    info = path.lstat()
    require(stat.S_ISDIR(info.st_mode) and info.st_uid == 0 and not info.st_mode & 0o022,
            'expected protected root-owned directory: ' + str(path))


def checkpoint(report, stage):
    # 在设备访问前保存本轮目标阶段，进程异常退出时仍可定位最后一次访问。
    report['stage'] = stage
    if report.get('attempt_path'):
        atomic_write(Path(report['attempt_path']),
                     (json.dumps(report, indent=2) + '\n').encode('utf-8'))
    print('BEAM_ADMISSION ' + stage, flush=True)


def install_gate(app):
    target = app / 'pynq_vision/beam_admission.py'
    new = payload('beam_admission.new')
    current = target.read_bytes()
    if digest(current) == digest(new):
        return {'changed': False, 'sha256': digest(new)}
    require(digest(current) == ORIGINAL_GATE, 'admission source has unrelated changes; preserving it')
    info = target.lstat()
    require(stat.S_ISREG(info.st_mode) and info.st_nlink == 1, 'unsafe admission source')
    table = app / 'FILES.tsv'
    table_info = table.lstat()
    require(stat.S_ISREG(table_info.st_mode) and table_info.st_nlink == 1, 'unsafe runtime inventory')
    old_table = table.read_bytes()
    rows = list(csv.DictReader(io.StringIO(old_table.decode('utf-8')), delimiter='\t'))
    matches = [row for row in rows if row['path'] == 'pynq_vision/beam_admission.py']
    require(len(matches) == 1 and matches[0]['sha256'] == ORIGINAL_GATE, 'runtime inventory differs')
    matches[0]['sha256'], matches[0]['bytes'] = digest(new), str(len(new))
    output = io.StringIO()
    writer = csv.DictWriter(output, fieldnames=['path', 'bytes', 'sha256'], delimiter='\t', lineterminator='\n')
    writer.writeheader()
    writer.writerows(rows)
    directory = Path('/root/beam_v14_setup_backups')
    protected_directory(directory)
    backup = directory / ('admission-' + uuid.uuid4().hex)
    backup.mkdir(mode=0o700)
    (backup / 'beam_admission.before').write_bytes(current)
    (backup / 'FILES.before').write_bytes(old_table)
    changed = False
    try:
        atomic_write(target, new, stat.S_IMODE(info.st_mode), (info.st_uid, info.st_gid))
        changed = True
        atomic_write(table, output.getvalue().encode('utf-8'), stat.S_IMODE(table_info.st_mode),
                     (table_info.st_uid, table_info.st_gid))
    except BaseException:
        if changed:
            atomic_write(target, current, stat.S_IMODE(info.st_mode), (info.st_uid, info.st_gid))
            atomic_write(table, old_table, stat.S_IMODE(table_info.st_mode),
                         (table_info.st_uid, table_info.st_gid))
        raise
    return {'changed': True, 'sha256': digest(new), 'backup': str(backup)}


def dma_proof(read, capture):
    offset = 0x30 if capture else 0
    control, status = int(read(offset)), int(read(offset + 4))
    sample = {'control': control, 'status': status}
    require(not control & 1 and status & 1 and not status & 0x89f0,
            'fresh DMA not clean HALTED: ' + json.dumps(sample))
    return sample


def ps_snapshot(barrier):
    descriptor = os.open('/dev/mem', os.O_RDONLY | os.O_SYNC | os.O_CLOEXEC)
    try:
        with mmap.mmap(descriptor, 4096, flags=mmap.MAP_SHARED,
                       prot=mmap.PROT_READ, offset=0xF8000000) as memory:
            require(barrier() == 0, 'PS read barrier failed')
            snapshot = {'fpga_reset': struct.unpack_from('<I', memory, 0x240)[0],
                        'level_shifters': struct.unpack_from('<I', memory, 0x900)[0]}
            require(barrier() == 0, 'PS read barrier failed')
            return snapshot
    finally:
        os.close(descriptor)


def isolated(snapshot):
    return type(snapshot.get('level_shifters')) is int and snapshot['level_shifters'] & 0xf == 0


def make_records(record, boot, ps, channels, evidence_path, evidence_hash):
    # 记录只能使用调用方本次从硬件取得的完整通道数据，不能填入推测的HALTED值。
    require(isolated(ps), 'isolated bootstrap evidence required')
    for role in ('capture', 'display'):
        sample = channels[role]
        require(type(sample['control']) is int and type(sample['status']) is int,
                'DMA evidence must contain actual integer registers')
        dma_proof(lambda offset: sample['control'] if offset in (0, 0x30) else sample['status'],
                  role == 'capture')
    receipt = {'schema': 'beam-pynq-mmio-admission-v1', 'boot_id': boot,
               'bit_sha256': record['bit_sha256'], 'hwh_sha256': record['hwh_sha256'],
               'ps_reference_hz': record['ps_reference_hz'],
               'evidence_path': str(evidence_path), 'evidence_sha256': evidence_hash}
    return receipt


def qualify(app, gate, report):
    import fcntl
    bundle = app / HARDWARE
    record = gate.inspect_bundle(bundle / 'hardware.json', bundle / 'system_wrapper.bit',
                                 bundle / 'libbeam_pynq.so')
    boot = gate.platform_inputs(record, '/dev/i2c-0')
    gate.check_uart_available('/dev/ttyPS0')
    report['boot_id'] = boot
    descriptor = os.open('/run/lock/game_linux_display.lock',
                         os.O_RDWR | os.O_CREAT | os.O_CLOEXEC | os.O_NOFOLLOW, 0o600)
    lock_info = os.fstat(descriptor)
    require(stat.S_ISREG(lock_info.st_mode) and lock_info.st_uid == 0 and
            lock_info.st_nlink == 1 and not lock_info.st_mode & 0o077, 'unsafe hardware lock')
    device = None
    try:
        fcntl.flock(descriptor, fcntl.LOCK_EX | fcntl.LOCK_NB)
        from pynq_vision.beam_runtime import load_library
        library = load_library(bundle / 'libbeam_pynq.so')
        library.beam_pynq_barrier.argtypes = []
        library.beam_pynq_barrier.restype = C.c_int
        checkpoint(report, 'read_ps_isolation')
        first = ps_snapshot(library.beam_pynq_barrier)
        time.sleep(.01)
        second = ps_snapshot(library.beam_pynq_barrier)
        report['bootstrap_ps'] = {'first': first, 'second': second}
        require(first == second and isolated(second),
                'PL interface is not stably isolated; no PL access or programming performed')
        checkpoint(report, 'isolation_verified')
        require(not gate.conflicting_owners(), 'device owners appeared before programming')
        # 使用同一PYNQ MMIO/FPGA-manager路径，不构造Xlnk分配器或探测XRT。
        import pynq
        signal.signal(signal.SIGSEGV, signal.SIG_DFL)
        require(pynq.__version__ == '2.6.2', 'PYNQ version differs')
        from pynq.pl_server.device import Device, XlnkDevice
        class MmioDevice(XlnkDevice):
            def __init__(self):
                Device.__init__(self, 'beam_admission', server_type='local')
                self.capabilities = {'MEMORY_MAPPED': True}
                self.default_memory = None
        device = MmioDevice()
        Device.active_device = device
        pynq.Clocks._instance._ref_clk_mhz = record['ps_reference_hz'] / 1000000.0
        overlay = pynq.Overlay(str(bundle / 'system_wrapper.bit'), download=False, device=device)
        for name, values in record['addresses'].items():
            metadata = overlay.ip_dict.get(name)
            require(metadata and metadata['phys_addr'] == values[0] and metadata['addr_range'] == values[1],
                    'Overlay metadata mismatch: ' + name)
        # 装载前不读未知PL；已隔离的旧设计由FPGA-manager完整重配置。
        checkpoint(report, 'download_matched_overlay')
        overlay.download()
        report['overlay_timestamp'] = str(overlay.timestamp)
        clocks = [getattr(pynq.Clocks, 'fclk{}_mhz'.format(i)) for i in range(3)]
        report['clocks_mhz'] = clocks
        require(all(abs(a-b) < .1 for a,b in zip(clocks, record['fclk_mhz'])), 'loaded clocks differ')
        report['dma'] = {}
        for role, name in (('capture', 'axi_vdma_1'), ('display', 'axi_vdma_0')):
            checkpoint(report, 'read_' + role + '_dma')
            base, span = record['addresses'][name]
            io_object = pynq.MMIO(base, span, device=device)
            require(library.beam_pynq_barrier() == 0, 'DMA read barrier failed')
            report['dma'][role] = dma_proof(io_object.read, role == 'capture')
            del io_object
        base, span = record['addresses']['MIPI_CSI_2_RX_0']
        checkpoint(report, 'read_csi_version')
        csi = pynq.MMIO(base, span, device=device)
        version = int(csi.read(12))
        report['csi_version'] = version
        del csi
        require(version == 0x10001, 'loaded CSI ABI differs')
        require(Path('/proc/sys/kernel/random/boot_id').read_text().strip() == boot, 'boot changed')
        directory = Path('/run/beam_pynq')
        protected_directory(directory)
        evidence_path = directory / ('evidence-' + uuid.uuid4().hex + '.json')
        evidence = {'schema': 'beam-pynq-quiesced-v1', 'boot_id': boot,
                    'bit_sha256': record['bit_sha256'], 'hwh_sha256': record['hwh_sha256'],
                    'dma': report['dma'], 'bootstrap_ps': report['bootstrap_ps'],
                    'csi_version': version, 'clocks_mhz': clocks,
                    'overlay_timestamp': report['overlay_timestamp']}
        encoded = (json.dumps(evidence, indent=2) + '\n').encode('utf-8')
        receipt = make_records(record, boot, second, report['dma'], evidence_path, digest(encoded))
        atomic_write(evidence_path, encoded)
        atomic_write(directory / 'admission.json',
                     (json.dumps(receipt, indent=2) + '\n').encode('utf-8'))
        gate.validate_receipt(json.loads((directory / 'admission.json').read_text()), boot, record)
        require(gate.sha(evidence_path) == receipt['evidence_sha256'], 'stored evidence hash differs')
        report['admission'] = str(directory / 'admission.json')
        report['result'] = 'ADMITTED_FROM_ACTUAL_HARDWARE'
        checkpoint(report, 'complete')
    finally:
        if device is not None:
            device.close()
        os.close(descriptor)


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--version', action='version', version=VERSION)
    mode = parser.add_mutually_exclusive_group(required=True)
    mode.add_argument('--qualify', action='store_true')
    mode.add_argument('--test10', action='store_true')
    args = parser.parse_args(argv)
    require(sys.platform == 'linux' and platform.machine() == 'armv7l' and
            sys.version_info[:2] == (3,6) and os.geteuid() == 0, 'root ARMv7 Python3.6 required')
    app = Path(sys.argv[0]).resolve().parent
    sys.path.insert(0, str(app))
    report = {'version': VERSION, 'mode': 'qualify' if args.qualify else 'test10',
              'boot_id': Path('/proc/sys/kernel/random/boot_id').read_text().strip()}
    protected_directory(Path('/run/beam_pynq'))
    report['attempt_path'] = '/run/beam_pynq/attempt-' + uuid.uuid4().hex + '.json'
    try:
        checkpoint(report, 'check_inputs')
        report['gate_update'] = install_gate(app)
        from pynq_vision import beam_admission as gate
        if args.qualify:
            qualify(app, gate, report)
        else:
            checkpoint(report, 'run_at_most_ten_frames')
            from pynq_vision.beam_launcher import main as launch
            bundle = app / HARDWARE
            launch(['--manifest', str(bundle / 'hardware.json'), '--overlay', str(bundle / 'system_wrapper.bit'),
                    '--library', str(bundle / 'libbeam_pynq.so'), '--uart', '/dev/ttyPS0',
                    '--i2c-device', '/dev/i2c-0', '--run', '--frames', '10'])
            report['result'] = 'TEST10_RETURNED'
    except Exception as error:
        report['result'] = 'STOPPED'
        report['error'] = repr(error)
        checkpoint(report, report.get('stage', 'stopped'))
        print(json.dumps(report, ensure_ascii=False, indent=2), flush=True)
        return 1
    print(json.dumps(report, ensure_ascii=False, indent=2), flush=True)
    return 0


if __name__ == '__main__':
    sys.exit(main())
