#!/usr/bin/env python3
"""Bridge Logitech G733 wheel input to desktop audio volume controls."""

from __future__ import annotations

import argparse
import ctypes
import fcntl
import os
import select
import shutil
import signal
import struct
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path


DEVICE_NAME = "Logitech G733 Gaming Headset Consumer Control"
ENV_PREFIX = "G733_WHEEL_"
KEY_MUTE = 113
KEY_VOLUMEDOWN = 114
KEY_VOLUMEUP = 115
DEFAULT_STEP = 0.08
TRUE_VALUES = {"1", "true", "yes", "on"}
FALSE_VALUES = {"0", "false", "no", "off"}

# EVIOCGRAB is defined as _IOW('E', 0x90, int). This matches Linux uapi.
EVIOCGRAB = 0x40044590


@dataclass(frozen=True)
class InputEvent:
    sec: int
    usec: int
    event_type: int
    code: int
    value: int


def env_name(name: str) -> str:
    return f"{ENV_PREFIX}{name}"


def read_env_text(name: str, default: str | None = None) -> str | None:
    value = os.environ.get(env_name(name))
    if value is None or value == "":
        return default
    return value


def read_env_float(name: str, default: float) -> float:
    value = read_env_text(name)
    if value is None:
        return default
    try:
        return float(value)
    except ValueError as exc:
        raise SystemExit(f"Invalid {env_name(name)} value: {value!r}") from exc


def read_env_bool(name: str, default: bool) -> bool:
    value = read_env_text(name)
    if value is None:
        return default
    lowered = value.strip().lower()
    if lowered in TRUE_VALUES:
        return True
    if lowered in FALSE_VALUES:
        return False
    raise SystemExit(f"Invalid {env_name(name)} boolean value: {value!r}")


def read_env_choice(name: str, default: str, choices: set[str]) -> str:
    value = read_env_text(name, default)
    if value not in choices:
        allowed = ", ".join(sorted(choices))
        raise SystemExit(f"Invalid {env_name(name)} value: {value!r}. Expected one of: {allowed}")
    return value


def format_percent(step: float) -> str:
    return f"{step * 100:.1f}".rstrip("0").rstrip(".")


