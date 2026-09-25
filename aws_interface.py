from fastapi import FastAPI, APIRouter, Request, UploadFile, File, Header
from fastapi.responses import JSONResponse, RedirectResponse
import json
import os
from aws_manager_visivel import AWSManagerVisivel
import requests
from typing import Optional

app = FastAPI(title="AWS Manager Interface")
router = APIRouter()

aws_manager = AWSManagerVisivel()


def _mgr_banco(x_banco_api_key: Optional[str] = None) -> AWSManagerVisivel:
    """Usa a senha digitada na tela, se houver; senão BANCO_API_KEY do .env."""
    chave = (x_banco_api_key or "").strip()
    if chave:
        return AWSManagerVisivel(banco_api_key=chave)
    return aws_manager

@router.get("/aws", include_in_schema=False)
async def aws_home():
    return RedirectResponse(url="/#s3", status_code=302)


@router.get("/api/testar-conexao")
async def testar_conexao():

    resultado = aws_manager.testar_conexao()
   
    if (not resultado.get("sucesso")) and (
        resultado.get("status_code") is None or
        (isinstance(resultado.get("mensagem"), str) and "Expecting value" in resultado.get("mensagem", ""))
    ):
        try:
            resp = requests.get(aws_manager.AWS_API_URL, headers=aws_manager.headers, timeout=10)
            conteudo_bruto = (resp.text or "").strip()
            return JSONResponse(content={
                "sucesso": resp.status_code == 200,
                "status_code": resp.status_code,
                "mensagem": "Conexão bem-sucedida" if resp.status_code == 200 else f"Erro: {resp.status_code}",
                "dados": None,
                "url": aws_manager.AWS_API_URL,
                "raw": conteudo_bruto[:500]
            })
        except Exception as e:
            return JSONResponse(content={
                "sucesso": False,
                "status_code": None,
                "mensagem": f"Erro de conexão: {str(e)}",
                "dados": None
            })
    return JSONResponse(content=resultado)


@router.get("/api/testar-banco")
async def testar_banco(
    x_banco_api_key: Optional[str] = Header(None, alias="X-Banco-Api-Key"),
):
    resultado = _mgr_banco(x_banco_api_key).testar_conexao_banco()
    return JSONResponse(content=resultado)

@router.post("/api/enviar-dados")
async def enviar_dados(request: Request):

    dados = await request.json()
    resultado = aws_manager.enviar_dados_visivel(dados)
    return JSONResponse(content=resultado)

@router.post("/api/enviar-arquivo")
async def enviar_arquivo(file: UploadFile = File(...)):

    try:

        temp_path = f"temp_{file.filename}"
        with open(temp_path, "wb") as buffer:
            content = await file.read()
            buffer.write(content)
        

        resultado = aws_manager.enviar_arquivo_json(temp_path)
        

        os.remove(temp_path)
        
        return JSONResponse(content=resultado)
    except Exception as e:
        return JSONResponse(content={
            "sucesso": False,
            "mensagem": f"Erro ao processar arquivo: {str(e)}"
        })



@router.post("/api/limpar-dados")
async def limpar_dados():

    resultado = aws_manager.limpar_dados()
    return JSONResponse(content=resultado)

@router.get("/api/listar-arquivos")
async def listar_arquivos():

    resultado = aws_manager.listar_arquivos_por_pasta()
    return JSONResponse(content=resultado)

@router.get("/api/obter-arquivo/{arquivo_id}")
async def obter_arquivo(arquivo_id: str):

    resultado = aws_manager.obter_arquivo_por_id(arquivo_id)
    return JSONResponse(content=resultado)

@router.put("/api/atualizar-arquivo/{arquivo_id}")
async def atualizar_arquivo(arquivo_id: str, request: Request):

    novos_dados = await request.json()
    resultado = aws_manager.atualizar_arquivo(arquivo_id, novos_dados)
    return JSONResponse(content=resultado)

@router.delete("/api/deletar-arquivo/{arquivo_id}")
async def deletar_arquivo(arquivo_id: str):

    resultado = aws_manager.deletar_arquivo(arquivo_id)
    return JSONResponse(content=resultado)


@router.get("/api/listar-por-pastas")
async def listar_por_pastas():
   
    resultado = aws_manager.listar_arquivos_por_pasta()
    return JSONResponse(content=resultado)

@router.post("/api/criar-pasta")
async def criar_pasta(request: Request):
   
    dados = await request.json()
    nome_pasta = dados.get("nome")
    cor = dados.get("cor", "#6c757d")
    
    if not nome_pasta:
        return JSONResponse(content={
            "sucesso": False,
            "mensagem": "Nome da pasta é obrigatório"
        })
    
    resultado = aws_manager.criar_pasta(nome_pasta, cor)
    return JSONResponse(content=resultado)

