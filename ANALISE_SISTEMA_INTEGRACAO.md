# Análise minuciosa do sistema de integração

Este documento descreve como o sistema funciona no processo de integração entre **dois sistemas distintos**: a **API de processamento local (main.py)** e o **AWS Manager (aws_interface.py + API AWS)**.

---

## 1. Visão geral da arquitetura

```
┌─────────────────────────────────────────────────────────────────────────────┐
│  SISTEMA 1: Fontes de dados locais (OneDrive)                                │
│  • Arquivos FEBRABRAN (.ret) – MAB                                            │
│  • Arquivos SAFCI (XLS) – MCR (classificação)                                 │
│  • Renúncia e Desconto / Arquivos SAFCI (.txt) – Deduções                    │
└───────────────────────────────────┬─────────────────────────────────────────┘
                                    │ leitura em disco
                                    ▼
┌─────────────────────────────────────────────────────────────────────────────┐
│  API PRINCIPAL (main.py) – FastAPI, porta 8000 (típico)                       │
│  • Processa pastas, filtra por dia/mês                                        │
│  • Agrega MAB (CEF + demais → Brasil)                                         │
│  • Expõe JSON para download (MAB, MCR, Renúncias, Descontos, Deduções, Todos) │
│  • Página HTML com sidebar para acessar endpoints                             │
└───────────────────────────────────┬─────────────────────────────────────────┘
                                    │
                    Fluxo manual: usuário baixa JSON e envia
                    (ou envia arquivo JSON na interface)
                                    │
                                    ▼
┌─────────────────────────────────────────────────────────────────────────────┐
│  AWS MANAGER INTERFACE (aws_interface.py) – FastAPI, porta 8001              │
│  • Interface web (tema claro/escuro)                                          │
│  • Upload de JSON (arquivo ou corpo) → enviar_dados_visivel()                │
│  • Lista/obtém/deleta arquivos (cache local + API AWS)                       │
└───────────────────────────────────┬─────────────────────────────────────────┘
                                    │ PUT/GET (x-api-key)
                                    ▼
┌─────────────────────────────────────────────────────────────────────────────┐
│  SISTEMA 2: API AWS (Lambda + S3)                                            │
│  • URL: https://kth8z2yge5.execute-api.sa-east-1.amazonaws.com/prod/files   │
│  • Estrutura: pastas MAB, MCR, DESCONTOS, RENUNCIAS, OUTROS                  │
│  • Arquivos JSON organizados por tipo e data                                  │
└─────────────────────────────────────────────────────────────────────────────┘
```

**Resumo:** Não há chamada automática da AWS Interface para a API principal. O fluxo é **manual**: o usuário obtém os JSON na API principal (por dia/mês) e depois envia para a AWS pela interface (upload de arquivo ou envio via “Enviar JSON”).

---

## 2. Sistema 1 – API principal (main.py)

### 2.1 Fontes de dados (caminhos)

| Módulo   | Finalidade        | Caminhos base |
|----------|-------------------|----------------|
| **MAB**  | Arrecadação bancária (FEBRABRAN) | `OneDrive.../Arquivos FEBRABRAN/{BANCO}/{PASTA}` (INTER, BANCOOB, BB, BRADESCO, CEF, ITAU, MERCANTIL, SANTANDER) |
| **MCR**  | Classificação (SAFCI) | `caminhos_classificacao` – pastas fixas por mês, ex.: `.../2025/Fevereiro 2025/Arquivos SAFCI` |
| **Deduções** | Renúncia (91) e Desconto (93) | Dinâmico: `gerar_caminhos_deducoes_dinamicos()` busca pasta "Renúncia e Desconto" em cada mês e adiciona `.../Arquivos SAFCI` |

- **MAB:** lista fixa `caminhos_base` (uma pasta por banco/ano).
- **MCR:** lista `caminhos_classificacao` (vários meses, cada um com `.../Arquivos SAFCI`).
- **Deduções:** caminhos gerados por mês a partir da pasta "Renúncia e Desconto" + "Arquivos SAFCI".

### 2.2 Processamento por módulo

**MAB (Movimento de Arrecadação Bancária)**  
- Lê arquivos `.ret`, `.RET`, `.txt` em cada `caminhos_base`.  
- Extrai segmentos **A** e **Z** (função `recuperar_segmentos_ret`).  
- O valor monetário está no final do segmento Z (bloco numérico).  
- **Agregação:** mantém CEF (código 4066) separada; soma os demais bancos no **Brasil** (código 6112). Função `agregar_resultados_mab`.  
- Filtro por dia/mês: `banco.endswith(f"{dia:02d}{mes:02d}")` (sufixo do nome do arquivo/pasta).

