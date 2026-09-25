"""Calendários de feriados nacionais e municipais (Contagem/MG).

Nacional: baixado da BrasilAPI e cacheado em data/.
Municipal: arquivo local editável (decreto Contagem), com opção de atualizar manualmente.
"""
from __future__ import annotations

import json
import os
from datetime import date, datetime, timedelta
from typing import Any, Dict, List, Optional, Set

import requests
from carregar_env import diretorio_projeto

BRASILAPI_FERIADOS = "https://brasilapi.com.br/api/feriados/v1/{ano}"


def _pasta_data() -> str:
    pasta = os.path.join(diretorio_projeto(), "data")
    os.makedirs(pasta, exist_ok=True)
    return pasta


def _caminho_nacional(ano: int) -> str:
    return os.path.join(_pasta_data(), f"feriados_nacionais_{ano}.json")


def _caminho_municipal(ano: int) -> str:
    return os.path.join(_pasta_data(), f"feriados_municipais_contagem_{ano}.json")


def _norm_iso(data_iso: str) -> str:
    return str(data_iso or "").strip()[:10]


def _parse_data(valor) -> Optional[date]:
    texto = str(valor or "").strip()
    if not texto:
        return None
    for fmt in ("%Y-%m-%d", "%d/%m/%Y", "%d-%m-%Y"):
        try:
            return datetime.strptime(texto[:10], fmt).date()
        except ValueError:
            continue
    return None


def _feriados_municipais_padrao_2026() -> List[Dict[str, Any]]:
    """Baseado no Decreto Contagem 2026 (feriados e pontos facultativos)."""
    return [
        {"date": "2026-01-02", "name": "Recesso pós Confraternização Universal", "type": "facultativo", "origem": "municipal"},
        {"date": "2026-02-16", "name": "Carnaval", "type": "facultativo", "origem": "municipal"},
        {"date": "2026-02-17", "name": "Carnaval", "type": "facultativo", "origem": "municipal"},
        {"date": "2026-02-18", "name": "Quarta-feira de Cinzas", "type": "facultativo", "origem": "municipal"},
        {"date": "2026-03-27", "name": "Jubileu de Nossa Senhora das Dores", "type": "feriado", "origem": "municipal"},
        {"date": "2026-04-02", "name": "Quinta-feira Santa", "type": "facultativo", "origem": "municipal"},
        {"date": "2026-04-03", "name": "Paixão de Cristo", "type": "feriado", "origem": "municipal"},
        {"date": "2026-04-20", "name": "Emenda Tiradentes", "type": "facultativo", "origem": "municipal"},
        {"date": "2026-06-04", "name": "Corpus Christi", "type": "feriado", "origem": "municipal"},
        {"date": "2026-06-05", "name": "Emenda Corpus Christi", "type": "facultativo", "origem": "municipal"},
        {"date": "2026-08-30", "name": "Dia do Município de Contagem", "type": "facultativo", "origem": "municipal"},
        {"date": "2026-10-30", "name": "Dia do Servidor Público", "type": "facultativo", "origem": "municipal"},
        {"date": "2026-12-08", "name": "Jubileu de Nossa Senhora da Conceição", "type": "feriado", "origem": "municipal"},
        {"date": "2026-12-24", "name": "Véspera de Natal", "type": "facultativo", "origem": "municipal"},
        {"date": "2026-12-31", "name": "Véspera de Ano Novo", "type": "facultativo", "origem": "municipal"},
    ]


def atualizar_feriados_nacionais(ano: int = 2026) -> Dict[str, Any]:
    url = BRASILAPI_FERIADOS.format(ano=int(ano))
    resp = requests.get(url, timeout=20)
    if resp.status_code != 200:
        return {
            "sucesso": False,
            "mensagem": f"Falha ao baixar feriados nacionais: HTTP {resp.status_code}",
            "body": (resp.text or "")[:500],
        }
    dados = resp.json()
    if not isinstance(dados, list):
        return {"sucesso": False, "mensagem": "Resposta inesperada da BrasilAPI."}
    itens = []
    for item in dados:
        if not isinstance(item, dict):
            continue
        data_iso = _norm_iso(item.get("date"))
        if not data_iso:
            continue
        itens.append({
            "date": data_iso,
            "name": item.get("name") or "Feriado nacional",
            "type": "feriado",
            "origem": "nacional",
            "weekday": item.get("weekday"),
        })
    payload = {
        "ano": int(ano),
        "fonte": url,
        "atualizado_em": datetime.now().isoformat(),
        "itens": itens,
    }
    caminho = _caminho_nacional(ano)
    with open(caminho, "w", encoding="utf-8") as f:
        json.dump(payload, f, ensure_ascii=False, indent=2)
    return {
        "sucesso": True,
        "mensagem": f"Calendário nacional {ano} atualizado ({len(itens)} datas).",
        "caminho": caminho,
        "total": len(itens),
        "itens": itens,
    }


