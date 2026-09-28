import os
import re
import copy
from decimal import Decimal, ROUND_HALF_UP
from fastapi import FastAPI, Query, UploadFile, File
from fastapi.responses import FileResponse, HTMLResponse, JSONResponse
import pandas as pd
from relatorios import gerar_relatorio_mab, gerar_relatorio_mcr
from aws_interface import router as aws_router
from carregar_env import carregar_env, sefaz_path
from gov_api import get_gov_client

carregar_env()


app = FastAPI(title="SEFAZ Integração")
app.include_router(aws_router)



####################################################
# Função utilitária (usada por todos os módulos)
####################################################

def corrigir_caminho(caminho: str) -> str:


    if os.name != "nt" or not caminho:
        return caminho

    # Ja esta no formato long-path
    if caminho.startswith("\\\\?\\"):
        return caminho

    # UNC path (rede): \\server\share\...
    if caminho.startswith("\\\\"):
        # remove os dois backslashes iniciais
        sem_prefixo = caminho.lstrip("\\")
        return "\\\\?\\UNC\\" + sem_prefixo

    # Caminho local (ex.: C:\...)
    return "\\\\?\\" + caminho

def normalizar_texto(texto: str) -> str:

    import unicodedata
    if texto is None:
        return ""
    

    texto_sem_acentos = unicodedata.normalize('NFD', texto)
    texto_sem_acentos = ''.join(c for c in texto_sem_acentos if not unicodedata.combining(c))
    

    return texto_sem_acentos.lower()

def encontrar_pasta_renuncia_desconto(caminho_base: str) -> str:
    """
    Busca a pasta de 'Renúncia e Desconto' ignorando acentos, maiúsculas e minúsculas.
    Retorna o caminho completo da pasta encontrada ou None se não encontrar.
    """
    if not os.path.exists(caminho_base):
        return None
    
    # Normaliza o termo de busca
    termo_busca = normalizar_texto("renuncia e desconto")
    
    try:
        # Lista todas as pastas no diretório base
        pastas = [d for d in os.listdir(caminho_base) if os.path.isdir(os.path.join(caminho_base, d))]
    except Exception:
        return None
    
    # Procura por correspondência normalizada
    for pasta in pastas:
        pasta_normalizada = normalizar_texto(pasta)
        if termo_busca in pasta_normalizada:
            return os.path.join(caminho_base, pasta)
    
    return None

def caminhos_safci_exportacao(ano: int = 2026, arquivos_safci: bool = False) -> list:
    meses = [
        "Janeiro", "Fevereiro", "Março", "Abril", "Maio", "Junho",
        "Julho", "Agosto", "Setembro", "Outubro", "Novembro", "Dezembro",
    ]
    caminhos = []
    for mes in meses:
        partes = [
            "Arrecadacao",
            "SEFAZ-Tesouraria",
            "SAFCI INTEGRACAO",
            "Arquivos Exportação ao SAFCI",
            str(ano),
            f"{mes} {ano}",
        ]
        if arquivos_safci:
            partes.append("Arquivos SAFCI")
        caminhos.append(sefaz_path(*partes))
    return caminhos

def gerar_caminhos_deducoes_dinamicos() -> list:
    """
    Gera os caminhos de deduções dinamicamente, buscando pastas de 'Renúncia e Desconto'
    ignorando acentos, maiúsculas e minúsculas.
    """
    caminhos_deducoes = []
    
    for caminho_base in caminhos_safci_exportacao():
        # Busca a pasta de 'Renúncia e Desconto' de forma inteligente
        pasta_renuncia_desconto = encontrar_pasta_renuncia_desconto(caminho_base)
        
        if pasta_renuncia_desconto:
            # A partir de 2026/abr os .xls ficam na raiz de "Renúncia e Desconto"
            # (não mais em .../Renúncia e Desconto/Arquivos SAFCI/{dia}/*.txt).
            caminhos_deducoes.append(pasta_renuncia_desconto)
    
    return caminhos_deducoes

@app.get("/testar_busca_pastas/")
def testar_busca_pastas():
    """
    Endpoint para testar a busca inteligente de pastas de 'Renúncia e Desconto'
    """
    caminhos_base = caminhos_safci_exportacao()
    
    resultados_teste = []
    
    for caminho_base in caminhos_base:
        if os.path.exists(caminho_base):
            # Lista todas as pastas disponíveis
            try:
                pastas_disponiveis = [d for d in os.listdir(caminho_base) if os.path.isdir(os.path.join(caminho_base, d))]
            except Exception as e:
                pastas_disponiveis = [f"Erro ao listar: {str(e)}"]
            
            # Busca a pasta de 'Renúncia e Desconto'
            pasta_encontrada = encontrar_pasta_renuncia_desconto(caminho_base)
            
            xls_na_pasta = []
            if pasta_encontrada:
                try:
                    xls_na_pasta = [
                        n for n in os.listdir(pasta_encontrada)
                        if n.lower().endswith((".xls", ".xlsx"))
                    ]
                except Exception:
                    xls_na_pasta = []
            resultados_teste.append({
                "caminho_base": caminho_base,
                "existe": os.path.exists(caminho_base),
                "pastas_disponiveis": pastas_disponiveis,
                "pasta_renuncia_desconto_encontrada": pasta_encontrada,
                "qtd_xls": len(xls_na_pasta),
                "xls": xls_na_pasta[:20],
            })
        else:
            resultados_teste.append({
                "caminho_base": caminho_base,
                "existe": False,
                "erro": "Caminho não existe"
            })
    
    return {
        "teste_busca_pastas": resultados_teste,
        "caminhos_deducoes_gerados": gerar_caminhos_deducoes_dinamicos()
    }


@app.get("/testar_gov_api/")
def testar_gov_api():
    """Autentica na API GovBR (Cidade360) e confirma o JWT."""
    return get_gov_client().autenticar(forcar=True)


@app.get("/diagnosticar_mcr_xls/")
def diagnosticar_mcr_xls(
    dia: int = Query(None, description="Filtra arquivos DDMMbb/DDMMcef deste dia"),
    mes: int = Query(None, description="Mês (1-12)"),
    ano: int = Query(2026),
    limite: int = Query(40, description="Máximo de arquivos testados"),
):
    """Lista XLS de classificação e tenta extrair, devolvendo erro por arquivo (debug Linux/CIFS)."""
    caminhos = caminhos_safci_exportacao(ano=ano, arquivos_safci=True)
    testados = []
    ok = 0
    falhas = 0
    for pasta in caminhos:
        if not pasta or not os.path.isdir(pasta):
            continue
        try:
            nomes = sorted(os.listdir(pasta))
        except Exception as e:
            testados.append({"pasta": pasta, "erro_listagem": str(e)})
            continue
        for nome in nomes:
            if not nome.lower().endswith((".xls", ".xlsx")):
                continue
            if dia is not None and mes is not None:
                prefixo = f"{int(dia):02d}{int(mes):02d}"
                base = os.path.splitext(nome)[0].lower()
                if not (base.startswith(prefixo) and (base.endswith("bb") or base.endswith("cef"))):
                    continue
            caminho = os.path.join(pasta, nome)
            item = {"arquivo": nome, "pasta": pasta, "caminho": caminho}
            try:
                dados = extrair_dados_classificacao(caminho)
                item["sucesso"] = True
                item["banco"] = dados.get("banco")
                item["registros"] = len(dados.get("dados") or [])
                ok += 1
            except Exception as e:
                item["sucesso"] = False
                item["erro"] = str(e)
                falhas += 1
            testados.append(item)
            if len(testados) >= int(limite):
                break
        if len(testados) >= int(limite):
            break
    return {
        "sucesso": falhas == 0 and ok > 0,
        "ok": ok,
        "falhas": falhas,
        "testados": testados,
        "caminhos_classificacao": caminhos,
    }


@app.get("/testar_gov_razao/")
def testar_gov_razao(
    data_inicio: str = Query(..., description="Data inicial yyyy-mm-dd ou dd/mm/aaaa"),
    data_final: str = Query(..., description="Data final yyyy-mm-dd ou dd/mm/aaaa"),
    fato_contabil: str | None = Query(None, description="Código numérico do fato para o path da API (opcional)"),
    fato: str | None = Query(None, description="Fato contábil (texto ou código, filtro local)"),
    conta: str | None = Query(None, description="Alias de natureza (compatibilidade)"),
    natureza: str | None = Query(None, description="Natureza da receita (prefixo por padrão)"),
    natureza_modo: str | None = Query("prefixo", description="prefixo|contem|exato|codigo"),
    conta_contabil: str | None = Query(None, description="Conta contábil nível (ex.: 6 ou 6.2.1)"),
    conta_contabil_modo: str | None = Query("prefixo", description="prefixo|contem|exato|codigo"),
    contra_partida: str | None = Query(None, description="Contra-partida contábil"),
    tipo_deducao: str | None = Query(None, description="91, 93, 96, 00 ou texto"),
    receita: str | None = Query(None, description="Código de receita/tributo"),
    fonte_recurso: str | None = Query(None, description="Fonte de recurso"),
    banco: str | None = Query(None, description="Código ou nome do banco"),
    movimento: str | None = Query(None, description="Original ou Estorno"),
    debito_credito: str | None = Query(None, description="D ou C"),
    desc_natureza: str | None = Query(None, description="Texto na descrição da natureza"),
    desc_conta: str | None = Query(None, description="Texto na descrição da conta"),
    historico: str | None = Query(None, description="Texto no histórico"),
    busca: str | None = Query(None, description="Busca livre"),
    valor_min: float | None = Query(None),
    valor_max: float | None = Query(None),
    preview: int = Query(0, ge=0, le=20),
    limite: int = Query(120, ge=0, le=500),
):
    """Consulta razão contábil com filtros combináveis para navegação na interface."""
    fato_api = None
    if fato_contabil and str(fato_contabil).strip():
        try:
            fato_api = int(str(fato_contabil).strip())
        except ValueError:
            # Se não for número, trata como filtro texto de fato.
            fato = fato or fato_contabil

    filtros = {
        "fato": fato,
        "natureza": natureza or conta,
        "natureza_modo": natureza_modo,
        "conta_contabil": conta_contabil,
        "conta_contabil_modo": conta_contabil_modo,
        "contra_partida": contra_partida,
        "tipo_deducao": tipo_deducao,
        "receita": receita,
        "fonte_recurso": fonte_recurso,
        "banco": banco,
        "movimento": movimento,
        "debito_credito": debito_credito,
        "desc_natureza": desc_natureza,
        "desc_conta": desc_conta,
        "historico": historico,
        "busca": busca,
        "valor_min": valor_min,
        "valor_max": valor_max,
    }
    return get_gov_client().consultar_razao(
        data_inicio=data_inicio,
        data_final=data_final,
        fato_contabil=fato_api,
        preview=preview,
        limite_lancamentos=limite,
        filtros=filtros,
    )


def calcular_dia_util_anterior_parts(
    dia: int,
    mes: int,
    ano: int = 2026,
    feriados=None,
) -> tuple:
    """Retorna (dia, mes, ano) do dia util imediatamente anterior a data informada."""
    from datetime import date, timedelta
    data = date(ano, mes, dia)
    anterior = data - timedelta(days=1)
    feriados = feriados or set()
    while anterior.weekday() >= 5 or anterior in feriados:
        anterior -= timedelta(days=1)
    return anterior.day, anterior.month, anterior.year

def calcular_dia_util_anterior(dia: int, mes: int, ano: int = 2026, feriados=None) -> str:
    d, m, a = calcular_dia_util_anterior_parts(dia, mes, ano, feriados=feriados)
    return f"{d:02d}/{m:02d}/{a}"

def calcular_proximo_dia_util(dia: int, mes: int, ano: int = 2026, feriados=None) -> str:

    from datetime import date, timedelta
    data = date(ano, mes, dia)
    proximo = data + timedelta(days=1)
    feriados = feriados or set()
    while proximo.weekday() >= 5 or proximo in feriados:
        proximo += timedelta(days=1)
    return proximo.strftime("%d/%m/%Y")

def encontrar_pasta_mes(caminho_base: str, mes_desejado: str) -> str:

    if not os.path.exists(caminho_base):
        return None
    

    mes_normalizado = normalizar_texto(mes_desejado)
    

    try:
        pastas = [d for d in os.listdir(caminho_base) if os.path.isdir(os.path.join(caminho_base, d))]
    except Exception:
        return None
    
    # Procura por correspondência
    for pasta in pastas:
        pasta_normalizada = normalizar_texto(pasta)
        if mes_normalizado in pasta_normalizada:
            return os.path.join(caminho_base, pasta)
    
    return None

##########################################
# Módulo MAB – Arquivos FEBRABRAN
##########################################

def recuperar_segmentos_ret(caminho_arquivo: str) -> dict:
    banco = os.path.basename(caminho_arquivo).split(".")[0]
    with open(caminho_arquivo, 'r', encoding='utf-8') as arquivo:
        linhas = arquivo.readlines()
    segmento_a = next((linha for linha in linhas if linha.startswith("A")), None)
    segmento_z = next((linha for linha in linhas if linha.startswith("Z")), None)
    if segmento_a and segmento_z:
        return {
            "banco": banco,
            "segmento_a": segmento_a.strip(),
            "segmento_z": segmento_z.strip(),
        }
    else:
        raise ValueError(f"Segmentos A ou Z ausentes no arquivo: {caminho_arquivo}")

def processar_pasta_completa(caminho_base: str) -> list:
    resultados = []
    extensoes_validas = [".ret", ".RET", ".txt", ".TXT", ""]
    for root, _, files in os.walk(caminho_base):
        for file in files:
            if any(file.endswith(ext) for ext in extensoes_validas):
                caminho_arquivo = os.path.join(root, file)
                try:
                    resultado = recuperar_segmentos_ret(caminho_arquivo)
                    resultados.append(resultado)
                except Exception:
                    pass
    return resultados

caminhos_base = [
    sefaz_path("Arrecadacao", "Recep", "Arquivos FEBRABRAN", "BANCO INTER", "INTER2026"),
    sefaz_path("Arrecadacao", "Recep", "Arquivos FEBRABRAN", "BANCOOB", "BANCOOB26"),
    sefaz_path("Arrecadacao", "Recep", "Arquivos FEBRABRAN", "BB", "BRASIL2026"),
    sefaz_path("Arrecadacao", "Recep", "Arquivos FEBRABRAN", "BRADESCO", "BRADE2026"),
    sefaz_path("Arrecadacao", "Recep", "Arquivos FEBRABRAN", "CEF", "CAIXA2026"),
    sefaz_path("Arrecadacao", "Recep", "Arquivos FEBRABRAN", "ITAU", "ITAU2026"),
    sefaz_path("Arrecadacao", "Recep", "Arquivos FEBRABRAN", "MERCANTIL", "MERC2026"),
    sefaz_path("Arrecadacao", "Recep", "Arquivos FEBRABRAN", "SANTANDER", "BSA26"),
]

#############################################################
# Helpers de agregação para MAB (saída JSON apenas)
#############################################################

def _extrair_bloco_numerico_final(texto: str):

    if texto is None:
        return texto, "", 0
    texto_strip = str(texto).strip()
    match = re.match(r"^(.*?)(\d+)$", texto_strip)
    if not match:
        return texto_strip, "", 0
    prefixo, digitos = match.groups()
    return prefixo, digitos, len(digitos)

def _valor_centavos_do_segmento_z(segmento_z: str) -> int:
    # Layout FEBRABAN do trailer (segmento Z):
    #   [6 digitos: quantidade de registros][17 digitos: valor total em centavos]
    # O valor total esta nos ULTIMOS 17 digitos do bloco numerico final.
    # Usar um recorte menor (ex.: 8) trunca silenciosamente qualquer arrecadacao
    # acima de R$ 999.999,99, o que corrompe a soma agregada do Brasil e o valor da CEF.
    _, digitos, _ = _extrair_bloco_numerico_final(segmento_z)
    if not digitos:
        return 0
    try:
        relevantes = digitos[-17:] if len(digitos) >= 17 else digitos
        return int(relevantes)
    except Exception:
        return 0

def _substituir_valor_no_segmento_z(segmento_z: str, valor_centavos: int) -> str:

    prefixo, digitos_orig, largura = _extrair_bloco_numerico_final(segmento_z)
    if largura == 0:
        return segmento_z
    novo = str(abs(int(valor_centavos)))
    if len(novo) > largura:
        novo = novo[-largura:]
    else:
        novo = novo.zfill(largura)
    return prefixo + novo

def _formatar_valor_centavos(valor_centavos: int) -> str:

    inteiro = valor_centavos // 100
    centavos = valor_centavos % 100
    return f"{inteiro},{centavos:02d}"

def _formatar_valor_monetario_json_como_mab(valor: float) -> str:
    """
    Mesmo padrao do valor_arrecadado do MAB (BRL, 2 decimais): parte inteira + virgula + centavos,
    sem separador de milhar e sem prefixo de moeda (alinhado a ISO 4217 para BRL com exponent 2).
    """
    neg = float(valor) < 0
    cent = int(round(abs(float(valor)) * 100))
    corpo = _formatar_valor_centavos(cent)
    return f"-{corpo}" if neg else corpo

