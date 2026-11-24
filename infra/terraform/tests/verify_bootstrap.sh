#!/usr/bin/env bash
# [req fase-1a:6.1, fase-1a:7.2, fase-1a:8.1, fase-1a:8.2]
# Ejecuta fmt, init (-backend=false), validate y terraform test del módulo bootstrap.
set -euo pipefail

TF_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
TF_IMAGE="hashicorp/terraform:1.16.6@sha256:bfffc1ded5fbf0a17beaaf22eb4793980abdb19d0761ff6a3a0efb2ab4d9b316"

run_tf() {
  if command -v terraform >/dev/null 2>&1; then
    terraform -chdir="${TF_DIR}" "$@"
  else
    docker run --rm \
      -u "$(id -u):$(id -g)" \
      -e HOME=/tmp \
      -v "${TF_DIR}:/workspace" \
      -w /workspace \
      "${TF_IMAGE}" "$@"
  fi
}

echo "[$(date '+%Y-%m-%d %H:%M:%S')] Validando formato Terraform..."
run_tf fmt -check -recursive

echo "[$(date '+%Y-%m-%d %H:%M:%S')] Inicializando proveedores sin backend remoto..."
run_tf init -backend=false -input=false

echo "[$(date '+%Y-%m-%d %H:%M:%S')] Validando configuración Terraform..."
run_tf validate

echo "[$(date '+%Y-%m-%d %H:%M:%S')] Ejecutando terraform test (bootstrap.tftest.hcl)..."
run_tf test -filter=tests/bootstrap.tftest.hcl
