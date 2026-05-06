#!/usr/bin/env bash
# Opens an SSH tunnel to the VAST cluster REST API for CI integration tests.
#
# Required env vars (set as GitLab CI/CD variables):
#   AWS_S3_ENDPOINT_URL   — cluster host:port, e.g. "172.27.151.2:443"
#   VASTDB_SSH_JUMP_HOST      — SSH jump host IP, e.g. "10.141.200.151"
#   VASTDB_ENDPOINT_USERNAME  — SSH username on jump host
#   VASTDB_ENDPOINT_PASSWORD  — SSH password on jump host
#
# After running this script, the calling shell must export the local endpoint:
#   export AWS_S3_ENDPOINT_URL="https://localhost:18151"
set -euo pipefail

LOCAL_PORT=18151
TUNNEL_HOST=$(echo "$AWS_S3_ENDPOINT_URL" | cut -d: -f1)
TUNNEL_PORT=$(echo "$AWS_S3_ENDPOINT_URL" | cut -d: -f2)

sshpass -p "$VASTDB_ENDPOINT_PASSWORD" ssh \
  -o StrictHostKeyChecking=no \
  -o UserKnownHostsFile=/dev/null \
  -f -N \
  -L "127.0.0.1:${LOCAL_PORT}:${TUNNEL_HOST}:${TUNNEL_PORT}" \
  "${VASTDB_ENDPOINT_USERNAME}@${VASTDB_SSH_JUMP_HOST}"

# Wait for tunnel to be ready before returning (DF-6).
MAX_WAIT=30
for i in $(seq 1 "$MAX_WAIT"); do
  if (exec 3<>/dev/tcp/127.0.0.1/"${LOCAL_PORT}") 2>/dev/null; then
    echo "Tunnel up: REST=https://localhost:${LOCAL_PORT}"
    exit 0
  fi
  sleep 1
done
echo "ERROR: tunnel to localhost:${LOCAL_PORT} not ready after ${MAX_WAIT}s" >&2
exit 1