def _round2_half_up(valor) -> Decimal:
    return Decimal(str(valor)).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)

def _formatar_valor_monetario_json_ponto_half_up(valor) -> str:
    arred = _round2_half_up(valor)
    return f"{arred:.2f}"

def _inferir_tipo_banco(valor: str) -> str:
    txt = str(valor or "").strip().lower()
    if txt.startswith("cef") or txt.endswith("cef"):
        return "cef"
    if txt.startswith("bras") or txt.endswith("bb") or "brasil" in txt:
        return "bb"
    return ""

def _validar_estrutura_mab_para_ajuste(mab_json: dict) -> str:
    if not isinstance(mab_json, dict):
        return "JSON do MAB invalido."
    if str(mab_json.get("tipo", "")).upper() != "MAB":
        return "Arquivo MAB invalido: campo 'tipo' diferente de MAB."
    if not mab_json.get("data_arrecadacao"):
        return "Arquivo MAB invalido: campo 'data_arrecadacao' ausente."
    if not isinstance(mab_json.get("resultados"), list):
        return "Arquivo MAB invalido: campo 'resultados' deve ser lista."
    return ""

def _validar_estrutura_mcr_para_ajuste(mcr_json: dict) -> str:
    if not isinstance(mcr_json, dict):
        return "JSON do MCR invalido."
    if str(mcr_json.get("tipo", "")).upper() != "MCR":
        return "Arquivo MCR invalido: campo 'tipo' diferente de MCR."
    if not mcr_json.get("data_arrecadacao"):
        return "Arquivo MCR invalido: campo 'data_arrecadacao' ausente."
    if not isinstance(mcr_json.get("totais_por_banco"), dict):
        return "Arquivo MCR invalido: campo 'totais_por_banco' deve ser objeto."
    if not isinstance(mcr_json.get("resultados"), list):
        return "Arquivo MCR invalido: campo 'resultados' deve ser lista."
    return ""

def _extrair_totais_mab_por_tipo_banco(mab_json: dict) -> dict:
    totais = {"cef": 0.0, "bb": 0.0}
    for item in mab_json.get("resultados", []):
        banco = item.get("banco", "")
        tipo = _inferir_tipo_banco(banco)
        if not tipo:
            continue
        totais[tipo] += _parse_valor_monetario(item.get("valor_arrecadado", "0"))
    return totais

def _extrair_totais_mcr_por_tipo_banco(mcr_json: dict) -> dict:
    totais = {"cef": 0.0, "bb": 0.0}
    for banco, valor in mcr_json.get("totais_por_banco", {}).items():
        tipo = _inferir_tipo_banco(banco)
        if not tipo:
            continue
        totais[tipo] += _parse_valor_monetario(valor)
    return totais

def _garantir_bloco_mcr(mcr_json: dict, tipo_banco: str) -> dict:
    """Garante um bloco em resultados para cef/bb (cria vazio se o dia não tiver XLS desse banco)."""
    for item in mcr_json.get("resultados", []) or []:
        if _inferir_tipo_banco(item.get("banco", "")) == tipo_banco:
            return item

    data_filtro = str(mcr_json.get("data_filtro", "")).strip()
    partes = data_filtro.split("/") if "/" in data_filtro else []
    if len(partes) == 3:
        dia, mes = partes[0].zfill(2), partes[1].zfill(2)
        banco = f"{dia}{mes}{'cef' if tipo_banco == 'cef' else 'bb'}"
    else:
        banco = "cef" if tipo_banco == "cef" else "bb"
    codigo = 7066 if tipo_banco == "cef" else 6112
    novo = {
        "arquivo": f"ajuste_{banco}",
        "banco": banco,
        "codigo_resumido": codigo,
        "dados": [],
    }
    mcr_json.setdefault("resultados", []).append(novo)
    mcr_json["total_registros"] = len(mcr_json.get("resultados") or [])
    return novo

def _adicionar_lancamento_ajuste_no_mcr(mcr_json: dict, tipo_banco: str, diferenca: float):
    item = _garantir_bloco_mcr(mcr_json, tipo_banco)
    if "dados" not in item or not isinstance(item["dados"], list):
        item["dados"] = []
    item["dados"].append({
        "Natureza_da_Receita": "1999992100",
        "codigo_receita": "1999992100",
        # No MCR, o detalhe usa ponto como separador decimal.
        "liquido": _formatar_valor_monetario_json_ponto_half_up(diferenca),
        "valor_receita": _formatar_valor_monetario_json_ponto_half_up(diferenca),
        "categoria": "Outras Receitas Nao Arrecadadas e Nao Projetadas pela RFB - Primarias - Principal",
    })
    return True

def _ajustar_mcr_com_mab(mab_json: dict, mcr_json: dict) -> dict:
    mab_data = str(mab_json.get("data_arrecadacao", "")).strip()
    mcr_data = str(mcr_json.get("data_arrecadacao", "")).strip()
    if mab_data != mcr_data:
        raise ValueError(
            f"Data de arrecadacao divergente: MAB={mab_data} e MCR={mcr_data}. "
            "Carregue arquivos do mesmo dia."
        )

    mcr_ajustado = copy.deepcopy(mcr_json)
    totais_mab = _extrair_totais_mab_por_tipo_banco(mab_json)
    totais_mcr = _extrair_totais_mcr_por_tipo_banco(mcr_json)

    diferencas = {
        "cef": float(_round2_half_up(totais_mab.get("cef", 0.0) - totais_mcr.get("cef", 0.0))),
        "bb": float(_round2_half_up(totais_mab.get("bb", 0.0) - totais_mcr.get("bb", 0.0))),
    }

    for tipo in ("cef", "bb"):
        dif = diferencas[tipo]
        if abs(dif) < 0.01:
            continue
        ok = _adicionar_lancamento_ajuste_no_mcr(mcr_ajustado, tipo, dif)
        if not ok:
            raise ValueError(
                f"Nao foi encontrado bloco de resultados do MCR para o banco '{tipo}'."
            )

        # Atualiza totais_por_banco mantendo a mesma estrutura do JSON atual.
        chave_encontrada = None
        for chave in mcr_ajustado.get("totais_por_banco", {}).keys():
            if _inferir_tipo_banco(chave) == tipo:
                chave_encontrada = chave
                break
        if chave_encontrada is None:
            data_filtro = str(mcr_ajustado.get("data_filtro", "")).strip()
            partes = data_filtro.split("/") if "/" in data_filtro else []
            if len(partes) == 3:
                dia = partes[0].zfill(2)
                mes = partes[1].zfill(2)
                chave_encontrada = f"{dia}{mes}{tipo}"
            else:
                chave_encontrada = tipo
        atual = _parse_valor_monetario(mcr_ajustado.get("totais_por_banco", {}).get(chave_encontrada, 0))
        novo_total = _round2_half_up(atual + dif)
        mcr_ajustado.setdefault("totais_por_banco", {})[chave_encontrada] = float(novo_total)

    return mcr_ajustado

def agregar_resultados_mab(resultados_filtrados: list) -> list:

    if not resultados_filtrados:
        return []

    registro_cef = next((r for r in resultados_filtrados if str(r.get("banco", "")).lower().startswith("cef")), None)
    registro_bras = next((r for r in resultados_filtrados if str(r.get("banco", "")).lower().startswith("bras")), None)

    if registro_cef is None or registro_bras is None:
        
        convertidos = []
        for r in resultados_filtrados:
            valor_centavos = _valor_centavos_do_segmento_z(r.get("segmento_z", ""))
            valor_formatado = _formatar_valor_centavos(valor_centavos)
            banco_lower = str(r.get("banco", "")).lower()
            codigo_resumido = 7066 if banco_lower.startswith("cef") else 6112
            novo = {
                "banco": r.get("banco"),
                "segmento_a": r.get("segmento_a"),
                "segmento_z": r.get("segmento_z"),
                "valor_arrecadado": valor_formatado,
                "codigo_resumido": codigo_resumido,
            }
            convertidos.append(novo)
        return convertidos

    soma_centavos = 0
    for r in resultados_filtrados:
        banco_lower = str(r.get("banco", "")).lower()
        if banco_lower.startswith("cef"):
            continue
        soma_centavos += _valor_centavos_do_segmento_z(r.get("segmento_z", ""))

    segmento_z_bras_agg = _substituir_valor_no_segmento_z(registro_bras.get("segmento_z", ""), soma_centavos)
    valor_bras_formatado = _formatar_valor_centavos(soma_centavos)

    bras_agg = {
        "banco": registro_bras.get("banco"),
        "segmento_a": registro_bras.get("segmento_a"),
        "segmento_z": segmento_z_bras_agg,
        "valor_arrecadado": valor_bras_formatado,
        "codigo_resumido": 6112,
    }

    cef_out = None
    if registro_cef is not None:
        valor_cef_centavos = _valor_centavos_do_segmento_z(registro_cef.get("segmento_z", ""))
        valor_cef_formatado = _formatar_valor_centavos(valor_cef_centavos)
        cef_out = {
            "banco": registro_cef.get("banco"),
            "segmento_a": registro_cef.get("segmento_a"),
            "segmento_z": registro_cef.get("segmento_z"),
            "valor_arrecadado": valor_cef_formatado,
            "codigo_resumido": 7066,
        }

 
    agregados = []
    if cef_out is not None:
        agregados.append(cef_out)
    agregados.append(bras_agg)
    return agregados


###############################################
# Módulo MCR – Classificação (Arquivos XLS)
###############################################

def ler_planilha_classificacao(caminho_arquivo: str) -> pd.DataFrame:
    caminho_corrigido = corrigir_caminho(caminho_arquivo)
    if caminho_arquivo.lower().endswith('.xls'):
        df = pd.read_excel(caminho_corrigido, engine='xlrd', header=None)
    else:
        df = pd.read_excel(caminho_corrigido, header=None)
    return df

def _texto_celula_flex(valor) -> str:
    """Normaliza texto de célula e tenta corrigir mojibake comum de XLS via CIFS."""
    texto = str(valor or "")
    if texto.lower() == "nan":
        return ""
    # Mojibake típico UTF-8 lido como Latin-1
    if "Ã" in texto or "Â" in texto:
        try:
            texto = texto.encode("latin-1").decode("utf-8")
        except Exception:
            pass
    return normalizar_texto(texto)

def _idx_coluna_norm(cabecalho: list, *candidatos: str) -> int:
    """Localiza coluna no cabeçalho ignorando acento/caixa."""
    alvos = [normalizar_texto(c) for c in candidatos]
    for i, celula in enumerate(cabecalho):
        n = _texto_celula_flex(celula)
        if not n:
            continue
        if n in alvos:
            return i
        for alvo in alvos:
            if alvo and alvo in n:
                return i
    raise KeyError(candidatos[0] if candidatos else "coluna")

def _eh_cabecalho_classificacao(linha) -> bool:
    norms = [_texto_celula_flex(c) for c in linha]
    tem_natureza = any("natureza" in n and "receita" in n for n in norms)
    tem_liquido = any(
        n == "liquido" or "liquido" in n or "lquido" in n
        for n in norms
    )
    return tem_natureza and tem_liquido

def _encontrar_secao_totais_natureza(linhas: list) -> tuple:
    """
    Preferência: bloco 'Totais por Natureza da Receita' (layout Page 1 atual).
    Fallback: linha 'Total Líquido Geral' e cabeçalho seguinte (layout legado).
    Retorna (indice_cabecalho, cabecalho).
    """
    for i, linha in enumerate(linhas):
        if any("totais por natureza" in _texto_celula_flex(c) for c in linha):
            for j in range(i + 1, min(i + 6, len(linhas))):
                if _eh_cabecalho_classificacao(linhas[j]):
                    return j, linhas[j]

    indice_total = None
    for idx, linha in enumerate(linhas):
        for celula in linha:
            n = _texto_celula_flex(celula)
            if not n:
                continue
            # "Total Líquido Geral" / "Total Lquido Geral" / variações
            if "total" in n and "geral" in n and ("liquido" in n or "lquido" in n or "liq" in n):
                indice_total = idx
                break
        if indice_total is not None:
            break
    if indice_total is None:
        raise Exception("Seção de totais do MCR não encontrada ( Totais por Natureza / Total Líquido Geral ).")

    for i in range(indice_total + 1, min(indice_total + 8, len(linhas))):
        if _eh_cabecalho_classificacao(linhas[i]):
            return i, linhas[i]
    raise Exception("Cabeçalho Natureza/Líquido não encontrado após os totais do MCR.")

def extrair_dados_classificacao(caminho_arquivo: str) -> dict:
    df = ler_planilha_classificacao(caminho_arquivo)
    if df is None or df.empty:
        raise Exception("Planilha de classificação vazia.")
    linhas = df.astype(str).values.tolist()
    indice_cabecalho, cabecalho = _encontrar_secao_totais_natureza(linhas)
    try:
        idx_natureza = _idx_coluna_norm(cabecalho, "Natureza da Receita")
        idx_liquido = _idx_coluna_norm(cabecalho, "Líquido", "Liquido", "Lquido")
    except Exception as e:
        raise Exception(f"Colunas Natureza/Líquido não encontradas no cabeçalho: {e}") from e
    try:
        idx_descricao = _idx_coluna_norm(cabecalho, "Descrição", "Descricao", "Descri")
    except Exception:
        idx_descricao = None

    dados_extraidos = []
    for linha in linhas[indice_cabecalho + 1:]:
        # Linhas totalmente vazias / NaN: pular (não encerrar — o XLS tem buracos entre blocos)
        if all(str(celula).strip() in ("", "nan", "None") for celula in linha):
            continue
        joined = " ".join(_texto_celula_flex(c) for c in linha if _texto_celula_flex(c))
        # Encera só em totais finais óbvios (não em "Totais por Natureza...")
        if joined.startswith("total geral") or joined.startswith("total liquido geral") or joined.startswith("total lquido geral"):
            break
        natureza = str(linha[idx_natureza]).strip()
        liquido = str(linha[idx_liquido]).strip()
        descricao = str(linha[idx_descricao]).strip() if idx_descricao is not None else ""
        if natureza.lower() in ("nan", "", "none") and liquido.lower() in ("nan", "", "none"):
            continue
        if not any(ch.isdigit() for ch in natureza):
            continue
        if liquido.lower() in ("nan", "", "none"):
            continue
        dados_extraidos.append({
            "Natureza_da_Receita": natureza,
            "liquido": liquido,
            "categoria": descricao.lower() if descricao.lower() != "nan" else "",
        })
    if not dados_extraidos:
        raise Exception("Nenhum lançamento extraído da seção de totais por natureza.")
    banco = os.path.basename(caminho_arquivo).split('.')[0]
    return {"arquivo": caminho_arquivo, "banco": banco, "dados": dados_extraidos}

def processar_pasta_classificacao(caminho_pasta: str) -> list:
    resultados = []
    extensoes_validas = [".xls", ".xlsx"]
    if not caminho_pasta or not os.path.isdir(caminho_pasta):
        return resultados
    for root, _, files in os.walk(caminho_pasta):
        for file in files:
            if any(file.lower().endswith(ext) for ext in extensoes_validas):
                caminho_arquivo = os.path.join(root, file)
                try:
                    resultado = extrair_dados_classificacao(caminho_arquivo)
                    resultados.append(resultado)
                except Exception as e:
                    print(f"Erro processando o arquivo {caminho_arquivo}: {e}")
    return resultados

caminhos_classificacao = caminhos_safci_exportacao(arquivos_safci=True)

#############################################################
# Helper: adicionar codigo_resumido em resultados do MCR
#############################################################

def normalizar_codigo_receita_10(codigo) -> str:
    if codigo is None:
        return ""
    digitos = "".join(ch for ch in str(codigo) if ch.isdigit())
    if not digitos:
        return ""
    if len(digitos) > 10:
        return digitos[:10]
    return digitos.zfill(10)

def _parse_valor_monetario(valor) -> float:
    if valor is None:
        return 0.0
    s = str(valor).strip()
    if s == "":
        return 0.0
    negativo = s.startswith("-")
    s = s.replace("-", "").replace(" ", "")
    if "," in s:
        s = s.replace(".", "").replace(",", ".")
    try:
        num = float(s)
    except Exception:
        return 0.0
    return -num if negativo else num

def _agrupar_registros_por_codigo_receita(registros: list) -> list:
    agregados = {}
    ordem = []
    for reg in registros:
        codigo = normalizar_codigo_receita_10(reg.get("codigo_receita", ""))
        if not codigo:
            continue
        if codigo not in agregados:
            agregados[codigo] = {
                "codigo_receita": codigo,
                "valor_receita_num": 0.0,
                "categoria": reg.get("categoria", ""),
            }
            ordem.append(codigo)
        agregados[codigo]["valor_receita_num"] += _parse_valor_monetario(reg.get("valor_receita", "0"))
        if not agregados[codigo]["categoria"] and reg.get("categoria"):
            agregados[codigo]["categoria"] = reg.get("categoria", "")

    saida = []
    for codigo in ordem:
        item = agregados[codigo]
        saida.append({
            "Natureza_da_Receita": item["codigo_receita"],
            "liquido": _formatar_valor_monetario_json_como_mab(item["valor_receita_num"]),
            "categoria": item["categoria"],
        })
    return saida

