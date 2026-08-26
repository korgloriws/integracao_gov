import os

PREFIXO_SEFAZ_PADRAO = r"\\10.129.1.254\sefas - sufin"


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
