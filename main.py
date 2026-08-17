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

carregar_env()


app = FastAPI(title="SEFAZ Integração")
app.include_router(aws_router)



####################################################
# Função utilitária (usada por todos os módulos)
####################################################

def corrigir_caminho(caminho: str) -> str:

    """
    Corrige caminho no Windows para suportar caminhos longos.

    - Drive letter:      C:\\pasta\\arquivo  -> \\\\?\\C:\\pasta\\arquivo
    - UNC (rede):       \\\\srv\\share\\...  -> \\\\?\\UNC\\srv\\share\\...
    """
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

def calcular_dia_util_anterior(dia: int, mes: int, ano: int = 2026) -> str:

    from datetime import date, timedelta
    data = date(ano, mes, dia)
    anterior = data - timedelta(days=1)
    while anterior.weekday() >= 5: 
        anterior -= timedelta(days=1)
    return anterior.strftime("%d/%m/%Y")

def calcular_dia_util_anterior_parts(dia: int, mes: int, ano: int = 2026) -> tuple:
    """Retorna (dia, mes, ano) do dia util imediatamente anterior a data informada."""
    from datetime import date, timedelta
    data = date(ano, mes, dia)
    anterior = data - timedelta(days=1)
    while anterior.weekday() >= 5:
        anterior -= timedelta(days=1)
    return anterior.day, anterior.month, anterior.year

def calcular_proximo_dia_util(dia: int, mes: int, ano: int = 2026) -> str:

    from datetime import date, timedelta
    data = date(ano, mes, dia)
    proximo = data + timedelta(days=1)
    while proximo.weekday() >= 5:  
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

def _adicionar_lancamento_ajuste_no_mcr(mcr_json: dict, tipo_banco: str, diferenca: float):
    for item in mcr_json.get("resultados", []):
        tipo_item = _inferir_tipo_banco(item.get("banco", ""))
        if tipo_item != tipo_banco:
            continue
        if "dados" not in item or not isinstance(item["dados"], list):
            item["dados"] = []
        item["dados"].append({
            "Natureza_da_Receita": "1999992100",
            # No MCR, o detalhe usa ponto como separador decimal.
            "liquido": _formatar_valor_monetario_json_ponto_half_up(diferenca),
            "categoria": "Outras Receitas Nao Arrecadadas e Nao Projetadas pela RFB - Primarias - Principal",
        })
        return True
    return False

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
            codigo_resumido = 4066 if banco_lower.startswith("cef") else 6112
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
            "codigo_resumido": 4066,
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
        df = pd.read_excel(caminho_corrigido, engine='xlrd')
    else:
        df = pd.read_excel(caminho_corrigido)
    return df

def encontrar_total_liquido_classificacao(df: pd.DataFrame):
    linhas = df.astype(str).values.tolist()
    indice_total = None
    for idx, linha in enumerate(linhas):
        if any("Total Líquido Geral:" in str(celula) for celula in linha):
            indice_total = idx
            break
    if indice_total is None:
        raise Exception("Linha com 'Total Líquido Geral:' não encontrada.")
    return indice_total, linhas

def extrair_dados_classificacao(caminho_arquivo: str) -> dict:
    df = ler_planilha_classificacao(caminho_arquivo)
    indice_total, linhas = encontrar_total_liquido_classificacao(df)
    indice_cabecalho = None
    cabecalho = None
    for i in range(indice_total + 1, len(linhas)):
        linha_atual = linhas[i]
        if "Natureza da Receita" in linha_atual and "Líquido" in linha_atual and "Descrição" in linha_atual:
            cabecalho = linha_atual
            indice_cabecalho = i
            break
    if cabecalho is None:
        raise Exception("Não foram encontradas as colunas 'Natureza da Receita', 'Líquido' ou 'Descrição'.")
    try:
        idx_natureza = cabecalho.index("Natureza da Receita")
        idx_liquido = cabecalho.index("Líquido")
        idx_descricao = cabecalho.index("Descrição")
    except Exception:
        raise Exception("Não foram encontradas as colunas 'Natureza da Receita', 'Líquido' ou 'Descrição' no cabeçalho.")
    dados_extraidos = []
    for linha in linhas[indice_cabecalho + 1:]:
        if all(str(celula).strip() == "" for celula in linha):
            break
        natureza = str(linha[idx_natureza]).strip()
        liquido = str(linha[idx_liquido]).strip()
        descricao = str(linha[idx_descricao]).strip()
        categoria = descricao.lower()
        if natureza.lower() == "nan" and liquido.lower() == "nan":
            continue
        dados_extraidos.append({
            "Natureza_da_Receita": natureza,
            "liquido": liquido,
            "categoria": categoria,
        })
    banco = os.path.basename(caminho_arquivo).split('.')[0]
    return {"arquivo": caminho_arquivo, "banco": banco, "dados": dados_extraidos}