def _agrupar_detalhamento_por_codigo_receita(detalhamento: list) -> list:
    agregados = {}
    ordem = []
    for det in detalhamento:
        codigo = normalizar_codigo_receita_10(det.get("codigo_receita", ""))
        if not codigo:
            continue
        if codigo not in agregados:
            agregados[codigo] = {
                "codigo_receita": codigo,
                "valor_receita_num": 0.0,
                "valor_deducao_num": 0.0,
                "codigo_deducao": det.get("codigo_deducao", ""),
            }
            ordem.append(codigo)
        agregados[codigo]["valor_receita_num"] += _parse_valor_monetario(det.get("valor_receita", "0"))
        agregados[codigo]["valor_deducao_num"] += _parse_valor_monetario(det.get("valor_deducao", "0"))

    saida = []
    for codigo in ordem:
        item = agregados[codigo]
        saida.append({
            "codigo_receita": item["codigo_receita"],
            "valor_receita": _formatar_valor_monetario_json_como_mab(item["valor_receita_num"]),
            "codigo_deducao": item["codigo_deducao"],
            "valor_deducao": _formatar_valor_monetario_json_como_mab(item["valor_deducao_num"]),
        })
    return saida

def adicionar_codigo_resumido_mcr(resultados: list) -> list:
    anotados = []
    for res in resultados:
        banco_lower = str(res.get("banco", "")).lower()
        codigo = 6112 if banco_lower.endswith("bb") else 7066 if banco_lower.endswith("cef") else None
        if codigo is None:
            anotados.append(res)
            continue
       
        dados_normalizados = []
        for reg in res.get("dados", []):
            codigo_receita = normalizar_codigo_receita_10(
                reg.get("Natureza_da_Receita", reg.get("Natureza da Receita", ""))
            )
            valor_receita = reg.get("liquido", reg.get("Líquido", ""))
            dados_normalizados.append({
                "codigo_receita": codigo_receita,
                "valor_receita": valor_receita,
                "categoria": reg.get("categoria", ""),
            })
        dados_normalizados = _agrupar_registros_por_codigo_receita(dados_normalizados)

        novo = {
            "arquivo": res.get("arquivo"),
            "banco": res.get("banco"),
            "codigo_resumido": codigo,
            "dados": dados_normalizados,
        }
        anotados.append(novo)
    return anotados

####################################################
# Módulo Desconto/Renúncia – Deduções (Arquivos XLS)
####################################################

def ler_planilha_deducao(caminho_arquivo: str) -> pd.DataFrame:
    caminho_corrigido = corrigir_caminho(caminho_arquivo)
    
    
    engines = ['openpyxl', 'xlrd', 'odf']
    
    for engine in engines:
        try:
            if engine == 'xlrd':
               
                if not caminho_arquivo.lower().endswith('.xls'):
                    continue
                df = pd.read_excel(caminho_corrigido, engine=engine)
            else:
         
                df = pd.read_excel(caminho_corrigido, engine=engine)
            
      
            df = df.ffill()
            return df
            
        except Exception:
            continue
    
    # Se nenhum engine funcionou, tenta uma abordagem mais agressiva
    try:
        # Tenta ler sem especificar engine (pandas escolhe automaticamente)
        df = pd.read_excel(caminho_corrigido)
        df = df.ffill()
        return df
    except Exception:
        pass
    
    # Tenta ler por chunks para arquivos muito grandes
    try:
        # Para arquivos muito grandes, tenta ler apenas as primeiras linhas
        df = pd.read_excel(caminho_corrigido, nrows=1000)
        df = df.ffill()
        return df
    except Exception:
        pass
    
    # Tenta com diferentes parâmetros para xlrd
    if caminho_arquivo.lower().endswith('.xls'):
        try:
            # Tenta com parâmetros específicos para arquivos corrompidos
            df = pd.read_excel(caminho_corrigido, engine='xlrd', formatting_info=False)
            df = df.ffill()
            return df
        except Exception:
            pass
        
        # Tenta com xlrd mais agressivo
        try:
            import xlrd
            workbook = xlrd.open_workbook(caminho_corrigido, on_demand=True, ragged_rows=True)
            sheet = workbook.sheet_by_index(0)
            
            # Converte para DataFrame
            data = []
            for row_idx in range(sheet.nrows):
                row_data = []
                for col_idx in range(sheet.ncols):
                    try:
                        cell_value = sheet.cell_value(row_idx, col_idx)
                        row_data.append(cell_value)
                    except:
                        row_data.append("")
                data.append(row_data)
            
            # Cria DataFrame
            df = pd.DataFrame(data)
            df = df.ffill()
            return df
        except Exception:
            pass
    
    # Última tentativa: tenta ler como CSV
    try:
        # Tenta ler como CSV com separador tab
        df = pd.read_csv(caminho_corrigido, sep='\t', encoding='utf-8')
        df = df.ffill()
        return df
    except Exception:
        pass
    
    # Tenta com encoding diferente
    try:
        df = pd.read_csv(caminho_corrigido, sep='\t', encoding='latin-1')
        df = df.ffill()
        return df
    except Exception:
        pass
    
    # Tenta com separador diferente
    try:
        df = pd.read_csv(caminho_corrigido, sep=None, engine='python', encoding='latin-1')
        df = df.ffill()
        return df
    except Exception:
        pass
    
    # SOLUÇÃO RADICAL: Tenta ler como texto e fazer parsing manual
    try:
        # Lê o arquivo como texto binário
        with open(caminho_corrigido, 'rb') as f:
            content = f.read()
        
        # Tenta diferentes encodings
        encodings = ['latin-1', 'cp1252', 'iso-8859-1', 'utf-8']
        text_content = None
        
        for encoding in encodings:
            try:
                text_content = content.decode(encoding, errors='ignore')
                break
            except:
                continue
        
        if text_content:
            # Procura por padrões específicos no texto
            lines = text_content.split('\n')
            data_rows = []
            
            # Procura por linhas que contenham dados relevantes
            for line in lines:
                line = line.strip()
                # Procura por linhas com datas (formato DD/MM/YYYY)
                if '/' in line and len(line.split('/')) == 3:
                    # Procura por números (valores)
                    import re
                    numbers = re.findall(r'\d+[,.]?\d*', line)
                    if len(numbers) >= 2:  # Pelo menos data e valor
                        # Tenta extrair dados da linha
                        parts = line.split('\t') if '\t' in line else line.split()
                        if len(parts) >= 4:
                            data_rows.append(parts)
            
            if data_rows:
                # Cria DataFrame com os dados extraídos
                df = pd.DataFrame(data_rows)
                df = df.ffill()
                return df
            
            # Se não encontrou dados estruturados, tenta uma abordagem mais agressiva
            # Procura por qualquer linha que contenha uma data e números
            for line in lines:
                line = line.strip()
                # Procura por padrão de data DD/MM/YYYY
                date_match = re.search(r'(\d{1,2}/\d{1,2}/\d{4})', line)
                if date_match:
                    # Procura por números que podem ser valores
                    value_matches = re.findall(r'(\d+[,.]?\d*)', line)
                    if len(value_matches) >= 1:
                        # Tenta extrair informações da linha
                        # Procura por palavras que indicam tipo de operação
                        if any(word in line.lower() for word in ['estorno', 'normal', 'iptu', 'principal']):
                            # Cria uma linha de dados estruturada
                            data_row = [date_match.group(1), '', '', value_matches[0]]
                            data_rows.append(data_row)
            
            if data_rows:
                # Cria DataFrame com os dados extraídos
                df = pd.DataFrame(data_rows, columns=['Data_Contabil', 'Nat_da_Receita', 'Nat_Oper', 'Valor'])
                return df
            
            # Última tentativa: procura por padrões específicos no conteúdo binário
            # Procura por strings que parecem datas e valores
            import re
            
            # Procura por padrões de data DD/MM/YYYY
            date_pattern = r'(\d{1,2}/\d{1,2}/\d{4})'
            dates = re.findall(date_pattern, text_content)
            
            # Procura por valores monetários (números com vírgula ou ponto)
            value_pattern = r'(\d+[,.]?\d*)'
            values = re.findall(value_pattern, text_content)
            
            if dates and values:
                # Cria linhas de dados baseadas nas datas encontradas
                for i, date in enumerate(dates):
                    if i < len(values):
                        # Determina o tipo de operação baseado no contexto
                        nat_oper = "Estorno" if "estorno" in text_content.lower() else "Normal"
                        nat_receita = "11125001000000"  # Código padrão para IPTU
                        valor = values[i]
                        
                        data_row = [date, nat_receita, nat_oper, valor]
                        data_rows.append(data_row)
                
                if data_rows:
                    # Cria DataFrame com os dados extraídos
                    df = pd.DataFrame(data_rows, columns=['Data_Contabil', 'Nat_da_Receita', 'Nat_Oper', 'Valor'])
                    return df
    except Exception:
        pass
    
    # Se nada funcionou, tenta criar um DataFrame vazio com estrutura básica
    try:
        # Cria um DataFrame vazio com as colunas esperadas
        colunas_esperadas = ['Data_Contabil', 'Nat_da_Receita', 'Nat_Oper', 'Valor']
        df = pd.DataFrame(columns=colunas_esperadas)
        return df
    except Exception:
        raise Exception(f"Não foi possível ler o arquivo {caminho_arquivo} com nenhum método disponível")

def calcular_deducao(nat_receita: str, nat_oper: str, valor: str, tipo: str):
    prefix = "93" if tipo == "desc" else "91"
    deducao = prefix + nat_receita[:-2]
    
    valor_str = valor.strip()
    if valor_str.startswith("-"):
        valor_abs = valor_str[1:].strip()
    else:
        valor_abs = valor_str

    # Usa normalização para comparar strings
    nat_oper_normalizada = normalizar_texto(nat_oper)
    if nat_oper_normalizada == normalizar_texto("normal"):
        final_valor = valor_abs
        valor_deducao = "-" + valor_abs
    elif nat_oper_normalizada == normalizar_texto("estorno"):
        final_valor = valor_str if valor_str.startswith("-") else "-" + valor_str
        valor_deducao = valor_abs
    else:
        final_valor = valor_abs
        valor_deducao = "-" + valor_abs

    return deducao, final_valor, valor_deducao

def extrair_dados_deducao_txt(caminho_arquivo: str, dia: int, ano: int = 2026) -> list:
    """
    Extrai dados de dedução de arquivos de texto (.txt)
    Formato esperado: "código; valor"
    Códigos que começam com 9 são deduções
    Retorna lista de registros individuais (não consolidados)
    ano: ano usado em Data_Contabil nos documentos gerados.
    """
    try:
        resultados = []
        
        with open(caminho_arquivo, 'r', encoding='utf-8') as f:
            linhas = f.readlines()
        
        for linha in linhas:
            linha = linha.strip()
            if not linha or ';' not in linha:
                continue
            
            # Separa código e valor
            partes = linha.split(';')
            if len(partes) != 2:
                continue
            
            codigo = partes[0].strip()
            valor_str = partes[1].strip()
            
            # Processa tanto receitas quanto deduções
            try:
                # Converte valor para float, lidando com separadores de milhares e decimais
                valor_limpo = valor_str.replace(' ', '')  # Remove espaços
                
                # Se tem vírgula, assume que é separador decimal
                if ',' in valor_limpo:
                    # Remove pontos (separadores de milhares) e substitui vírgula por ponto
                    valor_limpo = valor_limpo.replace('.', '').replace(',', '.')
                else:
                    # Se não tem vírgula, mantém como está
                    pass
                
                valor = float(valor_limpo)
                
                # Determina o tipo baseado no código
                if codigo.startswith('91'):
                    tipo = "ren"   # Renúncia
                    nat_oper = "Normal"
                elif codigo.startswith('93'):
                    tipo = "desc"  # Desconto
                    nat_oper = "Normal"
                else:
                    tipo = "rec"   # Receita
                    nat_oper = "Normal"
                
                # Extrai o mês do caminho do arquivo
                caminho_parts = caminho_arquivo.split('\\')
                mes = "02"  # Default
                
                # Procura pelo mês no caminho
                for part in caminho_parts:
                    part_lower = part.lower()
                    if "janeiro" in part_lower:
                        mes = "01"
                    elif "fevereiro" in part_lower:
                        mes = "02"
                    elif "março" in part_lower or "marco" in part_lower:
                        mes = "03"
                    elif "abril" in part_lower:
                        mes = "04"
                    elif "maio" in part_lower:
                        mes = "05"
                    elif "junho" in part_lower:
                        mes = "06"
                    elif "julho" in part_lower:
                        mes = "07"
                    elif "agosto" in part_lower:
                        mes = "08"
                    elif "setembro" in part_lower:
                        mes = "09"
                    elif "outubro" in part_lower:
                        mes = "10"
                    elif "novembro" in part_lower:
                        mes = "11"
                    elif "dezembro" in part_lower:
                        mes = "12"
                
                ano_str = str(ano)
                # Cria o registro individual
                rec = {
                    "Data_Contabil": f"{dia:02d}/{mes}/{ano_str}",
                    "Nat_da_Receita": codigo,
                    "Nat_Oper": nat_oper,
                    "Valor": valor_str,
                    "tipo": tipo,
                    "valor_numerico": valor  # Adiciona valor numérico para facilitar soma
                }
                
                resultados.append(rec)
                
            except ValueError:
                # Se não conseguir converter o valor, pula a linha
                continue
        
        return resultados
        
    except Exception as e:
        print(f"Erro processando arquivo {caminho_arquivo}: {e}")
        return []

def _prefixo_deducao_pelo_nome(nome_arquivo: str) -> str:
    """91 = renúncia, 93 = desconto, inferido pelo nome do .xls."""
    nome = normalizar_texto(os.path.basename(nome_arquivo or ""))
    if "renuncia" in nome:
        return "91"
    if "desconto" in nome:
        return "93"
    return ""


def _parse_data_celula(valor) -> str:
    """Converte a célula da coluna A para DD/MM/YYYY. Vazio se inválida."""
    from datetime import datetime, date, timedelta

    if valor is None:
        return ""
    try:
        if pd.isna(valor):
            return ""
    except Exception:
        pass

    if isinstance(valor, datetime):
        return valor.strftime("%d/%m/%Y")
    if isinstance(valor, date):
        return valor.strftime("%d/%m/%Y")
    if hasattr(valor, "to_pydatetime"):
        try:
            return valor.to_pydatetime().strftime("%d/%m/%Y")
        except Exception:
            pass

    if isinstance(valor, (int, float)) and not isinstance(valor, bool):
        serial = float(valor)
        if 20000 <= serial <= 80000:
            try:
                dt = datetime(1899, 12, 30) + timedelta(days=serial)
                return dt.strftime("%d/%m/%Y")
            except Exception:
                pass

    texto = str(valor).strip()
    match = re.match(r"^(\d{1,2})[/-](\d{1,2})[/-](\d{2,4})", texto)
    if not match:
        return ""
    dia, mes, ano = match.groups()
    if len(ano) == 2:
        ano = "20" + ano
    try:
        return f"{int(dia):02d}/{int(mes):02d}/{int(ano):04d}"
    except Exception:
        return ""


