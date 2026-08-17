import json
import os
from datetime import datetime
from pathlib import Path
from typing import Dict, List

import requests
from carregar_env import carregar_env

carregar_env()

API_URL = os.getenv(
    "API_URL",
    "https://v60yr1ma4f.execute-api.sa-east-1.amazonaws.com/prod/upload-arquivos",
)
API_KEY = os.getenv("AWS_API_KEY", "")
PASTA_ARQUIVOS = Path("arquivos")
TIMEOUT_SECONDS = 40


def montar_file_name(dados: Dict, tipo_forcado: str) -> str:
    data_arrec = str(dados.get("data_arrecadacao") or dados.get("data_filtro") or datetime.now().strftime("%d-%m-%Y"))
    data_arrec = data_arrec.replace("/", "-").strip()
    return f"{tipo_forcado}_{data_arrec}.json"


def carregar_arquivos() -> List[Dict]:
    mapa = [
        {"tipo": "MAB", "arquivo": "mab_dados_11_03_2026.json"},
        {"tipo": "MCR", "arquivo": "mcr_dados_11_03_2026 (1).json"},
        {"tipo": "DESCONTOS", "arquivo": "descontos_dados_11_03_2026.json"},
        {"tipo": "RENUNCIAS", "arquivo": "renuncias_dados_11_03_2026.json"},
    ]
    return mapa


def enviar_item(tipo: str, caminho_arquivo: Path) -> Dict:
    inicio = datetime.now()
    try:
        dados = json.loads(caminho_arquivo.read_text(encoding="utf-8"))
        dados["tipo"] = tipo
        if not dados.get("data_arrecadacao"):
            dados["data_arrecadacao"] = dados.get("data_filtro") or datetime.now().strftime("%d/%m/%Y")
        file_name = montar_file_name(dados, tipo)

        # API exige content como objeto JSON (dict), nao string nem array na raiz.
        payload = {
            "file_name": file_name,
            "content": dados,
        }
        payload_str = json.dumps(payload, ensure_ascii=False)

        headers = {
            "x-api-key": API_KEY,
            "Content-Type": "application/json; charset=utf-8",
            "Accept": "application/json",
        }

        resposta = requests.post(
            API_URL,
            headers=headers,
            json=payload,
            timeout=TIMEOUT_SECONDS,
        )
        fim = datetime.now()

        return {
            "sucesso_http": resposta.status_code in [200, 201, 202],
            "tipo": tipo,
            "arquivo_origem": str(caminho_arquivo),
            "file_name_enviado": file_name,
            "status_code": resposta.status_code,
            "response_headers": dict(resposta.headers),
            "response_body": (resposta.text or "")[:5000],
            "request_payload_preview": payload_str[:2000],
            "inicio": inicio.isoformat(),
            "fim": fim.isoformat(),
            "duracao_ms": int((fim - inicio).total_seconds() * 1000),
        }
    except Exception as exc:
        fim = datetime.now()
        return {
            "sucesso_http": False,
            "tipo": tipo,
            "arquivo_origem": str(caminho_arquivo),
            "erro_execucao": str(exc),
            "inicio": inicio.isoformat(),
            "fim": fim.isoformat(),
            "duracao_ms": int((fim - inicio).total_seconds() * 1000),
        }


def main() -> None:
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    log_txt = Path(f"log_envio_api_{timestamp}.log")
    log_json = Path(f"log_envio_api_{timestamp}.json")

    itens = carregar_arquivos()
    resultados = []

    print("=" * 90)
    print("ENVIO DIRETO PARA API - INICIO")
    print(f"API_URL: {API_URL}")
    print(f"PASTA_ARQUIVOS: {PASTA_ARQUIVOS.resolve()}")
    print("=" * 90)

    for item in itens:
        tipo = item["tipo"]
        caminho = PASTA_ARQUIVOS / item["arquivo"]
        resultado = enviar_item(tipo, caminho)
        resultados.append(resultado)

        linha = (
            f"{tipo:10} | arquivo={caminho.name} | file_name={resultado.get('file_name_enviado')} | "
            f"status={resultado.get('status_code')} | sucesso_http={resultado.get('sucesso_http')}"
        )
        print(linha)
        if resultado.get("erro_execucao"):
            print(f"  erro_execucao={resultado['erro_execucao']}")
        else:
            body_curto = (resultado.get("response_body") or "").replace("\n", " ")
            print(f"  response_body={body_curto[:200]}")

    resumo = {
        "gerado_em": datetime.now().isoformat(),
        "api_url": API_URL,
        "total_itens": len(resultados),
        "sucessos_http": sum(1 for r in resultados if r.get("sucesso_http")),
        "falhas_http": sum(1 for r in resultados if not r.get("sucesso_http")),
        "resultados": resultados,
    }

    log_json.write_text(json.dumps(resumo, ensure_ascii=False, indent=2), encoding="utf-8")

    linhas_txt = [
        "ENVIO DIRETO PARA API",
        f"gerado_em={resumo['gerado_em']}",
        f"api_url={resumo['api_url']}",
        f"total_itens={resumo['total_itens']}",
        f"sucessos_http={resumo['sucessos_http']}",
        f"falhas_http={resumo['falhas_http']}",
        "",
    ]
    for r in resultados:
        linhas_txt.append(
            f"tipo={r.get('tipo')} arquivo={r.get('arquivo_origem')} file_name={r.get('file_name_enviado')} "
            f"status={r.get('status_code')} sucesso_http={r.get('sucesso_http')} duracao_ms={r.get('duracao_ms')}"
        )
        if r.get("erro_execucao"):
            linhas_txt.append(f"erro_execucao={r.get('erro_execucao')}")
        else:
            body = (r.get("response_body") or "").replace("\n", " ")
            linhas_txt.append(f"response_body={body[:500]}")
        linhas_txt.append("")

    log_txt.write_text("\n".join(linhas_txt), encoding="utf-8")

    print("=" * 90)
    print("ENVIO DIRETO PARA API - FIM")
    print(f"Log TXT:  {log_txt.resolve()}")
    print(f"Log JSON: {log_json.resolve()}")
    print("=" * 90)


if __name__ == "__main__":
    main()
