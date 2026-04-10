#!/usr/bin/env bash
set -eu

APP_ID="logi-g733-wheel-bridge"
SERVICE_NAME="g733-wheel-bridge.service"
SCRIPT_DIR="$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)"
INSTALL_DIR="${XDG_DATA_HOME:-$HOME/.local/share}/${APP_ID}"
BIN_DIR="${HOME}/.local/bin"
CONFIG_DIR="${XDG_CONFIG_HOME:-$HOME/.config}"
SYSTEMD_USER_DIR="${CONFIG_DIR}/systemd/user"
CONFIG_FILE="${CONFIG_DIR}/logi-g733-wheel-bridge.env"
WRAPPER_PATH="${BIN_DIR}/logi-g733-wheel-bridge"
SERVICE_PATH="${SYSTEMD_USER_DIR}/${SERVICE_NAME}"
INSTALL_UDEV=0
START_SERVICE=1

usage() {
  printf '%s\n' "Usage: bash ./install.sh [--no-start] [--udev]"
}

install_udev_rule() {
  local source_rule="${SCRIPT_DIR}/udev/70-logi-g733-wheel.rules"
  local target_rule="/etc/udev/rules.d/70-logi-g733-wheel.rules"

  if [ "$(id -u)" -eq 0 ]; then
    install -Dm644 "${source_rule}" "${target_rule}"
    udevadm control --reload-rules
    udevadm trigger --subsystem-match=input
    return
  fi

  if ! command -v sudo >/dev/null 2>&1; then
    printf '%s\n' "sudo is required to install the udev rule." >&2
    return 1
  fi

  sudo install -Dm644 "${source_rule}" "${target_rule}"
  sudo udevadm control --reload-rules
  sudo udevadm trigger --subsystem-match=input
}

while [ "$#" -gt 0 ]; do
  case "$1" in
    --no-start)
      START_SERVICE=0
      ;;
    --udev)
      INSTALL_UDEV=1
      ;;
    -h|--help)
      usage
      exit 0
      ;;
    *)
      usage >&2
      exit 1
      ;;
  esac
  shift
done

if ! command -v python3 >/dev/null 2>&1; then
  printf '%s\n' "python3 is required." >&2
  exit 1
fi

install -d "${INSTALL_DIR}" "${BIN_DIR}" "${SYSTEMD_USER_DIR}" "${CONFIG_DIR}"
install -Dm755 "${SCRIPT_DIR}/g733_wheel_bridge.py" "${INSTALL_DIR}/g733_wheel_bridge.py"
install -Dm644 "${SCRIPT_DIR}/systemd/g733-wheel-bridge.service" "${SERVICE_PATH}"

if [ ! -f "${CONFIG_FILE}" ]; then
  install -Dm644 "${SCRIPT_DIR}/config/logi-g733-wheel-bridge.env.example" "${CONFIG_FILE}"
fi

cat > "${WRAPPER_PATH}" <<EOF
#!/usr/bin/env sh
exec /usr/bin/env python3 "${INSTALL_DIR}/g733_wheel_bridge.py" "\$@"
EOF
chmod 755 "${WRAPPER_PATH}"

if [ "${INSTALL_UDEV}" -eq 1 ]; then
  install_udev_rule
fi

if [ "${START_SERVICE}" -eq 1 ] && command -v systemctl >/dev/null 2>&1; then
  if systemctl --user daemon-reload && systemctl --user enable --now "${SERVICE_NAME}"; then
    printf '%s\n' "Installed and started ${SERVICE_NAME}."
  else
    printf '%s\n' "Installed files, but could not start the user service automatically." >&2
    printf '%s\n' "Try: systemctl --user daemon-reload && systemctl --user enable --now ${SERVICE_NAME}" >&2
  fi
else
  printf '%s\n' "Installed files without starting the user service."
  printf '%s\n' "Start it later with: systemctl --user daemon-reload && systemctl --user enable --now ${SERVICE_NAME}"
fi

printf '%s\n' "Wrapper: ${WRAPPER_PATH}"
printf '%s\n' "Config:  ${CONFIG_FILE}"
printf '%s\n' "Service: ${SERVICE_PATH}"