def extrair_dados_deducao_xls(caminho_arquivo: str) -> list:
    """
    Lê planilha de renúncia/desconto.
    Layout legado (aba Planilha1): A=data, F=conta, I=valor.
    Layout novo (aba Page 1 / relatório sintético): A=data, I=nat.receita, Q=valor.
    O tipo 91/93 vem do nome do arquivo (renuncia/desconto).
    """
    prefixo = _prefixo_deducao_pelo_nome(caminho_arquivo)
    if not prefixo:
        return []

    tipo = "ren" if prefixo == "91" else "desc"
    caminho = corrigir_caminho(caminho_arquivo)
    engine = "xlrd" if caminho_arquivo.lower().endswith(".xls") else "openpyxl"

    try:
        xl = pd.ExcelFile(caminho, engine=engine)
        sheet_names = list(xl.sheet_names or [])
    except Exception as e:
        print(f"Erro lendo planilha {caminho_arquivo}: {e}")
        return []

    # Preferência: Planilha1 (legado); senão Page 1 / primeira aba.
    sheet = None
    layout = None
    for nome in sheet_names:
        if str(nome).strip().lower() == "planilha1":
            sheet = nome
            layout = "planilha1"
            break
    if sheet is None:
        for nome in sheet_names:
            if str(nome).strip().lower() in ("page 1", "page1", "pagina 1", "página 1"):
                sheet = nome
                layout = "page1"
                break
    if sheet is None and sheet_names:
        sheet = sheet_names[0]
        layout = "page1"

    try:
        df = pd.read_excel(caminho, sheet_name=sheet, header=None, engine=engine)
    except Exception as e:
        print(f"Erro lendo aba {sheet} de {caminho_arquivo}: {e}")
        return []

    if df is None or df.empty:
        return []

    if layout == "planilha1":
        if df.shape[1] < 9:
            return []
        col_data, col_conta, col_valor = 0, 5, 8
    else:
        if df.shape[1] < 17:
            # tenta mapear automaticamente pelo cabeçalho
            col_data = col_conta = col_valor = None
            for i, row in df.iterrows():
                textos = {
                    j: normalizar_texto(str(row.iloc[j]))
                    for j in range(len(row))
                    if pd.notna(row.iloc[j])
                }
                if not textos:
                    continue
                for j, t in textos.items():
                    if col_data is None and ("data contabil" in t or t == "data"):
                        col_data = j
                    if col_conta is None and ("nat da receita" in t or "natureza da receita" in t):
                        col_conta = j
                    if col_valor is None and t == "valor":
                        col_valor = j
                if col_data is not None and col_conta is not None and col_valor is not None:
                    break
            if col_data is None or col_conta is None or col_valor is None:
                return []
        else:
            col_data, col_conta, col_valor = 0, 8, 16

    resultados = []
    for _, row in df.iterrows():
        if max(col_data, col_conta, col_valor) >= len(row):
            continue
        data_contabil = _parse_data_celula(row.iloc[col_data])
        if not data_contabil:
            continue
        conta = row.iloc[col_conta]
        valor = row.iloc[col_valor]
        try:
            if pd.isna(conta) or pd.isna(valor):
                continue
        except Exception:
            pass
        # Cabeçalho / totais textuais
        if isinstance(conta, str) and not re.search(r"\d", conta):
            continue
        valor_num = _parse_valor_monetario(valor)
        if abs(valor_num) < 0.0000001 and str(valor).strip() in ("", "0", "0,00", "0.00"):
            # ainda assim pode ser zero legítimo; só ignora se não for número
            pass
        try:
            if isinstance(valor, str) and not re.search(r"\d", valor):
                continue
        except Exception:
            pass

        codigo_10 = normalizar_codigo_receita_10(conta)
        if not codigo_10:
            continue
        codigo_original = prefixo + (codigo_10[:-2] if len(codigo_10) >= 2 else codigo_10)
        resultados.append({
            "Data_Contabil": data_contabil,
            "Nat_da_Receita": codigo_original,
            "Nat_Oper": "Normal",
            "Valor": _formatar_valor_monetario_json_como_mab(valor_num),
            "tipo": tipo,
            "valor_numerico": valor_num,
            "codigo_receita_10": codigo_10,
        })
    return resultados


def _consolidar_registros_xls_deducao(nome_arquivo: str, registros: list) -> dict:
    """Agrupa linhas do .xls por data da coluna A, no formato do JSON atual."""
    por_data = {}
    for rec in registros:
        data = rec.get("Data_Contabil") or ""
        if not data:
            continue
        por_data.setdefault(data, []).append(rec)

    dados_consolidados = []
    for data_contabil, recs in por_data.items():
        prefixo = "91" if recs[0].get("tipo") == "ren" else "93"
        total = sum(abs(float(r.get("valor_numerico") or 0)) for r in recs)
        dados_consolidados.append({
            "Data_Contabil": data_contabil,
            "deducao": prefixo,
            "Valor_Deducao": f"{total:.2f}".replace(".", ","),
            "detalhamento": [
                {
                    "codigo_original": rec["Nat_da_Receita"],
                    "valor_original": rec["Valor"],
                    "receitas_por_codigo": {
                        rec.get("codigo_receita_10", ""): rec["Valor"]
                    },
                }
                for rec in recs
            ],
        })

    if not dados_consolidados:
        return None
    return {
        "arquivo": nome_arquivo,
        "banco": nome_arquivo,
        "dados": dados_consolidados,
    }


def processar_pasta_deducoes(caminho_pasta: str, ano: int = 2026) -> list:
    resultados = []
    
    # Verifica se a pasta existe
    if not os.path.exists(caminho_pasta):
        return resultados

    arquivos_xls = [
        f for f in os.listdir(caminho_pasta)
        if os.path.isfile(os.path.join(caminho_pasta, f))
        and f.lower().endswith((".xls", ".xlsx"))
    ]
    if arquivos_xls:
        for file in arquivos_xls:
            caminho_arquivo = os.path.join(caminho_pasta, file)
            try:
                registros = extrair_dados_deducao_xls(caminho_arquivo)
                consolidado = _consolidar_registros_xls_deducao(file, registros) if registros else None
                if consolidado:
                    resultados.append(consolidado)
            except Exception as e:
                print(f"Erro processando o arquivo {caminho_arquivo}: {e}")
        return resultados
    
    # Agrupa dados por dia
    dados_por_dia = {}
    
    # Procura por pastas de dia (formato: DD ou DD-XX)
    for item in os.listdir(caminho_pasta):
        item_path = os.path.join(caminho_pasta, item)
        if os.path.isdir(item_path):
            # Extrai o dia da pasta
            dia = None
            if item.isdigit() and len(item) <= 2:  # Pasta com apenas dia (ex: "01")
                dia = int(item)
            elif '-' in item:  # Pasta com formato DD-XX ou DD-MM-YY (ex: "01-10" ou "02-05-25")
                try:
                    dia = int(item.split('-')[0])
                except:
                    continue
            
            if dia is not None:
                # Inicializa o dicionário para este dia se não existir
                if dia not in dados_por_dia:
                    dados_por_dia[dia] = []
                
                # Procura por arquivos .txt na pasta do dia
                for file in os.listdir(item_path):
                    if file.lower().endswith('.txt'):
                        caminho_arquivo = os.path.join(item_path, file)
                        try:
                            # Processa cada arquivo individualmente
                            registros = extrair_dados_deducao_txt(caminho_arquivo, dia, ano)
                            if registros:  # Só inclui se houver dados
                                # Cria um resultado por arquivo para manter o mapeamento 1:1
                                resultado_arquivo = {
                                    "arquivo": file,
                                    "banco": f"Dia_{dia:02d}_{file}",
                                    "dados": registros
                                }
                                dados_por_dia[dia].append(resultado_arquivo)
                        except Exception as e:
                            print(f"Erro processando o arquivo {caminho_arquivo}: {e}")
    
    # Processa cada arquivo individualmente para manter mapeamento 1:1
    for dia, arquivos_dia in dados_por_dia.items():
        if arquivos_dia:  # Só cria se houver dados
            for arquivo_info in arquivos_dia:
                registros = arquivo_info["dados"]
                
                # Mapa de receitas por código (para parear com deduções)
                receitas_por_codigo = {}
                total_91 = 0.0  # Renúncia (códigos que começam com 91)
                total_93 = 0.0  # Desconto (códigos que começam com 93)
                
                for rec in registros:
                    codigo = rec["Nat_da_Receita"]
                    valor_numerico = rec["valor_numerico"]  # Para cálculos
                    valor_original = rec["Valor"]  # Valor original formatado
                    
                    if codigo.startswith('91'):
                        total_91 += abs(valor_numerico)  # Usa valor absoluto para ignorar sinal negativo
                    elif codigo.startswith('93'):
                        total_93 += abs(valor_numerico)  # Usa valor absoluto para ignorar sinal negativo
                    elif rec.get("tipo") == "rec":
                        # Receita: armazena o valor original formatado
                        receitas_por_codigo[codigo] = valor_original
            
                # Extrai o mês do caminho
                mes = "06"  # Default
                ano_str = str(ano)
                
                # Procura pelo mês no caminho
                caminho_parts = arquivo_info["arquivo"].split('\\') if "\\" in arquivo_info["arquivo"] else caminho_pasta.split('\\')
                for part in caminho_parts:
                    part_lower = part.lower()
                    if "janeiro" in part_lower:
                        mes = "01"
                    elif "fevereiro" in part_lower:
                        mes = "02"
                    elif "março" in part_lower or "marco" in part_lower:
                        mes = "03"
                    elif "abril" in part_lower:
                        mes = "04"
                    elif "maio" in part_lower:
                        mes = "05"
                    elif "junho" in part_lower:
                        mes = "06"
                    elif "julho" in part_lower:
                        mes = "07"
                    elif "agosto" in part_lower:
                        mes = "08"
                    elif "setembro" in part_lower:
                        mes = "09"
                    elif "outubro" in part_lower:
                        mes = "10"
                    elif "novembro" in part_lower:
                        mes = "11"
                    elif "dezembro" in part_lower:
                        mes = "12"
                
                # Agrupa registros por tipo para detalhamento
                registros_91 = [rec for rec in registros if rec["Nat_da_Receita"].startswith('91')]
                registros_93 = [rec for rec in registros if rec["Nat_da_Receita"].startswith('93')]
                
                # Cria resultado consolidado para o arquivo
                dados_consolidados = []
                
                if total_91 > 0:
                    dados_consolidados.append({
                        "Data_Contabil": f"{dia:02d}/{mes}/{ano_str}",
                        "deducao": "91",
                        "Valor_Deducao": f"{total_91:.2f}".replace('.', ','),
                        "detalhamento": [
                            {
                                "codigo_original": rec["Nat_da_Receita"],
                                "valor_original": rec["Valor"],
                                "receitas_por_codigo": receitas_por_codigo  # Passa o mapa para usar no JSON
                            }
                            for rec in registros_91
                        ]
                    })
                
                if total_93 > 0:
                    dados_consolidados.append({
                        "Data_Contabil": f"{dia:02d}/{mes}/{ano_str}",
                        "deducao": "93",
                        "Valor_Deducao": f"{total_93:.2f}".replace('.', ','),
                        "detalhamento": [
                            {
                                "codigo_original": rec["Nat_da_Receita"],
                                "valor_original": rec["Valor"],
                                "receitas_por_codigo": receitas_por_codigo  # Passa o mapa para usar no JSON
                            }
                            for rec in registros_93
                        ]
                    })
                
                if dados_consolidados:
                    resultado_arquivo = {
                        "arquivo": arquivo_info["arquivo"],
                        "banco": arquivo_info["banco"],
                        "dados": dados_consolidados
                    }
                    resultados.append(resultado_arquivo)
    
    return resultados

# Lista estática removida - agora usamos gerar_caminhos_deducoes_dinamicos()

#####################

# Endpoints da API

#####################

@app.get("/status_fontes/")
def status_fontes():
    from aws_manager_visivel import AWSManagerVisivel
    from carregar_env import diagnosticar_share_sefaz, diretorio_projeto

    gov = get_gov_client().autenticar()
    mgr = AWSManagerVisivel()
    aws = mgr.testar_conexao()
    banco = mgr.testar_conexao_banco()
    share = diagnosticar_share_sefaz()
    pasta_saida = os.path.join(diretorio_projeto(), "saida_pacotes")
    return {
        "gov": {
            "sucesso": bool(gov.get("sucesso")),
            "mensagem": gov.get("mensagem"),
            "identificador": gov.get("identificador"),
        },
        "aws": {
            "sucesso": bool(aws.get("sucesso")),
            "mensagem": aws.get("mensagem"),
            "status_code": aws.get("status_code"),
        },
        "banco": {
            "sucesso": bool(banco.get("sucesso")),
            "mensagem": banco.get("mensagem"),
            "status_code": banco.get("status_code"),
            "tem_chave_env": bool((os.getenv("BANCO_API_KEY") or "").strip()),
        },
        "share": {
            "sucesso": bool(share.get("acessivel")),
            "mensagem": share.get("mensagem"),
            "root": share.get("root"),
            "pasta_saida": pasta_saida,
            "pasta_saida_gravavel": os.path.isdir(pasta_saida) and os.access(pasta_saida, os.W_OK),
        },
    }


@app.get("/", response_class=HTMLResponse)
def home():
    caminho = os.path.join(os.path.dirname(os.path.abspath(__file__)), "interface.html")
    with open(caminho, encoding="utf-8") as f:
        return f.read()


@app.get("/processar/")
def processar():
    resultados = []
    for caminho_base in caminhos_base:
        resultados.extend(processar_pasta_completa(caminho_base))
    return {"resultados": resultados}

@app.get("/filtrar_por_dia_mes/")
def filtrar_por_dia_mes(
    dia: int = Query(..., description="Dia do mês para filtrar os lançamentos"),
    mes: int = Query(..., description="Mês para filtrar os lançamentos")
):
    resultados = []
    for caminho_base in caminhos_base:
        resultados.extend(processar_pasta_completa(caminho_base))
    dia_str = f"{dia:02d}"
    mes_str = f"{mes:02d}"
    resultados_filtrados = [res for res in resultados if res["banco"].endswith(f"{dia_str}{mes_str}")]
    return {"resultados_filtrados": resultados_filtrados}

@app.get("/processar_classificacao/")
def processar_classificacao():
    resultados = []
    for caminho in caminhos_classificacao:
        resultados.extend(processar_pasta_classificacao(caminho))


    if not resultados:
        return {"erro": "Nenhum dado encontrado para o MCR."}


    totais_por_banco = {}
    for res in resultados:
        banco = res["banco"]
        if banco not in totais_por_banco:
            totais_por_banco[banco] = 0.0

        for registro in res["dados"]:
            try:
                valor = float(registro["liquido"])
            except Exception:
                valor = 0.0
            totais_por_banco[banco] += valor

    return {"resultados_filtrados": resultados, "totais_por_banco": totais_por_banco}


@app.get("/filtrar_classificacao_por_dia_mes/")
def filtrar_classificacao_por_dia_mes(
    dia: int = Query(..., description="Dia do mês para filtrar os lançamentos"),
    mes: int = Query(..., description="Mês para filtrar os lançamentos")
):
    resultados = []
    for caminho in caminhos_classificacao:
        resultados.extend(processar_pasta_classificacao(caminho))
    dia_str = f"{dia:02d}"
    mes_str = f"{mes:02d}"
    resultados_filtrados = [res for res in resultados if res["banco"][:2] == dia_str and res["banco"][2:4] == mes_str]
    totais_por_banco = {}
    for res in resultados_filtrados:
        banco = res["banco"]
        if banco not in totais_por_banco:
            totais_por_banco[banco] = 0.0
        for registro in res["dados"]:
            try:
                valor = float(registro["liquido"])
            except Exception:
                valor = 0.0
            totais_por_banco[banco] += valor
    return {"resultados_filtrados": resultados_filtrados, "totais_por_banco": totais_por_banco}

@app.get("/processar_deducoes/")
def processar_deducoes(ano: int = Query(2026, description="Ano para os documentos gerados")):
    resultados = []
    caminhos_deducoes = gerar_caminhos_deducoes_dinamicos()
    for caminho in caminhos_deducoes:
        resultados.extend(processar_pasta_deducoes(caminho, ano))
    return {"resultados": resultados}

@app.get("/filtrar_deducoes_por_dia_mes/")
def filtrar_deducoes_por_dia_mes(
    dia: int = Query(..., description="Dia do mês para filtrar os lançamentos"),
    mes: int = Query(..., description="Mês para filtrar os lançamentos"),
    ano: int = Query(2026, description="Ano para filtrar e documentos gerados")
):
    resultados = []
    caminhos_deducoes = gerar_caminhos_deducoes_dinamicos()
    for caminho in caminhos_deducoes:
        resultados.extend(processar_pasta_deducoes(caminho, ano))
    
    # Filtra por data usando a coluna "Data_Contabil"
    dia_str = f"{dia:02d}"
    mes_str = f"{mes:02d}"
    ano_str = str(ano)
    
    resultados_filtrados = []
    
    for res in resultados:
        dados_filtrados = []
        
        for registro in res["dados"]:
            data_contabil = registro.get("Data_Contabil", "")
            if data_contabil:

                try:
                    if "/" in data_contabil:
                        partes_data = data_contabil.split("/")
                        if len(partes_data) == 3:
                            dia_arquivo = partes_data[0].strip()
                            mes_arquivo = partes_data[1].strip()
                            ano_arquivo = partes_data[2].strip()
                            
                            # Usa normalização para comparar as datas
                            if (normalizar_texto(dia_arquivo) == normalizar_texto(dia_str) and 
                                normalizar_texto(mes_arquivo) == normalizar_texto(mes_str) and 
                                normalizar_texto(ano_arquivo) == normalizar_texto(ano_str)):
                                dados_filtrados.append(registro)
                except Exception:
                    continue
        
        if dados_filtrados:  # Só inclui se houver dados filtrados
            resultado_filtrado = {
                "arquivo": res["arquivo"],
                "banco": res["banco"],
                "dados": dados_filtrados
            }
            resultados_filtrados.append(resultado_filtrado)
    
    return {"resultados_filtrados": resultados_filtrados}


#############################################################
# Pacote local automatizado (substitui operacao manual)
#############################################################

def _montar_payload_mab(
    dia: int,
    mes: int,
    ano: int,
    data_arrecadacao: str = None,
    feriados=None,
) -> dict:
    from datetime import datetime
    resultados = []
    for caminho_base in caminhos_base:
        resultados.extend(processar_pasta_completa(caminho_base))
    dia_str = f"{dia:02d}"
    mes_str = f"{mes:02d}"
    resultados_filtrados = [res for res in resultados if res["banco"].endswith(f"{dia_str}{mes_str}")]
    resultados_agregados = agregar_resultados_mab(resultados_filtrados)
    # No pacote diario, data_arrecadacao = dia alvo (contabil). Fora do pacote,
    # mantem o proximo dia util apos o filtro (respeitando feriados se informados).
    data_arrecadacao_mab = (
        str(data_arrecadacao).strip()
        if data_arrecadacao
        else calcular_proximo_dia_util(dia, mes, ano, feriados=feriados)
    )
    return {
        "tipo": "MAB",
        "data_filtro": f"{dia:02d}/{mes:02d}/{ano}",
        "data_arrecadacao": data_arrecadacao_mab,
        "data_geracao": datetime.now().isoformat(),
        "total_registros": len(resultados_agregados),
        "resultados": resultados_agregados,
    }