@router.delete("/api/deletar-pasta/{nome_pasta}")
async def deletar_pasta(nome_pasta: str):

    resultado = aws_manager.deletar_pasta(nome_pasta)
    return JSONResponse(content=resultado)

@router.post("/api/mover-arquivo")
async def mover_arquivo(request: Request):

    dados = await request.json()
    arquivo_id = dados.get("arquivo_id")
    pasta_origem = dados.get("pasta_origem")
    pasta_destino = dados.get("pasta_destino")
    
    if not all([arquivo_id, pasta_origem, pasta_destino]):
        return JSONResponse(content={
            "sucesso": False,
            "mensagem": "arquivo_id, pasta_origem e pasta_destino são obrigatórios"
        })
    
    resultado = aws_manager.mover_arquivo(arquivo_id, pasta_origem, pasta_destino)
    return JSONResponse(content=resultado)

@router.post("/api/salvar-estrutura")
async def salvar_estrutura(request: Request):
    
    dados = await request.json()
    pastas = dados.get("pastas", {})
    arquivos_sem_pasta = dados.get("arquivos_sem_pasta", [])
    
    estrutura = {
        "pastas": pastas,
        "arquivos_sem_pasta": arquivos_sem_pasta
    }
    
    resultado = aws_manager._salvar_estrutura_pastas(estrutura)
    return JSONResponse(content=resultado)


@router.get("/api/get-remoto")
async def get_remoto(
    tipo: str,
    nome: str,
    x_banco_api_key: Optional[str] = Header(None, alias="X-Banco-Api-Key"),
):
    resultado = _mgr_banco(x_banco_api_key).baixar_arquivo_por_tipo_nome(tipo, nome)
    return JSONResponse(content=resultado)

#
@router.get("/api/get-remoto-por-id/{arquivo_id}")
async def get_remoto_por_id(arquivo_id: str):
    info = aws_manager.obter_arquivo_por_id(arquivo_id)
    if not info.get("sucesso"):
        return JSONResponse(content=info)
    metadados = info.get("metadados") or {}
    tipo = metadados.get("tipo") or (info.get("arquivo") or {}).get("tipo")
    nome_arquivo = metadados.get("nome_arquivo")
    if not tipo or not nome_arquivo:
        return JSONResponse(content={
            "sucesso": False,
            "mensagem": "Metadados insuficientes para GET remoto"
        })
    resultado = aws_manager.baixar_arquivo_por_tipo_nome(tipo, nome_arquivo)
    return JSONResponse(content=resultado)


@router.get("/api/listar-arquivos-remoto")
async def listar_arquivos_remoto(
    data: str,
    x_banco_api_key: Optional[str] = Header(None, alias="X-Banco-Api-Key"),
):
    resultado = _mgr_banco(x_banco_api_key).listar_arquivos_por_data(data)
    return JSONResponse(content=resultado)


@router.get("/api/listar-indice-local")
async def listar_indice_local(data: str = ""):
    """Lista o índice local (cache) filtrando por data dd/mm/aaaa quando informada."""
    resultado = aws_manager.listar_arquivos_por_pasta()
    if not resultado.get("sucesso"):
        return JSONResponse(content=resultado)

    data_ref = str(data or "").strip().replace("-", "/")
    arquivos = []
    pastas = resultado.get("pastas") or {}
    for nome_pasta, pasta in pastas.items():
        for arq in pasta.get("arquivos") or []:
            filtro = str(arq.get("data_filtro") or (arq.get("dados") or {}).get("data_filtro") or "")
            filtro_norm = filtro.replace("-", "/")
            if data_ref and filtro_norm and filtro_norm != data_ref:
                # também aceita data_arrecadacao
                arrec = str(
                    arq.get("data_arrecadacao")
                    or (arq.get("dados") or {}).get("data_arrecadacao")
                    or ""
                ).replace("-", "/")
                if arrec != data_ref:
                    continue
            arquivos.append({
                "fonte": "indice_local",
                "pasta": nome_pasta,
                "tipo": arq.get("tipo") or nome_pasta,
                "arquivo_id": arq.get("arquivo_id"),
                "file_name": arq.get("nome_arquivo"),
                "status": arq.get("status"),
                "created_at": arq.get("data_upload"),
                "data_filtro": arq.get("data_filtro"),
                "total_registros": arq.get("total_registros"),
                "presente": True,
            })
    for arq in resultado.get("arquivos_sem_pasta") or []:
        filtro = str(arq.get("data_filtro") or "").replace("-", "/")
        if data_ref and filtro and filtro != data_ref:
            continue
        arquivos.append({
            "fonte": "indice_local",
            "pasta": "sem_pasta",
            "tipo": arq.get("tipo") or "OUTROS",
            "arquivo_id": arq.get("arquivo_id"),
            "file_name": arq.get("nome_arquivo"),
            "status": arq.get("status"),
            "created_at": arq.get("data_upload"),
            "data_filtro": arq.get("data_filtro"),
            "total_registros": arq.get("total_registros"),
            "presente": True,
        })

    return JSONResponse(content={
        "sucesso": True,
        "fonte": "indice_local",
        "data": data_ref or None,
        "arquivos": arquivos,
        "total": len(arquivos),
    })