**MCR (Classificação)**  
- Lê planilhas XLS/XLSX em `caminhos_classificacao`.  
- Localiza linha "Total Líquido Geral:" e cabeçalho com "Natureza da Receita", "Líquido", "Descrição".  
- Extrai linhas de dados até linha em branco.  
- `codigo_resumido`: 6112 se banco termina com "bb", 4066 se "cef".  
- Filtro por dia/mês: `banco[:2] == dia_str and banco[2:4] == mes_str` (prefixo DDMM no nome do arquivo/banco).

**Deduções (Renúncia 91 / Desconto 93)**  
- Pastas por dia (ex.: `01`, `02`, ou `01-xx`) dentro de cada caminho de deduções.  
- Dentro de cada dia, lê arquivos `.txt` com formato `código; valor` (ex.: `91...; 123,45`).  
- Agrupa por arquivo: soma 91 (renúncia) e 93 (desconto), mantém `receitas_por_codigo` para detalhamento.  
- Data contábil: derivada do dia da pasta + mês/ano extraídos do caminho.  
- Filtro por dia/mês: compara `Data_Contabil` (DD/MM/YYYY) com dia/mês/2025.

### 2.3 Endpoints principais (main.py)

| Método | Rota | Uso |
|--------|------|-----|
| GET | `/` | Página HTML com sidebar (links e formulários para todos os recursos abaixo). |
| GET | `/testar_busca_pastas/` | Testa busca de pastas "Renúncia e Desconto" e "Arquivos SAFCI". |
| GET | `/processar/` | Processa todos os caminhos MAB; retorna `{ "resultados": [...] }`. |
| GET | `/filtrar_por_dia_mes/?dia=&mes=` | MAB filtrado por dia/mês. |
| GET | `/processar_classificacao/` | Processa MCR; retorna `resultados_filtrados` e `totais_por_banco`. |
| GET | `/filtrar_classificacao_por_dia_mes/?dia=&mes=` | MCR filtrado por dia/mês. |
| GET | `/processar_deducoes/` | Processa deduções (todos os caminhos dinâmicos). |
| GET | `/filtrar_deducoes_por_dia_mes/?dia=&mes=` | Deduções filtradas por dia/mês. |
| GET | `/download_mab_json/?dia=&mes=` | JSON MAB agregado (CEF + Brasil), pronto para integração. |
| GET | `/download_mcr_json/?dia=&mes=` | JSON MCR (com codigo_resumido). |
| GET | `/download_renuncias_json/?dia=&mes=` | Só renúncias (91). |
| GET | `/download_descontos_json/?dia=&mes=` | Só descontos (93). |
| GET | `/download_deducoes_json/?dia=&mes=` | Deduções completas (91+93) filtradas. |
| GET | `/download_todos_dados_json/?dia=&mes=` | Pacote único: MAB + MCR + deduções. |
| GET | `/gerar_relatorio_mab/?mes=` | Relatório Excel MAB (via `relatorios.gerar_relatorio_mab`). |
| GET | `/gerar_relatorio_mcr/?mes=` | Relatório Excel MCR (via `relatorios.gerar_relatorio_mcr`). |

- **download_*** endpoints retornam JSON (ou arquivo) já no formato usado na integração (datas, códigos, totais).  
- **gerar_relatorio_*** geram arquivos .xlsx no servidor e devolvem como download.

### 2.4 Funções utilitárias globais (main.py)

- `corrigir_caminho(caminho)` – prefixo `\\?\` no Windows para caminhos longos.  
- `normalizar_texto(texto)` – lower + remoção de acentos (NFD).  
- `encontrar_pasta_renuncia_desconto(caminho_base)` – localiza pasta "Renúncia e Desconto".  
- `gerar_caminhos_deducoes_dinamicos()` – lista de caminhos `.../Renúncia e Desconto/Arquivos SAFCI` por mês.  
- `calcular_dia_util_anterior / calcular_proximo_dia_util` – usados em MAB para `data_arrecadacao`.  
- `encontrar_pasta_mes(caminho_base, mes_desejado)` – busca pasta do mês por nome normalizado.

---

## 3. Sistema 2 – AWS Manager (aws_interface.py + aws_manager_visivel.py)

### 3.1 Papel de cada componente

- **aws_interface.py:** aplicação FastAPI (porta 8001) que serve a interface web e expõe APIs que, por sua vez, chamam `AWSManagerVisivel` e a API AWS.  
- **aws_manager_visivel.py:** classe que mantém estrutura em cache (`aws_cache_index.json`), gera IDs/nomes de arquivo, e envia/consulta a **API AWS** (Lambda + S3).

### 3.2 API AWS

- **Base:** `https://kth8z2yge5.execute-api.sa-east-1.amazonaws.com/prod/files`  
- **Autenticação:** header `x-api-key` (valor em `AWSManagerVisivel`: `aSbxVZ8Uoc4HUDSWTuJJ73ndTooBPKZCPZQZ8Eoj`).  
- **Estrutura remota:** pastas lógicas `MAB`, `MCR`, `DESCONTOS`, `RENUNCIAS`, `OUTROS`. Cada arquivo é um JSON com chave no formato `{PASTA}/{nome_arquivo}.json` (nome gerado por tipo, data_filtro, data_processamento).