def _montar_payload_mcr(dia: int, mes: int, ano: int) -> dict:
    from datetime import datetime
    resultados = []
    for caminho in caminhos_classificacao:
        resultados.extend(processar_pasta_classificacao(caminho))
    dia_str = f"{dia:02d}"
    mes_str = f"{mes:02d}"
    resultados_filtrados = [res for res in resultados if res["banco"][:2] == dia_str and res["banco"][2:4] == mes_str]
    totais_por_banco = {}
    for res in resultados_filtrados:
        banco = res["banco"]
        if banco not in totais_por_banco:
            totais_por_banco[banco] = 0.0
        for registro in res["dados"]:
            valor = _parse_valor_monetario(registro.get("liquido", registro.get("valor_receita", 0)))
            totais_por_banco[banco] += valor
        totais_por_banco[banco] = float(_round2_half_up(totais_por_banco[banco]))
    data_filtro_str = f"{dia:02d}/{mes:02d}/{ano}"
    return {
        "tipo": "MCR",
        "data_filtro": data_filtro_str,
        "data_arrecadacao": data_filtro_str,
        "data_geracao": datetime.now().isoformat(),
        "total_registros": len(resultados_filtrados),
        "totais_por_banco": totais_por_banco,
        "resultados": adicionar_codigo_resumido_mcr(resultados_filtrados),
    }

def _normalizar_deducoes_filtradas(resultados_filtrados: list, codigo_deducao: str) -> list:
    resultados_normalizados = []
    for res in resultados_filtrados:
        dados_norm = []
        for registro in res.get("dados", []):
            if registro.get("deducao") != codigo_deducao:
                continue
            detalhes_norm = []
            for det in registro.get("detalhamento", []):
                codigo_item = det.get("codigo_original")
                valor_deducao_item = det.get("valor_original")
                receitas_por_codigo = det.get("receitas_por_codigo", {})
                if isinstance(codigo_item, str) and codigo_item.startswith(codigo_deducao):
                    codigo_base = codigo_item[2:]
                    codigo_receita = codigo_base + "00"
                else:
                    codigo_receita = ""
                valor_receita = receitas_por_codigo.get(codigo_receita, "")
                detalhes_norm.append({
                    "codigo_receita": codigo_receita,
                    "valor_receita": valor_receita,
                    "codigo_deducao": codigo_item,
                    "valor_deducao": valor_deducao_item,
                })
            detalhes_norm = _agrupar_detalhamento_por_codigo_receita(detalhes_norm)
            dados_norm.append({
                "data_contabil": registro.get("Data_Contabil"),
                "deducao": registro.get("deducao"),
                "valor_deducao": _formatar_valor_monetario_json_como_mab(
                    sum(_parse_valor_monetario(d.get("valor_deducao", "0")) for d in detalhes_norm)
                ).replace("-", ""),
                "detalhamento": detalhes_norm,
            })
        if dados_norm:
            resultados_normalizados.append({
                "arquivo": res.get("arquivo"),
                "banco": res.get("banco"),
                "dados": dados_norm,
            })
    return resultados_normalizados

def _filtrar_deducoes_por_data(dia: int, mes: int, ano: int) -> list:
    resultados = []
    caminhos_deducoes = gerar_caminhos_deducoes_dinamicos()
    for caminho in caminhos_deducoes:
        if os.path.exists(caminho):
            try:
                resultados.extend(processar_pasta_deducoes(caminho, ano))
            except Exception:
                continue
    dia_str = f"{dia:02d}"
    mes_str = f"{mes:02d}"
    ano_str = str(ano)
    resultados_filtrados = []
    for res in resultados:
        dados_filtrados = []
        for registro in res["dados"]:
            data_contabil = registro.get("Data_Contabil", "")
            if not data_contabil or "/" not in data_contabil:
                continue
            try:
                partes_data = data_contabil.split("/")
                if len(partes_data) != 3:
                    continue
                dia_arquivo, mes_arquivo, ano_arquivo = [p.strip() for p in partes_data]
                if (
                    normalizar_texto(dia_arquivo) == normalizar_texto(dia_str)
                    and normalizar_texto(mes_arquivo) == normalizar_texto(mes_str)
                    and normalizar_texto(ano_arquivo) == normalizar_texto(ano_str)
                ):
                    dados_filtrados.append(registro)
            except Exception:
                continue
        if dados_filtrados:
            resultados_filtrados.append({
                "arquivo": res["arquivo"],
                "banco": res["banco"],
                "dados": dados_filtrados,
            })
    return resultados_filtrados

def _montar_payload_renuncias(dia: int, mes: int, ano: int) -> dict:
    from datetime import datetime
    filtrados = _filtrar_deducoes_por_data(dia, mes, ano)
    resultados_normalizados = _normalizar_deducoes_filtradas(filtrados, "91")
    return {
        "tipo": "Renuncias",
        "data_filtro": f"{dia:02d}/{mes:02d}/{ano}",
        "data_arrecadacao": f"{dia:02d}/{mes:02d}/{ano}",
        "data_geracao": datetime.now().isoformat(),
        "codigo_resumido": 6112,
        "total_registros": len(resultados_normalizados),
        "resultados": resultados_normalizados,
    }

def _montar_payload_descontos(dia: int, mes: int, ano: int) -> dict:
    from datetime import datetime
    filtrados = _filtrar_deducoes_por_data(dia, mes, ano)
    resultados_normalizados = _normalizar_deducoes_filtradas(filtrados, "93")
    return {
        "tipo": "Descontos",
        "data_filtro": f"{dia:02d}/{mes:02d}/{ano}",
        "data_arrecadacao": f"{dia:02d}/{mes:02d}/{ano}",
        "data_geracao": datetime.now().isoformat(),
        "codigo_resumido": 6112,
        "total_registros": len(resultados_normalizados),
        "resultados": resultados_normalizados,
    }

def _conferir_totais_mab_mcr(mab_json: dict, mcr_antes: dict, mcr_depois: dict) -> dict:
    totais_mab = _extrair_totais_mab_por_tipo_banco(mab_json)
    totais_mcr_antes = _extrair_totais_mcr_por_tipo_banco(mcr_antes)
    totais_mcr_depois = _extrair_totais_mcr_por_tipo_banco(mcr_depois)

    def _diff(a: float, b: float) -> float:
        return float(_round2_half_up(a - b))

    conferencia = {
        "data_arrecadacao_mab": mab_json.get("data_arrecadacao"),
        "data_arrecadacao_mcr": mcr_depois.get("data_arrecadacao"),
        "datas_compativeis": str(mab_json.get("data_arrecadacao", "")).strip()
            == str(mcr_depois.get("data_arrecadacao", "")).strip(),
        "totais_mab": {k: float(_round2_half_up(v)) for k, v in totais_mab.items()},
        "totais_mcr_antes": {k: float(_round2_half_up(v)) for k, v in totais_mcr_antes.items()},
        "totais_mcr_depois": {k: float(_round2_half_up(v)) for k, v in totais_mcr_depois.items()},
        "diferenca_antes": {
            "cef": _diff(totais_mab.get("cef", 0.0), totais_mcr_antes.get("cef", 0.0)),
            "bb": _diff(totais_mab.get("bb", 0.0), totais_mcr_antes.get("bb", 0.0)),
        },
        "diferenca_depois": {
            "cef": _diff(totais_mab.get("cef", 0.0), totais_mcr_depois.get("cef", 0.0)),
            "bb": _diff(totais_mab.get("bb", 0.0), totais_mcr_depois.get("bb", 0.0)),
        },
    }
    conferencia["bateu"] = (
        conferencia["datas_compativeis"]
        and abs(conferencia["diferenca_depois"]["cef"]) < 0.01
        and abs(conferencia["diferenca_depois"]["bb"]) < 0.01
    )
    return conferencia

def _salvar_json(pasta: str, nome_arquivo: str, dados: dict) -> str:
    import json
    caminho = os.path.join(pasta, nome_arquivo)
    with open(caminho, "w", encoding="utf-8") as f:
        json.dump(dados, f, ensure_ascii=False, indent=2)
    return caminho


TIPOS_ARQUIVO = ("mab", "mcr", "renuncias", "descontos")


def _parse_tipos_arquivo(tipos: str) -> list:
    texto = str(tipos or "todos").strip().lower()
    if texto in ("", "todos", "all", "*"):
        return list(TIPOS_ARQUIVO)
    pedidos = []
    for parte in re.split(r"[,\s|;]+", texto):
        p = parte.strip().lower()
        if p in ("renuncia", "renuncias", "91"):
            p = "renuncias"
        elif p in ("desconto", "descontos", "93"):
            p = "descontos"
        if p in TIPOS_ARQUIVO and p not in pedidos:
            pedidos.append(p)
    return pedidos or list(TIPOS_ARQUIVO)


def _parse_data_consulta(data_iso, dia, mes, ano):
    from datetime import datetime, date
    if data_iso:
        return datetime.strptime(str(data_iso).strip()[:10], "%Y-%m-%d").date()
    if dia is None or mes is None:
        raise ValueError("Informe data_inicio (YYYY-MM-DD) ou dia/mes/ano.")
    return date(int(ano or 2026), int(mes), int(dia))


def _iterar_dias_periodo(inicio, fim):
    from datetime import timedelta
    if fim < inicio:
        inicio, fim = fim, inicio
    dias = []
    atual = inicio
    while atual <= fim:
        dias.append(atual)
        atual += timedelta(days=1)
    if len(dias) > 31:
        raise ValueError("Periodo maximo de 31 dias por consulta.")
    return dias


def _nomes_arquivos_pacote(dia: int, mes: int, ano: int) -> dict:
    sufixo = f"{dia:02d}_{mes:02d}_{ano}"
    return {
        "mab": f"mab_dados_{sufixo}.json",
        "mcr": f"mcr_dados_{sufixo}.json",
        "renuncias": f"renuncias_dados_{sufixo}.json",
        "descontos": f"descontos_dados_{sufixo}.json",
    }


def _pasta_saida_dia(pasta_saida: str, dia: int, mes: int, ano: int) -> str:
    from carregar_env import diretorio_projeto
    pasta = os.path.join(diretorio_projeto(), pasta_saida, f"{ano}-{mes:02d}-{dia:02d}")
    os.makedirs(pasta, exist_ok=True)
    return pasta


def _resumo_arquivo(tipo: str, payload: dict) -> dict:
    tipo = (tipo or "").lower()
    if not payload:
        return {"tipo": tipo, "total": 0.0, "registros": 0, "por_conta": {}, "linhas": []}

    if tipo == "mab":
        linhas = []
        por_conta = {}
        total = 0.0
        for r in payload.get("resultados") or []:
            valor = _parse_valor_monetario(r.get("valor_arrecadado"))
            codigo = r.get("codigo_resumido")
            chave = str(codigo) if codigo is not None else ""
            linhas.append({
                "banco": r.get("banco"),
                "codigo_resumido": codigo,
                "valor": float(_round2_half_up(valor)),
            })
            total += valor
            por_conta[chave] = float(_round2_half_up(por_conta.get(chave, 0.0) + valor))
        return {
            "tipo": "mab",
            "total": float(_round2_half_up(total)),
            "registros": len(linhas),
            "por_conta": por_conta,
            "linhas": linhas,
        }

    if tipo == "mcr":
        linhas = []
        por_conta = {}
        total = 0.0
        por_banco = {}
        for item in payload.get("resultados") or []:
            codigo = item.get("codigo_resumido")
            chave = str(codigo) if codigo is not None else ""
            banco = item.get("banco")
            for d in item.get("dados") or []:
                natureza = (
                    d.get("codigo_receita")
                    or d.get("Natureza_da_Receita")
                    or d.get("Natureza da Receita")
                    or ""
                )
                valor = _parse_valor_monetario(
                    d.get("valor_receita", d.get("liquido", d.get("Líquido", "0")))
                )
                linhas.append({
                    "banco": banco,
                    "arquivo": item.get("arquivo"),
                    "codigo_resumido": codigo,
                    "codigo_receita": natureza,
                    "categoria": d.get("categoria") or "",
                    "valor": float(_round2_half_up(valor)),
                })
                total += valor
                por_conta[chave] = float(_round2_half_up(por_conta.get(chave, 0.0) + valor))
                por_banco[str(banco or "")] = float(
                    _round2_half_up(por_banco.get(str(banco or ""), 0.0) + valor)
                )
        totais_por_banco = payload.get("totais_por_banco") or por_banco
        if totais_por_banco:
            total_bancos = sum(_parse_valor_monetario(v) for v in totais_por_banco.values())
            if abs(total_bancos) >= 0.01:
                total = total_bancos
                por_banco = {str(k): float(_round2_half_up(_parse_valor_monetario(v))) for k, v in totais_por_banco.items()}
        return {
            "tipo": "mcr",
            "total": float(_round2_half_up(total)),
            "registros": len(linhas),
            "por_conta": por_conta,
            "totais_por_banco": por_banco,
            "linhas": linhas,
        }

    linhas = []
    total = 0.0
    codigo = payload.get("codigo_resumido")
    chave = str(codigo) if codigo is not None else "6112"
    for res in payload.get("resultados") or []:
        for dado in res.get("dados") or []:
            valor_reg = _parse_valor_monetario(dado.get("valor_deducao"))
            total += valor_reg
            detalhes = dado.get("detalhamento") or []
            if not detalhes:
                linhas.append({
                    "arquivo": res.get("arquivo"),
                    "codigo_resumido": codigo,
                    "codigo_receita": "",
                    "codigo_deducao": dado.get("deducao"),
                    "valor": float(_round2_half_up(valor_reg)),
                })
                continue
            for det in detalhes:
                valor = _parse_valor_monetario(det.get("valor_deducao"))
                linhas.append({
                    "arquivo": res.get("arquivo"),
                    "codigo_resumido": codigo,
                    "codigo_receita": det.get("codigo_receita"),
                    "codigo_deducao": det.get("codigo_deducao"),
                    "valor": float(_round2_half_up(valor)),
                })
    return {
        "tipo": tipo,
        "total": float(_round2_half_up(total)),
        "registros": len(linhas),
        "por_conta": {chave: float(_round2_half_up(total))},
        "linhas": linhas,
    }


def _carregar_payloads_locais(dia: int, mes: int, ano: int, pasta_saida: str, tipos: list) -> dict:
    import json
    pasta = _pasta_saida_dia(pasta_saida, dia, mes, ano)
    nomes = _nomes_arquivos_pacote(dia, mes, ano)
    payloads = {}
    faltando = []
    for tipo in tipos:
        caminho = os.path.join(pasta, nomes[tipo])
        if not os.path.exists(caminho):
            faltando.append(nomes[tipo])
            continue
        with open(caminho, "r", encoding="utf-8") as f:
            payloads[tipo] = json.load(f)
    return {"pasta": pasta, "payloads": payloads, "faltando": faltando, "nomes": nomes}


