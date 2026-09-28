#!/bin/bash
# Monta o compartilhamento SEFAZ em /mnt/sefaz (Linux / VPS).
# Requer: cifs-utils, VPN/rede até 10.129.1.254, arquivo de credenciais.
#
# Uso:
#   sudo cp scripts/sefaz-cifs.credentials.example /etc/sefaz-cifs.credentials
#   sudo nano /etc/sefaz-cifs.credentials   # preencha user/password
#   sudo chmod 600 /etc/sefaz-cifs.credentials
#   sudo ./scripts/montar-share-sefaz.sh

set -euo pipefail

MOUNT_POINT="${SEFAZ_MOUNT_POINT:-/mnt/sefaz}"
# Ajuste o nome do share se necessário (espaço vira %20 em alguns servidores)
UNC="${SEFAZ_CIFS_UNC:-//10.129.1.254/SEFAS - SUFIN}"
CREDS="${SEFAZ_CIFS_CREDENTIALS:-/etc/sefaz-cifs.credentials}"

if ! command -v mount.cifs >/dev/null 2>&1; then
  echo "Instale cifs-utils: apt-get install -y cifs-utils"
  exit 1
fi

if [[ ! -f "$CREDS" ]]; then
  echo "Arquivo de credenciais não encontrado: $CREDS"
  echo "Copie scripts/sefaz-cifs.credentials.example para $CREDS e preencha."
  exit 1
fi

mkdir -p "$MOUNT_POINT"

if mountpoint -q "$MOUNT_POINT"; then
  echo "Já montado em $MOUNT_POINT — desmontando para remontar..."
  umount "$MOUNT_POINT" || true
fi

mount -t cifs "$UNC" "$MOUNT_POINT" \
  -o "credentials=${CREDS},ro,vers=3.0,uid=0,gid=0,file_mode=0444,dir_mode=0555"

if [[ -d "$MOUNT_POINT/Arrecadacao" ]]; then
  echo "OK: $MOUNT_POINT/Arrecadacao acessível"
else
  echo "AVISO: montado em $MOUNT_POINT, mas Arrecadacao não encontrada — confira UNC/credenciais."
fi

echo ""
echo "Para persistir após reboot, adicione ao /etc/fstab (exemplo):"
echo "$UNC $MOUNT_POINT cifs credentials=$CREDS,ro,vers=3.0,_netdev 0 0"
echo ""
echo "No .env do projeto (Linux): SEFAZ_SHARE_HOST_PATH=/mnt/sefaz"
echo "Depois: docker compose up -d --build"
