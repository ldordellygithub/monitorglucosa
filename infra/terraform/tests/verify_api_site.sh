#!/usr/bin/env bash
# [req fase-1a:4.5, fase-1a:6.1, fase-1a:6.2, fase-1a:6.3, fase-1a:6.4, fase-1a:6.5]
# Ejecuta las pruebas de Terraform de los módulos `site` y `api` sin credenciales AWS.
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
TF_DIR="$(cd "${SCRIPT_DIR}/.." && pwd)"
TF_IMAGE="hashicorp/terraform:1.16.6@sha256:bfffc1ded5fbf0a17beaaf22eb4793980abdb19d0761ff6a3a0efb2ab4d9b316"

run_tf() {
  if command -v terraform >/dev/null 2>&1; then
    (cd "${TF_DIR}" && terraform "$@")
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

echo "[$(date '+%Y-%m-%d %H:%M:%S')] Inicializando módulos sin backend remoto..."
run_tf init -backend=false -input=false

echo "[$(date '+%Y-%m-%d %H:%M:%S')] Validando configuración Terraform..."
run_tf validate

echo "[$(date '+%Y-%m-%d %H:%M:%S')] Ejecutando terraform test (api_site.tftest.hcl)..."
run_tf test -filter=tests/api_site.tftest.hcl
