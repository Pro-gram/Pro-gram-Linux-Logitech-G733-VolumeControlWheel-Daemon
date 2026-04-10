#!/usr/bin/env bash
set -eu

APP_ID="logi-g733-wheel-bridge"
SERVICE_NAME="g733-wheel-bridge.service"
INSTALL_DIR="${XDG_DATA_HOME:-$HOME/.local/share}/${APP_ID}"
BIN_DIR="${HOME}/.local/bin"
CONFIG_DIR="${XDG_CONFIG_HOME:-$HOME/.config}"
SYSTEMD_USER_DIR="${CONFIG_DIR}/systemd/user"
CONFIG_FILE="${CONFIG_DIR}/logi-g733-wheel-bridge.env"
WRAPPER_PATH="${BIN_DIR}/logi-g733-wheel-bridge"
SERVICE_PATH="${SYSTEMD_USER_DIR}/${SERVICE_NAME}"
REMOVE_CONFIG=0
REMOVE_UDEV=0

usage() {
  printf '%s\n' "Usage: bash ./uninstall.sh [--purge-config] [--udev]"
}

remove_udev_rule() {
  local target_rule="/etc/udev/rules.d/70-logi-g733-wheel.rules"

  if [ ! -e "${target_rule}" ]; then
    return
  fi

  if [ "$(id -u)" -eq 0 ]; then
    rm -f "${target_rule}"
    udevadm control --reload-rules
    udevadm trigger --subsystem-match=input
    return
  fi

  if ! command -v sudo >/dev/null 2>&1; then
    printf '%s\n' "sudo is required to remove the udev rule." >&2
    return 1
  fi

  sudo rm -f "${target_rule}"
  sudo udevadm control --reload-rules
  sudo udevadm trigger --subsystem-match=input
}

while [ "$#" -gt 0 ]; do
  case "$1" in
    --purge-config)
      REMOVE_CONFIG=1
      ;;
    --udev)
      REMOVE_UDEV=1
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

if command -v systemctl >/dev/null 2>&1; then
  systemctl --user disable --now "${SERVICE_NAME}" >/dev/null 2>&1 || true
  systemctl --user daemon-reload >/dev/null 2>&1 || true
fi

rm -f "${WRAPPER_PATH}" "${SERVICE_PATH}"
rm -rf "${INSTALL_DIR}"

if [ "${REMOVE_CONFIG}" -eq 1 ]; then
  rm -f "${CONFIG_FILE}"
fi

if [ "${REMOVE_UDEV}" -eq 1 ]; then
  remove_udev_rule
fi

printf '%s\n' "Removed ${APP_ID}."
