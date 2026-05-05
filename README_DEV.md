# Developer Notes

Technical notes for maintaining and debugging the Logitech G733 Wheel Bridge.
The main user-facing instructions live in [README.md](README.md).

## Project Layout

- `g733_wheel_bridge.py`: daemon, CLI, input event reader, and audio backend logic.
- `install.sh`: installs the daemon, wrapper, config, user systemd unit, and optional udev rule.
- `uninstall.sh`: removes installed files.
- `systemd/g733-wheel-bridge.service`: user service.
- `udev/70-logi-g733-wheel.rules`: grants desktop-session access to the G733 input event node.
- `config/logi-g733-wheel-bridge.env.example`: default user config.

## Installer Behavior

`bash ./install.sh` installs the daemon under:

```text
~/.local/share/logi-g733-wheel-bridge/
```

It creates this stable launcher:

```text
~/.local/bin/logi-g733-wheel-bridge
```

It creates `~/.config/logi-g733-wheel-bridge.env` only if that file does not
already exist. This is intentional: users can reinstall without losing their
sensitivity or backend settings.

`bash ./install.sh --udev` additionally installs:

```text
/etc/udev/rules.d/70-logi-g733-wheel.rules
```

It reloads udev rules, triggers input devices, reloads the user systemd manager,
resets any failed `g733-wheel-bridge.service` state, then enables and starts the
service.

## Runtime Behavior

The daemon auto-detects this input device name:

```text
Logitech G733 Gaming Headset Consumer Control
```

It listens for Linux input key events:

```text
KEY_MUTE=113
KEY_VOLUMEDOWN=114
KEY_VOLUMEUP=115
```

Volume changes use PipeWire first through `wpctl`, then PulseAudio through
`pactl`.

The default wheel sensitivity is:

```text
G733_WHEEL_STEP=0.02
G733_WHEEL_MIN_INTERVAL_MS=40
```

`G733_WHEEL_STEP` controls the volume delta for each accepted wheel event.
`G733_WHEEL_MIN_INTERVAL_MS` ignores repeated events in the same direction that
arrive too close together. This normalizes bursty wheel behavior without hiding
opposite-direction changes.

## Config Variables

The service reads:

```text
~/.config/logi-g733-wheel-bridge.env
```

Supported variables:

```text
G733_WHEEL_STEP
G733_WHEEL_MIN_INTERVAL_MS
G733_WHEEL_BACKEND
G733_WHEEL_SINK
G733_WHEEL_SOURCE
G733_WHEEL_HANDLE_MUTE
G733_WHEEL_EVENT
G733_WHEEL_DEVICE_NAME
G733_WHEEL_GRAB
```

Equivalent CLI flags are available through:

```bash
logi-g733-wheel-bridge --help
```

## Udev Rule Details

The G733 wheel event node normally appears as `root:input`, which many desktop
users cannot read. The udev rule adds `uaccess` so the active desktop session
can read the device.

The rule intentionally matches input-parent attributes:

```text
ATTRS{id/vendor}=="046d", ATTRS{id/product}=="0afe", ATTRS{name}=="Logitech G733 Gaming Headset Consumer Control", TAG+="uaccess"
```

Do not change this back to `idVendor` or `idProduct`. Those attributes exist on
the USB parent, while `name` exists on the input parent. A udev rule cannot
combine `ATTRS{...}` matches from different parent devices, so the mixed-parent
version does not match and `uaccess` is never applied.

Check whether the rule applied:

```bash
udevadm info -q property -n /dev/input/eventX | grep CURRENT_TAGS
```

Expected output includes:

```text
uaccess
```

## Debugging

Check service state:

```bash
systemctl --user status g733-wheel-bridge.service --no-pager --full
journalctl --user -u g733-wheel-bridge.service -n 80 --no-pager
```

List input device names:

```bash
for event in /sys/class/input/event*; do
  name_file="$event/device/name"
  [ -r "$name_file" ] && printf '%s\t%s\n' "$(basename "$event")" "$(cat "$name_file")"
done
```

Probe raw G733 input events:

```bash
python3 ./g733_wheel_bridge.py --probe
```

Check audio backend availability:

```bash
wpctl get-volume @DEFAULT_AUDIO_SINK@
pactl get-sink-volume @DEFAULT_SINK@
```

If the service is stuck in `start-limit-hit` after a previous failure:

```bash
systemctl --user reset-failed g733-wheel-bridge.service
systemctl --user restart g733-wheel-bridge.service
```

## Local Key Remaps

System-wide hwdb or key-remapping tools can alter G733 wheel events before the
daemon reads them. A broad rule like this applies to every USB input device:

```text
evdev:input:b0003v*p*
 KEYBOARD_KEY_0114=enter
```

If users need such a rule for a separate device, scope it to that device's
vendor and product IDs, then reload hwdb:

```bash
sudo systemd-hwdb update
sudo udevadm trigger --subsystem-match=input
```

## Validation

Basic local checks:

```bash
bash -n install.sh uninstall.sh
python3 -m py_compile g733_wheel_bridge.py
python3 ./g733_wheel_bridge.py --help
```
