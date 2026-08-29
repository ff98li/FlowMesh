# Environment variables (curated)

The canonical declared set lives in
`cli/stack/src/flowmesh_cli_stack/env_schema.py` and is mirrored to
`cli/stack/src/flowmesh_cli_stack/assets/.env.example`. Run
`uv run scripts/dev/check_env_examples.py --write` after schema edits.

The tables below curate the knobs you actually tune. Anything not
listed here is in `.env.example`.

## Server

| Variable | Default | Description |
|----------|---------|-------------|
| `NODE_ROLE` | `root` | `root` deploys local Redis; `worker` skips it and connects to the root's Redis via the URLs below |
| `REDIS_CONTROL_URL` | `redis://localhost:6379/0` | Redis control channel. On worker nodes, must point at the root node's reachable Redis endpoint |
| `REDIS_TELEMETRY_URL` | `redis://localhost:6380/0` | Redis telemetry channel. On worker nodes, must point at the root node's reachable Redis endpoint |
| `DATABASE_URL` | – | Postgres connection string |
| `RESULTS_DIR` | `./results` | Server-side results directory |
| `SERVER_RESULTS_DIR` | `flowmesh_results` | Host-side directory/docker volume to mount at `RESULTS_DIR` in the server container |
| `WORKER_RESULTS_DIR` | `flowmesh_results` | Server-side directory/docker volume to mount to worker containers |
| `SERVER_HTTP_PORT` | `8000` | Public HTTP port |
| `SERVER_GRPC_HOST` | `0.0.0.0` | Supervisor gRPC bind address; use `127.0.0.1` for a single-node local-only deployment |
| `SERVER_GRPC_PORT` | `50051` | Supervisor gRPC port |
| `ORCHESTRATOR_DISPATCH_MODE` | `adaptive` | Scheduler mode |
| `ORCHESTRATOR_WORKER_SELECTION` | `best_fit` | `best_fit`, `first_fit`, `min_satisfying` |
| `SCHEDULER_LAMBDA_INFERENCE` | `0.4` | Inference task weight |
| `SCHEDULER_LAMBDA_TRAINING` | `0.8` | Training task weight |
| `SCHEDULER_LAMBDA_OTHER` | `0.5` | Other-task weight |
| `SCHEDULER_SELECTION_JITTER` | `1e-3` | Tie-break jitter |
| `ENABLE_TASK_MERGE` | `true` | DAG-level task coalescing |
| `TASK_MERGE_MAX_BATCH_SIZE` | `4` | Max merged tasks per dispatch |
| `ENABLE_CONTEXT_REUSE` | `true` | Bias toward workers with cached models |
| `WORKER_CACHE_TTL_SEC` | `3600` | Cache metadata TTL |
| `ENABLE_STAGE_WEIGHT_STICKINESS` | `false` | Pin stages to checkpoint-producing workers |
| `TASK_NO_WORKER_GRACE_SEC` | `60` | Grace before failing a task no worker can satisfy |
| `ENABLE_WORKER_WATCHDOG` | `true` | Worker death detection |
| `WORKER_DEATH_GRACE_SEC` | `60` | Grace period before marking dead |
| `WORKER_REHYDRATION_GRACE_SEC` | `120` | Extra grace for a worker's rehydrated in-flight tasks after the root restarts, before the watchdog may reclaim them |
| `FLOWMESH_PLUGINS` | – | Comma-separated plugin module names |
| `FLOWMESH_PLUGIN_DATA_DIR` | `./plugin-data` | Writable mount at `/app/plugin-data` for plugin state. A path -> host bind-mount (auto-created); a bare name -> external Docker volume of that name. |
| `SERVER_CUDA_PROBE_IMAGE` | `nvidia/cuda:12.9.1-base-ubuntu24.04` | CUDA image the server runs briefly to query local GPU names/indices |
| `DOCKER_GPU_RUNTIME` | nvidia | Optional Docker runtime name for GPU probe/worker containers; leave empty unless the host requires a named runtime such as `nvidia` |
| `FLOWMESH_API_KEY` | – | Forwarded to spawned workers as their server-callback bearer; also the expected static bearer when static auth is required |
| `FLOWMESH_REQUIRE_API_KEY` | `false` | Require `FLOWMESH_API_KEY` bearer authentication when no IdentityProvider plugin is installed |
| `FLOWMESH_READY_MIN_WORKERS` | `0` | Minimum number of non-stale IDLE/BUSY workers required by `/readyz` and `/healthz` |
| `FLOWMESH_ALLOW_PRIVILEGED_WORKER_OVERRIDES` | `false` | Allow dynamic worker requests to set host paths, image identity, Docker SSH/socket access, or container identity; keep disabled for shared deployments |
| `ENABLE_PERSISTENT_PORT_FORWARD` | `true` | Keep port-forward listeners bound between task sessions; disable to bind listeners only for active sessions |
| `ENABLE_SERVER_SSH_PROXY` | `true` | Enable the WebSocket proxy for interactive SSH tasks |
| `ENABLE_SERVER_SERVE_PROXY` | `true` | Enable the HTTP reverse proxy for `serve` tasks |
| `LOG_LEVEL` | `INFO` | Server log level |