class AudioController:
    backend_name = "base"
    binary_name = ""
    default_sink = ""

    def __init__(self, step: float, sink: str | None = None, binary_path: str | None = None) -> None:
        self.step = step
        self.sink = sink or self.default_sink
        self.binary_path = binary_path or self.resolve_binary()

    @classmethod
    def resolve_binary(cls) -> str:
        path = shutil.which(cls.binary_name)
        if path is None:
            raise FileNotFoundError(f"Could not find '{cls.binary_name}' in PATH.")
        return path

    @classmethod
    def probe(cls, sink: str | None = None) -> bool:
        try:
            binary_path = cls.resolve_binary()
        except FileNotFoundError:
            return False
        return cls._probe(binary_path, sink or cls.default_sink)

    @classmethod
    def _probe(cls, binary_path: str, sink: str) -> bool:
        raise NotImplementedError

    @staticmethod
    def _run(*args: str) -> None:
        subprocess.run(args, check=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)

    @staticmethod
    def _check(*args: str) -> bool:
        result = subprocess.run(args, check=False, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        return result.returncode == 0

    def volume_up(self) -> None:
        raise NotImplementedError

    def volume_down(self) -> None:
        raise NotImplementedError

    def toggle_mute(self) -> None:
        raise NotImplementedError


class WpctlController(AudioController):
    backend_name = "wpctl"
    binary_name = "wpctl"
    default_sink = "@DEFAULT_AUDIO_SINK@"

    @classmethod
    def _probe(cls, binary_path: str, sink: str) -> bool:
        return cls._check(binary_path, "get-volume", sink)

    def volume_up(self) -> None:
        self._run(self.binary_path, "set-volume", self.sink, f"{self.step:.2f}+")

    def volume_down(self) -> None:
        self._run(self.binary_path, "set-volume", self.sink, f"{self.step:.2f}-")

    def toggle_mute(self) -> None:
        self._run(self.binary_path, "set-mute", self.sink, "toggle")


class PactlController(AudioController):
    backend_name = "pactl"
    binary_name = "pactl"
    default_sink = "@DEFAULT_SINK@"

    @classmethod
    def _probe(cls, binary_path: str, sink: str) -> bool:
        return cls._check(binary_path, "get-sink-volume", sink)

    def volume_up(self) -> None:
        self._run(self.binary_path, "set-sink-volume", self.sink, f"{format_percent(self.step)}%+")

    def volume_down(self) -> None:
        self._run(self.binary_path, "set-sink-volume", self.sink, f"{format_percent(self.step)}%-")

    def toggle_mute(self) -> None:
        self._run(self.binary_path, "set-sink-mute", self.sink, "toggle")


CONTROLLERS: dict[str, type[AudioController]] = {
    WpctlController.backend_name: WpctlController,
    PactlController.backend_name: PactlController,
}


def create_controller(backend: str, step: float, sink: str | None) -> AudioController:
    if backend != "auto":
        controller_class = CONTROLLERS[backend]
        binary_path = controller_class.resolve_binary()
        if not controller_class._probe(binary_path, sink or controller_class.default_sink):
            raise RuntimeError(
                f"{controller_class.binary_name} is installed but could not control "
                f"{sink or controller_class.default_sink!r}."
            )
        return controller_class(step=step, sink=sink, binary_path=binary_path)

    for controller_class in (WpctlController, PactlController):
        if controller_class.probe(sink=sink):
            return controller_class(step=step, sink=sink)

    raise FileNotFoundError(
        "Could not find a working audio backend. Install PipeWire's 'wpctl' or PulseAudio's "
        "'pactl', or pass --backend and --sink explicitly."
    )


class G733WheelBridge:
    def __init__(
        self,
        event_path: Path,
        controller: AudioController | None,
        grab: bool = False,
        verbose: bool = False,
    ) -> None:
        self.event_path = event_path
        self.controller = controller
        self.grab = grab
        self.verbose = verbose
        self._running = True
        self._event_struct = self._build_event_struct()

    def run(self) -> int:
        with self.event_path.open("rb", buffering=0) as device:
            if self.grab:
                fcntl.ioctl(device.fileno(), EVIOCGRAB, 1)
            try:
                self._install_signal_handlers()
                if self.verbose:
                    print(
                        f"Listening on {self.event_path} with backend={self.controller.backend_name} "
                        f"sink={self.controller.sink}",
                        file=sys.stderr,
                        flush=True,
                    )
                while self._running:
                    readable, _, _ = select.select([device], [], [], 1.0)
                    if not readable:
                        continue
                    event = self._read_event(device)
                    if event is None:
                        return 1
                    self._handle_event(event)
            finally:
                if self.grab:
                    fcntl.ioctl(device.fileno(), EVIOCGRAB, 0)
        return 0

    def probe(self) -> int:
        with self.event_path.open("rb", buffering=0) as device:
            self._install_signal_handlers()
            print(f"Listening on {self.event_path}. Turn the wheel or press mute. Ctrl+C to stop.")
            while self._running:
                readable, _, _ = select.select([device], [], [], 1.0)
                if not readable:
                    continue
                event = self._read_event(device)
                if event is None:
                    return 1
                print(
                    f"time={event.sec}.{event.usec:06d} "
                    f"type={event.event_type} code={event.code} value={event.value}"
                )
                sys.stdout.flush()
        return 0

    def _handle_event(self, event: InputEvent) -> None:
        if event.event_type != 1 or event.value not in (1, 2):
            return

        if self.verbose:
            print(
                f"Received input: type={event.event_type} code={event.code} value={event.value}",
                file=sys.stderr,
                flush=True,
            )

        if event.code == KEY_VOLUMEUP:
            self.controller.volume_up()
        elif event.code == KEY_VOLUMEDOWN:
            self.controller.volume_down()
        elif event.code == KEY_MUTE:
            self.controller.toggle_mute()

    def _read_event(self, device) -> InputEvent | None:
        data = device.read(self._event_struct.size)
        if len(data) != self._event_struct.size:
            return None
        return InputEvent(*self._event_struct.unpack(data))

    @staticmethod
    def _build_event_struct() -> struct.Struct:
        long_size = ctypes.sizeof(ctypes.c_long)
        if long_size == 8:
            return struct.Struct("llHHi")
        if long_size == 4:
            return struct.Struct("iiHHi")
        raise RuntimeError(f"Unsupported C long size: {long_size}")

    def _install_signal_handlers(self) -> None:
        signal.signal(signal.SIGINT, self._stop)
        signal.signal(signal.SIGTERM, self._stop)

    def _stop(self, *_args) -> None:
        self._running = False


def find_event_device(device_name: str) -> Path:
    for event in sorted(Path("/sys/class/input").glob("event*")):
        try:
            name = (event / "device" / "name").read_text().strip()
        except FileNotFoundError:
            continue
        if name == device_name:
            return Path("/dev/input") / event.name
    raise FileNotFoundError(
        f"Could not find an input event for '{device_name}'. "
        "Check that the headset is connected and exposed in /sys/class/input."
    )


def build_parser() -> argparse.ArgumentParser:
    default_event = read_env_text("EVENT")
    default_backend = read_env_choice("BACKEND", "auto", {"auto", *CONTROLLERS})
    default_step = read_env_float("STEP", DEFAULT_STEP)
    default_grab = read_env_bool("GRAB", False)
    default_device_name = read_env_text("DEVICE_NAME", DEVICE_NAME) or DEVICE_NAME
    default_sink = read_env_text("SINK")

    parser = argparse.ArgumentParser(
        description="Listen to the Logitech G733 wheel and forward it to desktop volume controls."
    )
    parser.add_argument(
        "--backend",
        choices=["auto", *sorted(CONTROLLERS)],
        default=default_backend,
        help="Audio backend to use. Default: auto.",
    )
    parser.add_argument(
        "--event",
        type=Path,
        default=Path(default_event) if default_event else None,
        help="Explicit /dev/input/eventX path. Defaults to auto-detecting the G733 consumer-control device.",
    )
    parser.add_argument(
        "--device-name",
        default=default_device_name,
        help=f"Input device name to auto-detect. Default: {DEVICE_NAME!r}.",
    )
    parser.add_argument(
        "--step",
        type=float,
        default=default_step,
        help=f"Volume step per wheel notch. Default: {DEFAULT_STEP:.2f}.",
    )
    parser.add_argument(
        "--sink",
        default=default_sink,
        help="Explicit sink name or ID. Defaults to the backend's default audio sink token.",
    )
    grab_group = parser.add_mutually_exclusive_group()
    grab_group.add_argument(
        "--grab",
        action="store_true",
        default=default_grab,
        help="Grab the input device exclusively while the bridge is running.",
    )
    grab_group.add_argument(
        "--no-grab",
        action="store_false",
        dest="grab",
        help="Do not grab the input device exclusively.",
    )
    parser.add_argument(
        "--probe",
        action="store_true",
        help="Print raw input events instead of changing volume.",
    )
    parser.add_argument(
        "--verbose",
        action="store_true",
        help="Log startup and handled key events to stderr.",
    )
    return parser


def main() -> int:
    parser = build_parser()
    args = parser.parse_args()

    if args.step <= 0:
        parser.error("--step must be greater than 0.")

    event_path = args.event or find_event_device(args.device_name)

    if not event_path.exists():
        parser.error(f"{event_path} does not exist.")

    if not os.access(event_path, os.R_OK):
        parser.error(
            f"Cannot read {event_path}. You may need to add your user to the 'input' group "
            "or install the provided udev rule for this device."
        )

    try:
        if args.probe:
            bridge = G733WheelBridge(
                event_path=event_path,
                controller=None,
                grab=args.grab,
                verbose=args.verbose,
            )
            return bridge.probe()

        controller = create_controller(backend=args.backend, step=args.step, sink=args.sink)
        bridge = G733WheelBridge(
            event_path=event_path,
            controller=controller,
            grab=args.grab,
            verbose=args.verbose,
        )
        return bridge.run()
    except subprocess.CalledProcessError as exc:
        print(f"Audio control command failed: {exc}", file=sys.stderr)
        return exc.returncode or 1
    except (PermissionError, FileNotFoundError, RuntimeError) as exc:
        print(str(exc), file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