def _gerar_pacote_do_dia(
    dia: int,
    mes: int,
    ano: int,
    tipos: list,
    pasta_saida: str = "saida_pacotes",
    enviar_s3: bool = False,
    salvar_local: bool = True,
    calendario_feriados: str = None,
    incluir_facultativos: bool = False,
    mab_dia: int = None,
    mab_mes: int = None,
    mab_ano: int = None,
):
    from datetime import datetime
    from carregar_env import diagnosticar_share_sefaz

    tipos = [t for t in tipos if t in TIPOS_ARQUIVO]
    feriados = set()
    calendario_usado = None
    if calendario_feriados:
        from feriados import conjunto_datas_feriado
        calendario_usado = str(calendario_feriados).strip().lower()
        feriados = conjunto_datas_feriado(
            calendario_usado,
            ano=ano,
            incluir_facultativos=bool(incluir_facultativos),
        )

    if mab_dia is not None and mab_mes is not None:
        dia_mab, mes_mab, ano_mab = int(mab_dia), int(mab_mes), int(mab_ano or ano)
    else:
        dia_mab, mes_mab, ano_mab = calcular_dia_util_anterior_parts(
            dia, mes, ano, feriados=feriados or None
        )
    data_alvo = f"{dia:02d}/{mes:02d}/{ano}"
    data_mab_filtro = f"{dia_mab:02d}/{mes_mab:02d}/{ano_mab}"
    nomes_finais = _nomes_arquivos_pacote(dia, mes, ano)
    pasta_dia = _pasta_saida_dia(pasta_saida, dia, mes, ano)

    erros = []
    share = diagnosticar_share_sefaz()
    if not share.get("acessivel"):
        erros.append(f"Share SEFAZ: {share.get('mensagem')}")

    arquivos = {}
    mab_json = None
    mcr_json = None
    mcr_ajustado = None
    renuncias_json = None
    descontos_json = None
    conferencia = None
    precisa_mab = "mab" in tipos or "mcr" in tipos
    precisa_mcr = "mcr" in tipos

    if precisa_mab:
        try:
            # data_filtro = dia util anterior (arquivos FEBRABAN);
            # data_arrecadacao = dia alvo do pacote, para casar com o MCR no ajuste.
            mab_json = _montar_payload_mab(
                dia_mab,
                mes_mab,
                ano_mab,
                data_arrecadacao=data_alvo,
                feriados=feriados or None,
            )
        except Exception as e:
            erros.append(f"MAB: {e}")

    if precisa_mcr:
        try:
            mcr_json = _montar_payload_mcr(dia, mes, ano)
        except Exception as e:
            erros.append(f"MCR: {e}")

    if "renuncias" in tipos:
        try:
            renuncias_json = _montar_payload_renuncias(dia, mes, ano)
        except Exception as e:
            erros.append(f"Renuncias: {e}")

    if "descontos" in tipos:
        try:
            descontos_json = _montar_payload_descontos(dia, mes, ano)
        except Exception as e:
            erros.append(f"Descontos: {e}")

    if precisa_mcr and mab_json is not None and mcr_json is not None:
        try:
            erro_mab = _validar_estrutura_mab_para_ajuste(mab_json)
            erro_mcr = _validar_estrutura_mcr_para_ajuste(mcr_json)
            if erro_mab:
                raise ValueError(erro_mab)
            if erro_mcr:
                raise ValueError(erro_mcr)
            mcr_ajustado = _ajustar_mcr_com_mab(mab_json, mcr_json)
            mcr_ajustado = copy.deepcopy(mcr_ajustado)
            mcr_ajustado["ajuste_aplicado"] = True
            mcr_ajustado["data_ajuste"] = datetime.now().isoformat()
            mcr_ajustado["origem_mab"] = mab_json.get("data_filtro")
            conferencia = _conferir_totais_mab_mcr(mab_json, mcr_json, mcr_ajustado)
        except Exception as e:
            erros.append(f"Ajuste MCR x MAB: {e}")

    mcr_final = mcr_ajustado if mcr_ajustado is not None else None
    conteudo = {}
    if "mab" in tipos and mab_json is not None:
        conteudo["mab"] = mab_json
    if "mcr" in tipos and mcr_final is not None:
        conteudo["mcr"] = mcr_final
    elif "mcr" in tipos and mcr_json is not None:
        erros.append("MCR ajustado indisponivel; arquivo mcr_dados nao foi gerado.")
    if "renuncias" in tipos and renuncias_json is not None:
        conteudo["renuncias"] = renuncias_json
    if "descontos" in tipos and descontos_json is not None:
        conteudo["descontos"] = descontos_json

    if salvar_local:
        for tipo, dados in conteudo.items():
            try:
                arquivos[tipo] = _salvar_json(pasta_dia, nomes_finais[tipo], dados)
            except Exception as e:
                erros.append(f"Salvar {tipo.upper()}: {e}")

    envio_s3 = None
    if enviar_s3:
        mab_qtd = (mab_json or {}).get("total_registros") or 0
        mcr_qtd = (mcr_final or {}).get("total_registros") or 0
        if not share.get("acessivel"):
            erros.append("Envio ao S3 cancelado: compartilhamento SEFAZ inacessível no container.")
        elif "mab" in tipos and "mcr" in tipos and mab_qtd == 0 and mcr_qtd == 0:
            erros.append(
                "Envio ao S3 cancelado: MAB e MCR vieram vazios (provável falha de leitura das pastas)."
            )
        else:
            try:
                envio_s3 = _enviar_pacote_para_s3(
                    data_alvo,
                    {k: conteudo.get(k) for k in tipos},
                )
                if envio_s3.get("erros"):
                    erros.extend([f"S3 {e}" for e in envio_s3["erros"]])
            except Exception as e:
                envio_s3 = {"sucesso": False, "mensagem": str(e), "arquivos": [], "erros": [str(e)]}
                erros.append(f"S3: {e}")

    resumo = {tipo: _resumo_arquivo(tipo, conteudo.get(tipo)) for tipo in tipos}
    mab_regs = int((mab_json or {}).get("total_registros") or 0) if mab_json is not None else 0
    mab_total = float(((resumo.get("mab") or {}).get("total") or 0.0)) if "mab" in tipos else 0.0
    mab_vazio = bool(mab_json is not None and mab_regs == 0 and abs(mab_total) < 0.01)
    mcr_vazio = bool(
        "mcr" in tipos
        and (
            (conteudo.get("mcr") is None)
            or abs(float(((resumo.get("mcr") or {}).get("total") or 0.0))) < 0.01
        )
    )

    return {
        "data_alvo": data_alvo,
        "data_mab_filtro": data_mab_filtro,
        "nomenclatura": {k: nomes_finais[k] for k in tipos},
        "tipos": tipos,
        "contagens": {k: (conteudo.get(k) or {}).get("total_registros") for k in tipos},
        "resumo": resumo,
        "conteudo": conteudo,
        "conferencia_mab_mcr": conferencia,
        "share": share,
        "arquivos": arquivos,
        "pasta_saida": pasta_dia,
        "envio_s3": envio_s3,
        "erros": erros,
        "sucesso": len(erros) == 0 and len(conteudo) == len(tipos),
        "mab_vazio": mab_vazio,
        "mcr_vazio": mcr_vazio,
        "calendario_feriados": calendario_usado,
        # Alerta de feriado so quando o MAB (conteudo do filtro) veio vazio.
        "alerta_zerado": mab_vazio,
    }


def _proximo_nome_arquivo_s3(tipo: str, data_alvo: str, item_remoto: dict) -> dict:
    """
    Nome padrao: TIPO_DD-MM-YYYY.json
    Se o dia ja existe: TIPO_DD-MM-YYYY-RET1.json, RET2, ...
    """
    tipo = str(tipo or "").upper().strip()
    data_ref = str(data_alvo or "").replace("/", "-").strip()
    base = f"{tipo}_{data_ref}"
    item = item_remoto or {}
    if not item.get("presente"):
        return {"file_name": f"{base}.json", "retificacao": 0, "ja_existia": False}

    n = 0
    try:
        n = int(item.get("retificacao") if item.get("retificacao") is not None else 0)
    except (TypeError, ValueError):
        n = 0
    nome_atual = str(item.get("file_name") or "")
    match_ret = re.search(r"-RET(\d+)", nome_atual, re.IGNORECASE)
    if match_ret:
        n = max(n, int(match_ret.group(1)))
    proximo = n + 1
    return {
        "file_name": f"{base}-RET{proximo}.json",
        "retificacao": proximo,
        "ja_existia": True,
    }


def _retificacao_do_nome(nome: str) -> int:
    match_ret = re.search(r"-RET(\d+)", str(nome or ""), re.IGNORECASE)
    return int(match_ret.group(1)) if match_ret else 0


def _estado_versao_vazio(tipo: str) -> dict:
    return {
        "tipo": tipo,
        "presente": False,
        "file_name": None,
        "retificacao": 0,
        "versao": "ausente",
        "status": None,
        "created_at": None,
    }


def _estado_banco_por_data(data_alvo: str) -> dict:
    from aws_manager_visivel import AWSManagerVisivel

    mgr = AWSManagerVisivel()
    lista = mgr.listar_arquivos_por_data(data_alvo)
    por_tipo = {}
    if not lista.get("sucesso"):
        return {
            "sucesso": False,
            "mensagem": lista.get("mensagem") or "Falha ao consultar API Banco",
            "por_tipo": {},
            "bruto": lista,
        }
    for item in lista.get("versoes") or lista.get("tipos") or []:
        tipo = str(item.get("tipo") or "").upper()
        if not tipo:
            continue
        presente = bool(item.get("presente"))
        nome = item.get("file_name")
        n = 0
        try:
            n = int(item.get("retificacao") if item.get("retificacao") is not None else 0)
        except (TypeError, ValueError):
            n = 0
        n = max(n, _retificacao_do_nome(nome))
        if not presente:
            rotulo = "ausente"
        elif n <= 0:
            rotulo = "original"
        else:
            rotulo = f"RET{n}"
        por_tipo[tipo] = {
            "tipo": tipo,
            "presente": presente,
            "file_name": nome,
            "retificacao": n,
            "versao": rotulo,
            "status": item.get("status"),
            "created_at": item.get("created_at"),
        }
    return {
        "sucesso": True,
        "mensagem": "API Banco ok",
        "por_tipo": por_tipo,
        "bruto": lista,
    }


def _estado_indice_local_por_data(data_alvo: str) -> dict:
    from aws_manager_visivel import AWSManagerVisivel

    data_ref = str(data_alvo or "").replace("-", "/").strip()
    mgr = AWSManagerVisivel()
    estrutura = mgr.obter_estrutura_pastas()
    if not estrutura.get("sucesso"):
        return {
            "sucesso": False,
            "mensagem": estrutura.get("mensagem") or "Falha ao ler índice local",
            "por_tipo": {},
            "bruto": estrutura,
        }

    melhores = {}
    candidatos = []
    for nome_pasta, pasta in (estrutura.get("pastas") or {}).items():
        for arq in pasta.get("arquivos") or []:
            candidatos.append(arq)
    for arq in estrutura.get("arquivos_sem_pasta") or []:
        candidatos.append(arq)

    for arq in candidatos:
        filtro = str(
            arq.get("data_filtro")
            or (arq.get("dados") or {}).get("data_filtro")
            or arq.get("data_arrecadacao")
            or (arq.get("dados") or {}).get("data_arrecadacao")
            or ""
        ).replace("-", "/")
        nome = str(arq.get("nome_arquivo") or "")
        # também casa pelo nome TIPO_DD-MM-YYYY
        data_no_nome = None
        m = re.search(r"(\d{2})-(\d{2})-(\d{4})", nome)
        if m:
            data_no_nome = f"{m.group(1)}/{m.group(2)}/{m.group(3)}"
        if filtro != data_ref and data_no_nome != data_ref:
            continue
        tipo = str(arq.get("tipo") or "").upper()
        if not tipo:
            continue
        n = _retificacao_do_nome(nome)
        atual = melhores.get(tipo)
        if atual is None or n >= atual["retificacao"]:
            melhores[tipo] = {
                "tipo": tipo,
                "presente": True,
                "file_name": nome or None,
                "retificacao": n,
                "versao": "original" if n <= 0 else f"RET{n}",
                "status": arq.get("status"),
                "created_at": arq.get("data_upload"),
                "arquivo_id": arq.get("arquivo_id"),
            }

    return {
        "sucesso": True,
        "mensagem": "Índice local ok",
        "por_tipo": melhores,
        "bruto": {"total": len(melhores)},
    }


def _conferir_nomenclatura_fontes(data_alvo: str, tipos: list) -> dict:
    mapa = {
        "mab": "MAB",
        "mcr": "MCR",
        "descontos": "DESCONTOS",
        "renuncias": "RENUNCIAS",
    }
    tipos_upper = []
    for t in tipos:
        chave = str(t or "").lower()
        if chave in mapa:
            tipos_upper.append(mapa[chave])
        else:
            tipos_upper.append(str(t or "").upper())
    tipos_upper = list(dict.fromkeys(tipos_upper))

    banco = _estado_banco_por_data(data_alvo)
    local = _estado_indice_local_por_data(data_alvo)

    comparacao = []
    divergente = False
    for tipo in tipos_upper:
        item_banco = banco.get("por_tipo", {}).get(tipo) or _estado_versao_vazio(tipo)
        item_local = local.get("por_tipo", {}).get(tipo) or _estado_versao_vazio(tipo)
        prox_banco = _proximo_nome_arquivo_s3(tipo, data_alvo, item_banco)
        prox_local = _proximo_nome_arquivo_s3(tipo, data_alvo, item_local)
        dif = prox_banco["file_name"] != prox_local["file_name"]
        if dif:
            divergente = True
        comparacao.append({
            "tipo": tipo,
            "banco": {
                **item_banco,
                "proximo_nome": prox_banco["file_name"],
                "proximo_retificacao": prox_banco["retificacao"],
            },
            "local": {
                **item_local,
                "proximo_nome": prox_local["file_name"],
                "proximo_retificacao": prox_local["retificacao"],
            },
            "divergente": dif,
        })

    return {
        "sucesso": bool(banco.get("sucesso")) or bool(local.get("sucesso")),
        "data_alvo": data_alvo,
        "tipos": tipos_upper,
        "banco_ok": bool(banco.get("sucesso")),
        "local_ok": bool(local.get("sucesso")),
        "banco_mensagem": banco.get("mensagem"),
        "local_mensagem": local.get("mensagem"),
        "divergente": divergente,
        "comparacao": comparacao,
        "mensagem": (
            "Fontes divergem — escolha qual nomenclatura seguir."
            if divergente
            else "Fontes alinhadas — próximo nome igual nos dois."
        ),
    }


def _mapa_estado_por_fonte(data_alvo: str, fonte: str) -> dict:
    fonte = str(fonte or "banco").lower().strip()
    if fonte in ("local", "indice", "s3", "indice_local"):
        estado = _estado_indice_local_por_data(data_alvo)
        chave = "local"
    else:
        estado = _estado_banco_por_data(data_alvo)
        chave = "banco"
    if not estado.get("sucesso"):
        return {
            "sucesso": False,
            "fonte": chave,
            "mensagem": estado.get("mensagem") or f"Falha ao consultar fonte {chave}",
            "por_tipo": {},
        }
    return {
        "sucesso": True,
        "fonte": chave,
        "mensagem": estado.get("mensagem"),
        "por_tipo": estado.get("por_tipo") or {},
    }


def _enviar_pacote_para_s3(data_alvo: str, payloads: dict, fonte_nomenclatura: str = None) -> dict:
    """Envia os JSONs ao S3. Se as fontes divergirem e nenhuma for escolhida, pede escolha."""
    from aws_manager_visivel import AWSManagerVisivel

    mapa_tipo = {
        "mab": "MAB",
        "mcr": "MCR",
        "descontos": "DESCONTOS",
        "renuncias": "RENUNCIAS",
    }
    tipos_envio = [mapa_tipo[k] for k, v in payloads.items() if v is not None and k in mapa_tipo]
    conferencia = _conferir_nomenclatura_fontes(data_alvo, tipos_envio)

    fonte = str(fonte_nomenclatura or "").strip().lower()
    if not fonte:
        if conferencia.get("divergente"):
            return {
                "sucesso": False,
                "precisa_escolha": True,
                "mensagem": conferencia.get("mensagem"),
                "conferencia": conferencia,
                "arquivos": [],
                "erros": [],
            }
        # alinhados: preferir banco se ok, senão local
        fonte = "banco" if conferencia.get("banco_ok") else "local"

    estado = _mapa_estado_por_fonte(data_alvo, fonte)
    if not estado.get("sucesso"):
        # se a fonte escolhida falhou mas a outra existe, avisar
        return {
            "sucesso": False,
            "precisa_escolha": False,
            "mensagem": estado.get("mensagem"),
            "conferencia": conferencia,
            "arquivos": [],
            "erros": [estado.get("mensagem")],
        }

    por_tipo = estado.get("por_tipo") or {}
    mgr = AWSManagerVisivel()
    envios = []
    erros = []
    for chave, dados in payloads.items():
        if dados is None:
            continue
        tipo = mapa_tipo[chave]
        info_nome = _proximo_nome_arquivo_s3(tipo, data_alvo, por_tipo.get(tipo) or {})
        conteudo = copy.deepcopy(dados)
        conteudo["tipo"] = tipo
        if not conteudo.get("data_arrecadacao"):
            conteudo["data_arrecadacao"] = data_alvo
        put = mgr.put_arquivo_remoto(tipo, info_nome["file_name"], conteudo)
        envio = {
            "tipo": tipo,
            "file_name": info_nome["file_name"],
            "retificacao": info_nome["retificacao"],
            "ja_existia": info_nome["ja_existia"],
            "fonte_nomenclatura": estado.get("fonte"),
            "sucesso": bool(put.get("sucesso")),
            "status_code": put.get("status_code"),
            "mensagem": put.get("mensagem"),
        }
        envios.append(envio)
        if put.get("sucesso"):
            try:
                mgr.adicionar_entrada_indice(tipo, info_nome["file_name"], conteudo)
            except Exception:
                pass
        else:
            erros.append(f"{tipo}: {put.get('mensagem')}")

    return {
        "sucesso": len(erros) == 0 and len(envios) > 0,
        "precisa_escolha": False,
        "mensagem": "Envio ao S3 concluido" if not erros else "Falha em um ou mais envios ao S3",
        "fonte_nomenclatura": estado.get("fonte"),
        "conferencia": conferencia,
        "arquivos": envios,
        "erros": erros,
    }


@app.get("/feriados/")
def listar_feriados(
    calendario: str = Query("nacional", description="nacional | municipal"),
    ano: int = Query(2026),
):
    from feriados import carregar_calendario
    return JSONResponse(content=carregar_calendario(calendario, ano=ano))


