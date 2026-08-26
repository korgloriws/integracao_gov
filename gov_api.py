import base64
import json
import os
import re
import time
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

import requests
from carregar_env import carregar_env

carregar_env()

GOV_BASE_URL_PADRAO = "https://webapp1-contagem.cidade360.cloud/CustomData.Api"


def _exp_do_jwt(jwt: str) -> Optional[float]:
    try:
        partes = jwt.split(".")
        if len(partes) < 2:
            return None
        payload = partes[1] + "=" * (-len(partes[1]) % 4)
        dados = json.loads(base64.urlsafe_b64decode(payload.encode("ascii")))
        exp = dados.get("exp")
        return float(exp) if exp is not None else None
    except Exception:
        return None


def normalizar_data_iso(valor: str) -> Optional[str]:
    """Aceita yyyy-mm-dd ou dd/mm/aaaa e devolve yyyy-mm-dd."""
    texto = str(valor or "").strip()
    if not texto:
        return None
    for fmt in ("%Y-%m-%d", "%d/%m/%Y", "%d-%m-%Y"):
        try:
            return datetime.strptime(texto[:10], fmt).strftime("%Y-%m-%d")
        except ValueError:
            continue
    return None


def _norm(valor: Any) -> str:
    return str(valor or "").strip()


def _norm_lower(valor: Any) -> str:
    return _norm(valor).lower()


def _digits(valor: Any) -> str:
    return re.sub(r"\D+", "", _norm(valor))


def _match_prefixo_flexivel(valor: Any, filtro: Any) -> bool:
    """
    Prefixo flexível por dígitos OU por texto com pontos.
    Ex.: filtro "6", "62", "6.2", "621" casa com valor "6.2.1.3.01.01.01".
    Quantidade de dígitos = o que o usuário digitou (sem exigir o código completo).
    """
    texto = _norm(filtro)
    if not texto:
        return True
    alvo = _norm(valor)
    if not alvo:
        return False
    dig_f = _digits(texto)
    dig_a = _digits(alvo)
    if dig_f and dig_a and dig_a.startswith(dig_f):
        return True
    if alvo.lower().startswith(texto.lower()):
        return True
    # "6.2.1" vs "621..." — já coberto por dígitos; fallback texto sem pontos
    texto_limpo = re.sub(r"[.\s\-_/]+", "", texto).lower()
    alvo_limpo = re.sub(r"[.\s\-_/]+", "", alvo).lower()
    return bool(texto_limpo) and alvo_limpo.startswith(texto_limpo)


def _match_texto(valor: Any, filtro: str, modo: str = "contem") -> bool:
    """modo: contem | prefixo | exato | codigo | flexivel (prefixo por dígitos)."""
    texto = _norm(filtro)
    if not texto:
        return True
    alvo = _norm(valor)
    modo = (modo or "contem").lower()
    if modo in ("flexivel", "codigo", "prefixo"):
        # Conta/natureza: sempre prefixo flexível (ignora pontos / tamanho parcial).
        if modo == "prefixo" and not _digits(texto):
            return alvo.lower().startswith(texto.lower())
        return _match_prefixo_flexivel(alvo, texto)
    if modo == "exato":
        dig_f = _digits(texto)
        dig_a = _digits(alvo)
        if dig_f and dig_a:
            return dig_a == dig_f
        return alvo.lower() == texto.lower()
    return texto.lower() in alvo.lower()


