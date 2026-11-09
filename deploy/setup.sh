#!/usr/bin/env bash
# One-time setup of Ask Onboarding on a fresh Ubuntu server (24.04+, Google
# Cloud, Oracle Cloud, or any other). Run it from the repo folder:
#
#   bash deploy/setup.sh
#
# It opens ports 80/443, installs Docker, asks for a username and password
# for the site, writes .env, and starts the stack. Safe to run again: it
# keeps an existing .env. See deploy/README.md for the full guide.
set -euo pipefail
cd "$(dirname "$0")/.."

CADDY_IMAGE=caddy:2.10.2-alpine

# Minimal cloud images (such as Google's Ubuntu 26.04) leave out tools this
# script uses. Docker also needs iptables: without it the Docker service is
# installed but can't start ("failed to create NAT chain DOCKER").
# Checked through sudo, whose PATH is the one that matters here.
missing=""
for tool in curl openssl iptables; do
    sudo sh -c "command -v $tool" >/dev/null 2>&1 || missing="$missing $tool"
done
if [ -n "$missing" ]; then
    echo "==> Installing$missing"
    sudo apt-get update -qq && sudo apt-get install -y -qq $missing
fi

echo "==> 1/4 Opening ports 80 and 443 in the server's firewall"
# Oracle's Ubuntu images reject every incoming port except SSH (22) in the
# server's own firewall. Google leaves it open and filters in the cloud
# console instead, and its minimal images have no iptables at all.
if sudo sh -c 'command -v iptables' >/dev/null 2>&1; then
    for port in 80 443; do
        sudo iptables -C INPUT -p tcp --dport "$port" -m state --state NEW -j ACCEPT 2>/dev/null \
            || sudo iptables -I INPUT 1 -p tcp --dport "$port" -m state --state NEW -j ACCEPT
    done
    if command -v netfilter-persistent >/dev/null; then
        sudo netfilter-persistent save >/dev/null # keep the rules after a reboot
    fi
else
    echo "    No server firewall to change (normal on Google Cloud)"
fi

echo "==> 2/4 Installing Docker"
if ! command -v docker >/dev/null; then
    curl -fsSL https://get.docker.com | sudo sh
fi

echo "==> 3/4 Writing settings to .env"
if [ -f .env ]; then
    echo "    .env already exists, keeping it"
else
    ip=$(curl -4 -fsS https://ifconfig.me)
    read -rp "    Username for the site [demo]: " site_user
    site_user=${site_user:-demo}
    while true; do
        read -rsp "    Password for the site (at least 8 characters): " site_password
        echo
        [ "${#site_password}" -ge 8 ] && break
        echo "    Too short, try again."
    done
    hash=$(sudo docker run --rm "$CADDY_IMAGE" caddy hash-password --plaintext "$site_password")
    umask 077 # .env is readable only by you
    cat > .env <<EOF
# Written by deploy/setup.sh. Use both compose files on every command:
COMPOSE_FILE=docker-compose.yml:deploy/docker-compose.prod.yml

# Public address. sslip.io turns the IP into a host name, so Caddy can get an
# HTTPS certificate without you buying a domain.
SITE_ADDRESS=${ip//./-}.sslip.io

# Login for the site. The hash is in single quotes so the \$ signs stay literal.
DEMO_USER=${site_user}
DEMO_PASSWORD_HASH='${hash}'

POSTGRES_PASSWORD=$(openssl rand -hex 16)
EOF
    echo "    Saved. Site address: https://${ip//./-}.sslip.io"
fi

echo "==> 4/4 Building and starting (the first time takes about 10-15 minutes)"
sudo docker compose up -d --build

site=$(grep '^SITE_ADDRESS=' .env | cut -d= -f2)
cat <<EOF

Started. The first start also downloads the answer model (1.9 GB), so give it
a few more minutes, then open:

    https://${site}

Follow progress:   sudo docker compose logs -f api ollama-pull
Update later:      git pull && sudo docker compose up -d --build
EOF