@app.get("/feriados/atualizar/")
def atualizar_feriados(
    calendario: str = Query("nacional", description="nacional | municipal | ambos"),
    ano: int = Query(2026),
):
    from feriados import atualizar_feriados_nacionais, garantir_feriados_municipais
    cal = str(calendario or "").lower()
    out = {"sucesso": True, "ano": ano, "resultados": {}}
    if cal in ("nacional", "ambos", "all", "*"):
        out["resultados"]["nacional"] = atualizar_feriados_nacionais(ano)
    if cal in ("municipal", "contagem", "ambos", "all", "*"):
        out["resultados"]["municipal"] = garantir_feriados_municipais(ano)
    if not out["resultados"]:
        return JSONResponse(status_code=400, content={"sucesso": False, "mensagem": "Calendário inválido."})
    out["sucesso"] = all(r.get("sucesso") for r in out["resultados"].values())
    return JSONResponse(content=out)


@app.get("/verificar_feriado_mab/")
def verificar_feriado_mab(
    dia: int = Query(...),
    mes: int = Query(...),
    ano: int = Query(2026),
    calendario: str = Query("nacional", description="nacional | municipal"),
    incluir_facultativos: bool = Query(False),
):
    from feriados import verificar_mab_por_calendario
    return JSONResponse(content=verificar_mab_por_calendario(
        dia, mes, ano, calendario=calendario, incluir_facultativos=incluir_facultativos
    ))


@app.get("/gerar_pacote_local/")
def gerar_pacote_local(
    dia: int = Query(None, description="Dia ALVO (alternativa a data_inicio)."),
    mes: int = Query(None, description="Mes ALVO."),
    ano: int = Query(2026, description="Ano ALVO."),
    data_inicio: str = Query(None, description="Inicio do periodo YYYY-MM-DD."),
    data_final: str = Query(None, description="Fim do periodo YYYY-MM-DD (igual ao inicio se omitido)."),
    tipos: str = Query("todos", description="mab,mcr,renuncias,descontos ou todos."),
    pasta_saida: str = Query(
        "saida_pacotes",
        description="Pasta base (relativa ao projeto) onde os JSONs serao gravados.",
    ),
    enviar_s3: bool = Query(False, description="Se true, envia ao S3 depois de gravar. Padrao: so gera e mostra."),
    salvar_local: bool = Query(True, description="Grava JSON em saida_pacotes para conferencia e envio posterior."),
    calendario_feriados: str = Query(
        None,
        description="Opcional: nacional | municipal. So quando o usuario pedir ajuste por feriado.",
    ),
    incluir_facultativos: bool = Query(False, description="Se true, pontos facultativos tambem sao pulados no MAB."),
    mab_dia: int = Query(None, description="Override manual do dia do filtro MAB."),
    mab_mes: int = Query(None, description="Override manual do mes do filtro MAB."),
    mab_ano: int = Query(None, description="Override manual do ano do filtro MAB."),
):
    """
    Gera arquivos localmente (um dia ou periodo), devolve valores na resposta e so envia ao S3 se pedir.

    1) Data alvo = cada dia do periodo
    2) MAB = dia util anterior; MCR/Renuncias/Descontos = dia alvo
    3) MCR e ajustado com MAB quando o MCR e solicitado
    4) Grava somente os tipos pedidos (nao apaga os outros do dia)
    5) Envio S3 e opcional e separado
    """
    from datetime import datetime

    try:
        inicio = _parse_data_consulta(data_inicio, dia, mes, ano)
        fim = _parse_data_consulta(data_final, dia, mes, ano) if data_final else inicio
        lista_dias = _iterar_dias_periodo(inicio, fim)
        lista_tipos = _parse_tipos_arquivo(tipos)
    except ValueError as e:
        return JSONResponse(status_code=400, content={"sucesso": False, "erros": [str(e)]})

    dias = []
    erros = []
    for d in lista_dias:
        item = _gerar_pacote_do_dia(
            d.day,
            d.month,
            d.year,
            lista_tipos,
            pasta_saida=pasta_saida,
            enviar_s3=enviar_s3,
            salvar_local=salvar_local,
            calendario_feriados=calendario_feriados,
            incluir_facultativos=incluir_facultativos,
            mab_dia=mab_dia,
            mab_mes=mab_mes,
            mab_ano=mab_ano,
        )
        dias.append(item)
        erros.extend([f"{item['data_alvo']}: {e}" for e in (item.get("erros") or [])])

    primeiro = dias[0] if dias else {}
    relatorio = {
        "gerado_em": datetime.now().isoformat(),
        "periodo": {
            "inicio": inicio.strftime("%d/%m/%Y"),
            "fim": fim.strftime("%d/%m/%Y"),
            "dias": len(dias),
        },
        "tipos": lista_tipos,
        "enviar_s3": enviar_s3,
        "calendario_feriados": calendario_feriados,
        "nomenclatura": primeiro.get("nomenclatura"),
        "regra": {
            "mab": "conteudo do dia util anterior; nome do arquivo usa data contabil (dia alvo)",
            "mcr": "conteudo ajustado com MAB quando o MCR e gerado",
            "renuncias_descontos": "dia alvo",
            "s3": "envio separado; TIPO_DD-MM-YYYY.json ou -RETN se o dia ja existir",
            "feriados": "nao automatico; usuario confere calendario quando MAB vier zerado",
        },
        "dias": dias,
        "data_alvo": primeiro.get("data_alvo"),
        "data_mab_filtro": primeiro.get("data_mab_filtro"),
        "contagens": primeiro.get("contagens"),
        "resumo": primeiro.get("resumo"),
        "conteudo": primeiro.get("conteudo") if len(dias) == 1 else None,
        "conferencia_mab_mcr": primeiro.get("conferencia_mab_mcr"),
        "share": primeiro.get("share"),
        "arquivos": primeiro.get("arquivos"),
        "pasta_saida": primeiro.get("pasta_saida"),
        "envio_s3": primeiro.get("envio_s3") if len(dias) == 1 else [i.get("envio_s3") for i in dias],
        "alerta_zerado": any(i.get("alerta_zerado") or i.get("mab_vazio") for i in dias),
        "erros": erros,
        "sucesso": len(erros) == 0 and len(dias) > 0,
    }
    return JSONResponse(content=relatorio)


@app.get("/conferir_nomenclatura_s3/")
def conferir_nomenclatura_s3(
    dia: int = Query(None),
    mes: int = Query(None),
    ano: int = Query(2026),
    data_inicio: str = Query(None),
    data_final: str = Query(None),
    tipos: str = Query("todos"),
):
    """Compara nomenclatura RET entre API Banco e índice local (S3)."""
    try:
        inicio = _parse_data_consulta(data_inicio, dia, mes, ano)
        fim = _parse_data_consulta(data_final, dia, mes, ano) if data_final else inicio
        lista_dias = _iterar_dias_periodo(inicio, fim)
        lista_tipos = _parse_tipos_arquivo(tipos)
    except ValueError as e:
        return JSONResponse(status_code=400, content={"sucesso": False, "erros": [str(e)]})

    dias = []
    divergente = False
    for d in lista_dias:
        data_alvo = f"{d.day:02d}/{d.month:02d}/{d.year}"
        conf = _conferir_nomenclatura_fontes(data_alvo, lista_tipos)
        dias.append(conf)
        if conf.get("divergente"):
            divergente = True

    return JSONResponse(content={
        "sucesso": True,
        "divergente": divergente,
        "periodo": {
            "inicio": inicio.strftime("%d/%m/%Y"),
            "fim": fim.strftime("%d/%m/%Y"),
        },
        "tipos": lista_tipos,
        "dias": dias,
        "mensagem": (
            "Há diferença entre API Banco e índice local. Escolha qual seguir."
            if divergente
            else "Fontes alinhadas para o período."
        ),
    })


@app.get("/enviar_pacote_s3/")
def enviar_pacote_s3(
    dia: int = Query(None),
    mes: int = Query(None),
    ano: int = Query(2026),
    data_inicio: str = Query(None, description="Inicio YYYY-MM-DD."),
    data_final: str = Query(None, description="Fim YYYY-MM-DD."),
    tipos: str = Query("todos"),
    pasta_saida: str = Query("saida_pacotes"),
    fonte_nomenclatura: str = Query(
        None,
        description="banco | local. Se omitido e houver divergencia, retorna precisa_escolha.",
    ),
):
    """Envia ao S3 os JSON ja gravados em saida_pacotes (gerar antes, conferir na tela, depois enviar)."""
    try:
        inicio = _parse_data_consulta(data_inicio, dia, mes, ano)
        fim = _parse_data_consulta(data_final, dia, mes, ano) if data_final else inicio
        lista_dias = _iterar_dias_periodo(inicio, fim)
        lista_tipos = _parse_tipos_arquivo(tipos)
    except ValueError as e:
        return JSONResponse(status_code=400, content={"sucesso": False, "erros": [str(e)]})

    envios = []
    erros = []
    precisa_escolha = False
    conferencias = []
    for d in lista_dias:
        data_alvo = f"{d.day:02d}/{d.month:02d}/{d.year}"
        carregado = _carregar_payloads_locais(d.day, d.month, d.year, pasta_saida, lista_tipos)
        if carregado["faltando"]:
            msg = f"{data_alvo}: gere e confira antes de enviar. Faltando: " + ", ".join(carregado["faltando"])
            erros.append(msg)
            envios.append({"data_alvo": data_alvo, "sucesso": False, "mensagem": msg, "arquivos": [], "erros": [msg]})
            continue
        try:
            resultado = _enviar_pacote_para_s3(
                data_alvo,
                {k: carregado["payloads"].get(k) for k in lista_tipos},
                fonte_nomenclatura=fonte_nomenclatura,
            )
            if resultado.get("conferencia"):
                conferencias.append(resultado["conferencia"])
            if resultado.get("precisa_escolha"):
                precisa_escolha = True
                envios.append({"data_alvo": data_alvo, **resultado})
                continue
            envios.append({"data_alvo": data_alvo, **resultado})
            if resultado.get("erros"):
                erros.extend([f"{data_alvo}: {e}" for e in resultado["erros"]])
            elif not resultado.get("sucesso"):
                erros.append(f"{data_alvo}: {resultado.get('mensagem') or 'falha no envio'}")
        except Exception as e:
            erros.append(f"{data_alvo}: {e}")
            envios.append({"data_alvo": data_alvo, "sucesso": False, "mensagem": str(e), "arquivos": [], "erros": [str(e)]})

    return JSONResponse(content={
        "sucesso": (not precisa_escolha) and len(erros) == 0 and len(envios) > 0,
        "precisa_escolha": precisa_escolha,
        "mensagem": (
            "Diferença entre API Banco e índice local — escolha qual nomenclatura seguir."
            if precisa_escolha
            else ("Envio ao S3 concluido" if not erros else "Falha em um ou mais envios ao S3")
        ),
        "periodo": {
            "inicio": inicio.strftime("%d/%m/%Y"),
            "fim": fim.strftime("%d/%m/%Y"),
        },
        "tipos": lista_tipos,
        "fonte_nomenclatura": fonte_nomenclatura,
        "conferencias": conferencias,
        "envios": envios,
        "erros": erros,
    })


@app.get("/download_mab_json/")
def download_mab_json(
    dia: int = Query(..., description="Dia do mês para filtrar os lançamentos"),
    mes: int = Query(..., description="Mês para filtrar os lançamentos"),
    ano: int = Query(2026, description="Ano para os documentos gerados")
):

    from fastapi.responses import JSONResponse
    import json
    from datetime import datetime
    
    resultados = []
    for caminho_base in caminhos_base:
        resultados.extend(processar_pasta_completa(caminho_base))
    
    dia_str = f"{dia:02d}"
    mes_str = f"{mes:02d}"
    resultados_filtrados = [res for res in resultados if res["banco"].endswith(f"{dia_str}{mes_str}")]
    
    # Agregar conforme regra (Caixa mantida, demais somam em Brasil)
    resultados_agregados = agregar_resultados_mab(resultados_filtrados)

    data_arrecadacao_mab = calcular_proximo_dia_util(dia, mes, ano)

    dados_json = {
        "tipo": "MAB",
        "data_filtro": f"{dia:02d}/{mes:02d}/{ano}",
        "data_arrecadacao": data_arrecadacao_mab,
        "data_geracao": datetime.now().isoformat(),
        "total_registros": len(resultados_agregados),
        "resultados": resultados_agregados
    }
    
    
    nome_arquivo = f"mab_dados_{dia:02d}_{mes:02d}_{ano}.json"
    

    import tempfile
    import os
    
    with tempfile.NamedTemporaryFile(mode='w', suffix='.json', delete=False, encoding='utf-8') as f:
        json.dump(dados_json, f, ensure_ascii=False, indent=2)
        temp_path = f.name
    
    return FileResponse(
        temp_path,
        media_type="application/json",
        filename=nome_arquivo,
        headers={"Content-Disposition": f"attachment; filename={nome_arquivo}"}
    )

@app.get("/download_mcr_json/")
def download_mcr_json(
    dia: int = Query(..., description="Dia do mês para filtrar os lançamentos"),
    mes: int = Query(..., description="Mês para filtrar os lançamentos"),
    ano: int = Query(2026, description="Ano para os documentos gerados")
):

    from fastapi.responses import JSONResponse
    import json
    from datetime import datetime
    
    resultados = []
    for caminho in caminhos_classificacao:
        resultados.extend(processar_pasta_classificacao(caminho))
    
    dia_str = f"{dia:02d}"
    mes_str = f"{mes:02d}"
    resultados_filtrados = [res for res in resultados if res["banco"][:2] == dia_str and res["banco"][2:4] == mes_str]
    

    totais_por_banco = {}
    for res in resultados_filtrados:
        banco = res["banco"]
        if banco not in totais_por_banco:
            totais_por_banco[banco] = 0.0
        for registro in res["dados"]:
            try:
                valor = float(registro["liquido"])
            except Exception:
                valor = 0.0
            totais_por_banco[banco] += valor
    
    
    data_filtro_str = f"{dia:02d}/{mes:02d}/{ano}"

    dados_json = {
        "tipo": "MCR",
        "data_filtro": data_filtro_str,
        "data_arrecadacao": data_filtro_str,
        "data_geracao": datetime.now().isoformat(),
        "total_registros": len(resultados_filtrados),
        "totais_por_banco": totais_por_banco,
        "resultados": adicionar_codigo_resumido_mcr(resultados_filtrados)
    }
    

    nome_arquivo = f"mcr_dados_{dia:02d}_{mes:02d}_{ano}.json"
    

    import tempfile
    import os
    
    with tempfile.NamedTemporaryFile(mode='w', suffix='.json', delete=False, encoding='utf-8') as f:
        json.dump(dados_json, f, ensure_ascii=False, indent=2)
        temp_path = f.name
    
    return FileResponse(
        temp_path,
        media_type="application/json",
        filename=nome_arquivo,
        headers={"Content-Disposition": f"attachment; filename={nome_arquivo}"}
    )

@app.post("/ajustar_mcr_por_mab_json/")
async def ajustar_mcr_por_mab_json(
    mab_json_upload: UploadFile = File(...),
    mcr_json_upload: UploadFile = File(...)
):
    import json
    import tempfile
    from datetime import datetime

    try:
        mab_bytes = await mab_json_upload.read()
        mcr_bytes = await mcr_json_upload.read()
        mab_json = json.loads(mab_bytes.decode("utf-8-sig"))
        mcr_json = json.loads(mcr_bytes.decode("utf-8-sig"))
    except Exception as e:
        return JSONResponse(
            status_code=400,
            content={"erro": f"Nao foi possivel ler os arquivos JSON enviados: {str(e)}"}
        )

    erro_mab = _validar_estrutura_mab_para_ajuste(mab_json)
    if erro_mab:
        return JSONResponse(status_code=400, content={"erro": erro_mab})

    erro_mcr = _validar_estrutura_mcr_para_ajuste(mcr_json)
    if erro_mcr:
        return JSONResponse(status_code=400, content={"erro": erro_mcr})

    try:
        mcr_ajustado = _ajustar_mcr_com_mab(mab_json, mcr_json)
    except ValueError as e:
        return JSONResponse(status_code=400, content={"erro": str(e)})
    except Exception as e:
        return JSONResponse(
            status_code=500,
            content={"erro": f"Erro inesperado ao gerar ajuste contabil: {str(e)}"}
        )

    nome_arquivo = f"mcr_ajustado_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json"
    with tempfile.NamedTemporaryFile(mode="w", suffix=".json", delete=False, encoding="utf-8") as f:
        json.dump(mcr_ajustado, f, ensure_ascii=False, indent=2)
        temp_path = f.name

    return FileResponse(
        temp_path,
        media_type="application/json",
        filename=nome_arquivo,
        headers={"Content-Disposition": f"attachment; filename={nome_arquivo}"}
    )

