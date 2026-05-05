# Logitech G733 Wheel Bridge

Linux user service for making the Logitech G733 headset wheel control system volume.

The daemon listens to the G733 headset wheel and sends volume changes to PipeWire
or PulseAudio. It is intended for Arch Linux, but should work on similar
systemd-based desktop Linux setups.

## Requirements

- Logitech G733 headset connected
- `python3`
- PipeWire's `wpctl` or PulseAudio's `pactl`
- `systemctl --user`

## Install

Run this from the cloned repository directory:

```bash
bash ./install.sh --udev
```

`--udev` is recommended because the headset wheel is exposed as an input device,
and normal users usually need a udev rule to read it.

The installer creates:

- `~/.local/bin/logi-g733-wheel-bridge`
- `~/.config/systemd/user/g733-wheel-bridge.service`
- `~/.config/logi-g733-wheel-bridge.env`

It also starts the service immediately and enables it for future logins.

## Check Status

```bash
systemctl --user status g733-wheel-bridge.service --no-pager
```

If it is working, the service should show `active (running)`.

## Adjust Sensitivity

Edit:

```bash
~/.config/logi-g733-wheel-bridge.env
```

Recommended default:

```text
G733_WHEEL_STEP=0.02
G733_WHEEL_MIN_INTERVAL_MS=40
```

`G733_WHEEL_STEP` is the volume change per accepted wheel event. `0.02` means
2%. Increase it if the wheel feels too slow.

`G733_WHEEL_MIN_INTERVAL_MS` smooths out bursty wheel events. Increase it if one
small wheel movement feels like multiple jumps.

Restart after changing settings:

```bash
systemctl --user restart g733-wheel-bridge.service
```

The installer does not overwrite an existing config file, so reinstalling will
not reset your personal sensitivity settings.

## Common Fixes

If the service is missing:

```bash
bash ./install.sh --udev
```

If the service says it cannot read `/dev/input/eventX`, reinstall with the udev
rule and reconnect the headset receiver:

```bash
bash ./install.sh --udev
```

If the wheel is detected but volume does not change, check that `wpctl` or
`pactl` is installed:

```bash
command -v wpctl || command -v pactl
```

For detailed debugging, see [README_DEV.md](README_DEV.md).

## Mic Mute Keybinds

You can bind these commands to a keyboard or mouse shortcut:

```bash
logi-g733-wheel-bridge --toggle-mic-mute
logi-g733-wheel-bridge --mute-mic
logi-g733-wheel-bridge --unmute-mic
```

These control the desktop microphone mute state. They do not guarantee the
headset firmware's built-in mute tone.

## Uninstall

```bash
bash ./uninstall.sh
```

To also remove the config file and udev rule:

```bash
bash ./uninstall.sh --purge-config --udev
```
