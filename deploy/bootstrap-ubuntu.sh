#!/usr/bin/env bash
# Run on the single Ubuntu VM before building the deployment images.
set -euo pipefail
. /etc/os-release
if [ "$ID" != ubuntu ] || [ "$VERSION_ID" != 24.04 ]; then
  printf '%s\n' 'This script supports Ubuntu 24.04 only.' >&2
  exit 1
fi
if ! command -v docker >/dev/null || ! sudo docker compose version >/dev/null 2>&1; then
  sudo apt-get update -qq
  sudo env DEBIAN_FRONTEND=noninteractive apt-get install -y -qq ca-certificates curl
  sudo install -m 0755 -d /etc/apt/keyrings
  sudo curl -fsSL https://download.docker.com/linux/ubuntu/gpg -o /etc/apt/keyrings/docker.asc
  sudo chmod a+r /etc/apt/keyrings/docker.asc
  arch=$(dpkg --print-architecture)
  sudo tee /etc/apt/sources.list.d/docker.sources >/dev/null <<EOF
Types: deb
URIs: https://download.docker.com/linux/ubuntu
Suites: noble
Components: stable
Architectures: $arch
Signed-By: /etc/apt/keyrings/docker.asc
EOF
  sudo apt-get update -qq
  sudo env DEBIAN_FRONTEND=noninteractive apt-get install -y -qq docker-ce docker-ce-cli containerd.io docker-buildx-plugin docker-compose-plugin
fi
sudo systemctl enable --now docker
# Small college VMs need headroom for the frontend build. Never overwrite an existing file.
if [ "$(awk '/MemTotal/ {print $2}' /proc/meminfo)" -lt 3000000 ] && [ -z "$(swapon --show --noheadings)" ]; then
  if [ ! -e /swapfile-anvaya ]; then
    sudo install -m 0600 /dev/null /swapfile-anvaya
    sudo fallocate -l 2G /swapfile-anvaya
    sudo mkswap /swapfile-anvaya
    sudo swapon /swapfile-anvaya
    printf '%s\n' '/swapfile-anvaya none swap sw 0 0' | sudo tee -a /etc/fstab >/dev/null
  fi
fi
sudo docker --version
sudo docker compose version
free -m
