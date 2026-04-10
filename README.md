# ARCH Linux Logi-G733-Daemon-Audio-Wheel

Arch Linux daemon for restoring the Logitech G733 headset wheel as a system volume control.

## What `install.sh` Does

cd'd inside this repo, `bash ./install.sh` will do four things:

- It installs the daemon script into `~/.local/share/logi-g733-wheel-bridge/` and creates a launcher at `~/.local/bin/logi-g733-wheel-bridge` so the service has a stable executable path. See `install.sh`.
- It installs the user service into `~/.config/systemd/user/g733-wheel-bridge.service`. That service runs the launcher and reads optional settings from `~/.config/logi-g733-wheel-bridge.env`. See `systemd/g733-wheel-bridge.service`.
- It creates `~/.config/logi-g733-wheel-bridge.env` only if that file does not already exist, so it will not overwrite the user's tuning. The example values live in `config/logi-g733-wheel-bridge.env.example`.
- By default, it runs `systemctl --user daemon-reload` and `systemctl --user enable --now g733-wheel-bridge.service`, so the daemon starts immediately and comes back on login. That behavior is in `install.sh`.

If a user runs `bash ./install.sh --udev`, it also installs the udev rule in `/etc/udev/rules.d/70-logi-g733-wheel.rules`, reloads rules, and triggers input devices so access to the G733 event node works more reliably without adding the user to the `input` group. See `udev/70-logi-g733-wheel.rules`.

What it does not do:

- It does not install Python, `wpctl`, or `pactl`.
- It does not overwrite an existing config file.
- It does not need root unless `--udev` is used.

## Quick Install

```bash
bash ./install.sh
```

If the user hits input-permission issues:

```bash
bash ./install.sh --udev
```

============================

## What the Daemon Does

The daemon listens to the Logitech G733 consumer-control input device and turns the wheel and mute button into desktop audio actions.

Specifically, it does this:

- Auto-detects the `Logitech G733 Gaming Headset Consumer Control` event device instead of assuming a fixed `/dev/input/eventX`.
- Opens the headset input stream and listens for `KEY_VOLUMEUP`, `KEY_VOLUMEDOWN`, and `KEY_MUTE`.
- Maps wheel notches to system volume changes and maps the mute button to sink mute toggle.
- Prefers PipeWire through `wpctl` and falls back to PulseAudio through `pactl`.
- Supports a `--probe` mode so a user can verify the wheel is sending events before troubleshooting the audio backend.
- Supports config overrides through `~/.config/logi-g733-wheel-bridge.env` for things like step size, backend, sink, explicit event path, device name, and exclusive grab mode.
- Runs well as a user-level `systemd` service so it starts on login and stays in the background.

## Manual Run

Probe raw events:

```bash
python3 ./g733_wheel_bridge.py --probe
```

Run the daemon manually:

```bash
python3 ./g733_wheel_bridge.py
```

Useful examples:

```bash
python3 ./g733_wheel_bridge.py --step 0.10
python3 ./g733_wheel_bridge.py --backend wpctl
python3 ./g733_wheel_bridge.py --backend pactl
python3 ./g733_wheel_bridge.py --sink @DEFAULT_AUDIO_SINK@
python3 ./g733_wheel_bridge.py --event /dev/input/eventX
python3 ./g733_wheel_bridge.py --grab
```

## Uninstall

```bash
bash ./uninstall.sh
```

To also remove the config file and udev rule:

```bash
bash ./uninstall.sh --purge-config --udev
```
