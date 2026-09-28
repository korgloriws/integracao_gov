"""Agendamento diário: gera pacote, confere MAB×MCR e envia ao S3 só se bater."""
from __future__ import annotations

import json
import os
import threading
import time
from copy import deepcopy
from datetime import date, datetime
from typing import Any, Dict, Optional
from zoneinfo import ZoneInfo

from carregar_env import diretorio_projeto

TZ_PADRAO = "America/Sao_Paulo"
ARQUIVO_CFG = "agendamento.json"

_DEFAULT: Dict[str, Any] = {
    "ativo": False,
    "hora": "15:00",
    "timezone": TZ_PADRAO,
    "tipos": "todos",
    "enviar_se_bater": True,
    "dias_uteis_apenas": True,
    "fonte_nomenclatura": "banco",
    "calendario_feriados": "nacional",
    "tentar_municipal_se_zerado": True,
    "incluir_facultativos": False,
    "ultima_execucao": None,
    "ultima_chave": None,
}

_lock = threading.RLock()
_stop = threading.Event()
_thread: Optional[threading.Thread] = None


def _caminho_cfg() -> str:
    pasta = os.path.join(diretorio_projeto(), "data")
    os.makedirs(pasta, exist_ok=True)
    return os.path.join(pasta, ARQUIVO_CFG)


def _agora(tz_name: str = TZ_PADRAO) -> datetime:
    try:
        return datetime.now(ZoneInfo(tz_name or TZ_PADRAO))
    except Exception:
        return datetime.now(ZoneInfo(TZ_PADRAO))


def carregar_config() -> Dict[str, Any]:
    with _lock:
        caminho = _caminho_cfg()
        cfg = deepcopy(_DEFAULT)
        if os.path.exists(caminho):
            try:
                with open(caminho, "r", encoding="utf-8") as f:
                    dados = json.load(f)
                if isinstance(dados, dict):
                    cfg.update({k: dados.get(k, cfg[k]) for k in cfg.keys()})
            except Exception:
                pass
        hora = str(cfg.get("hora") or "15:00").strip()
        if len(hora) == 4 and hora[1] == ":":
            hora = "0" + hora
        if len(hora) >= 5:
            cfg["hora"] = hora[:5]
        if cfg.get("calendario_feriados") in (None, ""):
            cfg["calendario_feriados"] = "nacional"
        if "tentar_municipal_se_zerado" not in cfg:
            cfg["tentar_municipal_se_zerado"] = True
        return cfg


def salvar_config(novos: Dict[str, Any]) -> Dict[str, Any]:
    with _lock:
        cfg = carregar_config()
        if "ativo" in novos:
            cfg["ativo"] = bool(novos["ativo"])
        if "hora" in novos and novos["hora"] is not None:
            hora = str(novos["hora"]).strip()
            partes = hora.split(":")
            if len(partes) >= 2:
                cfg["hora"] = f"{int(partes[0]):02d}:{int(partes[1]):02d}"
        if "timezone" in novos and novos["timezone"]:
            cfg["timezone"] = str(novos["timezone"]).strip()
        if "tipos" in novos and novos["tipos"] is not None:
            cfg["tipos"] = str(novos["tipos"]).strip() or "todos"
        if "enviar_se_bater" in novos:
            cfg["enviar_se_bater"] = bool(novos["enviar_se_bater"])
        if "dias_uteis_apenas" in novos:
            cfg["dias_uteis_apenas"] = bool(novos["dias_uteis_apenas"])
        if "fonte_nomenclatura" in novos:
            fonte = str(novos["fonte_nomenclatura"] or "").strip().lower()
            cfg["fonte_nomenclatura"] = fonte if fonte in ("banco", "local") else "banco"
        if "calendario_feriados" in novos:
            cal = novos["calendario_feriados"]
            if cal in (None, "", "nenhum", "none", "off", "nao", "não"):
                cfg["calendario_feriados"] = "off"
            else:
                cfg["calendario_feriados"] = str(cal).strip().lower()
        if "tentar_municipal_se_zerado" in novos:
            cfg["tentar_municipal_se_zerado"] = bool(novos["tentar_municipal_se_zerado"])
        if "incluir_facultativos" in novos:
            cfg["incluir_facultativos"] = bool(novos["incluir_facultativos"])
        # preserva ultima_execucao / ultima_chave
        with open(_caminho_cfg(), "w", encoding="utf-8") as f:
            json.dump(cfg, f, ensure_ascii=False, indent=2)
        return cfg


