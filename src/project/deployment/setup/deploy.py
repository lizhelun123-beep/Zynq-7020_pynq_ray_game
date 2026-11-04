"""备份并配置已授权的固定网口与串口控制台，保留当前启动和设备占用证据。"""
import argparse
import hashlib
import json
import os
from pathlib import Path
import platform
import re
import stat
import sys
import time
import uuid

from prepare_console import patch as patch_boot

BOOT_ORIGINAL = '03e395686fe2e059f45b03ec072034915918c3caf16477e2f7868a1f274de6b7'
BOOT_CANDIDATE = '8e4a66ca8e565712017cdfc03a6eb8b7266b1152e8bd7fa7ac872a524a0002ca'
HARDWARE = 'output/build/game_app/pynq_beam_hardware_5'
MARKERS = ('/dev/mem', '/dev/xlnk', '/dev/uio', '/dev/dri/', '/dev/fb')
VERSION = '20261102-v2-factory-eth0-alias'


def digest(data):
    return hashlib.sha256(data).hexdigest()


def read_text(path):
    try:
        return path.read_text(encoding='utf-8', errors='replace').strip()
    except OSError as error:
        return {'read_error': str(error)}


def network_candidate(raw):
    text = raw.decode('utf-8')
    lines = text.splitlines(keepends=True)
    active = [' '.join(line.split('#', 1)[0].split()) for line in lines]
    active = [line for line in active if line]
    previous = ['auto eth0', 'iface eth0 inet dhcp']
    desired = ['auto eth0', 'iface eth0 inet static', 'address 192.168.2.99',
               'netmask 255.255.255.0']
    factory = ['auto eth0', 'iface eth0 inet dhcp', 'auto eth0:1',
               'iface eth0:1 inet static', 'address 192.168.2.99',
               'netmask 255.255.255.0']
    # 镜像的静态别名已提供直连地址，原样保留可避免无必要地改动网口。
    if active == desired or active == factory:
        return raw
    if active != previous:
        directives = [' '.join(line.split()[:4]) if line.startswith('iface ') else line.split()[0]
                      for line in active]
        raise ValueError('eth0 differs from reviewed profiles; preserving original file; '
                         'sha256=' + digest(raw) + '; directives=' + repr(directives))
    # 保留原文件的注释，只修改已确认的DHCP段落并补入直连地址。
    output = []
    for line in lines:
        if ' '.join(line.split('#', 1)[0].split()) == previous[1]:
            comment = (' #' + line.split('#', 1)[1].rstrip()) if '#' in line else ''
            output += ['iface eth0 inet static' + comment + '\n',
                       '    address 192.168.2.99\n', '    netmask 255.255.255.0\n']
        else:
            output.append(line)
    return ''.join(output).encode('utf-8')


def regular_file(path):
    info = path.lstat()
    if not stat.S_ISREG(info.st_mode) or info.st_nlink != 1:
        raise ValueError('expected independent regular file: ' + str(path))
    return info


def replace_file(path, data, mode):
    # 暂存文件与目标同一目录，写入落盘后替换，避免留下半份启动脚本。
    temporary = path.with_name('.' + path.name + '.beam-' + uuid.uuid4().hex)
    descriptor = os.open(str(temporary), os.O_WRONLY | os.O_CREAT | os.O_EXCL, mode)
    try:
        with os.fdopen(descriptor, 'wb') as stream:
            stream.write(data)
            stream.flush()
            os.fsync(stream.fileno())
        os.chmod(str(temporary), mode)
        os.replace(str(temporary), str(path))
    except BaseException:
        if temporary.exists():
            temporary.unlink()
        raise


