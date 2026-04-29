variable "REGISTRY" {
  default = "ghcr.io/mlsys-io"
}

variable "VERSION" {
  default = "dev"
}

variable "BUILD_REF" {
  default = "local"
}

variable "BUILD_CREATED" {
  default = "unknown"
}

group "server" {
  targets = ["flowmesh_server"]
}

group "workers" {
  targets = [
    "flowmesh_worker_cpu",
    "flowmesh_worker_gpu",
    "flowmesh_ssh_cpu",
    "flowmesh_ssh_gpu",
  ]
}

group "builders" {
  targets = [
    "flowmesh_worker_gpu_builder",
  ]
}

group "default" {
  targets = concat(
    group.server.targets,
    group.workers.targets,
  )
}

target "flowmesh_server" {
  context    = "."
  dockerfile = "src/server/Dockerfile"
  args = {
    BUILD_VERSION = "${VERSION}"
    BUILD_REF     = "${BUILD_REF}"
    BUILD_CREATED = "${BUILD_CREATED}"
  }
  tags = ["${REGISTRY}/flowmesh_server:${VERSION}"]
}

target "flowmesh_worker_cpu" {
  context    = "."
  dockerfile = "src/worker/docker/Dockerfile.cpu"
  args = {
    BUILD_VERSION = "${VERSION}"
    BUILD_REF     = "${BUILD_REF}"
    BUILD_CREATED = "${BUILD_CREATED}"
  }
  tags = ["${REGISTRY}/flowmesh_worker:${VERSION}-cpu"]
}

target "flowmesh_worker_gpu_builder" {
  context    = "."
  dockerfile = "src/worker/docker/Dockerfile.cuda.builder"
  args = {
    BUILD_VERSION = "${VERSION}"
    BUILD_REF     = "${BUILD_REF}"
    BUILD_CREATED = "${BUILD_CREATED}"
  }
  tags = ["${REGISTRY}/flowmesh_worker_builder:${VERSION}-gpu"]
}

target "flowmesh_worker_gpu" {
  context    = "."
  dockerfile = "src/worker/docker/Dockerfile.cuda"
  contexts = {
    builder = "target:flowmesh_worker_gpu_builder"
  }
  args = {
    BUILD_VERSION = "${VERSION}"
    BUILD_REF     = "${BUILD_REF}"
    BUILD_CREATED = "${BUILD_CREATED}"
  }
  tags = ["${REGISTRY}/flowmesh_worker:${VERSION}-gpu"]
}

target "flowmesh_ssh_cpu" {
  context    = "."
  dockerfile = "src/worker/docker/Dockerfile.ssh.cpu"
  args = {
    BUILD_VERSION = "${VERSION}"
    BUILD_REF     = "${BUILD_REF}"
    BUILD_CREATED = "${BUILD_CREATED}"
  }
  tags = ["${REGISTRY}/flowmesh_ssh:${VERSION}-cpu"]
}

target "flowmesh_ssh_gpu" {
  context    = "."
  dockerfile = "src/worker/docker/Dockerfile.ssh.gpu"
  args = {
    BUILD_VERSION = "${VERSION}"
    BUILD_REF     = "${BUILD_REF}"
    BUILD_CREATED = "${BUILD_CREATED}"
  }
  tags = ["${REGISTRY}/flowmesh_ssh:${VERSION}-gpu"]
}
