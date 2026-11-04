"""缩短固定板端工程的启动命令，并只读收集部署所需的实际系统信息。"""
import argparse
import hashlib
import json
import os
from pathlib import Path
import platform
import sys

HARDWARE = 'output/build/game_app/pynq_beam_hardware_5'


def read_text(path):
    try:
        return path.read_text(encoding='utf-8', errors='replace').strip()
    except OSError as error:
        return {'read_error': str(error)}


def fingerprint(path):
    try:
        digest = hashlib.sha256()
        with path.open('rb') as stream:
            for block in iter(lambda: stream.read(1024 * 1024), b''):
                digest.update(block)
        return {'bytes': path.stat().st_size, 'sha256': digest.hexdigest()}
    except OSError as error:
        return {'read_error': str(error)}


def ethernet_config(text):
    # 只输出有线接口的启动方式和地址，避免带出无线密码等无关配置。
    result, selected = [], False
    for line in text.splitlines():
        clean = line.split('#', 1)[0].strip()
        words = clean.split()
        if not words:
            continue
        if words[0] == 'iface':
            selected = len(words) > 1 and words[1] == 'eth0'
            if selected:
                result.append(clean)
        elif words[0] in ('auto', 'allow-hotplug') and 'eth0' in words[1:]:
            result.append(clean)
        elif selected and words[0] in ('address', 'netmask', 'gateway', 'metric'):
            result.append(clean)
    return result


def collect(root, system=Path('/')):
    from pynq_vision.beam_admission import inspect_bundle, conflicting_owners
    bundle = root / HARDWARE
    report = {'scope': 'READ_ONLY_FILES_AND_SYSFS', 'hardware_operations': 0,
              'python': platform.python_version(), 'machine': platform.machine(),
              'kernel': platform.release(), 'euid': getattr(os, 'geteuid', lambda: None)()}
    try:
        report['terminal'] = os.ttyname(0)
    except (AttributeError, OSError):
        report['terminal'] = 'not_a_terminal'
    try:
        data = inspect_bundle(bundle / 'hardware.json', bundle / 'system_wrapper.bit',
                              bundle / 'libbeam_pynq.so')
        report['bundle'] = {'version': data['version'], 'library_sha256': data['library_sha256']}
    except (OSError, ValueError, RuntimeError, KeyError) as error:
        report['bundle'] = {'error': str(error)}
    for key, path in (('boot_id', 'proc/sys/kernel/random/boot_id'),
                      ('cmdline', 'proc/cmdline'), ('consoles', 'proc/consoles'),
                      ('eth0_state', 'sys/class/net/eth0/operstate'),
                      ('eth0_carrier', 'sys/class/net/eth0/carrier'),
                      ('fpga_state', 'sys/class/fpga_manager/fpga0/state'),
                      ('fpga_firmware', 'sys/class/fpga_manager/fpga0/firmware')):
        report[key] = read_text(system / path)
    report['boot_files'] = {name: fingerprint(system / 'boot' / name)
                            for name in ('BOOT.BIN', 'boot.scr', 'image.ub', 'boot.py')}
    report['i2c'] = {p.name: str((p / 'device').resolve())
                     for p in sorted((system / 'sys/class/i2c-dev').glob('i2c-*'))}
    configs = [system / 'etc/network/interfaces']
    configs += sorted((system / 'etc/network/interfaces.d').glob('*'))[:16]
    report['eth0_boot_config'] = {}
    for path in configs:
        if path.is_file():
            text = read_text(path)
            if isinstance(text, str):
                report['eth0_boot_config'][str(path)] = ethernet_config(text)
    try:
        report['device_owner_pids'] = conflicting_owners(system / 'proc')
    except OSError as error:
        report['device_owner_pids'] = {'read_error': str(error)}
    receipt = system / 'run/beam_pynq/admission.json'
    report['admission_exists'] = receipt.is_file()
    report['next_requirement'] = 'UART console release and actual current-boot admission before --run'
    return report


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    action = parser.add_mutually_exclusive_group(required=True)
    action.add_argument('--check', action='store_true', help='只读检查，不导入PYNQ或访问PL/UART/I2C')
    action.add_argument('--inspect', action='store_true', help='检查原工程文件哈希')
    action.add_argument('--run', action='store_true', help='调用原运行入口，保留其全部准入条件')
    parser.add_argument('--frames', type=int, default=0)
    parser.add_argument('--uart', default='/dev/ttyPS0')
    parser.add_argument('--i2c-device', default='/dev/i2c-0')
    args = parser.parse_args(argv)
    root = Path(__file__).resolve().parent
    if not (root / 'pynq_vision/beam_launcher.py').is_file():
        parser.error('请把beam_v14.py放在beam_v14目录，与pynq_vision文件夹同级')
    sys.path.insert(0, str(root))
    if args.check:
        print(json.dumps(collect(root), ensure_ascii=False, indent=2))
        return 0
    from pynq_vision.beam_launcher import main as launch
    bundle = root / HARDWARE
    command = ['--manifest', str(bundle / 'hardware.json'),
               '--overlay', str(bundle / 'system_wrapper.bit'),
               '--library', str(bundle / 'libbeam_pynq.so')]
    if args.inspect:
        command.append('--inspect')
    else:
        command += ['--run', '--uart', args.uart, '--i2c-device', args.i2c_device,
                    '--frames', str(args.frames)]
    result = launch(command)
    return 0 if result is None else result


if __name__ == '__main__':
    sys.exit(main())