@router.get("/api/arquivo-saida-local")
async def arquivo_saida_local(data: str, tipo: str):
    """Abre o JSON gravado em saida_pacotes/YYYY-MM-DD/."""
    from datetime import datetime
    from carregar_env import diretorio_projeto

    data_ref = str(data or "").strip().replace("-", "/")
    tipo_l = str(tipo or "").strip().lower()
    mapa = {
        "mab": "mab",
        "mcr": "mcr",
        "renuncias": "renuncias",
        "renuncia": "renuncias",
        "descontos": "descontos",
        "desconto": "descontos",
    }
    chave = mapa.get(tipo_l)
    if not chave:
        return JSONResponse(content={"sucesso": False, "mensagem": "Tipo inválido. Use MAB, MCR, RENUNCIAS ou DESCONTOS."})
    try:
        dt = datetime.strptime(data_ref, "%d/%m/%Y")
    except ValueError:
        return JSONResponse(content={"sucesso": False, "mensagem": "Data inválida. Use dd/mm/aaaa."})

    nome = f"{chave}_dados_{dt.day:02d}_{dt.month:02d}_{dt.year}.json"
    caminho = os.path.join(diretorio_projeto(), "saida_pacotes", dt.strftime("%Y-%m-%d"), nome)
    if not os.path.exists(caminho):
        return JSONResponse(content={
            "sucesso": False,
            "mensagem": f"Arquivo local não encontrado: {nome}",
            "caminho": caminho,
        })
    try:
        with open(caminho, "r", encoding="utf-8") as f:
            conteudo = json.load(f)
        return JSONResponse(content={
            "sucesso": True,
            "fonte": "saida_pacotes",
            "file_name": nome,
            "caminho": caminho,
            "conteudo": conteudo,
        })
    except Exception as e:
        return JSONResponse(content={"sucesso": False, "mensagem": str(e)})


@router.get("/api/listar-remoto")
async def listar_remoto(tipo: str, data: str = ""):
    resultado = aws_manager.listar_pasta_remota(tipo, data=data)
    return JSONResponse(content=resultado)


@router.post("/api/put-remoto")
async def put_remoto(request: Request):
    body = await request.json()
    tipo = body.get("tipo")
    nome = body.get("nome")
    dados = body.get("dados")
    if not all([tipo, nome, dados is not None]):
        return JSONResponse(content={"sucesso": False, "mensagem": "tipo, nome e dados são obrigatórios"})
    
    # Único envio: PUT direto no S3 com o nome curto escolhido pelo usuário
    resultado_put = aws_manager.put_arquivo_remoto(tipo, nome, dados)
    
    # Se o PUT funcionou, apenas adiciona entrada ao índice (sem segundo upload)
    if resultado_put.get("sucesso"):
        resultado_indice = aws_manager.adicionar_entrada_indice(tipo, nome, dados)
        body_api = {}
        try:
            body_api = json.loads(resultado_put.get("body") or "{}")
        except Exception:
            body_api = {"raw": resultado_put.get("body")}
        resposta = {
            "sucesso": True,
            "status_code": resultado_put.get("status_code"),
            "url": resultado_put.get("url"),
            "path": body_api.get("path"),
            "message": body_api.get("message"),
            "mensagem": body_api.get("message") or f"Upload realizado. Arquivo: {nome}",
            "upload_direto": resultado_put,
            "indice_atualizado": resultado_indice.get("sucesso", False),
        }
        if resultado_indice.get("sucesso"):
            resposta["arquivo_id"] = resultado_indice.get("arquivo_id")
        return JSONResponse(content=resposta)
    return JSONResponse(content=resultado_put)

app.include_router(router)


@app.get("/", include_in_schema=False)
async def standalone_root():
    return RedirectResponse(url="/aws")


if __name__ == "__main__":
    import uvicorn
    uvicorn.run("aws_interface:app", host="0.0.0.0", port=8001) 