def garantir_feriados_municipais(ano: int = 2026) -> Dict[str, Any]:
    caminho = _caminho_municipal(ano)
    if os.path.exists(caminho):
        with open(caminho, "r", encoding="utf-8") as f:
            dados = json.load(f)
        return {
            "sucesso": True,
            "mensagem": "Calendário municipal já existe.",
            "caminho": caminho,
            "total": len(dados.get("itens") or []),
            "itens": dados.get("itens") or [],
            "criado": False,
        }
    if int(ano) != 2026:
        payload = {
            "ano": int(ano),
            "fonte": "manual",
            "cidade": "Contagem/MG",
            "atualizado_em": datetime.now().isoformat(),
            "itens": [],
            "observacao": "Preencha os feriados municipais deste ano manualmente neste arquivo.",
        }
    else:
        payload = {
            "ano": 2026,
            "fonte": "Decreto Contagem 2026 (feriados/facultativos) + Lei 3.484/2001",
            "cidade": "Contagem/MG",
            "atualizado_em": datetime.now().isoformat(),
            "itens": _feriados_municipais_padrao_2026(),
        }
    with open(caminho, "w", encoding="utf-8") as f:
        json.dump(payload, f, ensure_ascii=False, indent=2)
    return {
        "sucesso": True,
        "mensagem": f"Calendário municipal Contagem {ano} criado.",
        "caminho": caminho,
        "total": len(payload.get("itens") or []),
        "itens": payload.get("itens") or [],
        "criado": True,
    }


def carregar_calendario(calendario: str, ano: int = 2026, atualizar_se_faltando: bool = True) -> Dict[str, Any]:
    cal = str(calendario or "").strip().lower()
    ano = int(ano)
    if cal in ("nacional", "nacional_br", "br", "federal"):
        caminho = _caminho_nacional(ano)
        if not os.path.exists(caminho) and atualizar_se_faltando:
            baixado = atualizar_feriados_nacionais(ano)
            if not baixado.get("sucesso"):
                return baixado
        if not os.path.exists(caminho):
            return {"sucesso": False, "mensagem": f"Calendário nacional {ano} não encontrado."}
        with open(caminho, "r", encoding="utf-8") as f:
            dados = json.load(f)
        return {
            "sucesso": True,
            "calendario": "nacional",
            "ano": ano,
            "caminho": caminho,
            "fonte": dados.get("fonte"),
            "atualizado_em": dados.get("atualizado_em"),
            "itens": dados.get("itens") or [],
        }

    if cal in ("municipal", "contagem", "municipio"):
        garantia = garantir_feriados_municipais(ano)
        with open(_caminho_municipal(ano), "r", encoding="utf-8") as f:
            dados = json.load(f)
        return {
            "sucesso": True,
            "calendario": "municipal",
            "ano": ano,
            "caminho": _caminho_municipal(ano),
            "fonte": dados.get("fonte"),
            "atualizado_em": dados.get("atualizado_em"),
            "itens": dados.get("itens") or [],
            "criado": garantia.get("criado"),
        }

    return {"sucesso": False, "mensagem": "Calendário inválido. Use nacional ou municipal."}


def conjunto_datas_feriado(
    calendario: str,
    ano: int = 2026,
    incluir_facultativos: bool = False,
) -> Set[date]:
    dados = carregar_calendario(calendario, ano=ano)
    saida: Set[date] = set()
    if not dados.get("sucesso"):
        return saida
    for item in dados.get("itens") or []:
        tipo = str(item.get("type") or "feriado").lower()
        if tipo.startswith("facult") and not incluir_facultativos:
            continue
        dt = _parse_data(item.get("date"))
        if dt:
            saida.add(dt)
    return saida