def processar_pasta_classificacao(caminho_pasta: str) -> list:
    resultados = []
    extensoes_validas = [".xls", ".xlsx"]
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
        codigo = 6112 if banco_lower.endswith("bb") else 4066 if banco_lower.endswith("cef") else None
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
    Lê a aba Planilha1:
      A (0) = data, F (5) = conta, I (8) = valor.
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
        if "Planilha1" not in xl.sheet_names:
            return []
        df = pd.read_excel(caminho, sheet_name="Planilha1", header=None, engine=engine)
    except Exception as e:
        print(f"Erro lendo planilha {caminho_arquivo}: {e}")
        return []

    if df is None or df.empty or df.shape[1] < 9:
        return []

    resultados = []
    for _, row in df.iterrows():
        data_contabil = _parse_data_celula(row.iloc[0])
        if not data_contabil:
            continue
        conta = row.iloc[5]
        valor = row.iloc[8]
        try:
            if pd.isna(conta) or pd.isna(valor):
                continue
        except Exception:
            pass
        try:
            valor_num = float(valor)
        except (TypeError, ValueError):
            continue

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

@app.get("/", response_class=HTMLResponse)
def home():
    html_content = """
    <html>
    <head>
        <meta charset="utf-8">
        <title>API MAB, MCR & Desconto/Renúncia</title>
        <style>
            body {
                margin: 0;
                font-family: Arial, sans-serif;
                display: flex;
                flex-direction: column;
                height: 100vh;
                background-color: #f4f4f4;
            }
            .app-nav {
                background: #1f1f1f;
                padding: 8px 16px;
                display: flex;
                gap: 8px;
                align-items: center;
                flex-shrink: 0;
            }
            .app-nav a {
                color: #ccc;
                text-decoration: none;
                padding: 8px 14px;
                border-radius: 6px;
                font-weight: bold;
                font-size: 14px;
            }
            .app-nav a:hover {
                color: #fff;
                background: #444;
            }
            .app-nav a.active {
                color: #fff;
                background: #ff6600;
            }
            .layout {
                display: flex;
                flex: 1;
                min-height: 0;
            }
            .sidebar {
                width: 250px;
                background-color: #333;
                color: #fff;
                padding: 20px;
                box-sizing: border-box;
                overflow-y: auto;
            }
            .sidebar h1 {
                margin: 0 0 20px 0;
                font-size: 24px;
                border-bottom: 2px solid #ff6600;
                padding-bottom: 10px;
            }
            .sidebar h2 {
                font-size: 18px;
                margin-top: 20px;
                border-bottom: 1px solid #444;
                padding-bottom: 5px;
            }
            .sidebar h3 {
                font-size: 16px;
                margin: 10px 0 5px 0;
            }
            .sidebar a {
                color: #ff6600;
                text-decoration: none;
                display: block;
                margin-bottom: 10px;
            }
            .sidebar a:hover {
                color: #fff;
            }
            .sidebar form {
                margin-bottom: 15px;
            }
            .sidebar label {
                display: block;
                margin-bottom: 5px;
                font-size: 14px;
            }
            .sidebar input[type="number"] {
                width: 100%;
                padding: 5px;
                margin-bottom: 5px;
                box-sizing: border-box;
            }
            .sidebar input[type="submit"] {
                width: 100%;
                padding: 5px;
                background: #ff6600;
                border: none;
                color: #fff;
                cursor: pointer;
            }
            .sidebar input[type="submit"]:hover {
                background: #e65c00;
            }
            .content {
                flex-grow: 1;
                background-color: #fff;
                padding: 20px;
                box-sizing: border-box;
                overflow-y: auto;
                position: relative;
            }
            iframe {
                width: 100%;
                height: 100%;
                border: none;
            }
            .loading-bar {
                display: none;
                position: sticky;
                top: 0;
                z-index: 5;
                align-items: center;
                gap: 10px;
                margin: 0 0 15px 0;
                padding: 10px;
                background: #444;
                border: 1px solid #ff6600;
                border-radius: 5px;
                font-size: 13px;
            }
            .loading-bar.visible {
                display: flex;
            }
            .loading-overlay {
                display: none;
                position: absolute;
                inset: 0;
                background: rgba(255, 255, 255, 0.92);
                z-index: 4;
                align-items: center;
                justify-content: center;
                flex-direction: column;
                gap: 14px;
            }
            .loading-overlay.visible {
                display: flex;
            }
            .spinner {
                width: 18px;
                height: 18px;
                border: 3px solid #666;
                border-top-color: #ff6600;
                border-radius: 50%;
                animation: spin 0.8s linear infinite;
                flex-shrink: 0;
            }
            .spinner-lg {
                width: 42px;
                height: 42px;
                border: 4px solid #ddd;
                border-top-color: #ff6600;
                border-radius: 50%;
                animation: spin 0.8s linear infinite;
            }
            @keyframes spin {
                to { transform: rotate(360deg); }
            }
            .loading-overlay p {
                margin: 0;
                color: #333;
                font-size: 16px;
            }
            .loading-overlay .loading-sub {
                color: #888;
                font-size: 13px;
            }
        </style>
    </head>
    <body>
        <nav class="app-nav">
            <a href="/" class="active">Processamento</a>
            <a href="/aws">AWS / S3</a>
        </nav>
        <div class="layout">
        <div class="sidebar">
            <h1>API Integração</h1>
            <div id="loadingBar" class="loading-bar">
                <div class="spinner"></div>
                <span id="loadingBarText">Processando...</span>
            </div>
            
            <div style="margin-bottom: 15px; padding: 10px; background: #444; border-radius: 5px;">
                <label for="seletor_ano" style="display: block; margin-bottom: 5px; font-weight: bold;">Ano para documentos:</label>
                <select id="seletor_ano" style="width: 100%; padding: 8px; font-size: 16px;">
                    <option value="2024">2024</option>
                    <option value="2025">2025</option>
                    <option value="2026" selected>2026</option>
                    <option value="2027">2027</option>
                </select>
                <p style="font-size: 11px; margin-top: 5px; color: #aaa;">Usado em datas e nomes de arquivos</p>
            </div>
            <script>
                var loadingTimer = null;
                var loadingStartedAt = 0;

                function atualizarAno() {
                    var v = document.getElementById("seletor_ano").value;
                    document.querySelectorAll("input[name=ano]").forEach(function(i) { i.value = v; });
                    var link = document.getElementById("link_processar_deducoes");
                    if (link) link.href = "/processar_deducoes/?ano=" + v;
                }

                function textoAcao(formOuLink) {
                    if (!formOuLink) return "Processando";
                    if (formOuLink.tagName === "A") {
                        return (formOuLink.textContent || "Processando").trim();
                    }
                    var btn = formOuLink.querySelector('input[type="submit"]');
                    return btn && btn.value ? btn.value : "Processando";
                }

                function mostrarCarregamento(acao) {
                    var msg = (acao || "Processando") + "...";
                    document.getElementById("loadingBarText").textContent = msg + " 0s";
                    document.getElementById("loadingOverlayText").textContent = msg;
                    document.getElementById("loadingOverlaySub").textContent = "Aguarde, lendo arquivos da rede";
                    document.getElementById("loadingBar").classList.add("visible");
                    document.getElementById("loadingOverlay").classList.add("visible");
                    document.querySelectorAll('input[type="submit"]').forEach(function(b) { b.disabled = true; });
                    loadingStartedAt = Date.now();
                    if (loadingTimer) clearInterval(loadingTimer);
                    loadingTimer = setInterval(function() {
                        var s = Math.floor((Date.now() - loadingStartedAt) / 1000);
                        document.getElementById("loadingBarText").textContent = msg + " " + s + "s";
                        document.getElementById("loadingOverlaySub").textContent = "Aguarde, lendo arquivos da rede (" + s + "s)";
                    }, 500);
                }

                function ocultarCarregamento() {
                    document.getElementById("loadingBar").classList.remove("visible");
                    document.getElementById("loadingOverlay").classList.remove("visible");
                    document.querySelectorAll('input[type="submit"]').forEach(function(b) { b.disabled = false; });
                    if (loadingTimer) {
                        clearInterval(loadingTimer);
                        loadingTimer = null;
                    }
                }

                function nomeArquivoResposta(resp, fallback) {
                    var disp = resp.headers.get("Content-Disposition") || "";
                    var m = /filename\\*?=(?:UTF-8''|")?([^";]+)/i.exec(disp);
                    if (m) return decodeURIComponent(m[1].replace(/"/g, "").trim());
                    var ct = (resp.headers.get("Content-Type") || "").toLowerCase();
                    if (ct.indexOf("spreadsheet") >= 0 || ct.indexOf("excel") >= 0) return fallback + ".xlsx";
                    if (ct.indexOf("json") >= 0) return fallback + ".json";
                    return fallback;
                }

                function baixarBlob(blob, nome) {
                    var url = URL.createObjectURL(blob);
                    var a = document.createElement("a");
                    a.href = url;
                    a.download = nome;
                    document.body.appendChild(a);
                    a.click();
                    a.remove();
                    setTimeout(function() { URL.revokeObjectURL(url); }, 1000);
                }

                document.getElementById("seletor_ano").addEventListener("change", atualizarAno);
                document.addEventListener("DOMContentLoaded", function() {
                    atualizarAno();
                    var iframe = document.getElementById("content_frame");
                    iframe.addEventListener("load", ocultarCarregamento);

                    document.querySelectorAll('a[target="content_frame"]').forEach(function(link) {
                        link.addEventListener("click", function() {
                            mostrarCarregamento(textoAcao(link));
                        });
                    });

                    document.querySelectorAll(".sidebar form").forEach(function(form) {
                        form.addEventListener("submit", function(e) {
                            if (!form.checkValidity()) return;
                            var acao = textoAcao(form);
                            if ((form.getAttribute("target") || "") === "content_frame") {
                                mostrarCarregamento(acao);
                                return;
                            }
                            e.preventDefault();
                            mostrarCarregamento(acao);
                            var method = (form.getAttribute("method") || "get").toLowerCase();
                            var url = form.getAttribute("action") || "";
                            var opts = { method: method };
                            if (method === "get") {
                                var qs = new URLSearchParams(new FormData(form)).toString();
                                url += (url.indexOf("?") >= 0 ? "&" : "?") + qs;
                            } else {
                                opts.body = new FormData(form);
                            }
                            fetch(url, opts).then(function(resp) {
                                if (!resp.ok) throw new Error("HTTP " + resp.status);
                                return resp.blob().then(function(blob) {
                                    baixarBlob(blob, nomeArquivoResposta(resp, acao.replace(/\\s+/g, "_")));
                                });
                            }).catch(function(err) {
                                alert("Falha ao processar: " + err.message);
                            }).finally(ocultarCarregamento);
                        });
                    });
                });
            </script>

            <h2 style="color:#ff6600;">Pacote Automático</h2>
            <form action="/gerar_pacote_local/" method="get" target="content_frame">
                <input type="hidden" name="ano" value="2026">
                <h3>Gerar pacote e enviar ao S3</h3>
                <p style="font-size: 11px; color: #aaa; margin: 0 0 8px 0;">
                    Informe o DIA ALVO (ex.: 11). Gera 4 arquivos na pasta e envia ao S3:
                    MAB/MCR/DESCONTOS/RENUNCIAS_DD-MM-AAAA.json.
                    Se o dia já existir, sobe como RET1, RET2, etc.
                </p>
                <label for="dia_pacote">Dia alvo:</label>
                <input type="number" name="dia" id="dia_pacote" min="1" max="31" required>
                <label for="mes_pacote">Mês alvo:</label>
                <input type="number" name="mes" id="mes_pacote" min="1" max="12" required>
                <input type="submit" value="Gerar Pacote e Enviar S3" style="background: #ff6600;">
            </form>
            
            <h2>MAB</h2>
            <a href="/processar/" target="content_frame">Processar MAB</a>
            <form action="/filtrar_por_dia_mes/" method="get" target="content_frame">
                <input type="hidden" name="ano" value="2026">
                <h3>Filtrar MAB</h3>
                <label for="dia_mab">Dia:</label>
                <input type="number" name="dia" id="dia_mab" min="1" max="31" required>
                <label for="mes_mab">Mês:</label>
                <input type="number" name="mes" id="mes_mab" min="1" max="12" required>
                <input type="submit" value="Filtrar MAB">
            </form>

            <form action="/download_mab_json/" method="get">
                <input type="hidden" name="ano" value="2026">
                <h3>Baixar MAB JSON</h3>
                <label for="dia_mab_json">Dia:</label>
                <input type="number" name="dia" id="dia_mab_json" min="1" max="31" required>
                <label for="mes_mab_json">Mês:</label>
                <input type="number" name="mes" id="mes_mab_json" min="1" max="12" required>
                <input type="submit" value="Baixar MAB JSON" style="background: #28a745;">
            </form>

            <form action="/gerar_relatorio_mab/" method="get">
                <input type="hidden" name="ano" value="2026">
                <h3>Gerar Relatório MAB</h3>
                <label for="mes_relatorio_mab">Mês:</label>
                <input type="number" name="mes" id="mes_relatorio_mab" min="1" max="12" required>
                <input type="submit" value="Baixar Relatório MAB">
            </form>

            <h2>MCR</h2>
            <a href="/processar_classificacao/" target="content_frame">Processar MCR</a>
            <form action="/filtrar_classificacao_por_dia_mes/" method="get" target="content_frame">
                <input type="hidden" name="ano" value="2026">
                <h3>Filtrar MCR</h3>
                <label for="dia_mcr">Dia:</label>
                <input type="number" name="dia" id="dia_mcr" min="1" max="31" required>
                <label for="mes_mcr">Mês:</label>
                <input type="number" name="mes" id="mes_mcr" min="1" max="12" required>
                <input type="submit" value="Filtrar MCR">
            </form>

            <form action="/download_mcr_json/" method="get">
                <input type="hidden" name="ano" value="2026">
                <h3>Baixar MCR JSON</h3>
                <label for="dia_mcr_json">Dia:</label>
                <input type="number" name="dia" id="dia_mcr_json" min="1" max="31" required>
                <label for="mes_mcr_json">Mês:</label>
                <input type="number" name="mes" id="mes_mcr_json" min="1" max="12" required>
                <input type="submit" value="Baixar MCR JSON" style="background: #28a745;">
            </form>

            <form action="/gerar_relatorio_mcr/" method="get">
                <input type="hidden" name="ano" value="2026">
                <h3>Gerar Relatório MCR</h3>
                <label for="mes_relatorio_mcr">Mês:</label>
                <input type="number" name="mes" id="mes_relatorio_mcr" min="1" max="12" required>
                <input type="submit" value="Baixar Relatório MCR">
            </form>

            <h2>Ajuste MCR x MAB</h2>
            <form action="/ajustar_mcr_por_mab_json/" method="post" enctype="multipart/form-data" target="content_frame">
                <h3>Upload MAB + MCR (mesma data)</h3>
                <label for="mab_json_upload">Arquivo MAB JSON:</label>
                <input type="file" name="mab_json_upload" id="mab_json_upload" accept=".json,application/json" required>
                <label for="mcr_json_upload">Arquivo MCR JSON:</label>
                <input type="file" name="mcr_json_upload" id="mcr_json_upload" accept=".json,application/json" required>
                <p style="font-size: 11px; margin-top: 5px; color: #aaa;">
                    Alerta: os arquivos precisam ter a mesma data_arrecadacao.
                </p>
                <input type="submit" value="Gerar MCR Ajustado" style="background: #6f42c1;">
            </form>
            
            <h2>Desconto/Renúncia</h2>
            <a href="/processar_deducoes/?ano=2026" target="content_frame" id="link_processar_deducoes">Processar Deduções</a>
            <form action="/filtrar_deducoes_por_dia_mes/" method="get" target="content_frame">
                <input type="hidden" name="ano" value="2026">
                <h3>Filtrar Deduções</h3>
                <label for="dia_deducao">Dia:</label>
                <input type="number" name="dia" id="dia_deducao" min="1" max="31" required>
                <label for="mes_deducao">Mês:</label>
                <input type="number" name="mes" id="mes_deducao" min="1" max="12" required>
                <input type="submit" value="Filtrar Deduções">
            </form>

            <form action="/download_deducoes_json/" method="get">
                <input type="hidden" name="ano" value="2026">
                <h3>Baixar Deduções JSON (Completo)</h3>
                <label for="dia_deducao_json">Dia:</label>
                <input type="number" name="dia" id="dia_deducao_json" min="1" max="31" required>
                <label for="mes_deducao_json">Mês:</label>
                <input type="number" name="mes" id="mes_deducao_json" min="1" max="12" required>
                <input type="submit" value="Baixar Deduções JSON" style="background: #28a745;">
            </form>

            <form action="/download_renuncias_json/" method="get">
                <input type="hidden" name="ano" value="2026">
                <h3>Baixar Renúncias JSON (91)</h3>
                <label for="dia_renuncias_json">Dia:</label>
                <input type="number" name="dia" id="dia_renuncias_json" min="1" max="31" required>
                <label for="mes_renuncias_json">Mês:</label>
                <input type="number" name="mes" id="mes_renuncias_json" min="1" max="12" required>
                <input type="submit" value="Baixar Renúncias JSON" style="background: #ffc107; color: #000;">
            </form>

            <form action="/download_descontos_json/" method="get">
                <input type="hidden" name="ano" value="2026">
                <h3>Baixar Descontos JSON (93)</h3>
                <label for="dia_descontos_json">Dia:</label>
                <input type="number" name="dia" id="dia_descontos_json" min="1" max="31" required>
                <label for="mes_descontos_json">Mês:</label>
                <input type="number" name="mes" id="mes_descontos_json" min="1" max="12" required>
                <input type="submit" value="Baixar Descontos JSON" style="background: #dc3545; color: #fff;">
            </form>
        </div>
        <div class="content">
            <div id="loadingOverlay" class="loading-overlay">
                <div class="spinner-lg"></div>
                <p id="loadingOverlayText">Processando...</p>
                <p id="loadingOverlaySub" class="loading-sub">Aguarde, lendo arquivos da rede</p>
            </div>
            <iframe name="content_frame" id="content_frame"></iframe>
        </div>
        </div>
    </body>
    </html>
    """
    return html_content




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

