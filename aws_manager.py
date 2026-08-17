
import requests
import json
import os
from datetime import datetime
from typing import Dict, List, Optional, Any
from carregar_env import carregar_env

carregar_env()

class AWSManager:
    def __init__(self, api_key: str = None):

        self.AWS_API_URL = os.getenv(
            "API_URL",
            "https://v60yr1ma4f.execute-api.sa-east-1.amazonaws.com/prod/upload-arquivos",
        )

        self.api_key = api_key or os.getenv("AWS_API_KEY", "")
        self.headers = {
            "x-api-key": self.api_key,
            "Content-Type": "application/json"
        }

    def _normalizar_nome_arquivo(self, dados: Dict[str, Any]) -> str:
        tipo = str(dados.get("tipo", "OUTROS")).upper().strip() or "OUTROS"
        data_ref = str(dados.get("data_arrecadacao") or dados.get("data_filtro") or datetime.now().strftime("%d-%m-%Y"))
        data_ref = data_ref.replace("/", "-").strip()
        return f"{tipo}_{data_ref}.json"

    def _post_upload(self, file_name: str, content: Dict[str, Any]) -> Dict[str, Any]:
        payload = {
            "file_name": file_name,
            "content": content,
        }
        response = requests.post(self.AWS_API_URL, json=payload, headers=self.headers, timeout=20)
        return {
            "sucesso": response.status_code in [200, 201, 202],
            "status_code": response.status_code,
            "body": (response.text or "").strip()[:1000]
        }
    
    def testar_conexao(self) -> Dict[str, Any]:
        """Valida chave e conectividade via GET /listar-arquivos (não envia arquivos)."""
        try:
            base = self.AWS_API_URL.rsplit("/", 1)[0]
            url = f"{base}/listar-arquivos"
            hoje = datetime.now().strftime("%d/%m/%Y")
            headers = {"x-api-key": self.api_key, "Accept": "application/json"}
            response = requests.get(
                url, headers=headers, params={"data": hoje}, timeout=10
            )
            sucesso = response.status_code == 200
            return {
                "sucesso": sucesso,
                "status_code": response.status_code,
                "mensagem": (
                    "API acessível (consulta sem envio de arquivos)"
                    if sucesso
                    else (response.text or f"Erro HTTP {response.status_code}")[:500]
                ),
                "dados": None,
            }
        except Exception as e:
            return {
                "sucesso": False,
                "status_code": None,
                "mensagem": f"Erro de conexão: {str(e)}",
                "dados": None
            }
    
    def obter_dados(self) -> Dict[str, Any]:
        return {
            "sucesso": False,
            "mensagem": "Leitura remota desativada: API atual permite apenas upload via POST.",
            "dados": None
        }
    
    def enviar_dados(self, dados: Dict[str, Any]) -> Dict[str, Any]:

        try:
            if "data_processamento" not in dados:
                dados["data_processamento"] = datetime.now().isoformat()
            if "data_arrecadacao" not in dados:
                dados["data_arrecadacao"] = str(dados.get("data_filtro", datetime.now().strftime("%d-%m-%Y"))).replace("/", "-")
            nome_arquivo = self._normalizar_nome_arquivo(dados)
            upload = self._post_upload(nome_arquivo, dados)
            return {
                "sucesso": upload["sucesso"],
                "mensagem": "Upload concluido" if upload["sucesso"] else f"Falha no upload: {upload['status_code']}",
                "status_code": upload["status_code"],
                "dados_enviados": dados,
                "arquivo": nome_arquivo,
                "resposta": upload.get("body")
            }
                
        except Exception as e:
            return {
                "sucesso": False,
                "mensagem": f"Erro de conexão: {str(e)}",
                "status_code": None
            }
    
    def enviar_lista_dados(self, lista_dados: List[Dict[str, Any]]) -> Dict[str, Any]:

        try:
            resultados = []
            for item in lista_dados:
                nome = self._normalizar_nome_arquivo(item)
                resultados.append(self._post_upload(nome, item))
            sucesso_total = all(r.get("sucesso") for r in resultados) if resultados else False
            return {
                "sucesso": sucesso_total,
                "mensagem": f"Uploads processados: {len(resultados)}",
                "status_code": 200 if sucesso_total else 207,
                "total_arquivos": len(lista_dados),
                "resultados": resultados
            }
        except Exception as e:
            return {
                "sucesso": False,
                "mensagem": f"Erro de conexão: {str(e)}",
                "status_code": None
            }
    
    def enviar_dados_mab(self, dia: int, mes: int, dados_mab: List[Dict]) -> Dict[str, Any]:

        dados_estruturados = {
            "tipo": "MAB",
            "data_filtro": f"{dia:02d}/{mes:02d}/2025",
            "data_processamento": datetime.now().isoformat(),
            "total_registros": len(dados_mab),
            "resultados": dados_mab
        }
        return self.enviar_dados(dados_estruturados)
    
    def enviar_dados_mcr(self, dia: int, mes: int, dados_mcr: List[Dict]) -> Dict[str, Any]:

        dados_estruturados = {
            "tipo": "MCR",
            "data_filtro": f"{dia:02d}/{mes:02d}/2025",
            "data_processamento": datetime.now().isoformat(),
            "total_registros": len(dados_mcr),
            "resultados": dados_mcr
        }
        return self.enviar_dados(dados_estruturados)
    
    def enviar_dados_deducoes(self, dia: int, mes: int, dados_deducoes: List[Dict]) -> Dict[str, Any]:

        dados_estruturados = {
            "tipo": "DEDUCOES",
            "data_filtro": f"{dia:02d}/{mes:02d}/2025",
            "data_processamento": datetime.now().isoformat(),
            "total_registros": len(dados_deducoes),
            "resultados": dados_deducoes
        }
        return self.enviar_dados(dados_estruturados)
    
    def enviar_dados_consolidados(self, dia: int, mes: int, dados_mab: List[Dict], 
                                 dados_mcr: List[Dict], dados_deducoes: List[Dict]) -> Dict[str, Any]:

        dados_estruturados = {
            "tipo": "CONSOLIDADO",
            "data_filtro": f"{dia:02d}/{mes:02d}/2025",
            "data_processamento": datetime.now().isoformat(),
            "resumo": {
                "total_registros_mab": len(dados_mab),
                "total_registros_mcr": len(dados_mcr),
                "total_registros_deducoes": len(dados_deducoes),
                "total_geral": len(dados_mab) + len(dados_mcr) + len(dados_deducoes)
            },
            "dados": {
                "mab": {"tipo": "MAB", "resultados": dados_mab},
                "mcr": {"tipo": "MCR", "resultados": dados_mcr},
                "deducoes": {"tipo": "DEDUCOES", "resultados": dados_deducoes}
            }
        }
        return self.enviar_dados(dados_estruturados)
    
    def carregar_arquivo_json(self, caminho_arquivo: str) -> Dict[str, Any]:

        try:
            if not os.path.exists(caminho_arquivo):
                return {
                    "sucesso": False,
                    "mensagem": f"Arquivo não encontrado: {caminho_arquivo}"
                }
            
            with open(caminho_arquivo, 'r', encoding='utf-8') as f:
                dados = json.load(f)
            
            return {
                "sucesso": True,
                "dados": dados,
                "mensagem": f"Arquivo carregado com sucesso: {caminho_arquivo}"
            }
        except json.JSONDecodeError as e:
            return {
                "sucesso": False,
                "mensagem": f"Erro ao decodificar JSON: {str(e)}"
            }
        except Exception as e:
            return {
                "sucesso": False,
                "mensagem": f"Erro ao carregar arquivo: {str(e)}"
            }
    
    def enviar_arquivo_json(self, caminho_arquivo: str) -> Dict[str, Any]:

        resultado_carregamento = self.carregar_arquivo_json(caminho_arquivo)
        
        if not resultado_carregamento["sucesso"]:
            return resultado_carregamento
        
        return self.enviar_dados(resultado_carregamento["dados"])
    
    def limpar_dados(self) -> Dict[str, Any]:

        dados_vazios = {
            "tipo": "VAZIO",
            "data_processamento": datetime.now().isoformat(),
            "mensagem": "Dados limpos",
            "resultados": []
        }
        return self.enviar_dados(dados_vazios)
    
    def obter_estatisticas(self) -> Dict[str, Any]:

        resultado = self.obter_dados()
        
        if not resultado["sucesso"]:
            return resultado
        
        dados = resultado["dados"]
        estatisticas = {
            "tipo": dados.get("tipo") if isinstance(dados, dict) else "lista",
            "data_processamento": dados.get("data_processamento") if isinstance(dados, dict) else None,
            "total_registros": 0,
            "estrutura": "desconhecida"
        }
        
        if isinstance(dados, dict):
            if "resultados" in dados:
                estatisticas["total_registros"] = len(dados["resultados"])
                estatisticas["estrutura"] = "resultados_simples"
            elif "dados" in dados:
                estatisticas["estrutura"] = "dados_consolidados"
                if isinstance(dados["dados"], dict):
                    total = 0
                    for tipo, conteudo in dados["dados"].items():
                        if isinstance(conteudo, dict) and "resultados" in conteudo:
                            total += len(conteudo["resultados"])
                    estatisticas["total_registros"] = total
        elif isinstance(dados, list):
            estatisticas["total_registros"] = len(dados)
            estatisticas["estrutura"] = "lista"
        
        return {
            "sucesso": True,
            "estatisticas": estatisticas,
            "dados_completos": dados
        }
    
    def listar_arquivos(self) -> Dict[str, Any]:

        resultado = self.obter_dados()
        
        if not resultado["sucesso"]:
            return resultado
        
        dados = resultado["dados"]
        arquivos = []
        
        if isinstance(dados, dict):

            arquivo_id = self._gerar_id_arquivo(dados)
            arquivos.append({
                "id": arquivo_id,
                "nome": dados.get("tipo", "Arquivo"),
                "tipo": dados.get("tipo", "desconhecido"),
                "data_processamento": dados.get("data_processamento"),
                "data_filtro": dados.get("data_filtro"),
                "total_registros": len(dados.get("resultados", [])),
                "tamanho": len(str(dados))
            })
        elif isinstance(dados, list):

            for i, item in enumerate(dados):
                if isinstance(item, dict):
                    arquivo_id = self._gerar_id_arquivo(item)
                    arquivos.append({
                        "id": arquivo_id,
                        "nome": f"{item.get('tipo', 'Arquivo')} - {i+1}",
                        "tipo": item.get("tipo", "desconhecido"),
                        "data_processamento": item.get("data_processamento"),
                        "data_filtro": item.get("data_filtro"),
                        "total_registros": len(item.get("resultados", [])),
                        "tamanho": len(str(item)),
                        "indice": i
                    })
        
        return {
            "sucesso": True,
            "arquivos": arquivos,
            "total_arquivos": len(arquivos)
        }
    
    def obter_arquivo_por_id(self, arquivo_id: str) -> Dict[str, Any]:

        estrutura = self.obter_estrutura_pastas()
        
        if not estrutura["sucesso"]:
            return estrutura
        
        pastas = estrutura["pastas"]
        arquivos_sem_pasta = estrutura["arquivos_sem_pasta"]
        

        for nome_pasta, pasta in pastas.items():
            for arquivo in pasta["arquivos"]:
                if isinstance(arquivo, dict) and self._gerar_id_arquivo(arquivo) == arquivo_id:
                    return {
                        "sucesso": True,
                        "arquivo": arquivo,
                        "id": arquivo_id,
                        "pasta": nome_pasta
                    }
        

        for arquivo in arquivos_sem_pasta:
            if isinstance(arquivo, dict) and self._gerar_id_arquivo(arquivo) == arquivo_id:
                return {
                    "sucesso": True,
                    "arquivo": arquivo,
                    "id": arquivo_id,
                    "pasta": "sem_pasta"
                }
        
        return {
            "sucesso": False,
            "mensagem": f"Arquivo com ID '{arquivo_id}' não encontrado"
        }
    
    def atualizar_arquivo(self, arquivo_id: str, novos_dados: Dict[str, Any]) -> Dict[str, Any]:

        estrutura = self.obter_estrutura_pastas()
        
        if not estrutura["sucesso"]:
            return estrutura
        
        pastas = estrutura["pastas"]
        arquivos_sem_pasta = estrutura["arquivos_sem_pasta"]
        arquivo_encontrado = False
        

        for nome_pasta, pasta in pastas.items():
            for i, arquivo in enumerate(pasta["arquivos"]):
                if isinstance(arquivo, dict) and self._gerar_id_arquivo(arquivo) == arquivo_id:
                    pastas[nome_pasta]["arquivos"][i] = novos_dados
                    arquivo_encontrado = True
                    break
            if arquivo_encontrado:
                break
        

        if not arquivo_encontrado:
            for i, arquivo in enumerate(arquivos_sem_pasta):
                if isinstance(arquivo, dict) and self._gerar_id_arquivo(arquivo) == arquivo_id:
                    arquivos_sem_pasta[i] = novos_dados
                    arquivo_encontrado = True
                    break
        
        if not arquivo_encontrado:
            return {
                "sucesso": False,
                "mensagem": f"Arquivo com ID '{arquivo_id}' não encontrado"
            }
        

        nova_estrutura = {
            "pastas": pastas,
            "arquivos_sem_pasta": arquivos_sem_pasta
        }
        
        return self._salvar_estrutura_pastas(nova_estrutura)
    
    def deletar_arquivo(self, arquivo_id: str) -> Dict[str, Any]:

        estrutura = self.obter_estrutura_pastas()
        
        if not estrutura["sucesso"]:
            return estrutura
        
        pastas = estrutura["pastas"]
        arquivos_sem_pasta = estrutura["arquivos_sem_pasta"]
        arquivo_encontrado = False
        
       
        for nome_pasta, pasta in pastas.items():
            for i, arquivo in enumerate(pasta["arquivos"]):
                if isinstance(arquivo, dict) and self._gerar_id_arquivo(arquivo) == arquivo_id:

                    pastas[nome_pasta]["arquivos"].pop(i)
                    arquivo_encontrado = True
                    break
            if arquivo_encontrado:
                break
        
        
        if not arquivo_encontrado:
            for i, arquivo in enumerate(arquivos_sem_pasta):
                if isinstance(arquivo, dict) and self._gerar_id_arquivo(arquivo) == arquivo_id:
                    arquivos_sem_pasta.pop(i)
                    arquivo_encontrado = True
                    break
        
        if not arquivo_encontrado:
            return {
                "sucesso": False,
                "mensagem": f"Arquivo com ID '{arquivo_id}' não encontrado"
            }
        

        nova_estrutura = {
            "pastas": pastas,
            "arquivos_sem_pasta": arquivos_sem_pasta
        }
        
        return self._salvar_estrutura_pastas(nova_estrutura)
    
    def _gerar_id_arquivo(self, dados: Dict[str, Any]) -> str:
      
        tipo = dados.get("tipo", "desconhecido")
        data_processamento = dados.get("data_processamento", "")
        data_filtro = dados.get("data_filtro", "")
        
       
        id_string = f"{tipo}_{data_filtro}_{data_processamento}"
        
  
        import hashlib
        return hashlib.md5(id_string.encode()).hexdigest()[:12]
    
    def obter_estrutura_pastas(self) -> Dict[str, Any]:
 
        return {
            "sucesso": True,
            "pastas": {
                "MAB": {"nome": "MAB", "cor": "#ff6600", "cor_escuro": "#dc3545", "arquivos": []},
                "MCR": {"nome": "MCR", "cor": "#28a745", "cor_escuro": "#28a745", "arquivos": []},
                "DESCONTOS": {"nome": "Descontos", "cor": "#17a2b8", "cor_escuro": "#17a2b8", "arquivos": []},
                "RENUNCIAS": {"nome": "Renuncias", "cor": "#6f42c1", "cor_escuro": "#6f42c1", "arquivos": []},
                "OUTROS": {"nome": "OUTROS", "cor": "#6c757d", "cor_escuro": "#6c757d", "arquivos": []}
            },
            "arquivos_sem_pasta": []
        }
    
    def _salvar_estrutura_pastas(self, estrutura: Dict[str, Any]) -> Dict[str, Any]:
        return {
            "sucesso": True,
            "mensagem": "Estrutura local mantida; persistencia remota de indice desativada."
        }
    
    def criar_pasta(self, nome_pasta: str, cor: str = "#6c757d") -> Dict[str, Any]:

        estrutura = self.obter_estrutura_pastas()
        
        if not estrutura["sucesso"]:
            return estrutura
        
        pastas = estrutura["pastas"]
        

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
            "arquivos_sem_pasta": estrutura["arquivos_sem_pasta"]
        }
        
        return self._salvar_estrutura_pastas(nova_estrutura)
    
    def deletar_pasta(self, nome_pasta: str) -> Dict[str, Any]:

        estrutura = self.obter_estrutura_pastas()
        
        if not estrutura["sucesso"]:
            return estrutura
        
        pastas = estrutura["pastas"]
        

        if nome_pasta not in pastas:
            return {
                "sucesso": False,
                "mensagem": f"Pasta '{nome_pasta}' não encontrada"
            }
        

        if nome_pasta in ["MAB", "MCR", "DESCONTOS", "RENUNCIAS"]:
            return {
                "sucesso": False,
                "mensagem": f"Não é possível deletar a pasta padrão '{nome_pasta}'"
            }
        

        arquivos_sem_pasta = estrutura["arquivos_sem_pasta"] + pastas[nome_pasta]["arquivos"]
        

        del pastas[nome_pasta]
        

        nova_estrutura = {
            "pastas": pastas,
            "arquivos_sem_pasta": arquivos_sem_pasta
        }
        
        return self._salvar_estrutura_pastas(nova_estrutura)
    
    def mover_arquivo(self, arquivo_id: str, pasta_origem: str, pasta_destino: str) -> Dict[str, Any]:

        estrutura = self.obter_estrutura_pastas()
        
        if not estrutura["sucesso"]:
            return estrutura
        
        pastas = estrutura["pastas"]
        arquivos_sem_pasta = estrutura["arquivos_sem_pasta"]
        

        if pasta_destino not in pastas:
            return {
                "sucesso": False,
                "mensagem": f"Pasta de destino '{pasta_destino}' não encontrada"
            }
        
        arquivo_encontrado = None
        

        if pasta_origem == "sem_pasta":
            for i, arquivo in enumerate(arquivos_sem_pasta):
                if isinstance(arquivo, dict) and self._gerar_id_arquivo(arquivo) == arquivo_id:
                    arquivo_encontrado = arquivos_sem_pasta.pop(i)
                    break
        else:
            if pasta_origem in pastas:
                for i, arquivo in enumerate(pastas[pasta_origem]["arquivos"]):
                    if isinstance(arquivo, dict) and self._gerar_id_arquivo(arquivo) == arquivo_id:
                        arquivo_encontrado = pastas[pasta_origem]["arquivos"].pop(i)
                        break
        
        if not arquivo_encontrado:
            return {
                "sucesso": False,
                "mensagem": f"Arquivo com ID '{arquivo_id}' não encontrado"
            }
        
 
        pastas[pasta_destino]["arquivos"].append(arquivo_encontrado)
        

        nova_estrutura = {
            "pastas": pastas,
            "arquivos_sem_pasta": arquivos_sem_pasta
        }
        
        return self._salvar_estrutura_pastas(nova_estrutura)
    
    def listar_arquivos_por_pasta(self) -> Dict[str, Any]:
   
        estrutura = self.obter_estrutura_pastas()
        
        if not estrutura["sucesso"]:
            return estrutura
        
        pastas = estrutura["pastas"]
        arquivos_sem_pasta = estrutura["arquivos_sem_pasta"]
        
   
        resultado_pastas = {}
        for nome_pasta, pasta in pastas.items():
            arquivos_processados = []
            for arquivo in pasta["arquivos"]:
                if isinstance(arquivo, dict):
                    arquivo_id = self._gerar_id_arquivo(arquivo)
                    arquivos_processados.append({
                        "id": arquivo_id,
                        "nome": f"{arquivo.get('tipo', 'Arquivo')}",
                        "tipo": arquivo.get("tipo", "desconhecido"),
                        "data_processamento": arquivo.get("data_processamento"),
                        "data_filtro": arquivo.get("data_filtro"),
                        "total_registros": len(arquivo.get("resultados", [])),
                        "tamanho": len(str(arquivo)),
                        "dados": arquivo
                    })
            
            resultado_pastas[nome_pasta] = {
                "nome": pasta["nome"],
                "cor": pasta["cor"],
                "arquivos": arquivos_processados,
                "total_arquivos": len(arquivos_processados)
            }
        

        arquivos_sem_pasta_processados = []
        for arquivo in arquivos_sem_pasta:
            if isinstance(arquivo, dict):
                arquivo_id = self._gerar_id_arquivo(arquivo)
                arquivos_sem_pasta_processados.append({
                    "id": arquivo_id,
                    "nome": f"{arquivo.get('tipo', 'Arquivo')}",
                    "tipo": arquivo.get("tipo", "desconhecido"),
                    "data_processamento": arquivo.get("data_processamento"),
                    "data_filtro": arquivo.get("data_filtro"),
                    "total_registros": len(arquivo.get("resultados", [])),
                    "tamanho": len(str(arquivo)),
                    "dados": arquivo
                })
        
        return {
            "sucesso": True,
            "pastas": resultado_pastas,
            "arquivos_sem_pasta": arquivos_sem_pasta_processados,
            "total_pastas": len(pastas),
            "total_arquivos_sem_pasta": len(arquivos_sem_pasta_processados)
        } 