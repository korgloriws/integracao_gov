import pandas as pd
import os

def extrair_valor_segmento_z(segmento_z: str) -> float:
  
    if not segmento_z or len(segmento_z) < 11:
        return 0.0

    try:
        valor_str = ''.join(filter(str.isdigit, segmento_z[-11:])) 
        valor_reais = int(valor_str) / 100  
        return valor_reais
    except ValueError:
        return 0.0

def gerar_relatorio_mab(mab_resultados, nome_arquivo="relatorio_mab.xlsx", mes=None, ano=2026):
  

    lancamentos = []

    for item in mab_resultados["resultados"]:
        banco = item["banco"]
        segmento_z = item["segmento_z"]
        valor = extrair_valor_segmento_z(segmento_z)

        data_str = banco[-4:]  
        if len(data_str) != 4 or not data_str.isdigit():
            continue 

        dia, mes_arquivo = data_str[:2], data_str[2:4]
        data_formatada = f"{dia}/{mes_arquivo}/{ano}"

      
        if mes and mes_arquivo != mes:
            continue

        lancamentos.append({"Data": data_formatada, "Banco": banco, "Valor": valor})


    df_lancamentos = pd.DataFrame(lancamentos)

 
    if not df_lancamentos.empty:
        df_totais = df_lancamentos.groupby("Data").agg(
            Total_Bancos=("Valor", "sum"),
            Total_CEF=("Valor", lambda x: x[df_lancamentos["Banco"].str.startswith("cef")].sum()),
            Total_Banco_Brasil=("Valor", lambda x: x[~df_lancamentos["Banco"].str.startswith("cef")].sum())
        ).reset_index()
    else:
        df_totais = pd.DataFrame(columns=["Data", "Total_Bancos", "Total_CEF", "Total_Banco_brasil"])

    caminho_absoluto = os.path.abspath(nome_arquivo)

    with pd.ExcelWriter(caminho_absoluto, engine="xlsxwriter") as writer:

        df_lancamentos.to_excel(writer, sheet_name="MAB", index=False)
        df_totais.to_excel(writer, sheet_name="Totais_MAB", index=False)

    return caminho_absoluto




def gerar_relatorio_mcr(mcr_resultados, nome_arquivo="relatorio_mcr.xlsx", mes=None, ano=2026):

    if "resultados_filtrados" not in mcr_resultados or not mcr_resultados["resultados_filtrados"]:
        return {"erro": "Não há dados disponíveis para gerar o relatório do MCR."}

    lancamentos = []
    totais_por_banco = []
    totais_por_categoria = []

    for item in mcr_resultados["resultados_filtrados"]:
        banco = item["banco"]
        
        for registro in item["dados"]:
            # Chaves geradas por main.py.extrair_dados_classificacao:
            #   "Natureza_da_Receita", "liquido", "categoria"
            natureza = registro.get("Natureza_da_Receita") or registro.get("Natureza da Receita", "")
            liquido_raw = registro.get("liquido", registro.get("Líquido", "0"))
            try:
                # aceita tanto "1234.56" quanto "1.234,56" (formato BR)
                liquido_str = str(liquido_raw).strip().replace(".", "").replace(",", ".") \
                    if "," in str(liquido_raw) else str(liquido_raw).strip()
                valor = float(liquido_str) if liquido_str not in ("", "nan", "None") else 0.0
            except (ValueError, TypeError):
                valor = 0.0
            categoria = registro.get("categoria", "")

  
            data_str = banco[:4]  
            if len(data_str) != 4 or not data_str.isdigit():
                continue

            dia, mes_arquivo = data_str[:2], data_str[2:4]
            data_formatada = f"{dia}/{mes_arquivo}/{ano}"


            if mes and mes_arquivo != mes:
                continue


            lancamentos.append({"Data": data_formatada, "Banco": banco, "Categoria": categoria, "Valor": valor})


    df_lancamentos = pd.DataFrame(lancamentos)


    if not df_lancamentos.empty:
        df_totais = df_lancamentos.groupby(["Data", "Banco"]).agg(
            Total_Banco=("Valor", "sum")
        ).reset_index()

        df_totais_categoria = df_lancamentos.groupby(["Data", "Categoria", "Banco"]).agg(
            Total_Categoria=("Valor", "sum")
        ).reset_index()
    else:
        df_totais = pd.DataFrame(columns=["Data", "Banco", "Total_Banco"])
        df_totais_categoria = pd.DataFrame(columns=["Data", "Categoria", "Banco", "Total_Categoria"])


    caminho_absoluto = os.path.abspath(nome_arquivo)

    with pd.ExcelWriter(caminho_absoluto, engine="xlsxwriter") as writer:
        df_lancamentos.to_excel(writer, sheet_name="MCR", index=False)
        df_totais.to_excel(writer, sheet_name="Totais_MCR", index=False)
        df_totais_categoria.to_excel(writer, sheet_name="Totais_Categoria", index=False)

    return caminho_absoluto