def _montar_payload_mab(dia: int, mes: int, ano: int) -> dict:
    from datetime import datetime
    resultados = []
    for caminho_base in caminhos_base:
        resultados.extend(processar_pasta_completa(caminho_base))
    dia_str = f"{dia:02d}"
    mes_str = f"{mes:02d}"
    resultados_filtrados = [res for res in resultados if res["banco"].endswith(f"{dia_str}{mes_str}")]
    resultados_agregados = agregar_resultados_mab(resultados_filtrados)
    data_arrecadacao_mab = calcular_proximo_dia_util(dia, mes, ano)
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
            try:
                valor = float(registro["liquido"])
            except Exception:
                valor = 0.0
            totais_por_banco[banco] += valor
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


def _enviar_pacote_para_s3(data_alvo: str, payloads: dict) -> dict:
    """Envia os 4 JSONs do pacote para a API AWS, com RET se o dia ja existir."""
    from aws_manager_visivel import AWSManagerVisivel

    mapa_tipo = {
        "mab": "MAB",
        "mcr": "MCR",
        "descontos": "DESCONTOS",
        "renuncias": "RENUNCIAS",
    }
    mgr = AWSManagerVisivel()
    lista = mgr.listar_arquivos_por_data(data_alvo)
    if not lista.get("sucesso"):
        return {
            "sucesso": False,
            "mensagem": lista.get("mensagem") or "Falha ao consultar arquivos na AWS",
            "arquivos": [],
            "erros": [lista.get("mensagem") or "Falha ao consultar arquivos na AWS"],
        }

    por_tipo = {}
    for item in lista.get("tipos") or []:
        por_tipo[str(item.get("tipo") or "").upper()] = item

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
        "mensagem": "Envio ao S3 concluido" if not erros else "Falha em um ou mais envios ao S3",
        "arquivos": envios,
        "erros": erros,
    }


