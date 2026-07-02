# WCAG Dataset — Pipeline Completo

> Plataforma híbrida de análise automática de acessibilidade web aplicada ao portal institucional da UNESP.
> Integra crawler BFS, axe-core (desktop + mobile), DistilBERT, OCR (pytesseract) + BLIP + Helsinki-NLP e relatório HTML interativo.

[![CI](https://github.com/Rebeca1204/Websites-Acessiveis-UNESP/actions/workflows/ci.yml/badge.svg)](https://github.com/Rebeca1204/Websites-Acessiveis-UNESP/actions/workflows/ci.yml)
[![Python 3.12](https://img.shields.io/badge/python-3.12-blue)](https://www.python.org/)
[![Node 20](https://img.shields.io/badge/node-20-green)](https://nodejs.org/)
[![Testes](https://img.shields.io/badge/testes-97%20passando-brightgreen)](testar.py)

---

## Sumário

- [Instalação](#instalação)
- [Execução — passo a passo](#execução--passo-a-passo)
- [Scripts npm](#scripts-npm-disponíveis)
- [Estrutura do projeto](#estrutura-do-projeto)
- [Categorias WCAG cobertas](#categorias-wcag-cobertas-11)
- [Formato do dataset](#formato-do-dataset)
- [Saída do pipeline](#pipeline-integrado--saída)
- [Resultados obtidos](#resultados-obtidos)
- [Integração contínua](#integração-contínua-ci)
- [Checklist](#checklist-de-conclusão)
- [Limitações e trabalhos futuros](#limitações-e-trabalhos-futuros)

---

## Instalação

```bash
# Dependências Node.js
npm install

# Dependências Python
pip install -r requirements.txt

# Binário do Tesseract (OCR para logos e banners)
# Ubuntu/Debian:
sudo apt install tesseract-ocr tesseract-ocr-por

# macOS:
brew install tesseract tesseract-lang
```

---

## Execução — passo a passo

### Passo 1 — Crawler

Visita as páginas da UNESP usando **BFS com controle de profundidade máxima** (`MAX_PROFUNDIDADE = 3`).
As `SEED_URLS` entram com profundidade 0; URLs filhas herdam `profundidade + 1`.
Deduplicação de URLs via `Set` (O(1)) em vez de `fila.includes()` (O(n)).
Valida URLs antes de enfileirar — rejeita `ps://`, `ttps://`, âncoras, `mailto:` e domínios externos.

```bash
node crawler.js
```

Saída: `htmls/` e `urls-visitadas.json` (inclui campo `profundidade` por URL)

---

### Passo 2 — Análise de acessibilidade (desktop + mobile)

Roda o axe-core em **dois viewports por página**: desktop (1280×800) e mobile (375×667, iPhone SE).
Faz `delete window.axe` antes de reinjetar entre viewports — evita acumulação no namespace global.
Erros idênticos nos dois viewports são deduplicados; erros só detectados em mobile são marcados explicitamente.

```bash
node analisar.js
```

Saída: `relatorios/` — um `.json` por página com erros consolidados e viewport de origem

---

### Passo 3 — Salvar no banco

```bash
node salvar.js
```

Saída: `wcag.db` (SQLite via sql.js)

---

### Passo 3b — Injetar dados sintéticos

Injeta 200 HTMLs sintéticos por categoria para equilibrar classes minoritárias no dataset.

```bash
python3 injetar-sinteticos.py
```

---

### Passo 4 — Gerar dataset (11 categorias, 8.800 exemplos)

Usa `variacoes()` com **3 eixos de diversificação**:

- **Atributos extras** — injeta `class`, `id`, `loading`, `style` no elemento com erro
- **Texto circundante** — adiciona labels, legendas e parágrafos de contexto
- **Wrappers semânticos** — envolve em `<div>`, `<section>`, `<article>`, `<li>`

Isso evita que o modelo memorize padrões de wrapper em vez do erro WCAG em si.
Resultado: 12 variações por HTML base (eram 5), 800 exemplos por categoria.

```bash
python3 gerar-dataset-completo.py
```

Saída: `dataset-balanced.jsonl` — 8.800 exemplos balanceados

---

### Passo 5 — Fine-tuning do DistilBERT

- Modelo: `distilbert-base-uncased` (66M parâmetros, roda em CPU com ~4 GB RAM)
- *Weighted loss* para classes minoritárias
- Acumulação de gradientes: batch efetivo de 8 (`BATCH_SIZE=2`, `GRAD_ACCUM=4`)
- Gera **duas matrizes de confusão**: absoluta (`fmt="d"`) e normalizada por linha (`fmt=".0%"`)
- Grava `modelo-wcag/dataset_hash.txt` com o MD5 do dataset — o pipeline avisa se o modelo estiver desatualizado

```bash
python3 treinar.py
```

Saída: `modelo-wcag/` e `resultados/` (métricas JSON, matrizes de confusão, gráficos de loss/F1)

---

### Passo 6 — Inferência / teste do modelo

**Modo argumento (um HTML):**
```bash
python inferir.py "<button><i class='fa fa-bars'></i></button>"
```

**Modo interativo:**
```bash
python inferir.py
```

**Modo batch — classifica JSONL inteiro e calcula acurácia:**
```bash
python inferir.py --batch dataset-balanced.jsonl
python inferir.py --batch erros.jsonl --saida predicoes.jsonl
```

Formatos aceitos no `--batch`:

| Formato | Comportamento |
|---|---|
| `{"html": "..."}` | Classifica, sem acurácia |
| `{"html": "...", "categoria": "wcag-1.1.1"}` | Classifica + calcula acerto |
| `{"input": "### ERRO WCAG: ...", "output": "..."}` | Formato nativo do dataset |

Saída do batch: acurácia geral, acurácia por categoria (com barra visual) e top 5 confusões mais frequentes.

---

### Passo 7 — Pipeline integrado (relatório final)

Executa as 4 fases em sequência: axe-core → DistilBERT → OCR/BLIP → relatório.
Detecta automaticamente se o modelo está desatualizado (compara MD5 do dataset com `dataset_hash.txt`).

```bash
# Com HTMLs já coletados em /htmls (sem internet):
node pipeline.js --relatorios

# Analisar URL específica ao vivo:
node pipeline.js https://www.unesp.br
```

Saída: `relatorio-final.json` e `relatorio-final.html`

---

### Passo 8 — Testes automatizados

```bash
python3 testar.py        # todos os 97 testes
python3 testar.py -v     # modo verboso
```

**97 testes em 5 suites:**

| Suite | Escopo |
|---|---|
| `TestCorrigirRapidoJS` | `corrigirRapido()` do `pipeline.js` via Node.js — 11 categorias WCAG |
| `TestCorrigirPython` | `corrigir()` do `gerar-dataset-completo.py` — 11 categorias |
| `TestVisaoUtilitarios` | Funções puras do `visao.py` (sem BLIP/OCR): filtro SVG, deduplicação, `_limpar_repeticoes()` |
| `TestVisaoOcrECache` | OCR e cache do `visao.py` quando pytesseract está disponível |
| `TestEstruturaDoProjetoEMapeamentos` | Scripts existentes, mapeamentos axe→WCAG, estrutura do JSONL |

---

### Tudo de uma vez (sem fine-tuning e sem pipeline)

```bash
npm run tudo
```

---

## Scripts npm disponíveis

```bash
npm run 1-crawler          # node crawler.js
npm run 2-analisar         # node analisar.js
npm run 3-salvar           # node salvar.js
npm run 3b-sinteticos      # python3 injetar-sinteticos.py
npm run 4-dataset          # python3 gerar-dataset-completo.py
npm run 5-treinar          # python3 treinar.py
npm run 6-pipeline         # node pipeline.js --relatorios
npm run tudo               # passos 1 → 4 em sequência
```

---

## Estrutura do projeto

```
wcag-dataset/
├── .github/
│   └── workflows/
│       └── ci.yml              # CI: testes Python + lint JS a cada push
│
├── crawler.js                  # Passo 1 — BFS com controle de profundidade
├── analisar.js                 # Passo 2 — axe-core desktop + mobile
├── salvar.js                   # Passo 3 — persiste no SQLite
├── injetar-sinteticos.py       # Passo 3b — dados sintéticos (11 categorias)
├── gerar-dataset-completo.py   # Passo 4 — dataset com variacoes() diversificadas
├── treinar.py                  # Passo 5 — fine-tuning DistilBERT + hash do dataset
├── inferir.py                  # Passo 6 — inferência (argumento / interativo / batch)
├── pipeline.js                 # Passo 7 — sistema híbrido integrado
├── visao.py                    # Módulo de visão: OCR + BLIP + Helsinki-NLP + cache
├── testar.py                   # Passo 8 — 97 testes de regressão
├── db.js                       # Módulo SQLite (sql.js)
├── package.json
├── requirements.txt
│
├── htmls/                      # (gerado) HTMLs das páginas crawleadas
├── relatorios/                 # (gerado) Relatórios axe-core por página
├── modelo-wcag/                # (gerado) Modelo DistilBERT treinado
│   ├── dataset_hash.txt        # MD5 do dataset no último treino
│   └── label_encoder.pkl       # Encoder de rótulos (11 classes)
├── resultados/                 # (gerado) Métricas JSON, matrizes de confusão, gráficos
│   ├── matriz_confusao.png             # Contagens absolutas
│   └── matriz_confusao_normalizada.png # Normalizada por linha (% por classe real)
├── .blip-cache/                # (gerado) Cache de descrições com TTL + hash de conteúdo
│
├── wcag.db                     # (gerado) Banco SQLite
├── dataset-balanced.jsonl      # (gerado) Dataset — 8.800 exemplos
├── relatorio-final.json        # (gerado) Relatório estruturado do pipeline
└── relatorio-final.html        # (gerado) Relatório visual interativo
```

---

## Categorias WCAG cobertas (11)

| Categoria | Critério WCAG | Regras axe mapeadas | Exemplos |
|---|---|---|---|
| wcag-1.1.1 | Texto alternativo em imagens | `image-alt`, `input-image-alt`, `role-img-alt` | 800 |
| wcag-1.3.1 | Informação e relações semânticas | `td-headers-attr`, `th-has-data-cells`, `list`, `listitem` | 800 |
| wcag-1.4.3 | Contraste mínimo de cores | `color-contrast` | 800 |
| wcag-1.4.4 | Redimensionamento de texto | `meta-viewport` | 800 |
| wcag-2.1.1 | Acessibilidade por teclado | `keyboard`, `tabindex` | 800 |
| wcag-2.4.1 | Skip links (bypass) | `bypass` | 800 |
| wcag-2.4.2 | Título da página | `document-title` | 800 |
| wcag-2.4.4 | Finalidade do link | `link-name` | 800 |
| wcag-3.1.1 | Idioma da página | `html-has-lang`, `html-lang-valid` | 800 |
| wcag-4.1.1 | HTML válido (IDs duplicados etc.) | `duplicate-id`, `duplicate-id-active`, `duplicate-id-aria` | 800 |
| wcag-4.1.2 | Nome, função e valor (ARIA) | `button-name`, `label`, `select-name`, `textarea-name`, `aria-*` | 800 |
| **Total** | | **26 regras** | **8.800** |

---

## Formato do dataset

```json
{
  "input":  "### ERRO WCAG: wcag-1.1.1\n### HTML com problema:\n<img src=\"foto.jpg\">",
  "output": "<img src=\"foto.jpg\" alt=\"Imagem descritiva\">"
}
```

---

## Pipeline integrado — saída

O `relatorio-final.html` contém para cada página:

- **Score de acessibilidade** (0–100) com penalidade mínima por erros `critical` (−4 pts) e `serious` (−2 pts)
- **Viewport de detecção** — indica se o erro foi detectado em desktop, mobile ou ambos
- **Erros por impacto** (critical / serious / moderate / minor)
- **Categoria WCAG** mapeada pelo axe-core
- **Classificação ML** do DistilBERT com % de confiança
- **Badge de fonte** (🔤 OCR / 🤖 BLIP / ♻️ cache) para descrições de imagens
- **Texto OCR bruto** exibido abaixo do badge quando a fonte é OCR
- **Descrição traduzida** para pt-BR pelo Helsinki-NLP (quando fonte é BLIP)
- **Filtro por categoria** — JavaScript puro, sem dependências, integrado com paginação
- **Paginação dinâmica** — erros além de 50 revelados via "Mostrar mais N erro(s)"
- **Gráfico de barras** — erros por categoria WCAG (Chart.js)
- **Gráfico de rosca** — distribuição por nível de impacto com percentuais

---

## Resultados obtidos

| Métrica | Valor |
|---|---|
| Páginas analisadas | 26 |
| Total de erros detectados | 520 |
| Score médio de acessibilidade | 59/100 |
| Categoria dominante | `wcag-1.4.3` — Contraste (345 erros, 66% do total) |
| Macro F1 (DistilBERT) | 0,9977 |
| Acurácia no conjunto de validação | 100% (440 amostras estratificadas) |
| Imagens com alt sugerido | 14 de 15 processadas |
| Testes automatizados | 97 (100% passando) |
| Dataset | 8.800 exemplos (800/categoria) |
| Modelo base | DistilBERT-base-uncased (66M parâmetros) |
| Hardware de treino | CPU, ~4 GB RAM |

---

## Integração contínua (CI)

O repositório usa **GitHub Actions** com dois jobs executados a cada push (qualquer branch) e pull request para `main`/`master`:

### `testes` — Python 3.12 + Node.js 20

```
1. Checkout do código
2. Python 3.12 + Node.js 20
3. pip install (dependências leves — sem torch/transformers)
4. npm install --ignore-scripts
5. pytest testar.py -v --tb=short
6. Publica sumário de resultados no GitHub Step Summary
```

> Torch e transformers **não** são instalados no CI — os 97 testes cobrem lógica pura sem carregar modelos pesados, mantendo o tempo de execução abaixo de 2 minutos.

### `lint-js` — Node.js 20

```
node --check crawler.js analisar.js salvar.js pipeline.js db.js
```

Falha o job se qualquer arquivo apresentar erro de sintaxe JavaScript.

---

## Checklist de conclusão

- [x] Crawler com BFS e controle de profundidade (`MAX_PROFUNDIDADE = 3`)
- [x] Deduplicação de URLs via `Set` (O(1) por verificação)
- [x] Validação de URLs no crawler (rejeita `ps://`, âncoras, `mailto:`, externos)
- [x] Análise axe-core desktop + mobile (dois viewports por página)
- [x] Reset de `window.axe` entre viewports (evita acumulação no namespace global)
- [x] Deduplicação de erros entre viewports com `Set` de chaves compostas
- [x] Score de acessibilidade com penalidade mínima por erros graves
- [x] SQLite com dados reais + sintéticos (11 categorias)
- [x] Dataset balanceado — 8.800 exemplos, 800/categoria
- [x] `variacoes()` com 3 eixos: atributos, texto circundante, wrappers
- [x] Fine-tuning DistilBERT (Macro F1 = 0,9977)
- [x] Duas matrizes de confusão (absoluta + normalizada por classe real)
- [x] Hash do dataset gravado em `modelo-wcag/dataset_hash.txt`
- [x] Aviso automático se modelo estiver desatualizado
- [x] Inferência em modo batch com acurácia por categoria (`--batch`)
- [x] Visão computacional: OCR (pytesseract) → BLIP → Helsinki-NLP
- [x] Pré-processamento OCR: upscale proporcional + contraste para logos pequenos
- [x] Tratamento de GIFs animados, WebPs e formatos não identificados (`_abrir_imagem()`)
- [x] Cache com TTL (7 dias) + invalidação por hash de conteúdo da imagem
- [x] Badge de fonte no relatório (🔤 OCR / 🤖 BLIP / ♻️ cache)
- [x] Pipeline integrado com timeout proporcional e aviso de modelo ausente
- [x] Relatório HTML com gráficos interativos (Chart.js)
- [x] Filtro de categoria em JavaScript puro integrado com paginação
- [x] Paginação dinâmica (botão "Mostrar mais") com reapliação do filtro ativo
- [x] 97 testes automatizados de regressão (5 suites)
- [x] CI/CD via GitHub Actions (testes Python + lint JS a cada push)

---

## Limitações e trabalhos futuros

**Cobertura WCAG parcial** — 26 das 50+ regras do axe-core mapeadas. Critérios como `wcag-1.3.3`, `wcag-2.3.1`, `wcag-3.3.1` e `wcag-2.5.3` ficam de fora. Ampliar o mapeamento não exige retreinamento.

**Dataset de domínio único** — todos os exemplos reais vêm da UNESP. Incorporar outros sites públicos brasileiros (educação, governo) aumentaria a generalização do modelo.

**Correções sem contexto semântico** — `corrigirRapido()` usa regex; falha quando a correção depende do destino específico de um link ou do conteúdo da página. Uma integração futura com LLM permitiria correções contextualizadas.

**Análise limitada a código-fonte estático** — problemas que só aparecem em interação (foco em modais, carrosséis dinâmicos, atalhos de teclado) não são detectáveis pelo axe-core. Testes com leitores de tela reais (NVDA via Playwright) cobririam essa dimensão.

**Sem lockfile Python** — `requirements.txt` tem versões fixas mas sem `pip-compile`. Gerar `requirements.lock` garantiria reprodutibilidade entre máquinas com bibliotecas de sistema diferentes.

**`testar.py` não carrega modelos reais** — os testes cobrem lógica pura; não há teste de integração que rode OCR real em imagem de teste ou carregue o DistilBERT. Isso é intencional para manter o CI rápido, mas limita a cobertura de regressões em inferência real.
