# Sobe o container com share SEFAZ montado (Windows).
$ErrorActionPreference = "Stop"
$Root = Split-Path -Parent (Split-Path -Parent $MyInvocation.MyCommand.Path)
Set-Location $Root

& "$Root\scripts\montar-share-sefaz.ps1"

$envFile = Join-Path $Root ".env"
if (-not (Test-Path $envFile)) {
    Copy-Item (Join-Path $Root ".env.example") $envFile
    Write-Host "Criado .env a partir de .env.example — configure credenciais Gov/AWS."
}

$content = Get-Content $envFile -Raw
if ($content -notmatch "SEFAZ_SHARE_HOST_PATH") {
    Add-Content $envFile "`nSEFAZ_SHARE_HOST_PATH=Z:/"
    Write-Host "Adicionado SEFAZ_SHARE_HOST_PATH=Z:/ ao .env"
}

docker compose down
docker compose up -d --build
Write-Host ""
Write-Host "App: http://localhost:3080 (ou APP_PORT no .env)"
Write-Host "JSONs locais: $Root\saida_pacotes"
