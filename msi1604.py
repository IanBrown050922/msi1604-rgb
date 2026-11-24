"""Inspect the MSI MS-1604 or set keyboard colors and effects."""
import argparse
from collections import defaultdict
import fcntl
import hashlib
import os
from pathlib import Path
import re
import stat
import struct


SYSFS_HID = Path("/sys/bus/hid/devices")
DESCRIPTOR_SHA256 = "4370aa22b68480efdf25737263fe488975b4a93265ab8a36466b8f6d034dfd6d"
REPORT_LENGTH = 64
# Linux x86-64 hidraw ioctl numbers from <linux/hidraw.h>.
HIDIOCGRAWINFO = 0x80084803
HIDIOCSFEATURE = 0xC0404806
HIDIOCGFEATURE = 0xC0404807


def report_lengths(descriptor):
    """Return report lengths in bytes, including any report ID."""
    report_size = report_count = report_id = offset = 0
    stack = []
    lengths = defaultdict(int)
    main_items = {0x80: "Input", 0x90: "Output", 0xB0: "Feature"}

    while offset < len(descriptor):
        prefix = descriptor[offset]
        offset += 1
        if prefix == 0xFE:
            raise ValueError("long HID items are unsupported")
        size = (0, 1, 2, 4)[prefix & 3]
        if offset + size > len(descriptor):
            raise ValueError("truncated HID item")
        value = int.from_bytes(descriptor[offset:offset + size], "little")
        offset += size

        tag = prefix & 0xFC
        if tag == 0x74:
            report_size = value
        elif tag == 0x94:
            report_count = value
        elif tag == 0x84:
            if not 1 <= value <= 255:
                raise ValueError("invalid HID report ID")
            report_id = value
        elif tag == 0xA4:
            stack.append((report_size, report_count, report_id))
        elif tag == 0xB4:
            if not stack:
                raise ValueError("unmatched HID global Pop")
            report_size, report_count, report_id = stack.pop()
        elif tag in main_items:
            lengths[report_id, main_items[tag]] += report_size * report_count

    if stack:
        raise ValueError("unmatched HID global Push")
    return {key: (bits + 7) // 8 + bool(key[0]) for key, bits in lengths.items()}


def inspect():
    devices = sorted(SYSFS_HID.glob("0003:0DB0:1604.*"))
    if not devices:
        raise ValueError("USB HID device 0DB0:1604 was not found in sysfs")

    for device in devices:
        info = dict(line.split("=", 1) for line in
                    (device / "uevent").read_text().splitlines() if "=" in line)
        if info.get("HID_ID") != "0003:00000DB0:00001604":
            raise ValueError(f"unexpected HID identity at {device}")
        descriptor = (device / "report_descriptor").read_bytes()
        lengths = report_lengths(descriptor)
        print(device.name, info.get("HID_NAME", ""))
        interface = device.resolve().parent / "bInterfaceNumber"
        if interface.is_file():
            print(f"USB interface {interface.read_text().strip()}")
        print(f"Descriptor SHA-256 {hashlib.sha256(descriptor).hexdigest()}")
        for (report_id, kind), length in sorted(lengths.items()):
            print(f"  ID 0x{report_id:02x}  {kind:7}  {length:2} bytes")


def parse_color(value):
    digits = value.removeprefix("#")
    if not re.fullmatch(r"[0-9a-fA-F]{6}", digits):
        raise argparse.ArgumentTypeError("use six hex digits, for example FFFFFF")
    return bytes.fromhex(digits)


EFFECT_MODES = {"off": 0, "steady": 1, "breathing": 2, "color-cycle": 3, "wave": 4}
EFFECT_PERIODS = {"breathing": (8, 6, 4), "color-cycle": (8, 6, 4), "wave": (7, 5, 3)}
RAINBOW_FRAMES = bytes.fromhex(
    "00 ff 00 00 10 ff ff 00 20 00 ff 00 30 00 ff ff "
    "40 00 00 ff 50 ff 00 ff 64 ff 00 00"
)
WHITE = bytes.fromhex("ffffff")


def color_frames(colors):
    """Space colors evenly and repeat the first at the end of the cycle."""
    return b"".join(bytes((100 * index // len(colors),)) + rgb
                    for index, rgb in enumerate(colors)) + bytes((100,)) + colors[0]


def effect_report(name, frames, *, period=1, direction=0):
    # LEDKeeper2's effect report, with the MS-1604 wavelength and wave mode.
    header = bytes((2, 2, EFFECT_MODES[name])) + (period * 100).to_bytes(2, "little")
    header += bytes((0, 0, 15, 1, direction))
    return (header + frames).ljust(REPORT_LENGTH, bytes(1))


def lighting_sequence(effects, *, save=False):
    readback = bytes((1,)).ljust(REPORT_LENGTH, bytes(1))
    for zone, (mask, (name, effect)) in enumerate(zip((1, 2, 4, 8), effects), start=1):
        select = bytes((2, 1, mask)).ljust(REPORT_LENGTH, bytes(1))
        yield f"Zone {zone} select", HIDIOCSFEATURE, select
        yield f"Zone {zone} read after select", HIDIOCGFEATURE, readback
        yield f"Zone {zone} {name}", HIDIOCSFEATURE, effect
        yield f"Zone {zone} read after color", HIDIOCGFEATURE, readback

    if save:
        save_report = bytes((2, 0xA0)).ljust(REPORT_LENGTH, bytes(1))
        yield "Save all zones", HIDIOCSFEATURE, save_report
        yield "Read after save", HIDIOCGFEATURE, readback


def find_endpoint():
    devices = [
        device for device in SYSFS_HID.glob("0003:0DB0:1604.*")
        if (device.resolve().parent / "bInterfaceNumber").read_text().strip() == "00"
    ]
    if len(devices) != 1:
        raise ValueError(f"expected one MS-1604 on USB interface 00, found {len(devices)}")

    device = devices[0]
    descriptor = (device / "report_descriptor").read_bytes()
    if hashlib.sha256(descriptor).hexdigest() != DESCRIPTOR_SHA256:
        raise ValueError("MS-1604 descriptor differs from the verified descriptor")
    endpoints = list((device / "hidraw").glob("hidraw*"))
    if len(endpoints) != 1:
        raise ValueError("expected one hidraw endpoint for the MS-1604")
    endpoint = endpoints[0]
    major, minor = map(int, (endpoint / "dev").read_text().strip().split(":"))
    return Path("/dev") / endpoint.name, os.makedev(major, minor)


def apply_color(path, device_number, sequence):
    if os.uname().machine != "x86_64":
        raise ValueError("live HID access is supported on Linux x86-64")
    fd = os.open(path, os.O_RDWR | os.O_NOFOLLOW)
    try:
        info = os.fstat(fd)
        if not stat.S_ISCHR(info.st_mode) or info.st_rdev != device_number:
            raise ValueError("opened device does not match the MS-1604 endpoint")
        raw_info = fcntl.ioctl(fd, HIDIOCGRAWINFO, bytes(8))
        if struct.unpack("=IHH", raw_info) != (3, 0x0DB0, 0x1604):
            raise ValueError("opened device does not identify as USB 0DB0:1604")

        for label, request, report in sequence:
            buffer = bytearray(report)
            try:
                count = fcntl.ioctl(fd, request, buffer)
            except OSError as error:
                raise OSError(f"{label}: {error.strerror}. Earlier changes may be visible.") from error
            # MSI requests the readback but does not inspect its contents or length.
            if request == HIDIOCSFEATURE and count != REPORT_LENGTH:
                raise ValueError(f"{label}: wrote {count} of {REPORT_LENGTH} bytes. "
                                 "Earlier changes may be visible.")
    finally:
        os.close(fd)


def add_run_options(command):
    mode = command.add_mutually_exclusive_group()
    mode.add_argument("--dry-run", action="store_true", help="print the sequence (default)")
    mode.add_argument("--apply", action="store_true", help="send the reports to the keyboard")
    command.add_argument("--save", action="store_true", help="include the keyboard save command")


def preset_effects(args):
    name = "color-cycle" if args.name == "rainbow" else args.name
    if args.direction is not None and name != "wave":
        raise ValueError("--direction applies only to the wave preset")
    if args.speed is not None and name not in EFFECT_PERIODS:
        raise ValueError("--speed applies only to animated presets")
    if len(args.colors) > 6:
        raise ValueError("use up to six colors in a custom pattern")
    if name == "off" and args.colors:
        raise ValueError("off takes no colors")
    if name == "steady" and len(args.colors) > 1:
        raise ValueError("steady takes one color. Use zones for four different colors.")

    speed = ("slow", "medium", "fast").index(args.speed or "medium")
    period = EFFECT_PERIODS.get(name, (1, 1, 1))[speed]
    direction = int(args.direction == "reverse" or (name == "color-cycle" and bool(args.colors)))
    if name == "off":
        frames = color_frames([bytes(3)])
    elif args.colors:
        frames = color_frames(args.colors)
    elif name in ("color-cycle", "wave"):
        frames = RAINBOW_FRAMES
    else:
        frames = color_frames([WHITE])

    label = "steady color" if name == "steady" else name
    return [(label, effect_report(name, frames, period=period, direction=direction))] * 4


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    commands = parser.add_subparsers(dest="command")
    commands.add_parser("inspect", help="inspect the cached Linux descriptor")
    color = commands.add_parser("color", help="preview or apply a steady RGB color")
    color.add_argument("rgb", type=parse_color, help="six hex digits, for example FFFFFF")
    add_run_options(color)
    preset = commands.add_parser("preset", help="preview or apply a lighting preset")
    preset.add_argument("name", choices=(*EFFECT_MODES, "rainbow"))
    preset.add_argument("colors", type=parse_color, nargs="*", metavar="RGB",
                        help="optional hex colors in pattern order")
    preset.add_argument("--speed", choices=("slow", "medium", "fast"))
    preset.add_argument("--direction", choices=("forward", "reverse"))
    add_run_options(preset)
    zones = commands.add_parser("zones", help="set a different steady color for each zone")
    zones.add_argument("colors", type=parse_color, nargs=4, metavar="RGB")
    add_run_options(zones)
    args = parser.parse_args()
    try:
        if args.command in (None, "inspect"):
            inspect()
        else:
            if args.command == "preset":
                effects = preset_effects(args)
                description = args.name
            else:
                colors = [args.rgb] * 4 if args.command == "color" else args.colors
                effects = [("steady color", effect_report("steady", color_frames([rgb])))
                           for rgb in colors]
                description = (f"#{args.rgb.hex().upper()}" if args.command == "color"
                               else "custom zone colors")
            path, device_number = find_endpoint()
            sequence = lighting_sequence(effects, save=args.save)
            if args.apply:
                apply_color(path, device_number, sequence)
                print(f"Applied {description} to all four zones.")
                if args.save:
                    print("Sent the keyboard save command.")
                else:
                    print("No save command sent.")
            else:
                print(f"Dry run for MS-1604 ({path}). No reports sent.")
                for label, request, report in sequence:
                    details = report.hex(" ") if request == HIDIOCSFEATURE else "ID 01 (64 bytes)"
                    print(f"{label}: {details}")
    except (OSError, ValueError) as error:
        parser.exit(1, f"{parser.prog}: {error}\n")


if __name__ == "__main__":
    main()