@app.get("/download_renuncias_json/")
def download_renuncias_json(
    dia: int = Query(..., description="Dia do mês para filtrar os lançamentos"),
    mes: int = Query(..., description="Mês para filtrar os lançamentos"),
    ano: int = Query(2026, description="Ano para os documentos gerados")
):
    
    from fastapi.responses import JSONResponse
    import json
    from datetime import datetime
    import os
    
    resultados = []
    caminhos_deducoes = gerar_caminhos_deducoes_dinamicos()
    for caminho in caminhos_deducoes:
        if os.path.exists(caminho):
            try:
                res = processar_pasta_deducoes(caminho, ano)
                resultados.extend(res)
            except Exception as e:
                continue
    

    dia_str = f"{dia:02d}"
    mes_str = f"{mes:02d}"
    ano_str = str(ano)
    
    resultados_filtrados = []
    for res in resultados:
        dados_filtrados = []
        for registro in res["dados"]:
            # Filtra apenas códigos 91 (renúncias)
            if registro.get("deducao") == "91":
                data_contabil = registro.get("Data_Contabil", "")
                if data_contabil:
                    try:
                        if "/" in data_contabil:
                            partes_data = data_contabil.split("/")
                            if len(partes_data) == 3:
                                dia_arquivo = partes_data[0].strip()
                                mes_arquivo = partes_data[1].strip()
                                ano_arquivo = partes_data[2].strip()
                                
                                if (normalizar_texto(dia_arquivo) == normalizar_texto(dia_str) and 
                                    normalizar_texto(mes_arquivo) == normalizar_texto(mes_str) and 
                                    normalizar_texto(ano_arquivo) == normalizar_texto(ano_str)):
                                    dados_filtrados.append(registro)
                    except Exception:
                        continue
        
        if dados_filtrados:
            resultados_filtrados.append({
                "arquivo": res["arquivo"],
                "banco": res["banco"],
                "dados": dados_filtrados
            })

    
    resultados_normalizados = []
    for res in resultados_filtrados:
        dados_norm = []
        for registro in res.get("dados", []):
            detalhes_norm = []
            for det in registro.get("detalhamento", []):
                codigo_deducao = det.get("codigo_original")
                valor_deducao_item = det.get("valor_original")
                receitas_por_codigo = det.get("receitas_por_codigo", {})
                
                # Deriva o código de receita removendo o prefixo '91' quando aplicável
                # Para códigos como 9111210103, remove "91" e adiciona "00" no final
                if isinstance(codigo_deducao, str) and codigo_deducao.startswith("91"):
                    codigo_base = codigo_deducao[2:]  # Remove "91"
                    codigo_receita = codigo_base + "00"  # Adiciona "00" no final
                else:
                    codigo_receita = ""
                # Busca o valor da receita correspondente (já formatado)
                valor_receita = receitas_por_codigo.get(codigo_receita, "")
                detalhes_norm.append({
                    "codigo_receita": codigo_receita,
                    "valor_receita": valor_receita,
                    "codigo_deducao": codigo_deducao,
                    "valor_deducao": valor_deducao_item
                })
            detalhes_norm = _agrupar_detalhamento_por_codigo_receita(detalhes_norm)
            dados_norm.append({
                "data_contabil": registro.get("Data_Contabil"),
                "deducao": registro.get("deducao"),
                "valor_deducao": _formatar_valor_monetario_json_como_mab(
                    sum(_parse_valor_monetario(d.get("valor_deducao", "0")) for d in detalhes_norm)
                ).replace("-", ""),
                "detalhamento": detalhes_norm
            })
        resultados_normalizados.append({
            "arquivo": res.get("arquivo"),
            "banco": res.get("banco"),
            "dados": dados_norm
        })

    dados_json = {
        "tipo": "Renuncias",
        "data_filtro": f"{dia:02d}/{mes:02d}/{ano}",
        "data_arrecadacao": f"{dia:02d}/{mes:02d}/{ano}",
        "data_geracao": datetime.now().isoformat(),
        "codigo_resumido": 6112,
        "total_registros": len(resultados_normalizados),
        "resultados": resultados_normalizados
    }
    
    nome_arquivo = f"renuncias_dados_{dia:02d}_{mes:02d}_{ano}.json"
    
    import tempfile
    with tempfile.NamedTemporaryFile(mode='w', suffix='.json', delete=False, encoding='utf-8') as f:
        json.dump(dados_json, f, ensure_ascii=False, indent=2)
        temp_path = f.name
    
    return FileResponse(
        temp_path,
        media_type="application/json",
        filename=nome_arquivo,
        headers={"Content-Disposition": f"attachment; filename={nome_arquivo}"}
    )

@app.get("/download_descontos_json/")
def download_descontos_json(
    dia: int = Query(..., description="Dia do mês para filtrar os lançamentos"),
    mes: int = Query(..., description="Mês para filtrar os lançamentos"),
    ano: int = Query(2026, description="Ano para os documentos gerados")
):
    
    from fastapi.responses import JSONResponse
    import json
    from datetime import datetime
    import os
    
    resultados = []
    caminhos_deducoes = gerar_caminhos_deducoes_dinamicos()
    for caminho in caminhos_deducoes:
        if os.path.exists(caminho):
            try:
                res = processar_pasta_deducoes(caminho, ano)
                resultados.extend(res)
            except Exception as e:
                continue
    

    dia_str = f"{dia:02d}"
    mes_str = f"{mes:02d}"
    ano_str = str(ano)
    
    resultados_filtrados = []
    for res in resultados:
        dados_filtrados = []
        for registro in res["dados"]:
          
            if registro.get("deducao") == "93":
                data_contabil = registro.get("Data_Contabil", "")
                if data_contabil:
                    try:
                        if "/" in data_contabil:
                            partes_data = data_contabil.split("/")
                            if len(partes_data) == 3:
                                dia_arquivo = partes_data[0].strip()
                                mes_arquivo = partes_data[1].strip()
                                ano_arquivo = partes_data[2].strip()
                                
                                if (normalizar_texto(dia_arquivo) == normalizar_texto(dia_str) and 
                                    normalizar_texto(mes_arquivo) == normalizar_texto(mes_str) and 
                                    normalizar_texto(ano_arquivo) == normalizar_texto(ano_str)):
                                    dados_filtrados.append(registro)
                    except Exception:
                        continue
        
        if dados_filtrados:
            resultados_filtrados.append({
                "arquivo": res["arquivo"],
                "banco": res["banco"],
                "dados": dados_filtrados
            })

    # Normaliza chaves e estrutura (minúsculas, sem acentos) apenas para saída JSON
    resultados_normalizados = []
    for res in resultados_filtrados:
        dados_norm = []
        for registro in res.get("dados", []):
            detalhes_norm = []
            for det in registro.get("detalhamento", []):
                codigo_deducao = det.get("codigo_original")
                valor_deducao_item = det.get("valor_original")
                receitas_por_codigo = det.get("receitas_por_codigo", {})
                
                # Deriva o código de receita removendo o prefixo '93' quando aplicável
                # Para códigos como 9311210103, remove "93" e adiciona "00" no final
                if isinstance(codigo_deducao, str) and codigo_deducao.startswith("93"):
                    codigo_base = codigo_deducao[2:]  # Remove "93"
                    codigo_receita = codigo_base + "00"  # Adiciona "00" no final
                else:
                    codigo_receita = ""
                # Busca o valor da receita correspondente (já formatado)
                valor_receita = receitas_por_codigo.get(codigo_receita, "")
                detalhes_norm.append({
                    "codigo_receita": codigo_receita,
                    "valor_receita": valor_receita,
                    "codigo_deducao": codigo_deducao,
                    "valor_deducao": valor_deducao_item
                })
            detalhes_norm = _agrupar_detalhamento_por_codigo_receita(detalhes_norm)
            dados_norm.append({
                "data_contabil": registro.get("Data_Contabil"),
                "deducao": registro.get("deducao"),
                "valor_deducao": _formatar_valor_monetario_json_como_mab(
                    sum(_parse_valor_monetario(d.get("valor_deducao", "0")) for d in detalhes_norm)
                ).replace("-", ""),
                "detalhamento": detalhes_norm
            })
        resultados_normalizados.append({
            "arquivo": res.get("arquivo"),
            "banco": res.get("banco"),
            "dados": dados_norm
        })

    dados_json = {
        "tipo": "Descontos",
        "data_filtro": f"{dia:02d}/{mes:02d}/{ano}",
        "data_arrecadacao": f"{dia:02d}/{mes:02d}/{ano}",
        "data_geracao": datetime.now().isoformat(),
        "codigo_resumido": 6112,
        "total_registros": len(resultados_normalizados),
        "resultados": resultados_normalizados
    }
    
    nome_arquivo = f"descontos_dados_{dia:02d}_{mes:02d}_{ano}.json"
    
    import tempfile
    with tempfile.NamedTemporaryFile(mode='w', suffix='.json', delete=False, encoding='utf-8') as f:
        json.dump(dados_json, f, ensure_ascii=False, indent=2)
        temp_path = f.name
    
    return FileResponse(
        temp_path,
        media_type="application/json",
        filename=nome_arquivo,
        headers={"Content-Disposition": f"attachment; filename={nome_arquivo}"}
    )

@app.get("/download_deducoes_json/")
def download_deducoes_json(
    dia: int = Query(..., description="Dia do mês para filtrar os lançamentos"),
    mes: int = Query(..., description="Mês para filtrar os lançamentos"),
    ano: int = Query(2026, description="Ano para os documentos gerados")
):
   
    from fastapi.responses import JSONResponse
    import json
    from datetime import datetime
    import os
    
    resultados = []
    caminhos_deducoes = gerar_caminhos_deducoes_dinamicos()
    for caminho in caminhos_deducoes:
        if os.path.exists(caminho):
            try:
                res = processar_pasta_deducoes(caminho, ano)
                resultados.extend(res)
            except Exception as e:
               
                continue
    
  
    dia_str = f"{dia:02d}"
    mes_str = f"{mes:02d}"
    ano_str = str(ano)
    
    resultados_filtrados = []
    for res in resultados:
        dados_filtrados = []
        for registro in res["dados"]:
            data_contabil = registro.get("Data_Contabil", "")
            if data_contabil:
             
                try:
                    if "/" in data_contabil:
                        partes_data = data_contabil.split("/")
                        if len(partes_data) == 3:
                            dia_arquivo = partes_data[0].strip()
                            mes_arquivo = partes_data[1].strip()
                            ano_arquivo = partes_data[2].strip()
                            

                            if (normalizar_texto(dia_arquivo) == normalizar_texto(dia_str) and 
                                normalizar_texto(mes_arquivo) == normalizar_texto(mes_str) and 
                                normalizar_texto(ano_arquivo) == normalizar_texto(ano_str)):
                                dados_filtrados.append(registro)
                except Exception:
                    continue
        
        if dados_filtrados:  
            resultado_filtrado = {
                "arquivo": res["arquivo"],
                "banco": res["banco"],
                "dados": dados_filtrados
            }
            resultados_filtrados.append(resultado_filtrado)
    
    dados_json = {
        "tipo": "Deducoes_Renuncia",
        "data_filtro": f"{dia:02d}/{mes:02d}/{ano}",
        "data_geracao": datetime.now().isoformat(),
        "total_registros": len(resultados_filtrados),
        "resultados": resultados_filtrados
    }
    

    nome_arquivo = f"deducoes_dados_{dia:02d}_{mes:02d}_{ano}.json"
    

    import tempfile
    import os
    
    with tempfile.NamedTemporaryFile(mode='w', suffix='.json', delete=False, encoding='utf-8') as f:
        json.dump(dados_json, f, ensure_ascii=False, indent=2)
        temp_path = f.name
    
    return FileResponse(
        temp_path,
        media_type="application/json",
        filename=nome_arquivo,
        headers={"Content-Disposition": f"attachment; filename={nome_arquivo}"}
    )

@app.get("/download_todos_dados_json/")
def download_todos_dados_json(
    dia: int = Query(..., description="Dia do mês para filtrar os lançamentos"),
    mes: int = Query(..., description="Mês para filtrar os lançamentos"),
    ano: int = Query(2026, description="Ano para os documentos gerados")
):

    from fastapi.responses import JSONResponse
    import json
    from datetime import datetime
    

    resultados_mab = []
    for caminho_base in caminhos_base:
        resultados_mab.extend(processar_pasta_completa(caminho_base))
    
    dia_str = f"{dia:02d}"
    mes_str = f"{mes:02d}"
    ano_str = str(ano)
    mab_filtrados = [res for res in resultados_mab if res["banco"].endswith(f"{dia_str}{mes_str}")]
    mab_agregado = agregar_resultados_mab(mab_filtrados)
    

    resultados_mcr = []
    for caminho in caminhos_classificacao:
        resultados_mcr.extend(processar_pasta_classificacao(caminho))
    mcr_filtrados = [res for res in resultados_mcr if res["banco"][:2] == dia_str and res["banco"][2:4] == mes_str]
    

    totais_mcr_por_banco = {}
    for res in mcr_filtrados:
        banco = res["banco"]
        if banco not in totais_mcr_por_banco:
            totais_mcr_por_banco[banco] = 0.0
        for registro in res["dados"]:
            try:
                valor = float(registro["liquido"])
            except Exception:
                valor = 0.0
            totais_mcr_por_banco[banco] += valor
    

    resultados_deducoes = []
    caminhos_deducoes = gerar_caminhos_deducoes_dinamicos()
    for caminho in caminhos_deducoes:
        resultados_deducoes.extend(processar_pasta_deducoes(caminho, ano))
    
   
    deducoes_filtrados = []
    for res in resultados_deducoes:
        dados_filtrados = []
        for registro in res["dados"]:
            data_contabil = registro.get("Data_Contabil", "")
            if data_contabil:

                try:
                    if "/" in data_contabil:
                        partes_data = data_contabil.split("/")
                        if len(partes_data) == 3:
                            dia_arquivo = partes_data[0].strip()
                            mes_arquivo = partes_data[1].strip()
                            ano_arquivo = partes_data[2].strip()
                            

                            if (normalizar_texto(dia_arquivo) == normalizar_texto(dia_str) and 
                                normalizar_texto(mes_arquivo) == normalizar_texto(mes_str) and 
                                normalizar_texto(ano_arquivo) == normalizar_texto(ano_str)):
                                dados_filtrados.append(registro)
                except Exception:
                    continue
        
        if dados_filtrados:  
            resultado_filtrado = {
                "arquivo": res["arquivo"],
                "banco": res["banco"],
                "dados": dados_filtrados
            }
            deducoes_filtrados.append(resultado_filtrado)
    

    dados_consolidados = {
        "data_filtro": f"{dia:02d}/{mes:02d}/{ano}",
        "data_geracao": datetime.now().isoformat(),
        "resumo": {
            "total_registros_mab": len(mab_agregado),
            "total_registros_mcr": len(mcr_filtrados),
            "total_registros_deducoes": len(deducoes_filtrados),
            "total_geral": len(mab_agregado) + len(mcr_filtrados) + len(deducoes_filtrados)
        },
        "dados": {
            "mab": {
                "tipo": "MAB",
                "resultados": mab_agregado
            },
            "mcr": {
                "tipo": "MCR",
                "totais_por_banco": totais_mcr_por_banco,
                "resultados": adicionar_codigo_resumido_mcr(mcr_filtrados)
            },
            "deducoes": {
                "tipo": "Deducoes_Renuncia",
                "resultados": deducoes_filtrados
            }
        }
    }
    

    nome_arquivo = f"todos_dados_{dia:02d}_{mes:02d}_{ano}.json"
    

    import tempfile
    import os
    
    with tempfile.NamedTemporaryFile(mode='w', suffix='.json', delete=False, encoding='utf-8') as f:
        json.dump(dados_consolidados, f, ensure_ascii=False, indent=2)
        temp_path = f.name
    
    return FileResponse(
        temp_path,
        media_type="application/json",
        filename=nome_arquivo,
        headers={"Content-Disposition": f"attachment; filename={nome_arquivo}"}
    )


@app.get("/gerar_relatorio_mab/")
def gerar_relatorio_mab_endpoint(
    mes: str = Query(None, description="Mês no formato MM (ex: '02' para Fevereiro)"),
    ano: int = Query(2026, description="Ano para os documentos gerados")
):
  
    from main import processar  

    mab_resultados = processar() 

    if not mab_resultados or "resultados" not in mab_resultados:
        return {"erro": "Não foi possível obter os dados do MAB."}

    nome_arquivo = f"relatorio_mab_{mes}_{ano}.xlsx"
    caminho_arquivo = gerar_relatorio_mab(mab_resultados, nome_arquivo, mes, ano)

    return FileResponse(
        caminho_arquivo,
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        filename=nome_arquivo
    )




@app.get("/gerar_relatorio_mcr/")
def gerar_relatorio_mcr_endpoint(
    mes: str = Query(None, description="Mês no formato MM"),
    ano: int = Query(2026, description="Ano para os documentos gerados")
):
   
    mcr_resultados = processar_classificacao()  

    if "resultados_filtrados" not in mcr_resultados or not mcr_resultados["resultados_filtrados"]:
        return {"erro": "Não foi possível obter os dados do MCR."}

    nome_arquivo = f"relatorio_mcr_{mes}_{ano}.xlsx" if mes else f"relatorio_mcr_{ano}.xlsx"
    caminho_arquivo = gerar_relatorio_mcr(mcr_resultados, nome_arquivo, mes, ano)

    return FileResponse(
        caminho_arquivo,
        filename=nome_arquivo,
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
    )


if __name__ == "__main__":
    import uvicorn
    uvicorn.run("main:app", host="0.0.0.0", port=int(os.getenv("PORT", "8000")))