### 3.3 Fluxo de envio para AWS

1. **Entrada de dados**  
   - Upload de arquivo JSON (formulário "Enviar arquivo") **ou**  
   - Envio via "Enviar JSON (PUT dinâmico)" (tipo + nome + corpo JSON).

2. **Processamento (aws_manager_visivel.py)**  
   - `enviar_dados_visivel(dados)` ou `enviar_arquivo_json(caminho)`:  
     - Gera `arquivo_id` (hash) e `nome_arquivo` (ex.: `MAB_28-01-2025_20250128_120000.json`).  
     - Define `pasta_destino` pelo campo `tipo` (MAB, MCR, DESCONTOS, RENUNCIAS, OUTROS).  
     - Chave S3: `{pasta_destino}/{nome_arquivo}` (URL-encoded).  
   - Atualiza estrutura local (pastas + arquivos) e chama `_upload_arquivo_individual` (PUT na API AWS).  
   - Persiste índice em `aws_cache_index.json`.

3. **Endpoints da interface (aws_interface.py)**  
   - `POST /api/enviar-dados` – body JSON → `enviar_dados_visivel`.  
   - `POST /api/enviar-arquivo` – upload de arquivo → `enviar_arquivo_json`.  
   - `GET /api/listar-por-pastas` – lista do cache local.  
   - `GET /api/obter-arquivo/{id}` – obtém arquivo do cache.  
   - `PUT /api/atualizar-arquivo/{id}` – atualiza dados no cache.  
   - `DELETE /api/deletar-arquivo/{id}` – remove do cache (e possivelmente da AWS, conforme implementação).  
   - `GET /api/listar-remoto?tipo=` – lista arquivos na AWS por tipo.  
   - `GET /api/get-remoto?tipo=&nome=` – baixa conteúdo de um arquivo na AWS.  
   - `POST /api/put-remoto` – envia JSON para a AWS (PUT dinâmico).  
   - Testar conexão: `GET /api/testar-conexao` (chama a URL base da API AWS).

### 3.4 Formato esperado do JSON enviado

Para que o AWS Manager classifique e nomeie corretamente:

- **tipo:** "MAB" | "MCR" | "DESCONTOS" | "RENUNCIAS" | "OUTROS"  
- **data_filtro:** ex. "28/01/2025" (usado no nome do arquivo e metadados).  
- **data_processamento:** ISO (preenchido automaticamente se omitido).  
- **resultados:** array de registros (conteúdo igual ao que a API principal retorna em cada `download_*_json`).

Os JSON gerados por `download_mab_json`, `download_mcr_json`, `download_renuncias_json`, `download_descontos_json` e `download_deducoes_json` já possuem estrutura compatível (tipo, data_filtro, resultados, etc.).

---

## 4. Fluxo completo de integração (passo a passo)

1. **Preparar dados no Sistema 1**  
   - Garantir que os caminhos do OneDrive (MAB, MCR, Deduções) existam e estejam atualizados.  
   - Opcional: `GET /testar_busca_pastas/` para validar pastas de Renúncia e Desconto.

2. **Obter JSON por dia/mês (API principal – main.py)**  
   - Acessar a página `/` (porta 8000) e usar os formulários da sidebar **ou** chamar diretamente:  
     - `/download_mab_json/?dia=28&mes=1`  
     - `/download_mcr_json/?dia=28&mes=1`  
     - `/download_renuncias_json/?dia=28&mes=1`  
     - `/download_descontos_json/?dia=28&mes=1`  
     - `/download_deducoes_json/?dia=28&mes=1`  
     - Ou um único: `/download_todos_dados_json/?dia=28&mes=1`

