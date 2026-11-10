#!/usr/bin/env bash
set -euo pipefail
tag=docker.n8n.io/n8nio/n8n:2.47.3
docker pull "$tag"
image=$(docker image inspect --format '{{.Id}}' "$tag")
docker image inspect --format '{{json .RepoDigests}}' "$tag"
state=$(mktemp -d)
trap 'sudo rm -rf -- "$state"' EXIT
sudo chown 1000:1000 "$state"
sudo chmod 700 "$state"
fixture="$(pwd)/n8n-watchdog.synthetic.json"
args=(--rm --network none --cap-drop ALL --security-opt no-new-privileges
  -e N8N_DIAGNOSTICS_ENABLED=false -e N8N_VERSION_NOTIFICATIONS_ENABLED=false
  -e N8N_TEMPLATES_ENABLED=false -e N8N_RUNNERS_MODE=internal
  -v "$state:/home/node/.n8n" -v "$fixture:/fixture.json:ro")
docker run "${args[@]}" "$image" --version
docker run "${args[@]}" "$image" import:workflow --input=/fixture.json
docker run "${args[@]}" "$image" execute --id=XraySynthetic001 --rawOutput > /tmp/xray-n8n-execution.json
python3 n8n-runtime-check.py /tmp/xray-n8n-execution.json
