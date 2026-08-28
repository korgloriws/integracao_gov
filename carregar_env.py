import os

PREFIXO_SEFAZ_PADRAO = r"\\10.129.1.254\sefas - sufin"
_DIRETORIO_PROJETO = os.path.dirname(os.path.abspath(__file__))


def diretorio_projeto() -> str:
    """Raiz do projeto (main.py, saida_pacotes, .env). Não depende de os.getcwd()."""
    return _DIRETORIO_PROJETO


def diagnosticar_share_sefaz() -> dict:
    """
    Verifica se o compartilhamento SEFAZ está acessível.
    No Docker, SEFAZ_SHARE_ROOT=/mnt/sefaz precisa estar montado no host.
    """
    carregar_env()
    root = os.getenv("SEFAZ_SHARE_ROOT", PREFIXO_SEFAZ_PADRAO).rstrip("/\\")
    teste_mab = sefaz_path("Arrecadacao", "Recep", "Arquivos FEBRABRAN", "CEF", "CAIXA2026")
    teste_safci = sefaz_path(
        "Arrecadacao", "SEFAZ-Tesouraria", "SAFCI INTEGRACAO",
        "Arquivos Exportação ao SAFCI", "2026",
    )
    root_ok = os.path.isdir(root)
    mab_ok = os.path.isdir(teste_mab)
    safci_ok = os.path.isdir(teste_safci)
    acessivel = mab_ok or safci_ok
    if acessivel:
        msg = "Compartilhamento SEFAZ acessível"
    elif root_ok:
        msg = (
            f"Pasta raiz existe ({root}), mas subpastas MAB/SAFCI não foram encontradas. "
            "Verifique VPN e caminhos do ano."
        )
    elif root.startswith("/mnt/"):
        msg = (
            f"Share não montado em {root}. No Docker (Windows): execute scripts/montar-share-sefaz.ps1, "
            "defina SEFAZ_SHARE_HOST_PATH no .env e reinicie o container."
        )
    else:
        msg = f"Não foi possível acessar {root}. Verifique rede/VPN."
    return {
        "acessivel": acessivel,
        "mensagem": msg,
        "root": root,
        "root_existe": root_ok,
        "mab_existe": mab_ok,
        "safci_existe": safci_ok,
        "teste_mab": teste_mab,
        "teste_safci": teste_safci,
    }


def carregar_env() -> None:
    caminho = os.path.join(os.path.dirname(os.path.abspath(__file__)), ".env")
    if not os.path.isfile(caminho):
        return
    with open(caminho, encoding="utf-8") as arquivo:
        for linha in arquivo:
            linha = linha.strip()
            if not linha or linha.startswith("#") or "=" not in linha:
                continue
            chave, valor = linha.split("=", 1)
            chave = chave.strip()
            valor = valor.strip().strip('"').strip("'")
            if not chave or not valor:
                continue
            # Linha vazia no .env não pode "prender" a variável como string vazia
            if not (os.environ.get(chave) or "").strip():
                os.environ[chave] = valor


def sefaz_path(*partes: str) -> str:
    """Monta caminho na pasta da SEFAZ. No Docker use SEFAZ_SHARE_ROOT=/mnt/sefaz."""
    carregar_env()
    root = os.getenv("SEFAZ_SHARE_ROOT", PREFIXO_SEFAZ_PADRAO).rstrip("/\\")
    rel = "/".join(p.replace("\\", "/").strip("/") for p in partes if p)
    if not rel:
        return root
    if root.startswith("\\\\") or (len(root) >= 2 and root[1] == ":"):
        return root + "\\" + rel.replace("/", "\\")
    return root + "/" + rel