class GovApiClient:
    def __init__(self) -> None:
        carregar_env()
        self.base_url = os.getenv("GOV_BASE_URL", GOV_BASE_URL_PADRAO).rstrip("/")
        self.identificador = os.getenv("GOV_IDENTIFICADOR", "")
        self.senha = os.getenv("GOV_SENHA", "")
        self.email = os.getenv("GOV_EMAIL", "")
        self.timeout = int(os.getenv("GOV_TIMEOUT", "60"))
        self._jwt: Optional[str] = None
        self._jwt_exp: float = 0.0

    def _payload_auth(self) -> Dict[str, str]:
        return {
            "identificador": self.identificador,
            "senha": self.senha,
            "email": self.email,
        }

    def autenticar(self, forcar: bool = False) -> Dict[str, Any]:
        if not self.identificador or not self.senha or not self.email:
            return {
                "sucesso": False,
                "mensagem": "Configure GOV_IDENTIFICADOR, GOV_SENHA e GOV_EMAIL no arquivo .env",
            }

        agora = time.time()
        if not forcar and self._jwt and agora < (self._jwt_exp - 60):
            return {
                "sucesso": True,
                "mensagem": "Token JWT em cache",
                "cached": True,
                "url_auth": f"{self.base_url}/api/autenticacao",
                "identificador": self.identificador,
                "email": self.email,
                "jwt_exp": datetime.fromtimestamp(self._jwt_exp, tz=timezone.utc).isoformat(),
            }

        url = f"{self.base_url}/api/autenticacao"
        try:
            resp = requests.post(url, json=self._payload_auth(), timeout=30)
        except Exception as e:
            return {"sucesso": False, "mensagem": f"Erro de conexão na autenticação: {e}", "url_auth": url}

        if resp.status_code != 200:
            return {
                "sucesso": False,
                "status_code": resp.status_code,
                "mensagem": (resp.text or f"HTTP {resp.status_code}")[:800],
                "url_auth": url,
            }

        try:
            dados = resp.json()
        except Exception:
            return {"sucesso": False, "mensagem": "Resposta de autenticação não é JSON", "url_auth": url}

        jwt = dados.get("jwt") if isinstance(dados, dict) else None
        if not jwt:
            return {"sucesso": False, "mensagem": "Resposta sem campo jwt", "url_auth": url}

        self._jwt = jwt
        self._jwt_exp = _exp_do_jwt(jwt) or (agora + 3600)
        return {
            "sucesso": True,
            "status_code": resp.status_code,
            "mensagem": "Autenticado na API GovBR",
            "cached": False,
            "url_auth": url,
            "identificador": self.identificador,
            "email": self.email,
            "jwt_exp": datetime.fromtimestamp(self._jwt_exp, tz=timezone.utc).isoformat(),
        }

    def consultar_razao(
        self,
        data_inicio: str,
        data_final: str,
        fato_contabil: Optional[int] = None,
        preview: int = 0,
        limite_lancamentos: int = 120,
        filtros: Optional[Dict[str, Any]] = None,
        # compatibilidade com chamadas antigas
        conta: Optional[str] = None,
        tipo_deducao: Optional[str] = None,
        busca: Optional[str] = None,
    ) -> Dict[str, Any]:
        auth = self.autenticar()
        if not auth.get("sucesso"):
            return auth

        inicio = normalizar_data_iso(data_inicio)
        final = normalizar_data_iso(data_final)
        if not inicio or not final:
            return {
                "sucesso": False,
                "mensagem": "Informe data_inicio e data_final no formato yyyy-mm-dd (ou dd/mm/aaaa)",
            }

        filtros_eff = dict(filtros or {})
        if conta and not filtros_eff.get("natureza"):
            filtros_eff["natureza"] = conta
        if tipo_deducao and not filtros_eff.get("tipo_deducao"):
            filtros_eff["tipo_deducao"] = tipo_deducao
        if busca and not filtros_eff.get("busca"):
            filtros_eff["busca"] = busca

        # Se veio código numérico de fato e ainda não há filtro texto, usa o path da API.
        fato_path = fato_contabil
        if fato_path is None:
            fato_txt = _norm(filtros_eff.get("fato") or filtros_eff.get("fato_contabil") or "")
            if fato_txt.isdigit():
                fato_path = int(fato_txt)

        if fato_path is not None:
            url = f"{self.base_url}/api/cp/razaocontabilidade/{inicio}/{final}/{int(fato_path)}"
        else:
            url = f"{self.base_url}/api/cp/razaocontabilidade/{inicio}/{final}"

        headers = {
            "Authorization": f"Bearer {self._jwt}",
            "Accept": "application/json",
        }
        try:
            resp = requests.get(url, headers=headers, timeout=self.timeout)
        except Exception as e:
            return {"sucesso": False, "mensagem": f"Erro de conexão na razão: {e}", "url": url}

        if resp.status_code != 200:
            return {
                "sucesso": False,
                "status_code": resp.status_code,
                "mensagem": (resp.text or f"HTTP {resp.status_code}")[:800],
                "url": url,
            }

        try:
            dados = resp.json()
        except Exception:
            return {"sucesso": False, "mensagem": "Resposta da razão não é JSON", "url": url}

        movimentos = dados.get("razaoContabilidade") if isinstance(dados, dict) else None
        if not isinstance(movimentos, list):
            movimentos = []

        return self._montar_resumo_razao(
            movimentos=movimentos,
            url=url,
            inicio=inicio,
            final=final,
            fato_contabil_api=fato_path,
            mensagem=(dados.get("resposta") or {}).get("mensagem") if isinstance(dados, dict) else "OK",
            status_code=resp.status_code,
            filtros=filtros_eff,
            limite_lancamentos=limite_lancamentos,
            preview=preview,
        )

    @staticmethod
    def _prefixo_deducao(valor: str) -> str:
        texto = _norm(valor)
        dig = _digits(texto)
        if dig.startswith("91"):
            return "91"
        if dig.startswith("93"):
            return "93"
        if dig.startswith("96"):
            return "96"
        if dig.startswith("0") or texto.lower().startswith("0"):
            return "00"
        return "00"

    @staticmethod
    def _codigo_fato(valor: Any) -> str:
        texto = _norm(valor)
        m = re.match(r"^(\d+)", texto)
        return m.group(1) if m else _digits(texto)

    def _passa_filtros(self, item: Dict[str, Any], f: Dict[str, Any]) -> bool:
        natureza = _norm(item.get("naturezaReceita"))
        conta_nivel = _norm(item.get("contaContabilNivel"))
        contra = _norm(item.get("contraPartidaNivel"))
        desc_nat = _norm(item.get("descNaturezaReceita"))
        desc_conta = _norm(item.get("contaContabilDescNivel"))
        fato = _norm(item.get("fatoContabil"))
        tipo = _norm(item.get("tipoDeducao"))
        receita = _norm(item.get("receita"))
        fonte = _norm(item.get("fonteRecurso"))
        banco = _norm(item.get("banco"))
        nome_banco = _norm(item.get("nomeBanco"))
        movimento = _norm(item.get("movimento"))
        dc = _norm(item.get("debitoCredito")).upper()
        historico = _norm(item.get("historico"))
        ug = _norm(item.get("ug"))

        # Conta contábil — prefixo flexível (6, 62, 6.2, 621... todos AND com os demais)
        if not _match_prefixo_flexivel(conta_nivel, f.get("conta_contabil")):
            return False
        if not _match_texto(conta_nivel, f.get("conta_contabil_contem"), "contem"):
            return False

        # Natureza da receita — mesmo critério (quantidade parcial de dígitos)
        if not _match_prefixo_flexivel(natureza, f.get("natureza")):
            return False
        if not _match_texto(natureza, f.get("natureza_contem"), "contem"):
            return False
        if not _match_texto(desc_nat, f.get("desc_natureza"), "contem"):
            return False

        # Contra-partida
        if not _match_prefixo_flexivel(contra, f.get("contra_partida")):
            return False

        # Fato contábil — código numérico parcial (29) ou texto
        fato_filtro = _norm(f.get("fato") or f.get("fato_texto") or "")
        if fato_filtro:
            dig = _digits(fato_filtro)
            codigo = self._codigo_fato(fato)
            so_numero = bool(re.fullmatch(r"[\d.\s\-_/]+", fato_filtro))
            if dig and so_numero:
                if not (codigo == dig or codigo.startswith(dig)):
                    return False
            elif dig:
                if not (
                    codigo == dig
                    or codigo.startswith(dig)
                    or _match_texto(fato, fato_filtro, "contem")
                ):
                    return False
            elif not _match_texto(fato, fato_filtro, "contem"):
                return False

        # Tipo dedução 91/93/96/00 ou texto
        tipo_filtro = _norm(f.get("tipo_deducao"))
        if tipo_filtro:
            pref = self._prefixo_deducao(tipo)
            if tipo_filtro in ("00", "0"):
                if pref != "00":
                    return False
            elif tipo_filtro.isdigit() and len(tipo_filtro) <= 2:
                if pref != tipo_filtro:
                    return False
            elif tipo_filtro.lower() not in tipo.lower() and not tipo.lower().startswith(tipo_filtro.lower()):
                return False

        # Código receita / tributo
        if not _match_texto(receita, f.get("receita"), f.get("receita_modo") or "exato"):
            return False
        if not _match_texto(fonte, f.get("fonte_recurso"), f.get("fonte_modo") or "exato"):
            return False

        # Banco (código ou nome)
        banco_filtro = _norm(f.get("banco"))
        if banco_filtro:
            if not (
                _match_texto(banco, banco_filtro, "contem")
                or _match_texto(nome_banco, banco_filtro, "contem")
            ):
                return False

        if not _match_texto(movimento, f.get("movimento"), f.get("movimento_modo") or "exato"):
            return False
        if not _match_texto(dc, f.get("debito_credito"), "exato"):
            return False
        if not _match_texto(ug, f.get("ug"), "exato"):
            return False
        if not _match_texto(desc_conta, f.get("desc_conta"), "contem"):
            return False
        if not _match_texto(historico, f.get("historico"), "contem"):
            return False

        # Faixa de valor
        try:
            valor = float(item.get("valor") or 0)
        except (TypeError, ValueError):
            valor = 0.0
        vmin = f.get("valor_min")
        vmax = f.get("valor_max")
        if vmin not in (None, ""):
            try:
                if valor < float(vmin):
                    return False
            except (TypeError, ValueError):
                pass
        if vmax not in (None, ""):
            try:
                if valor > float(vmax):
                    return False
            except (TypeError, ValueError):
                pass

        # Busca livre em vários campos
        busca = _norm_lower(f.get("busca"))
        if busca:
            blob = " ".join([
                natureza, conta_nivel, contra, desc_nat, desc_conta, fato, tipo,
                receita, fonte, banco, nome_banco, movimento, historico, ug,
                _norm(item.get("lancamento")),
            ]).lower()
            if busca not in blob:
                return False

        return True

    def _montar_resumo_razao(
        self,
        movimentos: list,
        url: str,
        inicio: str,
        final: str,
        fato_contabil_api: Optional[int],
        mensagem: str,
        status_code: int,
        filtros: Dict[str, Any],
        limite_lancamentos: int,
        preview: int,
    ) -> Dict[str, Any]:
        filtros_limpos = {
            k: v for k, v in (filtros or {}).items()
            if v is not None and str(v).strip() != ""
        }

        filtrados = [m for m in movimentos if self._passa_filtros(m, filtros_limpos)]

        por_natureza: Dict[str, Dict[str, Any]] = {}
        por_conta: Dict[str, Dict[str, Any]] = {}
        por_tipo: Dict[str, Dict[str, Any]] = {}
        por_fato: Dict[str, Dict[str, Any]] = {}
        por_receita: Dict[str, Dict[str, Any]] = {}
        por_fonte: Dict[str, Dict[str, Any]] = {}
        por_banco: Dict[str, Dict[str, Any]] = {}
        total_valor = 0.0
        total_debito = 0.0
        total_credito = 0.0

        def _acc(mapa, chave, descricao=""):
            item = mapa.setdefault(chave, {
                "chave": chave,
                "descricao": descricao or "",
                "lancamentos": 0,
                "debito": 0.0,
                "credito": 0.0,
                "valor": 0.0,
                "saldo": 0.0,
            })
            if descricao and not item["descricao"]:
                item["descricao"] = descricao
            return item

        for item in filtrados:
            try:
                valor = float(item.get("valor") or 0)
            except (TypeError, ValueError):
                valor = 0.0
            dc = _norm(item.get("debitoCredito")).upper()
            signed = -valor if dc == "C" else valor
            total_valor += signed
            if dc == "C":
                total_credito += valor
            else:
                total_debito += valor

            nat = _norm(item.get("naturezaReceita")) or "(sem natureza)"
            n_item = _acc(por_natureza, nat, _norm(item.get("descNaturezaReceita")))
            n_item["lancamentos"] += 1
            n_item["valor"] += valor
            n_item["saldo"] += signed
            if dc == "C":
                n_item["credito"] += valor
            else:
                n_item["debito"] += valor

            conta = _norm(item.get("contaContabilNivel")) or "(sem conta)"
            c_item = _acc(por_conta, conta, _norm(item.get("contaContabilDescNivel")))
            c_item["lancamentos"] += 1
            c_item["valor"] += valor
            c_item["saldo"] += signed
            if dc == "C":
                c_item["credito"] += valor
            else:
                c_item["debito"] += valor

            tipo = _norm(item.get("tipoDeducao")) or "(sem tipo)"
            t_item = _acc(por_tipo, tipo)
            t_item["prefixo"] = self._prefixo_deducao(tipo)
            t_item["lancamentos"] += 1
            t_item["valor"] += valor

            fato = _norm(item.get("fatoContabil")) or "(sem fato)"
            f_item = _acc(por_fato, fato)
            f_item["codigo"] = self._codigo_fato(fato)
            f_item["lancamentos"] += 1
            f_item["valor"] += valor

            rec = _norm(item.get("receita")) or "(sem receita)"
            r_item = _acc(por_receita, rec, _norm(item.get("descNaturezaReceita")))
            r_item["lancamentos"] += 1
            r_item["valor"] += valor

            fonte = _norm(item.get("fonteRecurso")) or "(sem fonte)"
            fo_item = _acc(por_fonte, fonte, _norm(item.get("descFonteRecurso")))
            fo_item["lancamentos"] += 1
            fo_item["valor"] += valor

            banco_chave = _norm(item.get("nomeBanco")) or _norm(item.get("banco")) or "(sem banco)"
            b_item = _acc(por_banco, banco_chave)
            b_item["codigo"] = _norm(item.get("banco"))
            b_item["lancamentos"] += 1
            b_item["valor"] += valor

        def _round_map(bloco: Dict[str, Any]) -> Dict[str, Any]:
            out = dict(bloco)
            for chave in ("debito", "credito", "saldo", "valor"):
                if chave in out:
                    out[chave] = round(float(out[chave]), 2)
            return out

        def _sorted(mapa: Dict[str, Dict[str, Any]], key="valor") -> List[Dict[str, Any]]:
            return sorted((_round_map(v) for v in mapa.values()), key=lambda x: -abs(float(x.get(key) or 0)))

        limite = max(0, min(int(limite_lancamentos or 0), 500))
        preview_n = max(0, min(int(preview or 0), 20))
        lancamentos = []
        for item in filtrados[:limite]:
            lancamentos.append({
                "data": item.get("data"),
                "natureza": item.get("naturezaReceita"),
                "desc_natureza": item.get("descNaturezaReceita"),
                "conta_contabil": item.get("contaContabilNivel"),
                "desc_conta": item.get("contaContabilDescNivel"),
                "contra_partida": item.get("contraPartidaNivel"),
                "desc_contra": item.get("contraPartidaDescNivel"),
                "receita": item.get("receita"),
                "fonte_recurso": item.get("fonteRecurso"),
                "desc_fonte": item.get("descFonteRecurso"),
                "debitoCredito": item.get("debitoCredito"),
                "valor": item.get("valor"),
                "tipoDeducao": item.get("tipoDeducao"),
                "fatoContabil": item.get("fatoContabil"),
                "historico": item.get("historico"),
                "banco": item.get("banco"),
                "nomeBanco": item.get("nomeBanco"),
                "movimento": item.get("movimento"),
                "ug": item.get("ug"),
                "lancamento": item.get("lancamento"),
                # aliases usados pela UI antiga
                "conta": item.get("naturezaReceita") or item.get("contaContabilNivel"),
                "descricao": item.get("descNaturezaReceita") or item.get("contaContabilDescNivel"),
            })

        # Opções para popular selects (sobre o conjunto filtrado; se vazio, sobre o bruto)
        base_opcoes = filtrados if filtrados or filtros_limpos else movimentos
        if not base_opcoes:
            base_opcoes = movimentos

        def _uniq(campo: str, limit: int = 80) -> List[str]:
            vals = sorted({_norm(m.get(campo)) for m in base_opcoes if _norm(m.get(campo))})
            return vals[:limit]

        return {
            "sucesso": True,
            "status_code": status_code,
            "mensagem": mensagem,
            "url": url,
            "data_inicio": inicio,
            "data_final": final,
            "fato_contabil": fato_contabil_api,
            "total_bruto": len(movimentos),
            "total_movimentos": len(filtrados),
            "total_contas": len(por_conta),
            "total_naturezas": len(por_natureza),
            "total_debito": round(total_debito, 2),
            "total_credito": round(total_credito, 2),
            "total_valor": round(total_valor, 2),
            "tipos_deducao": [t["chave"] for t in _sorted(por_tipo)],
            "por_tipo_deducao": [
                {**t, "tipo": t["chave"], "prefixo": t.get("prefixo", self._prefixo_deducao(t["chave"]))}
                for t in _sorted(por_tipo)
            ],
            "por_fato": [{**f, "fato": f["chave"]} for f in _sorted(por_fato)],
            "por_natureza": [{**n, "natureza": n["chave"], "conta": n["chave"]} for n in _sorted(por_natureza, "saldo")],
            "por_conta_contabil": [{**c, "conta_contabil": c["chave"], "conta": c["chave"]} for c in _sorted(por_conta, "saldo")],
            # alias antigo: "contas" = natureza (tributo)
            "contas": [{**n, "conta": n["chave"]} for n in _sorted(por_natureza, "saldo")],
            "por_receita": [{**r, "receita": r["chave"]} for r in _sorted(por_receita)],
            "por_fonte": [{**fo, "fonte": fo["chave"]} for fo in _sorted(por_fonte)],
            "por_banco": [{**b, "banco": b["chave"]} for b in _sorted(por_banco)],
            "filtro": filtros_limpos,
            "opcoes": {
                "fatos": _uniq("fatoContabil"),
                "tipos_deducao": _uniq("tipoDeducao"),
                "naturezas": _uniq("naturezaReceita"),
                "contas_contabeis": _uniq("contaContabilNivel"),
                "receitas": _uniq("receita"),
                "fontes": _uniq("fonteRecurso"),
                "bancos": sorted({
                    _norm(m.get("nomeBanco")) or _norm(m.get("banco"))
                    for m in base_opcoes
                    if _norm(m.get("nomeBanco")) or _norm(m.get("banco"))
                })[:80],
                "movimentos": _uniq("movimento"),
                "debito_credito": _uniq("debitoCredito"),
            },
            "lancamentos_filtrados": len(filtrados),
            "lancamentos": lancamentos,
            "preview": movimentos[:preview_n] if preview_n else [],
        }


_cliente: Optional[GovApiClient] = None


def get_gov_client() -> GovApiClient:
    global _cliente
    if _cliente is None:
        _cliente = GovApiClient()
    return _cliente