def consultar_data_no_calendario(
    data_ref,
    calendario: str,
    incluir_facultativos: bool = False,
) -> Dict[str, Any]:
    dt = data_ref if isinstance(data_ref, date) else _parse_data(data_ref)
    if not dt:
        return {"sucesso": False, "mensagem": "Data inválida."}
    dados = carregar_calendario(calendario, ano=dt.year)
    if not dados.get("sucesso"):
        return dados
    encontrados = []
    for item in dados.get("itens") or []:
        item_dt = _parse_data(item.get("date"))
        if item_dt != dt:
            continue
        tipo = str(item.get("type") or "feriado").lower()
        if tipo.startswith("facult") and not incluir_facultativos:
            continue
        encontrados.append(item)
    eh_feriado = any(not str(i.get("type") or "").lower().startswith("facult") for i in encontrados)
    eh_facultativo = any(str(i.get("type") or "").lower().startswith("facult") for i in encontrados)
    return {
        "sucesso": True,
        "calendario": dados.get("calendario"),
        "data": dt.strftime("%d/%m/%Y"),
        "data_iso": dt.isoformat(),
        "eh_feriado": eh_feriado,
        "eh_facultativo": eh_facultativo and not eh_feriado,
        "itens": encontrados,
        "fonte": dados.get("fonte"),
    }


def dia_util_anterior_com_feriados(
    dia: int,
    mes: int,
    ano: int = 2026,
    feriados: Optional[Set[date]] = None,
) -> date:
    data = date(int(ano), int(mes), int(dia))
    anterior = data - timedelta(days=1)
    feriados = feriados or set()
    while anterior.weekday() >= 5 or anterior in feriados:
        anterior -= timedelta(days=1)
    return anterior


def verificar_mab_por_calendario(
    dia: int,
    mes: int,
    ano: int = 2026,
    calendario: str = "nacional",
    incluir_facultativos: bool = False,
) -> Dict[str, Any]:
    """Compara o MAB atual (só sáb/dom) com o MAB sugerido pulando feriados do calendário."""
    from datetime import date as date_cls

    data_alvo = date_cls(int(ano), int(mes), int(dia))
    # regra padrão atual do sistema
    mab_atual = data_alvo - timedelta(days=1)
    while mab_atual.weekday() >= 5:
        mab_atual -= timedelta(days=1)

    consulta_alvo = consultar_data_no_calendario(data_alvo, calendario, incluir_facultativos)
    consulta_mab = consultar_data_no_calendario(mab_atual, calendario, incluir_facultativos)
    if not consulta_mab.get("sucesso"):
        return consulta_mab

    feriados = conjunto_datas_feriado(calendario, ano=ano, incluir_facultativos=incluir_facultativos)
    mab_sugerido = dia_util_anterior_com_feriados(dia, mes, ano, feriados=feriados)
    mudou = mab_sugerido != mab_atual

    return {
        "sucesso": True,
        "calendario": consulta_mab.get("calendario"),
        "data_alvo": data_alvo.strftime("%d/%m/%Y"),
        "data_mab_atual": mab_atual.strftime("%d/%m/%Y"),
        "data_mab_sugerida": mab_sugerido.strftime("%d/%m/%Y"),
        "mab_atual_eh_feriado": bool(consulta_mab.get("eh_feriado")),
        "mab_atual_eh_facultativo": bool(consulta_mab.get("eh_facultativo")),
        "alvo_eh_feriado": bool(consulta_alvo.get("eh_feriado")),
        "itens_mab": consulta_mab.get("itens") or [],
        "itens_alvo": consulta_alvo.get("itens") or [],
        "deve_ajustar": mudou and (consulta_mab.get("eh_feriado") or (incluir_facultativos and consulta_mab.get("eh_facultativo"))),
        "mensagem": (
            f"O filtro MAB {mab_atual.strftime('%d/%m/%Y')} é feriado no calendário {consulta_mab.get('calendario')}. "
            f"Sugestão: usar {mab_sugerido.strftime('%d/%m/%Y')}."
            if mudou and consulta_mab.get("eh_feriado")
            else (
                f"O filtro MAB {mab_atual.strftime('%d/%m/%Y')} é ponto facultativo. "
                f"Sugestão: usar {mab_sugerido.strftime('%d/%m/%Y')}."
                if mudou and consulta_mab.get("eh_facultativo")
                else f"No calendário {consulta_mab.get('calendario')}, o MAB {mab_atual.strftime('%d/%m/%Y')} não exige ajuste."
            )
        ),
    }