def _gravar_ultima(cfg_parcial: Dict[str, Any]) -> Dict[str, Any]:
    with _lock:
        cfg = carregar_config()
        cfg.update(cfg_parcial)
        with open(_caminho_cfg(), "w", encoding="utf-8") as f:
            json.dump(cfg, f, ensure_ascii=False, indent=2)
        return cfg


def _chave_execucao(cfg: Dict[str, Any], agora: datetime) -> str:
    return f"{agora.date().isoformat()}|{cfg.get('hora')}"


def _deve_rodar_agora(cfg: Dict[str, Any], agora: datetime) -> bool:
    if not cfg.get("ativo"):
        return False
    hora = str(cfg.get("hora") or "15:00")[:5]
    if agora.strftime("%H:%M") != hora:
        return False
    if cfg.get("dias_uteis_apenas") and agora.weekday() >= 5:
        return False
    if cfg.get("ultima_chave") == _chave_execucao(cfg, agora):
        return False
    return True


def executar_rotina(forcar: bool = False, data_alvo: Optional[date] = None) -> Dict[str, Any]:
    """
    Gera o pacote do dia, confere MAB×MCR e envia ao S3 somente se bateu
    (quando enviar_se_bater=True).
    """
    # import local evita ciclo na carga do main
    from main import (
        _enviar_pacote_para_s3,
        _gerar_pacote_do_dia,
        _parse_tipos_arquivo,
    )

    cfg = carregar_config()
    agora = _agora(cfg.get("timezone"))
    alvo = data_alvo or agora.date()
    tipos = _parse_tipos_arquivo(cfg.get("tipos") or "todos")
    inicio_iso = datetime.now().isoformat()

    resultado: Dict[str, Any] = {
        "inicio": inicio_iso,
        "fim": None,
        "data_alvo": alvo.strftime("%d/%m/%Y"),
        "hora_config": cfg.get("hora"),
        "forcar": bool(forcar),
        "tipos": tipos,
        "gerado": False,
        "bateu": None,
        "enviado": False,
        "mensagem": "",
        "erros": [],
        "conferencia": None,
        "envio_s3": None,
        "pacote": None,
    }

    try:
        if cfg.get("dias_uteis_apenas") and alvo.weekday() >= 5 and not forcar:
            resultado["mensagem"] = "Dia não útil — rotina ignorada."
            resultado["fim"] = datetime.now().isoformat()
            _gravar_ultima({
                "ultima_execucao": resultado,
                "ultima_chave": _chave_execucao(cfg, agora) if not forcar else cfg.get("ultima_chave"),
            })
            return resultado

        # Padrão: calendário nacional. Se MAB continuar zerado, tenta municipal.
        calendario_cfg = cfg.get("calendario_feriados")
        if calendario_cfg in (None, "", "nenhum", "none"):
            calendario_cfg = "nacional"
        calendario_cfg = str(calendario_cfg).strip().lower()
        calendario = None if calendario_cfg == "off" else calendario_cfg
        tentar_municipal = bool(cfg.get("tentar_municipal_se_zerado", True))
        facultativos = bool(cfg.get("incluir_facultativos"))

        item = _gerar_pacote_do_dia(
            alvo.day,
            alvo.month,
            alvo.year,
            tipos,
            pasta_saida="saida_pacotes",
            enviar_s3=False,
            salvar_local=True,
            calendario_feriados=calendario,
            incluir_facultativos=facultativos,
        )
        resultado["calendario_usado"] = calendario or "nenhum"
        resultado["tentou_municipal"] = False

        # Fallback: se ainda zerado e o primeiro passo não foi municipal, tenta Contagem.
        # (Com nacional padrão, cobre feriado só municipal; com off, ainda tenta municipal se pedido.)
        if item.get("mab_vazio") and tentar_municipal and calendario != "municipal":
            # Se estava off/sem calendário, tenta nacional antes do municipal
            if calendario is None:
                item_nac = _gerar_pacote_do_dia(
                    alvo.day,
                    alvo.month,
                    alvo.year,
                    tipos,
                    pasta_saida="saida_pacotes",
                    enviar_s3=False,
                    salvar_local=True,
                    calendario_feriados="nacional",
                    incluir_facultativos=facultativos,
                )
                if not item_nac.get("mab_vazio"):
                    item = item_nac
                    calendario = "nacional"
                    resultado["calendario_usado"] = "nacional"
                    resultado["mensagem_feriado"] = (
                        "MAB zerado sem calendário; regenerado com calendário nacional."
                    )
            if item.get("mab_vazio"):
                item_mun = _gerar_pacote_do_dia(
                    alvo.day,
                    alvo.month,
                    alvo.year,
                    tipos,
                    pasta_saida="saida_pacotes",
                    enviar_s3=False,
                    salvar_local=True,
                    calendario_feriados="municipal",
                    incluir_facultativos=facultativos,
                )
                resultado["tentou_municipal"] = True
                resultado["calendario_nacional_mab_vazio"] = True
                if not item_mun.get("mab_vazio"):
                    item = item_mun
                    calendario = "municipal"
                    resultado["calendario_usado"] = "municipal"
                    resultado["mensagem_feriado"] = (
                        "MAB zerado com calendário nacional; regenerado com municipal Contagem."
                    )
                else:
                    resultado["mensagem_feriado"] = (
                        "MAB zerado no nacional e também no municipal — conferir pasta/arquivos."
                    )

        resultado["gerado"] = True
        resultado["pacote"] = {
            "sucesso": item.get("sucesso"),
            "data_alvo": item.get("data_alvo"),
            "data_mab_filtro": item.get("data_mab_filtro"),
            "mab_vazio": item.get("mab_vazio"),
            "alerta_zerado": item.get("alerta_zerado"),
            "calendario_feriados": item.get("calendario_feriados") or calendario,
            "erros": item.get("erros") or [],
            "resumo": item.get("resumo"),
            "conferencia_mab_mcr": item.get("conferencia_mab_mcr"),
        }
        if item.get("erros"):
            resultado["erros"].extend(item["erros"])

        conf = item.get("conferencia_mab_mcr")
        resultado["conferencia"] = conf
        precisa_mcr = "mcr" in tipos and "mab" in tipos
        if precisa_mcr:
            bateu = bool(conf and conf.get("bateu"))
        else:
            # sem MCR no pacote: considera ok se gerou sem erros e MAB não zerado (se pedido)
            bateu = bool(item.get("sucesso")) and not item.get("mab_vazio")
        resultado["bateu"] = bateu

        if item.get("mab_vazio"):
            resultado["mensagem"] = (
                "MAB veio zerado após calendário nacional"
                + (" e municipal" if resultado.get("tentou_municipal") else "")
                + ". Não enviado. Confira feriados/pasta na interface."
            )
        elif not item.get("sucesso") or (item.get("erros") and precisa_mcr and not bateu):
            resultado["mensagem"] = (
                "Geração com erros ou conferência incompleta — não enviado. Confira o pacote."
            )
        elif precisa_mcr and not bateu:
            resultado["mensagem"] = (
                "MCR × MAB não bateu — pacote gerado e salvo, mas NÃO enviado ao S3. "
                "Confera os valores na interface."
            )
        elif cfg.get("enviar_se_bater") is False:
            resultado["mensagem"] = (
                "Pacote gerado e conferido. Envio automático desligado nas ferramentas."
            )
        elif not bateu:
            resultado["mensagem"] = "Conferência não aprovada — não enviado."
        else:
            # envia
            envio = _enviar_pacote_para_s3(
                item.get("data_alvo"),
                {k: (item.get("conteudo") or {}).get(k) for k in tipos},
                fonte_nomenclatura=cfg.get("fonte_nomenclatura") or "banco",
            )
            resultado["envio_s3"] = {
                "sucesso": envio.get("sucesso"),
                "mensagem": envio.get("mensagem"),
                "precisa_escolha": envio.get("precisa_escolha"),
                "erros": envio.get("erros") or [],
                "arquivos": envio.get("arquivos") or [],
            }
            if envio.get("precisa_escolha"):
                resultado["mensagem"] = (
                    "Pacote ok, mas nomenclatura S3 divergiu (API Banco × índice local). "
                    "Não enviado automaticamente — escolha a fonte na interface."
                )
                resultado["erros"].append("precisa_escolha_nomenclatura")
            elif envio.get("sucesso"):
                resultado["enviado"] = True
                extra = resultado.get("mensagem_feriado") or ""
                resultado["mensagem"] = (
                    "Pacote gerado, conferência bateu e envio ao S3 concluído."
                    + ((" " + extra) if extra else "")
                )
            else:
                resultado["mensagem"] = "Conferência bateu, mas falhou o envio ao S3."
                resultado["erros"].extend(envio.get("erros") or [envio.get("mensagem") or "falha S3"])

        if resultado.get("mensagem_feriado") and not resultado.get("enviado") and not item.get("mab_vazio"):
            # reforça contexto do fallback municipal quando ainda há mensagem pendente de envio
            if resultado.get("mensagem") and resultado["mensagem_feriado"] not in resultado["mensagem"]:
                resultado["mensagem"] = resultado["mensagem_feriado"] + " " + resultado["mensagem"]

    except Exception as e:
        resultado["erros"].append(str(e))
        resultado["mensagem"] = f"Falha na rotina automática: {e}"

    resultado["fim"] = datetime.now().isoformat()
    chave = _chave_execucao(cfg, agora)
    _gravar_ultima({
        "ultima_execucao": resultado,
        "ultima_chave": chave if not forcar else (cfg.get("ultima_chave") or chave),
    })
    # se forcar no mesmo minuto do agendamento, marca chave para não duplicar
    if forcar and agora.strftime("%H:%M") == str(cfg.get("hora") or "")[:5]:
        _gravar_ultima({"ultima_chave": chave, "ultima_execucao": resultado})
    return resultado


