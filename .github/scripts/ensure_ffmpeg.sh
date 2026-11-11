#!/usr/bin/env bash
# GitHub Ubuntu 24.04 setup only. Existing working tools need no APT/network.
set -euo pipefail

toolchain_ready() {
  command -v ffmpeg >/dev/null && command -v ffprobe >/dev/null || return 1
  timeout 15s ffmpeg -version >/dev/null 2>&1 || return 1
  timeout 15s ffprobe -version >/dev/null 2>&1 || return 1
  local encoders filters
  encoders="$(timeout 15s ffmpeg -hide_banner -encoders 2>/dev/null)" || return 1
  filters="$(timeout 15s ffmpeg -hide_banner -filters 2>/dev/null)" || return 1
  test -r /usr/share/fonts/truetype/dejavu/DejaVuSansMono-Bold.ttf || return 1
  [[ "$encoders" =~ [[:space:]]libx264[[:space:]] ]] &&
    [[ "$encoders" =~ [[:space:]]aac[[:space:]] ]] &&
    [[ "$filters" =~ [[:space:]]drawtext[[:space:]] ]]
}

ubuntu_codename() {
  # Trusted OS metadata; never a repository-supplied shell file.
  . /etc/os-release
  [[ "${ID:-}" = ubuntu && "${VERSION_CODENAME:-}" = noble ]] || {
    printf '%s\n' 'FFmpeg installation requires the pinned Ubuntu 24.04 runner.' >&2
    return 1
  }
  [[ "$(dpkg --print-architecture)" = amd64 ]] || return 1
  printf '%s\n' noble
}

install_signed_ubuntu() (
  local codename apt_dir
  codename="$(ubuntu_codename)"
  apt_dir="$(mktemp -d /tmp/nextphase-ci-apt.XXXXXX)"
  trap 'apt_exit=$?; sudo -n rm -rf -- "$apt_dir" || true; exit "$apt_exit"' EXIT
  chmod 0755 "$apt_dir"
  mkdir -p "$apt_dir/lists/partial"
  # Isolate sources/lists: do not follow the runner's failing mirror+file Azure
  # rotation, mix stale indexes into the install, or edit global APT configuration.
  cat > "$apt_dir/sources.list" <<EOF
deb [arch=amd64 signed-by=/usr/share/keyrings/ubuntu-archive-keyring.gpg] https://archive.ubuntu.com/ubuntu $codename main universe
deb [arch=amd64 signed-by=/usr/share/keyrings/ubuntu-archive-keyring.gpg] https://archive.ubuntu.com/ubuntu $codename-updates main universe
deb [arch=amd64 signed-by=/usr/share/keyrings/ubuntu-archive-keyring.gpg] https://security.ubuntu.com/ubuntu $codename-security main universe
EOF
  local options=(
    -o "Dir::Etc::sourcelist=$apt_dir/sources.list"
    -o 'Dir::Etc::sourceparts=-'
    -o "Dir::State::lists=$apt_dir/lists"
    -o 'APT::Get::List-Cleanup=0'
    -o 'APT::Update::Error-Mode=any'
    -o 'Acquire::Languages=none'
    -o 'Acquire::Retries=2'
    -o 'Acquire::http::Timeout=20'
    -o 'Acquire::https::Timeout=20'
  )
  sudo -n env DEBIAN_FRONTEND=noninteractive timeout --signal=TERM --kill-after=10s 90s \
    apt-get "${options[@]}" update
  sudo -n env DEBIAN_FRONTEND=noninteractive timeout --signal=TERM --kill-after=10s 240s \
    apt-get "${options[@]}" install -y --no-install-recommends ffmpeg fonts-dejavu-core
)

main() {
  if toolchain_ready; then
    printf '%s\n' 'Using available FFmpeg/ffprobe with libx264, AAC, drawtext and DejaVu.'
  else
    printf '%s\n' 'Installing FFmpeg from isolated signed Ubuntu sources (bounded timeouts).'
    install_signed_ubuntu
    if ! toolchain_ready; then
      printf '%s\n' 'FFmpeg setup failed: working ffmpeg, ffprobe, libx264, AAC, drawtext and DejaVu are required.' >&2
      return 1
    fi
  fi
  local ffmpeg_version ffprobe_version
  ffmpeg_version="$(timeout 15s ffmpeg -version)"
  ffprobe_version="$(timeout 15s ffprobe -version)"
  printf '%s\n' "${ffmpeg_version%%$'\n'*}" "${ffprobe_version%%$'\n'*}"
}

if [[ "${BASH_SOURCE[0]}" = "$0" ]]; then main; fi
