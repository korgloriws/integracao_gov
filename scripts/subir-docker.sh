#!/bin/bash
# Sobe o container na VPS/Linux (share deve estar em /mnt/sefaz).
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT"

if [[ -f scripts/montar-share-sefaz.sh ]] && [[ ! -d /mnt/sefaz/Arrecadacao ]]; then
  echo "Share ainda não montado. Execute como root:"
  echo "  sudo ./scripts/montar-share-sefaz.sh"
  exit 1
fi

ENV_FILE="$ROOT/.env"
if [[ ! -f "$ENV_FILE" ]]; then
  cp .env.example "$ENV_FILE"
  echo "Criado .env — configure credenciais Gov/AWS."
fi

if grep -q '^SEFAZ_SHARE_HOST_PATH=Z:' "$ENV_FILE" 2>/dev/null; then
  sed -i 's|^SEFAZ_SHARE_HOST_PATH=Z:/|SEFAZ_SHARE_HOST_PATH=/mnt/sefaz|' "$ENV_FILE"
  echo "Corrigido SEFAZ_SHARE_HOST_PATH para /mnt/sefaz (Linux)."
fi

if ! grep -q '^SEFAZ_SHARE_HOST_PATH=' "$ENV_FILE" 2>/dev/null; then
  echo 'SEFAZ_SHARE_HOST_PATH=/mnt/sefaz' >> "$ENV_FILE"
fi

docker compose down
docker compose up -d --build
echo "App: http://$(hostname -I | awk '{print $1}'):${APP_PORT:-3080}"
echo "JSONs: $ROOT/saida_pacotes"