def install_configs(system=Path('/')):
    boot_id = (system / 'proc/sys/kernel/random/boot_id').read_text().strip()
    if str(uuid.UUID(boot_id)) != boot_id:
        raise ValueError('current boot_id is not valid')
    cmdline = (system / 'proc/cmdline').read_text().strip()
    paths = {'network': system / 'etc/network/interfaces.d/eth0',
             'boot': system / 'boot/boot.scr'}
    metadata = {name: regular_file(path) for name, path in paths.items()}
    before = {name: path.read_bytes() for name, path in paths.items()}
    boot_sha = digest(before['boot'])
    if boot_sha == BOOT_ORIGINAL:
        new_boot, unused = patch_boot(before['boot'], cmdline)
        if digest(new_boot) != BOOT_CANDIDATE:
            raise ValueError('current kernel arguments differ from reviewed boot candidate')
    elif boot_sha == BOOT_CANDIDATE:
        new_boot = before['boot']
    else:
        raise ValueError('boot.scr is neither reviewed original nor reviewed candidate')
    after = {'network': network_candidate(before['network']), 'boot': new_boot}
    changed = [name for name in paths if before[name] != after[name]]
    if not changed:
        return {'changed': [], 'boot_id': boot_id, 'reboot_performed': False}
    base = system / 'root/beam_v14_setup_backups'
    if base.exists() and (base.is_symlink() or not base.is_dir()):
        raise ValueError('unsafe backup directory')
    base.mkdir(mode=0o700, parents=True, exist_ok=True)
    if os.name == 'posix':
        info = base.stat()
        if info.st_uid != 0 or info.st_mode & 0o022:
            raise ValueError('backup directory must be protected and root-owned')
    backup = base / (time.strftime('%Y%m%dT%H%M%SZ', time.gmtime()) + '-' + uuid.uuid4().hex[:8])
    backup.mkdir(mode=0o700)
    record = {'boot_id': boot_id, 'reboot_performed': False, 'applied': False, 'files': {}}
    for name, path in paths.items():
        saved = backup / (name + '.before')
        descriptor = os.open(str(saved), os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
        with os.fdopen(descriptor, 'wb') as stream:
            stream.write(before[name])
            stream.flush()
            os.fsync(stream.fileno())
        record['files'][name] = {'target': str(path), 'backup': saved.name,
            'before_sha256': digest(before[name]), 'after_sha256': digest(after[name]),
            'mode': stat.S_IMODE(metadata[name].st_mode)}
    journal = backup / 'record.json'
    journal.write_text(json.dumps(record, indent=2) + '\n', encoding='utf-8')
    written = []
    try:
        for name in changed:
            if paths[name].read_bytes() != before[name]:
                raise ValueError('target changed after backup: ' + name)
            regular_file(paths[name])
            replace_file(paths[name], after[name], record['files'][name]['mode'])
            written.append(name)
            if paths[name].read_bytes() != after[name]:
                raise ValueError('write verification failed: ' + name)
        record['applied'] = True
        journal.write_text(json.dumps(record, indent=2) + '\n', encoding='utf-8')
    except BaseException:
        # 配置写入失败时恢复本轮已改文件；完整备份仍保留。
        for name in reversed(written):
            replace_file(paths[name], before[name], record['files'][name]['mode'])
        raise
    return {'changed': changed, 'backup': str(backup), 'boot_id': boot_id,
            'installed_boot_sha256': digest(after['boot']), 'reboot_performed': False}


def owner_details(proc=Path('/proc')):
    result = []
    for process in sorted(proc.iterdir()):
        if not process.name.isdigit():
            continue
        try:
            first_stat = (process / 'stat').read_text()
            start = first_stat.rsplit(')', 1)[1].split()[19]
            paths = {}
            for descriptor in (process / 'fd').iterdir():
                try:
                    target = os.readlink(str(descriptor))
                    if any(marker in target for marker in MARKERS):
                        paths[descriptor.name] = target
                except FileNotFoundError:
                    pass
            mappings = [line for line in (process / 'maps').read_text().splitlines()
                        if any(marker in line for marker in MARKERS)]
            if not paths and not mappings:
                continue
            command = (process / 'cmdline').read_bytes().replace(b'\0', b' ').decode('utf-8', errors='replace')
            command = re.sub(r'(?i)((?:token|password|passwd|secret|api_key)[=\s]+)\S+',
                             r'\1[redacted]', command)
            current_stat = (process / 'stat').read_text()
            current_start = current_stat.rsplit(')', 1)[1].split()[19]
            result.append({'pid': int(process.name), 'start_ticks': start,
                           'identity_stable': start == current_start, 'cmdline': command.strip(),
                           'cgroup': read_text(process / 'cgroup'), 'fds': paths,
                           'device_maps': mappings[:64]})
        except (FileNotFoundError, ProcessLookupError):
            pass
    return result


def file_hashes(system):
    result = {}
    for name, relative in (('network', 'etc/network/interfaces.d/eth0'), ('boot', 'boot/boot.scr')):
        try:
            result[name] = digest((system / relative).read_bytes())
        except OSError as error:
            result[name] = {'read_error': str(error)}
    return result


def apply_with_report(report, system=Path('/')):
    before = file_hashes(system)
    try:
        report['configuration'] = install_configs(system)
    except (ValueError, OSError) as error:
        # 即使校验拒绝也保留已采集的占用者信息，并按实际哈希判断文件是否变化。
        after = file_hashes(system)
        report['configuration'] = {'error': str(error), 'files_unchanged': before == after,
                                   'before_sha256': before, 'after_sha256': after}
        return 2
    report['eth0_config_after'] = read_text(system / 'etc/network/interfaces.d/eth0')
    return 0


def audit(app, system=Path('/')):
    report = {'boot_id': read_text(system / 'proc/sys/kernel/random/boot_id'),
              'consoles': read_text(system / 'proc/consoles'),
              'cmdline': read_text(system / 'proc/cmdline'),
              'eth0_config': read_text(system / 'etc/network/interfaces.d/eth0'),
              'device_owners': owner_details(system / 'proc'),
              'fpga_state': read_text(system / 'sys/class/fpga_manager/fpga0/state'),
              'admission_exists': (system / 'run/beam_pynq/admission.json').is_file(),
              'pl_mmio_accesses': 0, 'reboot_performed': False}
    bundle = app / HARDWARE
    from pynq_vision.beam_admission import inspect_bundle
    inspected = inspect_bundle(bundle / 'hardware.json', bundle / 'system_wrapper.bit',
                               bundle / 'libbeam_pynq.so')
    report['bundle_version'] = inspected['version']
    return report


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--version', action='version', version=VERSION)
    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument('--audit', action='store_true')
    group.add_argument('--apply-config', action='store_true')
    args = parser.parse_args(argv)
    if (sys.platform != 'linux' or platform.machine() != 'armv7l' or
            platform.release() != '5.4.0-xilinx-v2020.1' or
            sys.version_info[:2] != (3, 6) or os.geteuid() != 0):
        parser.error('requires root on the confirmed ARMv7 Python3.6 board')
    terminal = os.ttyname(0)
    if not terminal.startswith('/dev/pts/'):
        parser.error('run from the established SSH terminal, not business UART')
    app = Path(sys.argv[0]).resolve().parent
    sys.path.insert(0, str(app))
    report = audit(app)
    report['deployment_version'] = VERSION
    code = 0
    if args.apply_config:
        code = apply_with_report(report)
    report['terminal'] = terminal
    print(json.dumps(report, ensure_ascii=False, indent=2))
    return code


if __name__ == '__main__':
    sys.exit(main())
