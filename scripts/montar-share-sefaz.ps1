# Mapeia o compartilhamento SEFAZ para a unidade Z: (necessário para Docker no Windows).
# Execute como usuário que tem acesso à rede/VPN da prefeitura.
# Requer permissão para montar unidade de rede.

$ErrorActionPreference = "Stop"

$Unc = "\\10.129.1.254\sefas - sufin"
$Drive = "Z:"

Write-Host "Montando SEFAZ em $Drive -> $Unc"

# Remove mapeamento antigo se existir
$existing = net use $Drive 2>$null
if ($LASTEXITCODE -eq 0) {
    net use $Drive /delete /y | Out-Null
}

net use $Drive $Unc /persistent:yes
if ($LASTEXITCODE -ne 0) {
    Write-Error "Falha ao mapear $Unc. Verifique VPN/rede e credenciais."
    exit 1
}

# Teste rápido
$teste = Join-Path $Drive "Arrecadacao"
if (-not (Test-Path $teste)) {
    Write-Warning "Unidade mapeada, mas pasta Arrecadacao não encontrada em $teste"
} else {
    Write-Host "OK: $teste acessível"
}

Write-Host ""
Write-Host "Próximos passos:"
Write-Host "  1. Docker Desktop > Settings > Resources > File sharing > inclua a unidade Z:"
Write-Host "  2. No .env do projeto: SEFAZ_SHARE_HOST_PATH=Z:/"
Write-Host "  3. docker compose down && docker compose up -d --build"
Write-Host "  4. Teste APIs na interface (deve aparecer Share SEFAZ ok)"
