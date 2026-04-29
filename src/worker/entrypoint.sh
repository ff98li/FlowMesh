#!/usr/bin/env bash
set -euo pipefail

# -----------------------------
# Server defaults (override via env)
# -----------------------------
: "${SERVER_HOST:=flowmesh_server}"
: "${SERVER_GRPC_PORT:=50051}"
: "${SUPERVISOR_GRPC_EXTERNAL_PORT:=}"

if [[ -z "${SUPERVISOR_GRPC_TARGET:-}" ]]; then
  if [[ -n "${SUPERVISOR_GRPC_EXTERNAL_PORT}" ]]; then
    export SUPERVISOR_GRPC_TARGET="${SERVER_HOST}:${SUPERVISOR_GRPC_EXTERNAL_PORT}"
  else
    export SUPERVISOR_GRPC_TARGET="${SERVER_HOST}:${SERVER_GRPC_PORT}"
  fi
fi

# -----------------------------
# Optional worker namespace, cluster, and alias (leave empty to let app decide)
# -----------------------------
export WORKER_NAMESPACE="${WORKER_NAMESPACE:-flowmesh}"
export WORKER_CLUSTER="${WORKER_CLUSTER:-cluster}"
export WORKER_ALIAS="${WORKER_ALIAS:-}"

# -----------------------------
# HuggingFace authentication and model pre-downloading
# -----------------------------
# Use token-based auth via env.
if [[ -n "${HF_TOKEN:-}" ]]; then
  # Sanitize HF_TOKEN
  raw_token="${HF_TOKEN}"
  token=$(printf '%s' "${raw_token}" | sed -e 's/^[[:space:]]*//' -e 's/[[:space:]]*$//')
  if [[ "$token" =~ ^\".*\"$ ]]; then token="${token:1:${#token}-2}"; fi
  if [[ "$token" =~ ^\'.*\'$ ]]; then token="${token:1:${#token}-2}"; fi
  
  # Set cache dirs
  export HF_HOME="${HF_HOME:-/home/appuser/.cache/huggingface}"
  export HUGGINGFACE_HUB_TOKEN="${token}"
  export HUGGINGFACE_HUB_CACHE="${HF_HOME}/hub"
  export HF_HUB_CACHE="${HUGGINGFACE_HUB_CACHE}"
  mkdir -p "${HUGGINGFACE_HUB_CACHE}" 2>/dev/null || true
  echo "[HF] Using token from environment. HF_HOME=${HF_HOME} HUB_CACHE=${HUGGINGFACE_HUB_CACHE}"

  # Pre-download models if list is provided
  if [[ -n "${PREDOWNLOAD_MODEL_LIST:-}" ]]; then
    if command -v hf >/dev/null 2>&1; then
      sleep $((RANDOM % 3))
      # Acquire a lock; wait up to PREFETCH_LOCK_WAIT seconds
      mkdir -p "${HF_HOME}" 2>/dev/null || true
      exec {lockfd}>"${HF_HOME}/.prefetch.lock" || true
      lock_wait="${PREFETCH_LOCK_WAIT:-300}"
      if flock -w "$lock_wait" "$lockfd"; then
        # Set umask to make files group/other readable and writable
        umask 0000
        IFS=',' read -ra MODEL_ARRAY <<< "$PREDOWNLOAD_MODEL_LIST"
        for model in "${MODEL_ARRAY[@]}"; do
          # sanitize quotes and trim whitespace
          model=$(printf '%s' "$model" | tr -d '"' | sed -e 's/^[[:space:]]*//' -e 's/[[:space:]]*$//')
          if [[ -n "$model" ]]; then
            echo "[HF] Downloading: $model"
            log_file="${HF_HOME}/prefetch_$(echo "$model" | tr '/' '_').log"
            if hf download "$model" --token "${HUGGINGFACE_HUB_TOKEN}" > "$log_file" 2>&1; then
              echo "[HF] ✓ $model"
            else
              echo "[HF] ✗ $model (see $log_file)"
            fi
          fi
        done
        flock -u "$lockfd" || true
        chmod -R a+rw "${HUGGINGFACE_HUB_CACHE}" 2>/dev/null || true
        find "${HUGGINGFACE_HUB_CACHE}" -type d -exec chmod a+rwx {} \; 2>/dev/null || true
        # Cleanup: remove lock file and log files
        rm -f "${HF_HOME}/.prefetch.lock" 2>/dev/null || true
        rm -f "${HF_HOME}"/prefetch_*.log 2>/dev/null || true
        echo "[HF] Cleaned up prefetch lock and log files"
      else
        echo "[HF] Another worker is pre-downloading; lock wait (${lock_wait}s) elapsed, skipping"
      fi
      echo "[HF] Model pre-downloading completed"
    else
      echo "[HF] Warning: hf CLI not found; skipping model pre-download"
    fi
  else
    echo "[HF] No models specified for pre-downloading (PREDOWNLOAD_MODEL_LIST is empty)"
  fi
else
echo "[HF] No HF_TOKEN provided. Skipping HuggingFace auth and pre-download."
echo "[HF] Note: Some gated models (e.g., Llama) require authentication."
fi

# -----------------------------
# Print key environment values
# -----------------------------
echo "Starting worker..."
echo "SUPERVISOR_GRPC_TARGET=${SUPERVISOR_GRPC_TARGET}"
echo "RESULTS_DIR=${RESULTS_DIR:-./results}"
echo "HEARTBEAT_INTERVAL_SEC=${HEARTBEAT_INTERVAL_SEC:-30}"
echo "HF_HOME=${HF_HOME:-/home/appuser/.cache/huggingface}"

# -----------------------------
# Run worker
# -----------------------------
cd /app && exec python -m worker.main
