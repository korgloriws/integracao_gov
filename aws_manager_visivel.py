import requests
import json
import os
import re
from datetime import datetime
from typing import Dict, List, Optional, Any
import hashlib
from urllib.parse import quote
import io
import xml.etree.ElementTree as ET
from carregar_env import carregar_env

carregar_env()

class AWSManagerVisivel:
    def __init__(self, api_key: str = None, banco_api_key: str = None):
        carregar_env()
        self.AWS_API_URL = os.getenv(
            "API_URL",
            "https://v60yr1ma4f.execute-api.sa-east-1.amazonaws.com/prod/upload-arquivos",
        )
        # S3 / upload
        self.api_key = (api_key or os.getenv("AWS_API_KEY") or "").strip()
        # API Banco / listar-arquivos — se vazio, reutiliza a chave S3
        if banco_api_key is not None:
            self.banco_api_key = str(banco_api_key).strip()
        else:
            self.banco_api_key = (os.getenv("BANCO_API_KEY") or "").strip() or self.api_key
        self.BANCO_API_URL = (
            os.getenv("BANCO_API_URL")
            or f"{self.AWS_API_URL.rsplit('/', 1)[0]}/listar-arquivos"
        ).strip()

        self.headers = {"Content-Type": "application/json"}
        self.headers_get = {"Accept": "application/json"}
        self.headers_banco = {"Accept": "application/json"}
        if self.api_key:
            self.headers["x-api-key"] = self.api_key
            self.headers_get["x-api-key"] = self.api_key
        if self.banco_api_key:
            self.headers_banco["x-api-key"] = self.banco_api_key

    def _api_base_prod(self) -> str:
        return self.AWS_API_URL.rsplit("/", 1)[0]

    @property
    def LISTAR_API_URL(self) -> str:
        return self.BANCO_API_URL or f"{self._api_base_prod()}/listar-arquivos"

    def listar_arquivos_por_data(self, data: str) -> Dict[str, Any]:
        """GET API Banco /listar-arquivos?data=dd/mm/aaaa (usa BANCO_API_KEY)."""
        try:
            data_param = str(data or "").strip()
            if not data_param:
                return {"sucesso": False, "mensagem": "Informe a data no formato dd/mm/aaaa"}
            if not self.banco_api_key:
                return {
                    "sucesso": False,
                    "mensagem": "BANCO_API_KEY vazia. Preencha no .env ou digite a senha na tela.",
                }

            response = requests.get(
                self.LISTAR_API_URL,
                headers=self.headers_banco,
                params={"data": data_param},
                timeout=20,
            )
            if response.status_code != 200:
                return {
                    "sucesso": False,
                    "status_code": response.status_code,
                    "mensagem": (response.text or f"Erro HTTP {response.status_code}")[:1000],
                }

            dados = response.json()
            tipos = dados.get("tipos", []) if isinstance(dados, dict) else []
            versoes = []
            for item in tipos:
                n = 0
                try:
                    n = int(item.get("retificacao") if item.get("retificacao") is not None else 0)
                except (TypeError, ValueError):
                    n = 0
                nome = str(item.get("file_name") or "")
                match_ret = re.search(r"-RET(\d+)", nome, re.IGNORECASE)
                if match_ret:
                    n = max(n, int(match_ret.group(1)))
                if not item.get("presente"):
                    rotulo = "ausente"
                elif n <= 0:
                    rotulo = "original"
                else:
                    rotulo = f"RET{n}"
                versoes.append({
                    "tipo": item.get("tipo"),
                    "obrigatorio": item.get("obrigatorio"),
                    "presente": bool(item.get("presente")),
                    "file_name": nome or None,
                    "status": item.get("status"),
                    "created_at": item.get("created_at"),
                    "retificacao": n,
                    "versao": rotulo,
                })

            historico_local = []
            data_ref = str(dados.get("data", data_param) if isinstance(dados, dict) else data_param)
            cache = self._ler_cache()
            for pasta in (cache.get("pastas") or {}).values():
                for arq in pasta.get("arquivos") or []:
                    filtro = str(arq.get("data_filtro") or arq.get("dados", {}).get("data_filtro") or "")
                    if filtro.replace("-", "/") != data_ref.replace("-", "/"):
                        continue
                    nome = str(arq.get("nome_arquivo") or "")
                    n = 0
                    match_ret = re.search(r"-RET(\d+)", nome, re.IGNORECASE)
                    if match_ret:
                        n = int(match_ret.group(1))
                    historico_local.append({
                        "tipo": arq.get("tipo") or pasta.get("nome"),
                        "file_name": nome,
                        "versao": "original" if n <= 0 else f"RET{n}",
                        "retificacao": n,
                        "origem": "indice_local",
                        "data_upload": arq.get("data_upload"),
                        "total_registros": arq.get("total_registros"),
                    })

            return {
                "sucesso": True,
                "status_code": response.status_code,
                "data": data_ref,
                "tipos": tipos,
                "versoes": versoes,
                "historico_local": historico_local,
                "total": len(tipos),
                "presentes": sum(1 for t in tipos if t.get("presente")),
                "retificados": sum(1 for v in versoes if v.get("retificacao", 0) > 0),
                "dados": dados,
            }
        except Exception as e:
            return {"sucesso": False, "mensagem": f"Erro de conexão: {str(e)}"}

    def _estrutura_vazia_padrao(self) -> Dict[str, Any]:
        return {
            "pastas": {
                "MAB": {"nome": "MAB", "cor": "#ff6600", "cor_escuro": "#dc3545", "arquivos": []},
                "MCR": {"nome": "MCR", "cor": "#28a745", "cor_escuro": "#28a745", "arquivos": []},
                "DESCONTOS": {"nome": "Descontos", "cor": "#17a2b8", "cor_escuro": "#17a2b8", "arquivos": []},
                "RENUNCIAS": {"nome": "Renuncias", "cor": "#6f42c1", "cor_escuro": "#6f42c1", "arquivos": []},
                "OUTROS": {"nome": "OUTROS", "cor": "#6c757d", "cor_escuro": "#6c757d", "arquivos": []}
            },
            "arquivos_sem_pasta": [],
            "metadata": {
                "ultima_atualizacao": datetime.now().isoformat(),
                "total_arquivos": 0,
                "versao_sistema": "2.0-visivel"
            }
        }

    def _cache_path(self) -> str:
        return os.getenv(
            "AWS_CACHE_INDEX",
            os.path.join(os.getcwd(), "aws_cache_index.json"),
        )

    def _ler_cache(self) -> Dict[str, Any]:
        try:
            caminho = self._cache_path()
            if os.path.exists(caminho):
                with open(caminho, "r", encoding="utf-8") as f:
                    dados = json.load(f)
                # Sanitizar estrutura mínima
                if not isinstance(dados, dict) or "pastas" not in dados:
                    return self._estrutura_vazia_padrao()
                return dados
            return self._estrutura_vazia_padrao()
        except Exception:
            return self._estrutura_vazia_padrao()

    def _salvar_cache(self, estrutura: Dict[str, Any]) -> None:
        try:
            caminho = self._cache_path()
            with open(caminho, "w", encoding="utf-8") as f:
                json.dump(estrutura, f, ensure_ascii=False, indent=2)
        except Exception:
            pass
    
    def testar_conexao(self) -> Dict[str, Any]:
        """Valida a chave S3 (AWS_API_KEY) — upload / API_URL."""
        try:
            if not self.api_key:
                return {
                    "sucesso": False,
                    "status_code": None,
                    "mensagem": "AWS_API_KEY vazia no .env. Preencha a chave S3 e reinicie o servidor.",
                    "dados": None,
                }
            # upload-arquivos é POST; GET costuma devolver 403 Missing Authentication Token
            # mesmo com chave válida. Testamos com a mesma chave via listar (ou aceitamos esse 403).
            resp = requests.get(self.AWS_API_URL, headers=self.headers_get, timeout=12)
            texto = (resp.text or "").strip()
            if resp.status_code in (200, 201, 202, 400, 404, 405):
                return {
                    "sucesso": True,
                    "status_code": resp.status_code,
                    "mensagem": "S3/API_URL acessível (chave AWS_API_KEY presente)",
                    "dados": None,
                }
            if resp.status_code == 403 and "Missing Authentication Token" in texto:
                return {
                    "sucesso": True,
                    "status_code": resp.status_code,
                    "mensagem": "S3 ok (AWS_API_KEY presente; endpoint de upload é POST)",
                    "dados": None,
                }
            if resp.status_code == 403:
                return {
                    "sucesso": False,
                    "status_code": 403,
                    "mensagem": "Erro de autenticação S3 (AWS_API_KEY)",
                    "dados": texto[:500],
                }
            return {
                "sucesso": False,
                "status_code": resp.status_code,
                "mensagem": f"S3 respondeu HTTP {resp.status_code}",
                "dados": texto[:500],
            }
        except Exception as e:
            return {
                "sucesso": False,
                "status_code": None,
                "mensagem": f"Erro de conexão S3: {str(e)}",
                "dados": None,
            }

    def testar_conexao_banco(self) -> Dict[str, Any]:
        """Valida BANCO_API_KEY via GET listar-arquivos."""
        try:
            if not self.banco_api_key:
                return {
                    "sucesso": False,
                    "status_code": None,
                    "mensagem": "BANCO_API_KEY vazia. Preencha no .env ou digite na tela.",
                    "dados": None,
                }
            hoje = datetime.now().strftime("%d/%m/%Y")
            resultado = self.listar_arquivos_por_data(hoje)
            status = resultado.get("status_code")
            if resultado.get("sucesso"):
                return {
                    "sucesso": True,
                    "status_code": status,
                    "mensagem": "API Banco acessível (listar-arquivos)",
                    "dados": None,
                }
            if status == 403:
                return {
                    "sucesso": False,
                    "status_code": status,
                    "mensagem": f"Erro de autenticação API Banco: {status}",
                    "dados": resultado.get("mensagem"),
                }
            return {
                "sucesso": False,
                "status_code": status,
                "mensagem": resultado.get("mensagem") or f"Erro HTTP {status}",
                "dados": None,
            }
        except Exception as e:
            return {
                "sucesso": False,
                "status_code": None,
                "mensagem": f"Erro de conexão API Banco: {str(e)}",
                "dados": None,
            }
    
    def _gerar_id_arquivo(self, dados: Dict[str, Any]) -> str:
        """Gera um ID único para o arquivo. Usa apenas data_filtro (não data_arrecadacao)
        para evitar que o mesmo arquivo gere dois IDs e apareça duplicado."""
        tipo = dados.get("tipo", "desconhecido")
        data_processamento = dados.get("data_processamento", "")
        data_filtro = dados.get("data_filtro", "")
        
        id_string = f"{tipo}_{data_filtro}_{data_processamento}"
        return hashlib.md5(id_string.encode()).hexdigest()[:12]
    
    def _gerar_nome_arquivo(self, dados: Dict[str, Any]) -> str:
        """Gera um nome de arquivo organizado. Usa apenas data_filtro (não data_arrecadacao)
        para consistência com o ID e evitar duplicatas no S3."""
        tipo = dados.get("tipo", "arquivo").upper()
        data_filtro = dados.get("data_filtro", "sem_data")
        data_processamento = dados.get("data_processamento", "")
        
        # Formatar data de processamento
        try:
            dt = datetime.fromisoformat(data_processamento.replace('Z', '+00:00'))
            data_formatada = dt.strftime("%Y%m%d_%H%M%S")
        except:
            data_formatada = "sem_data"
   
        data_filtro_seguro = str(data_filtro).replace('/', '-').replace('\\', '-').replace(':', '-').replace(' ', '_')
        tipo_seguro = str(tipo).replace('/', '-').replace('\\', '-').replace(':', '-').replace(' ', '_')

        return f"{tipo_seguro}_{data_filtro_seguro}_{data_formatada}.json"
    
    def enviar_dados_visivel(self, dados: Dict[str, Any]) -> Dict[str, Any]:
       
        try:
            if "data_processamento" not in dados:
                dados["data_processamento"] = datetime.now().isoformat()
            

            arquivo_id = self._gerar_id_arquivo(dados)
            nome_arquivo = self._gerar_nome_arquivo(dados)
            
            
            tipo = dados.get("tipo", "").upper()
            pasta_destino = "MAB"  # Default
            
            if tipo == "MCR":
                pasta_destino = "MCR"
            elif tipo == "MAB":
                pasta_destino = "MAB"
            elif tipo == "DESCONTOS":
                pasta_destino = "DESCONTOS"
            elif tipo == "RENUNCIAS":
                pasta_destino = "RENUNCIAS"
            else:
                pasta_destino = "OUTROS"
            

            remote_url = self.AWS_API_URL

            arquivo_visivel = {
                "arquivo_id": arquivo_id,
                "nome_arquivo": nome_arquivo,
                "pasta": pasta_destino,
                "tipo": tipo,
                "data_filtro": dados.get("data_filtro"),
                "data_processamento": dados.get("data_processamento"),
                "data_upload": datetime.now().isoformat(),
                "total_registros": len(dados.get("resultados", [])),
                "tamanho_bytes": len(json.dumps(dados)),
                "status": "ativo",
                "dados": dados,
                "remote_key_encoded": None,
                "remote_url": remote_url
            }
            

            estrutura = self.obter_estrutura_pastas()
            
            if not estrutura["sucesso"]:
                return estrutura
            
            pastas = estrutura["pastas"]
            arquivos_sem_pasta = estrutura["arquivos_sem_pasta"]
            
            # Evitar duplicata: remover entrada existente com o mesmo arquivo_id na pasta
            def remover_por_id(lista_arquivos, aid):
                return [a for a in lista_arquivos if a.get("arquivo_id") != aid]
            if pasta_destino in pastas:
                pastas[pasta_destino]["arquivos"] = remover_por_id(pastas[pasta_destino]["arquivos"], arquivo_id)
                pastas[pasta_destino]["arquivos"].append(arquivo_visivel)
            else:
                arquivos_sem_pasta = remover_por_id(arquivos_sem_pasta, arquivo_id)
                arquivos_sem_pasta.append(arquivo_visivel)
            

            nova_estrutura = {
                "pastas": pastas,
                "arquivos_sem_pasta": arquivos_sem_pasta,
                "metadata": {
                    "ultima_atualizacao": datetime.now().isoformat(),
                    "total_arquivos": sum(len(pasta["arquivos"]) for pasta in pastas.values()) + len(arquivos_sem_pasta),
                    "versao_sistema": "2.0-visivel"
                }
            }
           
            resultado_upload_individual = self._upload_arquivo_individual(arquivo_visivel)

       
            resultado_salvamento = self._salvar_estrutura_pastas(nova_estrutura)
            
            if resultado_salvamento["sucesso"]:
                return {
                    "sucesso": True,
                    "mensagem": f"Arquivo '{nome_arquivo}' enviado com sucesso para pasta '{pasta_destino}'",
                    "arquivo_id": arquivo_id,
                    "nome_arquivo": nome_arquivo,
                    "pasta_destino": pasta_destino,
                    "status_code": 200,
                    "upload_individual": resultado_upload_individual
                }
            else:
                return resultado_salvamento
                
        except Exception as e:
            return {
                "sucesso": False,
                "mensagem": f"Erro de conexão: {str(e)}",
                "status_code": None
            }
    
    def obter_estrutura_pastas(self) -> Dict[str, Any]:
       
        try:
            dados_cache = self._ler_cache()
            return {
                "sucesso": True,
                "pastas": dados_cache.get("pastas", {}),
                "arquivos_sem_pasta": dados_cache.get("arquivos_sem_pasta", [])
            }
        except Exception as e:
            return {"sucesso": False, "mensagem": f"Erro ao carregar cache local: {str(e)}"}
    
    def _migrar_dados_antigos(self, dados_antigos) -> Dict[str, Any]:
       
        try:
            pastas = {
                "MAB": {"nome": "MAB", "cor": "#ff6600", "cor_escuro": "#dc3545", "arquivos": []},
                "MCR": {"nome": "MCR", "cor": "#28a745", "cor_escuro": "#28a745", "arquivos": []},
                "DESCONTOS": {"nome": "Descontos", "cor": "#17a2b8", "cor_escuro": "#17a2b8", "arquivos": []},
                "RENUNCIAS": {"nome": "Renuncias", "cor": "#6f42c1", "cor_escuro": "#6f42c1", "arquivos": []},
                "OUTROS": {"nome": "OUTROS", "cor": "#6c757d", "cor_escuro": "#6c757d", "arquivos": []}
            }
            arquivos_sem_pasta = []
            

            if isinstance(dados_antigos, list):
                for i, item in enumerate(dados_antigos):
                    if isinstance(item, dict):
                        arquivo_visivel = self._criar_arquivo_visivel(item, i)
                        tipo = item.get("tipo", "").upper()
                        
                        if tipo == "MAB":
                            pastas["MAB"]["arquivos"].append(arquivo_visivel)
                        elif tipo == "MCR":
                            pastas["MCR"]["arquivos"].append(arquivo_visivel)
                        elif tipo == "DESCONTOS":
                            pastas["DESCONTOS"]["arquivos"].append(arquivo_visivel)
                        elif tipo == "RENUNCIAS":
                            pastas["RENUNCIAS"]["arquivos"].append(arquivo_visivel)
                        else:
                            pastas["OUTROS"]["arquivos"].append(arquivo_visivel)
            
            elif isinstance(dados_antigos, dict):
                arquivo_visivel = self._criar_arquivo_visivel(dados_antigos, 0)
                tipo = dados_antigos.get("tipo", "").upper()
                
                if tipo == "MAB":
                    pastas["MAB"]["arquivos"].append(arquivo_visivel)
                elif tipo == "MCR":
                    pastas["MCR"]["arquivos"].append(arquivo_visivel)
                elif tipo == "DESCONTOS":
                    pastas["DESCONTOS"]["arquivos"].append(arquivo_visivel)
                elif tipo == "RENUNCIAS":
                    pastas["RENUNCIAS"]["arquivos"].append(arquivo_visivel)
                else:
                    pastas["OUTROS"]["arquivos"].append(arquivo_visivel)
            

            nova_estrutura = {
                "pastas": pastas,
                "arquivos_sem_pasta": arquivos_sem_pasta,
                "metadata": {
                    "ultima_atualizacao": datetime.now().isoformat(),
                    "total_arquivos": sum(len(pasta["arquivos"]) for pasta in pastas.values()) + len(arquivos_sem_pasta),
                    "versao_sistema": "2.0-visivel",
                    "migracao_realizada": True
                }
            }
            
            self._salvar_estrutura_pastas(nova_estrutura)
            
            return {
                "sucesso": True,
                "pastas": pastas,
                "arquivos_sem_pasta": arquivos_sem_pasta
            }
            
        except Exception as e:
            return {
                "sucesso": False,
                "mensagem": f"Erro na migração: {str(e)}"
            }
    
    def _criar_arquivo_visivel(self, dados: Dict[str, Any], indice: int) -> Dict[str, Any]:
       
        arquivo_id = self._gerar_id_arquivo(dados)
        nome_arquivo = self._gerar_nome_arquivo(dados)
        
        return {
            "arquivo_id": arquivo_id,
            "nome_arquivo": nome_arquivo,
            "pasta": dados.get("tipo", "OUTROS").upper(),
            "tipo": dados.get("tipo", "desconhecido"),
            "data_filtro": dados.get("data_filtro"),
            "data_processamento": dados.get("data_processamento"),
            "data_upload": datetime.now().isoformat(),
            "total_registros": len(dados.get("resultados", [])),
            "tamanho_bytes": len(json.dumps(dados)),
            "status": "ativo",
            "indice_original": indice,
            "dados": dados
        }
    
    def _upload_arquivo_individual(self, arquivo_visivel: Dict[str, Any]) -> Dict[str, Any]:

        try:
            tipo = (arquivo_visivel.get("tipo") or "OUTROS").upper()
            nome_arquivo = arquivo_visivel.get("nome_arquivo") or f"{tipo}_{arquivo_visivel.get('arquivo_id','semid')}.json"
            dados = arquivo_visivel.get("dados", {}) or {}
            if "data_arrecadacao" not in dados:
                dados["data_arrecadacao"] = str(dados.get("data_filtro", datetime.now().strftime("%d-%m-%Y"))).replace("/", "-")
            payload = {"file_name": nome_arquivo, "content": dados}
            resp = requests.post(self.AWS_API_URL, json=payload, headers=self.headers, timeout=15)
            sucesso = resp.status_code in [200, 201, 202]
            return {
                "sucesso": sucesso,
                "status_code": resp.status_code,
                "mensagem": "Upload realizado" if sucesso else f"Falha no upload: {resp.status_code}",
                "url": self.AWS_API_URL,
                "body": (resp.text or "").strip()[:1000]
            }
        except Exception as e:
            return {
                "sucesso": False,
                "status_code": None,
                "mensagem": f"Erro de conexão no upload individual: {str(e)}"
            }

    def baixar_arquivo_por_tipo_nome(self, tipo: str, nome_arquivo: str) -> Dict[str, Any]:
        """Tenta obter o conteudo remoto; se a API nao tiver GET de download, retorna metadados da listagem."""
        tipo_u = str(tipo or "").upper().strip()
        nome = str(nome_arquivo or "").strip()
        if not tipo_u or not nome:
            return {"sucesso": False, "mensagem": "Informe tipo e nome do arquivo."}

        # Alguns backends expõem o conteúdo no próprio listar-arquivos.
        # Extrai a data do nome: TIPO_DD-MM-YYYY.json ou TIPO_DD-MM-YYYY-RETn.json
        data_match = re.search(r"(\d{2})-(\d{2})-(\d{4})", nome)
        if data_match:
            data_param = f"{data_match.group(1)}/{data_match.group(2)}/{data_match.group(3)}"
            lista = self.listar_arquivos_por_data(data_param)
            if lista.get("sucesso"):
                for item in lista.get("tipos") or []:
                    if str(item.get("file_name") or "") != nome:
                        continue
                    conteudo = (
                        item.get("content")
                        or item.get("conteudo")
                        or item.get("dados")
                        or item.get("body")
                    )
                    if conteudo is not None:
                        return {
                            "sucesso": True,
                            "fonte": "listar-arquivos",
                            "tipo": tipo_u,
                            "file_name": nome,
                            "conteudo": conteudo,
                            "metadados": item,
                        }
                    return {
                        "sucesso": True,
                        "fonte": "listar-arquivos",
                        "tipo": tipo_u,
                        "file_name": nome,
                        "conteudo": None,
                        "metadados": item,
                        "mensagem": (
                            "Arquivo encontrado na API remota, mas o endpoint listar-arquivos "
                            "não devolve o conteúdo interno. Use o índice local ou a pasta saida_pacotes."
                        ),
                    }

        return {
            "sucesso": False,
            "mensagem": (
                "Download do corpo do arquivo não está disponível nesta API "
                "(apenas listagem e upload). Consulte o índice local ou saida_pacotes."
            ),
            "tipo": tipo_u,
            "file_name": nome,
        }

    def listar_pasta_remota(self, tipo: str, data: Optional[str] = None) -> Dict[str, Any]:
        if not data:
            return {
                "sucesso": False,
                "mensagem": "Informe a data (dd/mm/aaaa) para consultar arquivos na API.",
            }

        resultado = self.listar_arquivos_por_data(data)
        if not resultado.get("sucesso"):
            return resultado

        tipo_upper = (tipo or "").upper()
        tipos = resultado.get("tipos", [])
        filtrados = [t for t in tipos if str(t.get("tipo", "")).upper() == tipo_upper]
        arquivos = []
        for item in filtrados:
            if item.get("presente"):
                arquivos.append({
                    "tipo": item.get("tipo"),
                    "nome": item.get("file_name"),
                    "status": item.get("status"),
                    "created_at": item.get("created_at"),
                    "retificacao": item.get("retificacao"),
                    "remote_url": self.AWS_API_URL,
                })

        return {
            "sucesso": True,
            "tipo": tipo_upper,
            "data": resultado.get("data"),
            "arquivos": arquivos,
            "total": len(arquivos),
            "resumo_tipo": filtrados[0] if filtrados else None,
            "dados_completos": resultado.get("dados"),
        }

    def adicionar_entrada_indice(self, tipo: str, nome_arquivo: str, dados: Dict[str, Any]) -> Dict[str, Any]:
        """Adiciona entrada ao índice (para aparecer na interface) sem fazer upload.
        Usado após put_arquivo_remoto: o arquivo já foi enviado com o nome curto; só registramos no índice."""
        try:
            if isinstance(dados, dict) and "data_processamento" not in dados:
                dados = dict(dados)
                dados["data_processamento"] = datetime.now().isoformat()
            elif not isinstance(dados, dict):
                dados = {"resultados": [], "data_processamento": datetime.now().isoformat()}
            tipo_upper = (tipo or "OUTROS").upper()
            arquivo_id = self._gerar_id_arquivo(dados)
            pasta_destino = "MAB"
            if tipo_upper == "MCR":
                pasta_destino = "MCR"
            elif tipo_upper == "MAB":
                pasta_destino = "MAB"
            elif tipo_upper == "DESCONTOS":
                pasta_destino = "DESCONTOS"
            elif tipo_upper == "RENUNCIAS":
                pasta_destino = "RENUNCIAS"
            else:
                pasta_destino = "OUTROS"
            remote_url = self.AWS_API_URL
            arquivo_visivel = {
                "arquivo_id": arquivo_id,
                "nome_arquivo": nome_arquivo,
                "pasta": pasta_destino,
                "tipo": tipo_upper,
                "data_filtro": dados.get("data_filtro"),
                "data_processamento": dados.get("data_processamento"),
                "data_upload": datetime.now().isoformat(),
                "total_registros": len(dados.get("resultados", [])),
                "tamanho_bytes": len(json.dumps(dados)),
                "status": "ativo",
                "dados": dados,
                "remote_key_encoded": None,
                "remote_url": remote_url
            }
            estrutura = self.obter_estrutura_pastas()
            if not estrutura["sucesso"]:
                return estrutura
            pastas = estrutura["pastas"]
            arquivos_sem_pasta = estrutura["arquivos_sem_pasta"]

            def remover_por_id(lista_arquivos, aid):
                return [a for a in lista_arquivos if a.get("arquivo_id") != aid]
            if pasta_destino in pastas:
                pastas[pasta_destino]["arquivos"] = remover_por_id(pastas[pasta_destino]["arquivos"], arquivo_id)
                pastas[pasta_destino]["arquivos"].append(arquivo_visivel)
            else:
                arquivos_sem_pasta = remover_por_id(arquivos_sem_pasta, arquivo_id)
                arquivos_sem_pasta.append(arquivo_visivel)
            nova_estrutura = {
                "pastas": pastas,
                "arquivos_sem_pasta": arquivos_sem_pasta,
                "metadata": {
                    "ultima_atualizacao": datetime.now().isoformat(),
                    "total_arquivos": sum(len(p["arquivos"]) for p in pastas.values()) + len(arquivos_sem_pasta),
                    "versao_sistema": "2.0-visivel"
                }
            }
            resultado_salvamento = self._salvar_estrutura_pastas(nova_estrutura)
            if resultado_salvamento["sucesso"]:
                return {
                    "sucesso": True,
                    "mensagem": f"Entrada '{nome_arquivo}' adicionada ao índice",
                    "arquivo_id": arquivo_id,
                    "nome_arquivo": nome_arquivo,
                    "pasta_destino": pasta_destino
                }
            return resultado_salvamento
        except Exception as e:
            return {"sucesso": False, "mensagem": f"Erro ao adicionar ao índice: {str(e)}"}

    def put_arquivo_remoto(self, tipo: str, nome_arquivo: str, dados: Any) -> Dict[str, Any]:
        """Upload remoto via endpoint unico /upload-arquivos."""
        try:
            if isinstance(dados, dict):
                body_obj = dados
            elif isinstance(dados, list):
                body_obj = {"resultados": dados}
            else:
                try:
                    parsed = json.loads(str(dados))
                    body_obj = parsed if isinstance(parsed, dict) else {"resultados": parsed}
                except Exception:
                    body_obj = {"conteudo": str(dados)}
            if "data_arrecadacao" not in body_obj:
                body_obj["data_arrecadacao"] = body_obj.get("data_filtro") or datetime.now().strftime("%d/%m/%Y")
            if isinstance(body_obj.get("data_arrecadacao"), str):
                body_obj["tipo"] = (tipo or body_obj.get("tipo") or "OUTROS").upper()
            payload = {"file_name": nome_arquivo, "content": body_obj}
            resp = requests.post(self.AWS_API_URL, headers=self.headers, json=payload, timeout=20)
            sucesso = resp.status_code in [200, 201, 202]
            return {"sucesso": sucesso, "status_code": resp.status_code, "url": self.AWS_API_URL,
                    "mensagem": "Upload remoto realizado" if sucesso else f"Falha: {resp.status_code}",
                    "body": (resp.text or "").strip()[:1000]}
        except Exception as e:
            return {"sucesso": False, "mensagem": f"Erro de conexão: {str(e)}"}

    def _salvar_estrutura_pastas(self, estrutura: Dict[str, Any]) -> Dict[str, Any]:
       
        try:

            self._salvar_cache(estrutura)

            return {
                "sucesso": True,
                "mensagem": "Estrutura salva apenas em cache local."
            }
        except Exception as e:
            return {
                "sucesso": False,
                "mensagem": f"Erro de conexão: {str(e)}"
            }
    
    def listar_arquivos_por_pasta(self) -> Dict[str, Any]:

        try:
            estrutura_resultado = self.obter_estrutura_pastas()
            
            if not estrutura_resultado["sucesso"]:
                return estrutura_resultado
            
            pastas = estrutura_resultado["pastas"]
            arquivos_sem_pasta = estrutura_resultado["arquivos_sem_pasta"]
            

            resultado_pastas = {}
            for nome_pasta, pasta in pastas.items():
                arquivos_processados = []
                
                for arquivo in pasta["arquivos"]:
                    
                    nome_arq = arquivo.get("nome_arquivo", "")
                    remote_key_encoded = arquivo.get("remote_key_encoded")
                    remote_url = arquivo.get("remote_url") or self.AWS_API_URL

                    arquivos_processados.append({
                        "id": arquivo.get("arquivo_id", ""),
                        "nome": nome_arq,
                        "tipo": arquivo.get("tipo", ""),
                        "data_processamento": arquivo.get("data_processamento", ""),
                        "data_filtro": arquivo.get("data_filtro", ""),
                        "total_registros": arquivo.get("total_registros", 0),
                        "tamanho": arquivo.get("tamanho_bytes", 0),
                        "dados": arquivo.get("dados", {}),
                        "remote_url": remote_url,
                        "remote_key_encoded": remote_key_encoded
                    })
                
                resultado_pastas[nome_pasta] = {
                    "nome": pasta["nome"],
                    "cor": pasta["cor"],
                    "arquivos": arquivos_processados,
                    "total_arquivos": len(arquivos_processados)
                }
            
         
            arquivos_sem_pasta_processados = []
            for arquivo in arquivos_sem_pasta:
                arquivos_sem_pasta_processados.append({
                    "id": arquivo.get("arquivo_id", ""),
                    "nome": arquivo.get("nome_arquivo", ""),
                    "tipo": arquivo.get("tipo", ""),
                    "data_processamento": arquivo.get("data_processamento", ""),
                    "data_filtro": arquivo.get("data_filtro", ""),
                    "total_registros": arquivo.get("total_registros", 0),
                    "tamanho": arquivo.get("tamanho_bytes", 0),
                    "dados": arquivo.get("dados", {}),
                    "remote_url": None,
                    "remote_key_encoded": None
                })
            
            return {
                "sucesso": True,
                "pastas": resultado_pastas,
                "arquivos_sem_pasta": arquivos_sem_pasta_processados,
                "total_pastas": len(pastas),
                "total_arquivos_sem_pasta": len(arquivos_sem_pasta_processados)
            }
            
        except Exception as e:
            return {
                "sucesso": False,
                "mensagem": f"Erro de conexão: {str(e)}"
            }
    
    def obter_arquivo_por_id(self, arquivo_id: str) -> Dict[str, Any]:

        try:
            estrutura_resultado = self.obter_estrutura_pastas()
            
            if not estrutura_resultado["sucesso"]:
                return estrutura_resultado
            
            pastas = estrutura_resultado["pastas"]
            arquivos_sem_pasta = estrutura_resultado["arquivos_sem_pasta"]
            

            for nome_pasta, pasta in pastas.items():
                for arquivo in pasta["arquivos"]:
                    if arquivo["arquivo_id"] == arquivo_id:
                        return {
                            "sucesso": True,
                            "arquivo": arquivo["dados"],
                            "id": arquivo_id,
                            "pasta": nome_pasta,
                            "metadados": arquivo
                        }
            
           
            for arquivo in arquivos_sem_pasta:
                if arquivo["arquivo_id"] == arquivo_id:
                    return {
                        "sucesso": True,
                        "arquivo": arquivo["dados"],
                        "id": arquivo_id,
                        "pasta": "sem_pasta",
                        "metadados": arquivo
                    }
            
            return {
                "sucesso": False,
                "mensagem": f"Arquivo com ID '{arquivo_id}' não encontrado"
            }
            
        except Exception as e:
            return {
                "sucesso": False,
                "mensagem": f"Erro de conexão: {str(e)}"
            }
    
    def criar_pasta(self, nome_pasta: str, cor: str = "#6c757d") -> Dict[str, Any]:
       
        try:
            estrutura_resultado = self.obter_estrutura_pastas()
            
            if not estrutura_resultado["sucesso"]:
                return estrutura_resultado
            
            pastas = estrutura_resultado["pastas"]
            
            if nome_pasta in pastas:
                return {
                    "sucesso": False,
                    "mensagem": f"Pasta '{nome_pasta}' já existe"
                }
            
            pastas[nome_pasta] = {
                "nome": nome_pasta,
                "cor": cor,
                "arquivos": []
            }
            
            nova_estrutura = {
                "pastas": pastas,
                "arquivos_sem_pasta": estrutura_resultado["arquivos_sem_pasta"]
            }
            
            return self._salvar_estrutura_pastas(nova_estrutura)
            
        except Exception as e:
            return {
                "sucesso": False,
                "mensagem": f"Erro de conexão: {str(e)}"
            }
    
    def deletar_pasta(self, nome_pasta: str) -> Dict[str, Any]:
 
        try:
            estrutura_resultado = self.obter_estrutura_pastas()
            
            if not estrutura_resultado["sucesso"]:
                return estrutura_resultado
            
            pastas = estrutura_resultado["pastas"]
            
            if nome_pasta not in pastas:
                return {
                    "sucesso": False,
                    "mensagem": f"Pasta '{nome_pasta}' não encontrada"
                }
            
            if nome_pasta in ["MAB", "MCR", "DESCONTOS", "RENUNCIAS", "OUTROS"]:
                return {
                    "sucesso": False,
                    "mensagem": f"Não é possível deletar a pasta padrão '{nome_pasta}'"
                }
            
           
            arquivos_sem_pasta = estrutura_resultado["arquivos_sem_pasta"] + pastas[nome_pasta]["arquivos"]
            

            del pastas[nome_pasta]
            
            nova_estrutura = {
                "pastas": pastas,
                "arquivos_sem_pasta": arquivos_sem_pasta
            }
            
            return self._salvar_estrutura_pastas(nova_estrutura)
            
        except Exception as e:
            return {
                "sucesso": False,
                "mensagem": f"Erro de conexão: {str(e)}"
            }
    
    def mover_arquivo(self, arquivo_id: str, pasta_origem: str, pasta_destino: str) -> Dict[str, Any]:
      
        try:
            estrutura_resultado = self.obter_estrutura_pastas()
            
            if not estrutura_resultado["sucesso"]:
                return estrutura_resultado
            
            pastas = estrutura_resultado["pastas"]
            arquivos_sem_pasta = estrutura_resultado["arquivos_sem_pasta"]
            
            if pasta_destino not in pastas:
                return {
                    "sucesso": False,
                    "mensagem": f"Pasta de destino '{pasta_destino}' não encontrada"
                }
            
            arquivo_encontrado = None
            
           
            if pasta_origem == "sem_pasta":
                for i, arquivo in enumerate(arquivos_sem_pasta):
                    if arquivo["arquivo_id"] == arquivo_id:
                        arquivo_encontrado = arquivos_sem_pasta.pop(i)
                        break
            else:
                if pasta_origem in pastas:
                    for i, arquivo in enumerate(pastas[pasta_origem]["arquivos"]):
                        if arquivo["arquivo_id"] == arquivo_id:
                            arquivo_encontrado = pastas[pasta_origem]["arquivos"].pop(i)
                            break
            
            if not arquivo_encontrado:
                return {
                    "sucesso": False,
                    "mensagem": f"Arquivo com ID '{arquivo_id}' não encontrado"
                }
              # Adicionar à pasta destino
            pastas[pasta_destino]["arquivos"].append(arquivo_encontrado)
            
            nova_estrutura = {
                "pastas": pastas,
                "arquivos_sem_pasta": arquivos_sem_pasta
            }
            
            return self._salvar_estrutura_pastas(nova_estrutura)
            
        except Exception as e:
            return {
                "sucesso": False,
                "mensagem": f"Erro de conexão: {str(e)}"
            }
    
    def deletar_arquivo(self, arquivo_id: str) -> Dict[str, Any]:
        """Deleta um arquivo"""
        try:
            estrutura_resultado = self.obter_estrutura_pastas()
            
            if not estrutura_resultado["sucesso"]:
                return estrutura_resultado
            
            pastas = estrutura_resultado["pastas"]
            arquivos_sem_pasta = estrutura_resultado["arquivos_sem_pasta"]
            arquivo_encontrado = False
            
            # Procurar e remover das pastas
            for nome_pasta, pasta in pastas.items():
                for i, arquivo in enumerate(pasta["arquivos"]):
                    if arquivo["arquivo_id"] == arquivo_id:
                        pastas[nome_pasta]["arquivos"].pop(i)
                        arquivo_encontrado = True
                        break
                if arquivo_encontrado:
                    break
            
            # Se não encontrou nas pastas, procurar em arquivos sem pasta
            if not arquivo_encontrado:
                for i, arquivo in enumerate(arquivos_sem_pasta):
                    if arquivo["arquivo_id"] == arquivo_id:
                        arquivos_sem_pasta.pop(i)
                        arquivo_encontrado = True
                        break
            
            if not arquivo_encontrado:
                return {
                    "sucesso": False,
                    "mensagem": f"Arquivo com ID '{arquivo_id}' não encontrado"
                }
            
            # Salvar estrutura atualizada
            nova_estrutura = {
                "pastas": pastas,
                "arquivos_sem_pasta": arquivos_sem_pasta
            }
            
            return self._salvar_estrutura_pastas(nova_estrutura)
            
        except Exception as e:
            return {
                "sucesso": False,
                "mensagem": f"Erro de conexão: {str(e)}"
            }
    
    def limpar_dados(self) -> Dict[str, Any]:
        """Limpa todos os dados"""
        try:
            estrutura_vazia = {
                "pastas": {
                    "MAB": {"nome": "MAB", "cor": "#ff6600", "arquivos": []},
                    "MCR": {"nome": "MCR", "cor": "#28a745", "arquivos": []},
                    "DESCONTOS": {"nome": "Descontos", "cor": "#17a2b8", "arquivos": []},
                    "RENUNCIAS": {"nome": "Renuncias", "cor": "#6f42c1", "arquivos": []},
                    "OUTROS": {"nome": "OUTROS", "cor": "#6c757d", "arquivos": []}
                },
                "arquivos_sem_pasta": [],
                "metadata": {
                    "ultima_atualizacao": datetime.now().isoformat(),
                    "total_arquivos": 0,
                    "versao_sistema": "2.0-visivel"
                }
            }
            
            resultado = self._salvar_estrutura_pastas(estrutura_vazia)
            
            if resultado["sucesso"]:
                return {
                    "sucesso": True,
                    "mensagem": "Todos os dados foram limpos com sucesso"
                }
            else:
                return resultado
                
        except Exception as e:
            return {
                "sucesso": False,
                "mensagem": f"Erro de conexão: {str(e)}"
            } 
    
    def atualizar_arquivo(self, arquivo_id: str, novos_dados: Dict[str, Any]) -> Dict[str, Any]:
        """Atualiza um arquivo existente"""
        try:
            estrutura_resultado = self.obter_estrutura_pastas()
            
            if not estrutura_resultado["sucesso"]:
                return estrutura_resultado
            
            pastas = estrutura_resultado["pastas"]
            arquivos_sem_pasta = estrutura_resultado["arquivos_sem_pasta"]
            arquivo_encontrado = False
            
            # Procurar e atualizar nas pastas
            for nome_pasta, pasta in pastas.items():
                for i, arquivo in enumerate(pasta["arquivos"]):
                    if arquivo["arquivo_id"] == arquivo_id:
                        # Atualizar dados do arquivo
                        arquivo["dados"].update(novos_dados)
                        arquivo["data_processamento"] = datetime.now().isoformat()
                        arquivo["tamanho_bytes"] = len(json.dumps(arquivo["dados"]))
                        arquivo["total_registros"] = len(arquivo["dados"].get("resultados", []))
                        arquivo_encontrado = True
                        break
                if arquivo_encontrado:
                    break
            
            # Se não encontrou nas pastas, procurar em arquivos sem pasta
            if not arquivo_encontrado:
                for i, arquivo in enumerate(arquivos_sem_pasta):
                    if arquivo["arquivo_id"] == arquivo_id:
                        # Atualizar dados do arquivo
                        arquivo["dados"].update(novos_dados)
                        arquivo["data_processamento"] = datetime.now().isoformat()
                        arquivo["tamanho_bytes"] = len(json.dumps(arquivo["dados"]))
                        arquivo["total_registros"] = len(arquivo["dados"].get("resultados", []))
                        arquivo_encontrado = True
                        break
            
            if not arquivo_encontrado:
                return {
                    "sucesso": False,
                    "mensagem": f"Arquivo com ID '{arquivo_id}' não encontrado"
                }
            
            # Salvar estrutura atualizada
            nova_estrutura = {
                "pastas": pastas,
                "arquivos_sem_pasta": arquivos_sem_pasta
            }
            
            return self._salvar_estrutura_pastas(nova_estrutura)
            
        except Exception as e:
            return {
                "sucesso": False,
                "mensagem": f"Erro de conexão: {str(e)}"
            }
    
    def enviar_arquivo_json(self, caminho_arquivo: str) -> Dict[str, Any]:
        """Envia um arquivo JSON para o AWS"""
        try:
            with open(caminho_arquivo, 'r', encoding='utf-8') as arquivo:
                dados = json.load(arquivo)
            
            return self.enviar_dados_visivel(dados)
            
        except FileNotFoundError:
            return {
                "sucesso": False,
                "mensagem": f"Arquivo '{caminho_arquivo}' não encontrado"
            }
        except json.JSONDecodeError:
            return {
                "sucesso": False,
                "mensagem": f"Arquivo '{caminho_arquivo}' não é um JSON válido"
            }
        except Exception as e:
            return {
                "sucesso": False,
                "mensagem": f"Erro ao processar arquivo: {str(e)}"
            } 