@app.get("/gerar_pacote_local/")
def gerar_pacote_local(
    dia: int = Query(..., description="Dia ALVO da operacao (ex.: 10). MCR/Renuncias/Descontos usam este dia."),
    mes: int = Query(..., description="Mes ALVO da operacao (ex.: 7)."),
    ano: int = Query(2026, description="Ano ALVO da operacao."),
    pasta_saida: str = Query(
        "saida_pacotes",
        description="Pasta base (relativa ao projeto) onde os JSONs serao gravados.",
    ),
    enviar_s3: bool = Query(True, description="Apos gravar o pacote local, envia os 4 JSON para o S3."),
):
    """
    Automatiza o fluxo local e o envio ao S3:

    1) Data alvo = dia/mes/ano informado (ex.: 10/07)
    2) MAB = dia util anterior (ex.: 09/07)  -> data_arrecadacao cai no dia alvo
    3) MCR, Renuncias e Descontos = dia alvo
    4) Ajusta MCR com MAB (corretor)
    5) Grava exatamente 4 arquivos na pasta, todos com a data contabil (dia alvo)
    6) Envia ao S3 com nome TIPO_DD-MM-YYYY.json; se o dia ja existir, usa -RET1, -RET2...
    """
    from datetime import datetime

    dia_mab, mes_mab, ano_mab = calcular_dia_util_anterior_parts(dia, mes, ano)
    data_alvo = f"{dia:02d}/{mes:02d}/{ano}"
    data_mab_filtro = f"{dia_mab:02d}/{mes_mab:02d}/{ano_mab}"
    sufixo_data = f"{dia:02d}_{mes:02d}_{ano}"

    pasta_dia = os.path.join(
        os.getcwd(),
        pasta_saida,
        f"{ano}-{mes:02d}-{dia:02d}",
    )
    os.makedirs(pasta_dia, exist_ok=True)

    erros = []
    arquivos = {}

    mab_json = None
    mcr_json = None
    renuncias_json = None
    descontos_json = None
    mcr_ajustado = None
    conferencia = None

    try:
        mab_json = _montar_payload_mab(dia_mab, mes_mab, ano_mab)
    except Exception as e:
        erros.append(f"MAB: {e}")

    try:
        mcr_json = _montar_payload_mcr(dia, mes, ano)
    except Exception as e:
        erros.append(f"MCR: {e}")

    try:
        renuncias_json = _montar_payload_renuncias(dia, mes, ano)
    except Exception as e:
        erros.append(f"Renuncias: {e}")

    try:
        descontos_json = _montar_payload_descontos(dia, mes, ano)
    except Exception as e:
        erros.append(f"Descontos: {e}")

    if mab_json is not None and mcr_json is not None:
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

    # Grava somente os 4 arquivos finais (nomenclatura unificada na data contabil)
    nomes_finais = {
        "mab": f"mab_dados_{sufixo_data}.json",
        "mcr": f"mcr_dados_{sufixo_data}.json",
        "renuncias": f"renuncias_dados_{sufixo_data}.json",
        "descontos": f"descontos_dados_{sufixo_data}.json",
    }

    # Remove arquivos antigos da pasta (ex.: mcr_ajustado_*, relatorio_*, nomes com data do filtro MAB)
    for item in os.listdir(pasta_dia):
        if item.lower().endswith(".json"):
            try:
                os.remove(os.path.join(pasta_dia, item))
            except Exception:
                pass

    if mab_json is not None:
        try:
            arquivos["mab"] = _salvar_json(pasta_dia, nomes_finais["mab"], mab_json)
        except Exception as e:
            erros.append(f"Salvar MAB: {e}")

    if mcr_ajustado is not None:
        try:
            arquivos["mcr"] = _salvar_json(pasta_dia, nomes_finais["mcr"], mcr_ajustado)
        except Exception as e:
            erros.append(f"Salvar MCR: {e}")
    elif mcr_json is not None:
        erros.append("MCR ajustado indisponivel; arquivo mcr_dados nao foi gravado.")

    if renuncias_json is not None:
        try:
            arquivos["renuncias"] = _salvar_json(pasta_dia, nomes_finais["renuncias"], renuncias_json)
        except Exception as e:
            erros.append(f"Salvar Renuncias: {e}")

    if descontos_json is not None:
        try:
            arquivos["descontos"] = _salvar_json(pasta_dia, nomes_finais["descontos"], descontos_json)
        except Exception as e:
            erros.append(f"Salvar Descontos: {e}")

    envio_s3 = None
    if enviar_s3:
        try:
            envio_s3 = _enviar_pacote_para_s3(
                data_alvo,
                {
                    "mab": mab_json if "mab" in arquivos else None,
                    "mcr": mcr_ajustado if "mcr" in arquivos else None,
                    "renuncias": renuncias_json if "renuncias" in arquivos else None,
                    "descontos": descontos_json if "descontos" in arquivos else None,
                },
            )
            if envio_s3.get("erros"):
                erros.extend([f"S3 {e}" for e in envio_s3["erros"]])
        except Exception as e:
            envio_s3 = {"sucesso": False, "mensagem": str(e), "arquivos": [], "erros": [str(e)]}
            erros.append(f"S3: {e}")

    relatorio = {
        "gerado_em": datetime.now().isoformat(),
        "data_alvo": data_alvo,
        "data_mab_filtro": data_mab_filtro,
        "nomenclatura": nomes_finais,
        "regra": {
            "mab": "conteudo do dia util anterior; nome do arquivo usa data contabil (dia alvo)",
            "mcr": "conteudo ajustado com MAB; nome mcr_dados_{data_alvo}",
            "renuncias_descontos": "dia alvo",
            "s3": "TIPO_DD-MM-YYYY.json; se o dia ja existir, TIPO_DD-MM-YYYY-RETN.json",
        },
        "contagens": {
            "mab": (mab_json or {}).get("total_registros"),
            "mcr": (mcr_ajustado or {}).get("total_registros"),
            "renuncias": (renuncias_json or {}).get("total_registros"),
            "descontos": (descontos_json or {}).get("total_registros"),
        },
        "conferencia_mab_mcr": conferencia,
        "arquivos": arquivos,
        "pasta_saida": pasta_dia,
        "envio_s3": envio_s3,
        "erros": erros,
        "sucesso": len(erros) == 0 and len(arquivos) == 4,
    }

    return JSONResponse(content=relatorio)


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