def _loop():
    while not _stop.is_set():
        try:
            cfg = carregar_config()
            agora = _agora(cfg.get("timezone"))
            if _deve_rodar_agora(cfg, agora):
                # marca chave antes para evitar corrida em dois ticks
                _gravar_ultima({"ultima_chave": _chave_execucao(cfg, agora)})
                executar_rotina(forcar=False)
        except Exception as e:
            try:
                _gravar_ultima({
                    "ultima_execucao": {
                        "fim": datetime.now().isoformat(),
                        "mensagem": f"Erro no loop do agendador: {e}",
                        "erros": [str(e)],
                    }
                })
            except Exception:
                pass
        _stop.wait(20)


def iniciar_agendador() -> None:
    global _thread
    with _lock:
        if _thread and _thread.is_alive():
            return
        _stop.clear()
        _thread = threading.Thread(target=_loop, name="agendamento-sefaz", daemon=True)
        _thread.start()


def parar_agendador() -> None:
    _stop.set()
    t = _thread
    if t and t.is_alive():
        t.join(timeout=2)


def status_agendador() -> Dict[str, Any]:
    cfg = carregar_config()
    agora = _agora(cfg.get("timezone"))
    return {
        "sucesso": True,
        "agora": agora.isoformat(),
        "thread_ativa": bool(_thread and _thread.is_alive()),
        "config": cfg,
        "proxima_dica": (
            f"Dispara às {cfg.get('hora')} ({cfg.get('timezone')}) "
            f"{'em dias úteis' if cfg.get('dias_uteis_apenas') else 'todos os dias'}; "
            f"{'envia S3 se bater' if cfg.get('enviar_se_bater') else 'só gera/confere'}; "
            f"feriados={cfg.get('calendario_feriados') or 'nacional'}; "
            f"{'se MAB zerar tenta municipal' if cfg.get('tentar_municipal_se_zerado', True) else 'sem fallback municipal'}."
        ),
    }