**Notes:**
- In Docker deployments, `SERVER_RESULTS_DIR` and `WORKER_RESULTS_DIR`
are the host directories or Docker volumes mounted into the server and
worker containers for storing and reading task results. For workflows
with a local output destination (`spec.output.destination.type="local"`)
that have downstream tasks, both variables must point to the same shared
directory or volume so the server can access the worker's task results.
Otherwise, downstream tasks that depend on upstream outputs will stall
in the dispatching loop indefinitely.
- When multiple deployments share one host, you can set `FLOWMESH_STACK_SUFFIX`
in `.env` to differentiate the deployments so that FlowMesh stack CLI does
not interfere with each other.
- `DOCKER_GPU_RUNTIME` defaults to `nvidia`. On hosts where Docker GPU access
works with `--gpus all` but fails with `--runtime=nvidia` (for example, DGX
Spark), set `DOCKER_GPU_RUNTIME=` in the stack env.

## Worker provider safety

Dynamic Docker-worker requests accept only resource selection and metadata:
`worker_type`, `gpu_count`, `cuda_devices`, `worker_alias`, `tags`,
`network_bandwidth`, and `worker_cost_per_hour`. Host bind paths, image
registry/version, SSH/socket access, and container names must come from the
operator-owned worker configuration. Native requests use the same allowlist.
Docker display aliases are kept separate from generated container identities,
so an alias cannot select and force-remove an unrelated stopped container.
Vast.ai requests accept bounded offer-selection fields (`disk`, `order`,
`search_limit`, and `label`) plus non-privileged metadata, but cannot replace
the operator's trusted-offer constraints, select an existing instance, replace
the configured image, redirect the supervisor connection, choose host paths,
or inject credentials. The privileged override switch above disables these
request-layer safeguards and should only be used on a separately authenticated
administrative control plane.
Dynamic requests also cannot choose their gRPC worker token; the supervisor
generates an unpredictable token after validation.
Stack scaffolding leaves `ENABLE_SSH_BY_DEFAULT=false`; enable it only in an
operator-owned deployment configuration that intentionally grants workers
access to the Docker socket.

Native workers always execute the current Python interpreter with
`-m worker.main` from FlowMesh's source directory. API/config payloads cannot
replace the command, working directory, heartbeat file, or log directory.
Native logs are placed under the operator-configured `WORKER_HB_DIR`.
Heartbeat and log filenames are derived from a digest rather than a
request-supplied worker token or alias.
Native child processes inherit only a runtime allowlist (for example PATH,
locale, CUDA/HPC runtime, TLS certificate, temporary-directory and Slurm
metadata variables) plus FlowMesh's explicit worker environment. Unrelated
supervisor environment variables are not copied into workers.