3. **Enviar para o Sistema 2 (AWS)**  
   - Abrir a AWS Manager Interface (porta 8001).  
   - **Opção A:** em "Enviar arquivo", fazer upload do JSON baixado (o sistema infere tipo e nome pelo conteúdo).  
   - **Opção B:** em "Enviar JSON (PUT dinâmico)", escolher tipo (MAB, MCR, etc.), informar nome (ou usar o sugerido) e colar/colocar o JSON (ou selecionar arquivo).  
   - A interface chama a API AWS (PUT) e atualiza o cache local; os arquivos ficam listados por pasta (MAB, MCR, Descontos, Renúncias).

4. **Consultas e manutenção na AWS**  
   - "Ver MAB (AWS)", "Ver MCR (AWS)", etc.: listam arquivos no S3 por tipo.  
   - Obter/baixar arquivo remoto, deletar, mover entre pastas (conforme endpoints acima).

---

## 5. Pontos de atenção para mudanças

- **Caminhos fixos:** MAB e MCR usam listas fixas de caminhos em `main.py`. Incluir novo mês ou novo banco exige alterar essas listas (ou torná-las configuráveis).  
- **Deduções:** já são dinâmicas por `gerar_caminhos_deducoes_dinamicos()`; apenas os meses base precisam estar na lista em `gerar_caminhos_deducoes_dinamicos`.  
- **Filtro por dia/mês:**  
  - MAB: sufixo do nome (DDMM).  
  - MCR: prefixo do nome do arquivo/banco (DDMM).  
  - Deduções: campo `Data_Contabil` no formato DD/MM/YYYY.  
  Qualquer alteração no padrão de nomes de arquivos ou no formato de data quebra o filtro.  
- **Agregação MAB:** regra fixa (CEF separado, demais somados em Brasil). Alterar bancos ou códigos exige mudar `agregar_resultados_mab` e possivelmente `codigo_resumido` em outros módulos.  
- **Integração automática:** hoje não existe. Se quiser que a AWS Manager chame a API principal e envie automaticamente, será necessário:  
  - Configurar URL base da API principal (ex.: `http://localhost:8000`).  
  - Na interface, adicionar fluxo "Buscar da API e enviar para AWS" chamando `download_*_json` e em seguida `enviar_dados_visivel`.  
- **Relatórios Excel:** `gerar_relatorio_mab` e `gerar_relatorio_mcr` (em `relatorios.py`) usam estruturas específicas de `mab_resultados` e `mcr_resultados`; mudanças nos formatos de saída da API devem ser refletidas ali.  
- **Segurança:** a API principal não tem autenticação. A API AWS usa apenas `x-api-key`. Em produção, considerar autenticação/autorização na API principal e revisão do uso da chave AWS.

---

## 6. Resumo dos dois sistemas

| Aspecto | Sistema 1 (main.py) | Sistema 2 (AWS Manager + API AWS) |
|--------|----------------------|-----------------------------------|
| Função | Ler dados locais (OneDrive), processar, agregar e expor JSON/relatórios | Receber JSON, organizar por tipo e enviar para AWS; listar/baixar da AWS |
| Porta | 8000 (convencional) | 8001 (aws_interface) |
| Autenticação | Nenhuma | x-api-key na API AWS |
| Entrada | Arquivos .ret, .xls/.xlsx, .txt em pastas fixas/dinâmicas | JSON (upload ou corpo) |
| Saída | JSON (download) e Excel (relatórios) | Arquivos JSON na AWS (S3) e cache local |
| Ligação entre os dois | Manual: usuário baixa da API e envia na interface | - |

Com essa análise, você pode localizar onde alterar caminhos, filtros, agregações e onde introduzir automação ou novos formatos sem quebrar o fluxo atual.

---

## 7. Validação no navegador (Browser)

- **API Principal (porta 8000):** Página `/` carrega a sidebar "API Integração" com:
  - **MAB:** Processar MAB, Filtrar MAB (dia/mês), Baixar MAB JSON, Gerar Relatório MAB
  - **MCR:** Processar MCR, Filtrar MCR, Baixar MCR JSON, Gerar Relatório MCR
  - **Desconto/Renúncia:** Processar Deduções, Filtrar Deduções, Baixar Deduções JSON, Baixar Renúncias JSON (91), Baixar Descontos JSON (93)
- Os links "Processar *" abrem no **iframe** (target=`content_frame`); a resposta JSON é exibida no iframe (ex.: `GET /processar/` → `{"resultados":[]}`).
- Os formulários "Baixar * JSON" fazem GET com `dia` e `mes` e disparam download do arquivo.
- **AWS Manager (porta 8001):** Interface separada; para testar o fluxo completo, subir também `uvicorn aws_interface:app --port 8001` e abrir `http://127.0.0.1:8001/`. O envio para AWS é feito por upload de JSON ou pelo formulário "Enviar JSON (PUT dinâmico)".
