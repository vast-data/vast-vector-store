#!/usr/bin/env bash
# Opens an SSH tunnel to the VAST cluster REST API for CI integration tests.
#
# Required env vars (set as GitLab CI/CD variables):
#   VASTDB__ENDPOINT          — cluster host:port, e.g. "172.27.151.2:443"
#   VASTDB__SSH_JUMP_HOST     — SSH jump host IP, e.g. "10.141.200.151"
#   VASTDB__ENDPOINT_USERNAME — SSH username on jump host
#   VASTDB__ENDPOINT_PASSWORD — SSH password on jump host
#
# After running this script, override the endpoint env var in the calling shell:
#   export VASTDB__ENDPOINT="https://localhost:18151"
set -euo pipefail

LOCAL_PORT=18151
TUNNEL_HOST=$(echo "$VASTDB__ENDPOINT" | cut -d: -f1)
TUNNEL_PORT=$(echo "$VASTDB__ENDPOINT" | cut -d: -f2)

sshpass -p "$VASTDB__ENDPOINT_PASSWORD" ssh \
  -o StrictHostKeyChecking=no \
  -o UserKnownHostsFile=/dev/null \
  -f -N \
  -L "${LOCAL_PORT}:${TUNNEL_HOST}:${TUNNEL_PORT}" \
  "${VASTDB__ENDPOINT_USERNAME}@${VASTDB__SSH_JUMP_HOST}"

echo "Tunnel up: REST=https://localhost:${LOCAL_PORT}"