For native GPU workers, `cuda_devices` contains allocation-relative slots, not
host-global GPU numbers. FlowMesh preserves the parent
`CUDA_VISIBLE_DEVICES` tokens, including GPU UUID and MIG UUID forms, and maps
slot `0` to the first token in that allocation. Omitting `cuda_devices` and
setting `gpu_count` is preferred for scheduler-managed allocations.

Provider stop must confirm the native process, Docker container, or Vast.ai
instance has exited before FlowMesh releases an in-process GPU/offer
reservation. This quarantine state is not durable across a supervisor crash or
restart; deployments must still use Slurm/cgroup cleanup and reconcile orphaned
remote instances after abnormal termination.

## Worker

| Variable | Default | Description |
|----------|---------|-------------|
| `WORKER_TOKEN` | – | Auth token for supervisor gRPC |
| `SUPERVISOR_GRPC_TARGET` | – | Supervisor gRPC endpoint |
| `RESULTS_DIR` | `./results` | Task output directory |
| `WORKER_TAGS` | `` | Scheduler hints |
| `WORKER_COST_PER_HOUR` | `1.0` | Cost metadata |
| `WORKER_UPLOAD_RESULTS` | `false` | Upload results when no destination set |
| `WORKER_EXECUTOR_IDLE_CLEANUP_SEC` | `60` | Seconds a worker waits before unloading an idle executor to release the resources it holds; higher values avoid reload thrash between tasks but keep those resources reserved while idle |
| `HF_CACHE_DIR` | – | Shared HuggingFace cache mount |
| `HEARTBEAT_INTERVAL_SEC` | `30` | Heartbeat cadence |
| `SERVE_DEFAULT_TTL_SEC` | `3600` | Default vLLM serve session TTL when `spec.ttlSeconds` is unset |
| `SERVE_MAX_TTL_SEC` | `86400` | Upper bound on vLLM serve session TTL, regardless of `spec.ttlSeconds` |

## Supervisor

| Variable | Default | Description |
|----------|---------|-------------|
| `NODE_NAMESPACE` / `NODE_CLUSTER` / `NODE_ALIAS` | defaults | Identity |
| `NODE_TAGS` | `` | Scheduler hints (CSV) |
| `SUPERVISOR_GRPC_DISABLE_SERVER_TLS` | `false` | Local-only insecure gRPC |
| `SUPERVISOR_GRPC_KEEPALIVE_PERMIT_WITHOUT_CALLS` | `true` | gRPC keepalive |
| `SUPERVISOR_GRPC_EXTERNAL_PORT` | – | External port (when port-forwarded) |
| `SERVER_GRPC_TLS_*` | – | TLS certificate files |

## SSH session resource caps

When `enable_ssh` is true on a Docker worker, these configured
ceilings bound every SSH session container spawned by that worker.
Unset values mean unbounded (host-wide access).

| Variable | Default | Description |
|----------|---------|-------------|
| `SSH_MAX_CPU` | – | Max CPU cores per SSH container (float, e.g. `4` or `2.5`). Sets Docker `nano_cpus`. |
| `SSH_MAX_MEMORY` | – | Max memory per SSH container (e.g. `8Gi`, `512Mi`, or a byte count). Sets Docker `mem_limit`. |
| `SSH_MAX_PIDS` | – | Max PIDs per SSH container. Sets Docker `pids_limit`. Admin-only — not user-overridable. |
| `ENABLE_SSH_GPU_LIMIT` | `false` | When `true`, mount only the GPU subset matching the spec (`count` / `type` / `memory`); otherwise mount all worker GPUs. |

The effective CPU/memory limit is `min(spec.resources.hardware, worker
cap)`. A task that requests more than the worker cap is dispatched to
another worker if one has a larger cap; otherwise the dispatcher
follows its standard requeue/retry behavior. The worker logs a startup
warning if SSH is enabled with no cap configured.
