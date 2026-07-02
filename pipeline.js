// pipeline.js — crawler → axe-core → DistilBERT → relatório final

// Uso:
//   node pipeline.js                        → analisa URLs padrão (UNESP)
//   node pipeline.js https://exemplo.com    → analisa URL específica
//   node pipeline.js --relatorios           → analisa HTMLs já salvos em /htmls

// Saída:
//   relatorio-final.json   → dados estruturados
//   relatorio-final.html   → relatório visual

const puppeteer  = require("puppeteer");
const axe        = require("axe-core");
const fs         = require("fs");
const path       = require("path");
const { execSync, spawn } = require("child_process");

const DEFAULT_URLS = [
  "https://www.unesp.br",
  "https://www.unesp.br/portal#!/noticia",
  "https://www.unesp.br/portal#!/graduacao",
];

const OUTPUT_JSON  = path.join(__dirname, "relatorio-final.json");
const OUTPUT_HTML  = path.join(__dirname, "relatorio-final.html");
const HTMLS_DIR    = path.join(__dirname, "htmls");
const TIMEOUT_MS   = 20000;

const RULE_TO_WCAG = {
  "image-alt":              "wcag-1.1.1",
  "input-image-alt":        "wcag-1.1.1",
  "role-img-alt":           "wcag-1.1.1",
  "td-headers-attr":        "wcag-1.3.1",
  "th-has-data-cells":      "wcag-1.3.1",
  "list":                   "wcag-1.3.1",
  "listitem":               "wcag-1.3.1",
  "color-contrast":         "wcag-1.4.3",
  "meta-viewport":          "wcag-1.4.4",
  "keyboard":               "wcag-2.1.1",
  "tabindex":               "wcag-2.1.1",
  "bypass":                 "wcag-2.4.1",
  "document-title":         "wcag-2.4.2",
  "link-name":              "wcag-2.4.4",
  "html-has-lang":          "wcag-3.1.1",
  "html-lang-valid":        "wcag-3.1.1",
  "duplicate-id":           "wcag-4.1.1",
  "duplicate-id-active":    "wcag-4.1.1",
  "duplicate-id-aria":      "wcag-4.1.1",
  "button-name":            "wcag-4.1.2",
  "label":                  "wcag-4.1.2",
  "select-name":            "wcag-4.1.2",
  "textarea-name":          "wcag-4.1.2",
  "aria-required-attr":     "wcag-4.1.2",
  "aria-required-children": "wcag-4.1.2",
  "aria-roles":             "wcag-4.1.2",
};

const WCAG_DESCRICOES = {
  "wcag-1.1.1": "Texto alternativo em imagens",
  "wcag-1.3.1": "Informação e relações semânticas",
  "wcag-1.4.3": "Contraste mínimo de cores",
  "wcag-1.4.4": "Redimensionamento de texto",
  "wcag-2.1.1": "Acessibilidade por teclado",
  "wcag-2.4.1": "Skip links (bypass)",
  "wcag-2.4.2": "Título da página",
  "wcag-2.4.4": "Finalidade do link",
  "wcag-3.1.1": "Idioma da página",
  "wcag-4.1.1": "HTML válido (IDs duplicados etc.)",
  "wcag-4.1.2": "Nome, função e valor (ARIA)",
};

const IMPACTO_PESO = { critical: 4, serious: 3, moderate: 2, minor: 1 };

function calcularScore(erros, totalElementos = 0) {
  if (erros.length === 0) return 100;
  const penalidade = erros.reduce((acc, e) => {
    return acc + (IMPACTO_PESO[e.impacto] || 1);
  }, 0);
  const base = Math.max(totalElementos, erros.length * 2, 10);
  const taxa = penalidade / (base * 4);
  const scoreProporcional = Math.round((1 - taxa) * 100);
  const penalidadeMinima = erros.reduce((acc, e) => {
    if (e.impacto === "critical") return acc + 4;
    if (e.impacto === "serious")  return acc + 2;
    return acc;
  }, 0);

  const scoreTeto = 100 - penalidadeMinima;
  return Math.max(0, Math.min(scoreProporcional, scoreTeto));
}

async function analisarUrl(page, url) {
  try {
    await page.goto(url, { waitUntil: "domcontentloaded", timeout: TIMEOUT_MS });
    await page.addScriptTag({ content: axe.source });

    const resultado = await page.evaluate(async () => {
      return await window.axe.run(document, { resultTypes: ["violations", "passes"] });
    });
    const REGRAS_MAPEADAS = new Set(Object.keys(RULE_TO_WCAG));
    const elementosTestados = new Set();
    for (const v of resultado.violations) {
      if (!REGRAS_MAPEADAS.has(v.id)) continue;
      for (const n of v.nodes) {
        if (n.target?.[0]) elementosTestados.add(n.target[0]);
      }
    }
    for (const p of (resultado.passes || [])) {
      if (!REGRAS_MAPEADAS.has(p.id)) continue;
      for (const n of p.nodes) {
        if (n.target?.[0]) elementosTestados.add(n.target[0]);
      }
    }
    const totalElementos = elementosTestados.size;

    const erros = [];
    for (const violacao of resultado.violations) {
      const categoria = RULE_TO_WCAG[violacao.id];
      if (!categoria) continue;
      for (const no of violacao.nodes) {
        const html = no.html || (no.target?.[0] ? `<!-- ${no.target[0]} -->` : "");
        if (!html || html.length < 5) continue;
        erros.push({
          categoria,
          regra:    violacao.id,
          impacto:  violacao.impact,
          html,
          mensagem: violacao.description,
        });
      }
    }

    return { url, erros, totalElementos, status: "ok" };
  } catch (err) {
    return { url, erros: [], status: "erro", mensagem: err.message };
  }
}

async function analisarArquivo(page, filePath) {
  const url = `file://${filePath}`;
  const resultado = await analisarUrl(page, url);
  resultado.url = path.basename(filePath);
  return resultado;
}

function classificarComModelo(htmlsECategorias) {
  const modelDir = path.join(__dirname, "modelo-wcag");

  if (!fs.existsSync(modelDir)) {
    console.log("Modelo DistilBERT não encontrado em ./modelo-wcag/");
    console.log("Execute primeiro: python3 treinar.py");
    console.log("Pulando classificação ML \n");
    return {};
  }

  const labelEncoder = path.join(modelDir, "label_encoder.pkl");
  const configFile   = path.join(modelDir, "config.json");
  if (!fs.existsSync(labelEncoder) || !fs.existsSync(configFile)) {
    console.log("Modelo em ./modelo-wcag/ está incompleto (falta config.json ou label_encoder.pkl)");
    console.log("Execute novamente: python3 treinar.py");
    console.log("Pulando classificação ML\n");
    return {};
  }
  const hashFile    = path.join(modelDir, "dataset_hash.txt");
  const datasetPath = path.join(__dirname, "dataset-balanced.jsonl");
  if (fs.existsSync(hashFile) && fs.existsSync(datasetPath)) {
    const { createHash } = require("crypto");
    const hashSalvo = fs.readFileSync(hashFile, "utf8").trim();
    const hashAtual = createHash("md5").update(fs.readFileSync(datasetPath)).digest("hex");
    if (hashSalvo !== hashAtual) {
      console.log("dataset-balanced.jsonl foi modificado desde o último treino.");
      console.log("O modelo pode estar desatualizado — considere rodar: python3 treinar.py");
    }
  }
  const tmpInput  = path.join(__dirname, ".tmp-classify-input.json");
  const tmpOutput = path.join(__dirname, ".tmp-classify-output.json");

  const entradas = htmlsECategorias.map(({ html }) => html);
  fs.writeFileSync(tmpInput, JSON.stringify(entradas), "utf8");
  const script = `
import sys, json, pickle, torch
from transformers import DistilBertTokenizerFast, DistilBertForSequenceClassification

MODEL_DIR  = "${modelDir.replace(/\\/g, '/')}"
MAX_LENGTH = 128

tokenizer = DistilBertTokenizerFast.from_pretrained(MODEL_DIR)
model     = DistilBertForSequenceClassification.from_pretrained(MODEL_DIR)
model.eval()

with open(f"{MODEL_DIR}/label_encoder.pkl", "rb") as f:
    le = pickle.load(f)

with open("${tmpInput.replace(/\\/g, '/')}", "r") as f:
    htmls = json.load(f)

resultados = []
for html in htmls:
    texto = f"### ERRO WCAG: \\n### HTML com problema:\\n{html}"
    enc = tokenizer(texto, truncation=True, padding="max_length",
                    max_length=MAX_LENGTH, return_tensors="pt")
    with torch.no_grad():
        outputs = model(**enc)
        probs   = torch.softmax(outputs.logits, dim=1)[0]
        pred    = torch.argmax(probs).item()
    resultados.append({
        "categoria": le.inverse_transform([pred])[0],
        "confianca": round(probs[pred].item(), 4),
    })

with open("${tmpOutput.replace(/\\/g, '/')}", "w") as f:
    json.dump(resultados, f)
`;

  const tmpScript = path.join(__dirname, ".tmp-classify.py");
  fs.writeFileSync(tmpScript, script, "utf8");

  try {
    execSync(`python3 "${tmpScript}"`, { stdio: "pipe" });
    const saida = JSON.parse(fs.readFileSync(tmpOutput, "utf8"));
    const mapa = {};
    htmlsECategorias.forEach(({ html }, i) => {
      mapa[html] = saida[i];
    });
    return mapa;
  } catch (err) {
    console.log(`Erro na classificação ML: ${err.message.slice(0, 80)}`);
    return {};
  } finally {
    [tmpInput, tmpOutput, tmpScript].forEach((f) => { try { fs.unlinkSync(f); } catch {} });
  }
}

function gerarHtml(dados) {
  const { gerado_em, resumo, paginas } = dados;

  const scoreCor = (s) => s >= 80 ? "#22c55e" : s >= 50 ? "#f59e0b" : "#ef4444";
  const impactoCor = { critical: "#ef4444", serious: "#f97316", moderate: "#f59e0b", minor: "#6b7280" };

  const paginasHtml = paginas.map((p) => {
    const cor = scoreCor(p.score);
    const PAGINACAO_INICIAL = 50;

    const errosHtml = p.erros.map((e, idx) => `
      <tr data-categoria="${e.categoria}" data-impacto="${e.impacto || ''}" class="${idx >= PAGINACAO_INICIAL ? 'pag-oculta' : ''}">
        <td><span class="badge" style="background:${impactoCor[e.impacto] || '#888'}">${e.impacto}</span></td>
        <td><code class="cat">${e.categoria}</code></td>
        <td class="small">${WCAG_DESCRICOES[e.categoria] || e.categoria}</td>
        <td><pre class="html-snippet">${escapeHtml(e.html.slice(0, 200))}</pre></td>
        ${e.ml_categoria ? `<td><code class="cat ml">${e.ml_categoria}</code> <small>${(e.ml_confianca * 100).toFixed(0)}%</small></td>` : '<td>—</td>'}
        ${e.blip_alt
          ? (() => {
              const metodo = e.blip_metodo || "blip";
              const badgeCfg = {
                ocr:   { cls: "visao-tag-ocr",   icon: "🔤", label: "OCR"   },
                blip:  { cls: "visao-tag-blip",  icon: "🤖", label: "BLIP"  },
                cache: { cls: "visao-tag-cache",  icon: "♻️",  label: "cache" },
              };
              const cfg = badgeCfg[metodo] || badgeCfg.blip;
              const linhaEn = e.blip_descricao
                ? `<br><small class="blip-en">${escapeHtml(e.blip_descricao)}</small>`
                : "";
              const linhaOcr = metodo === "ocr" && e.blip_ocr_texto
                ? `<br><small class="blip-en">OCR: ${escapeHtml(e.blip_ocr_texto.slice(0, 60))}</small>`
                : "";
              return `<span class="visao-tag ${cfg.cls}">${cfg.icon} ${cfg.label}</span>${linhaEn}${linhaOcr}<br><code class="blip-alt">${escapeHtml(e.blip_alt)}</code>`;
            })()
          : '<span class="no-blip">—</span>'}</td>
        <td><pre class="html-snippet fixed">${escapeHtml((e.html_corrigido || "—").slice(0, 200))}</pre></td>
      </tr>`).join("");

    const totalOculto = Math.max(0, p.erros.length - PAGINACAO_INICIAL);
    const botaoMostrarMais = totalOculto > 0
      ? `<button class="btn-mostrar-mais" data-restante="${totalOculto}">Mostrar mais ${totalOculto} erro(s)</button>`
      : "";

    return `
    <details class="page-card" data-erros-count="${p.erros.length}">
      <summary>
        <span class="score-badge" style="background:${cor}">${p.score}</span>
        <span class="page-url">${escapeHtml(p.url)}</span>
        <span class="erros-count">${p.total_erros} erro(s)${totalOculto > 0 ? ` · ${totalOculto} oculto(s)` : ''}</span>
      </summary>
      <div class="page-body">
        ${p.erros.length === 0
          ? '<p class="ok-msg">Nenhum erro WCAG mapeado detectado!</p>'
          : `<div class="table-wrap"><table>
              <thead><tr>
                <th>Impacto</th><th>Categoria</th><th>Critério</th>
                <th>HTML original</th><th>Classificação ML</th><th>Visão computacional</th><th>Correção sugerida</th>
              </tr></thead>
              <tbody>${errosHtml}</tbody>
            </table></div>
            ${botaoMostrarMais}`
        }
      </div>
    </details>`;
  }).join("\n");

  const catStats = resumo.por_categoria
    .map((c) => `<tr><td><code>${c.categoria}</code></td><td>${WCAG_DESCRICOES[c.categoria] || ""}</td><td><strong>${c.total}</strong></td></tr>`)
    .join("");

  const filtroBotoesHtml = resumo.por_categoria
    .map((c) => `<button class="filtro-btn" data-filtro-categoria="${c.categoria}">
        <code>${c.categoria}</code> <span class="filtro-count">${c.total}</span>
      </button>`)
    .join("");

  return `<!DOCTYPE html>
<html lang="pt-BR">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>Relatório WCAG — UNESP</title>
<style>
  *, *::before, *::after { box-sizing: border-box; }
  body { font-family: system-ui, sans-serif; margin: 0; background: #f8fafc; color: #1e293b; }
  header { background: #1e3a5f; color: #fff; padding: 2rem; }
  header h1 { margin: 0 0 .5rem; font-size: 1.6rem; }
  header p  { margin: 0; opacity: .8; font-size: .9rem; }
  main { max-width: 1100px; margin: 2rem auto; padding: 0 1.5rem; }
  .summary-grid { display: grid; grid-template-columns: repeat(auto-fit, minmax(160px, 1fr)); gap: 1rem; margin-bottom: 2rem; }
  .kpi { background: #fff; border-radius: 12px; padding: 1.2rem 1.5rem; box-shadow: 0 1px 4px #0001; }
  .kpi .val { font-size: 2.2rem; font-weight: 700; line-height: 1; }
  .kpi .lbl { font-size: .8rem; color: #64748b; margin-top: .3rem; }
  .section-title { font-size: 1.1rem; font-weight: 600; margin: 1.5rem 0 .8rem; border-bottom: 2px solid #e2e8f0; padding-bottom: .4rem; }
  .cat-table { width: 100%; border-collapse: collapse; background: #fff; border-radius: 10px; overflow: hidden; box-shadow: 0 1px 4px #0001; margin-bottom: 2rem; }
  .cat-table th, .cat-table td { padding: .6rem 1rem; text-align: left; border-bottom: 1px solid #f1f5f9; font-size: .88rem; }
  .cat-table th { background: #f1f5f9; font-weight: 600; }
  .page-card { background: #fff; border-radius: 12px; box-shadow: 0 1px 4px #0001; margin-bottom: 1rem; overflow: hidden; }
  .page-card summary { display: flex; align-items: center; gap: 1rem; padding: 1rem 1.2rem; cursor: pointer; user-select: none; list-style: none; }
  .page-card summary::-webkit-details-marker { display: none; }
  .page-card summary:hover { background: #f8fafc; }
  .score-badge { font-size: 1.1rem; font-weight: 700; color: #fff; border-radius: 8px; padding: .2rem .7rem; min-width: 48px; text-align: center; }
  .page-url { flex: 1; font-size: .85rem; word-break: break-all; color: #334155; }
  .erros-count { font-size: .8rem; color: #64748b; white-space: nowrap; }
  .page-body { padding: 0 1.2rem 1.2rem; }
  .table-wrap { overflow-x: auto; }
  table { width: 100%; border-collapse: collapse; font-size: .8rem; }
  th, td { padding: .45rem .6rem; border-bottom: 1px solid #f1f5f9; vertical-align: top; }
  th { background: #f8fafc; font-weight: 600; white-space: nowrap; }
  .badge { display: inline-block; padding: .15rem .5rem; border-radius: 4px; color: #fff; font-size: .72rem; font-weight: 600; white-space: nowrap; }
  .cat { background: #eff6ff; color: #1d4ed8; border-radius: 4px; padding: .1rem .4rem; font-size: .78rem; }
  .cat.ml { background: #f0fdf4; color: #166534; }
  .small { font-size: .78rem; color: #64748b; }
  .html-snippet { margin: 0; font-size: .72rem; background: #f8fafc; border: 1px solid #e2e8f0; border-radius: 4px; padding: .3rem .5rem; white-space: pre-wrap; word-break: break-all; max-width: 260px; overflow: hidden; }
  .html-snippet.fixed { background: #f0fdf4; border-color: #bbf7d0; }
  .ok-msg { color: #16a34a; font-weight: 500; padding: .5rem 0; }
  .blip-tag { display: inline-block; background: #ede9fe; color: #5b21b6; border-radius: 4px; padding: .1rem .4rem; font-size: .72rem; font-weight: 600; }
  .visao-tag       { display: inline-block; border-radius: 4px; padding: .1rem .4rem; font-size: .72rem; font-weight: 600; }
  .visao-tag-ocr   { background: #dcfce7; color: #166534; }
  .visao-tag-blip  { background: #ede9fe; color: #5b21b6; }
  .visao-tag-cache { background: #f1f5f9; color: #475569; }
  .blip-alt { background: #faf5ff; color: #6d28d9; border-radius: 4px; padding: .15rem .4rem; font-size: .78rem; display: inline-block; margin-top: .2rem; }
  .blip-en  { color: #94a3b8; font-size: .72rem; }
  .no-blip  { color: #cbd5e1; }
  .charts-row { display: grid; grid-template-columns: 1fr 1fr; gap: 1.5rem; margin-bottom: 2rem; }
  .chart-card { background: #fff; border-radius: 12px; box-shadow: 0 1px 4px #0001; padding: 1.2rem 1.5rem; }
  .chart-card h3 { font-size: .95rem; font-weight: 600; margin: 0 0 .8rem; color: #1e293b; }
  .chart-legend { display: flex; flex-wrap: wrap; gap: 8px; margin-bottom: 10px; }
  .chart-legend span { display: flex; align-items: center; gap: 5px; font-size: .72rem; color: #64748b; }
  .chart-legend i { width: 10px; height: 10px; border-radius: 2px; flex-shrink: 0; display: inline-block; }
  @media (max-width: 640px) { .charts-row { grid-template-columns: 1fr; } }
  .filter-bar { display: flex; flex-wrap: wrap; gap: .5rem; margin-bottom: .8rem; }
  .filtro-btn { display: inline-flex; align-items: center; gap: .4rem; background: #fff; border: 1px solid #e2e8f0; border-radius: 999px; padding: .4rem .9rem; font-size: .82rem; color: #334155; cursor: pointer; transition: all .15s ease; }
  .filtro-btn:hover { border-color: #94a3b8; background: #f8fafc; }
  .filtro-btn.active { background: #1e3a5f; border-color: #1e3a5f; color: #fff; }
  .filtro-btn.active .filtro-count { background: rgba(255,255,255,.2); color: #fff; }
  .filtro-btn .filtro-count { background: #f1f5f9; color: #64748b; border-radius: 999px; padding: .05rem .45rem; font-size: .72rem; font-weight: 600; }
  .filtro-empty-msg { text-align: center; color: #94a3b8; font-size: .85rem; padding: 1rem 0; }
  tr.filtro-oculto { display: none; }
  details.page-card.filtro-oculto { display: none; }
  tr.pag-oculta { display: none; }
  .btn-mostrar-mais { display: block; width: 100%; margin-top: .6rem; padding: .55rem; background: #f1f5f9; border: 1px dashed #cbd5e1; border-radius: 8px; color: #334155; font-size: .82rem; font-weight: 500; cursor: pointer; transition: all .15s ease; }
  .btn-mostrar-mais:hover { background: #e2e8f0; border-color: #94a3b8; }
  .btn-mostrar-mais:disabled { display: none; }
</style>
</head>
<body>
<header>
  <h1>Relatório de Acessibilidade WCAG — UNESP</h1>
  <p>Gerado em ${gerado_em} · Sistema híbrido axe-core + DistilBERT</p>
</header>
<main>
  <div class="summary-grid">
    <div class="kpi"><div class="val">${resumo.total_paginas}</div><div class="lbl">Páginas analisadas</div></div>
    <div class="kpi"><div class="val">${resumo.total_erros}</div><div class="lbl">Erros encontrados</div></div>
    <div class="kpi"><div class="val" style="color:${scoreCor(resumo.score_medio)}">${resumo.score_medio}</div><div class="lbl">Score médio (/100)</div></div>
    <div class="kpi"><div class="val">${resumo.paginas_criticas}</div><div class="lbl">Páginas críticas (&lt;50)</div></div>
    <div class="kpi"><div class="val">${resumo.ml_classificacoes}</div><div class="lbl">Classificações ML</div></div>
    <div class="kpi"><div class="val" style="color:#7c3aed">${resumo.visao_descricoes || 0}</div><div class="lbl">Imagens descritas (OCR/BLIP)</div></div>
  </div>

  <div class="section-title">Distribuição de erros</div>
  <div class="charts-row">
    <div class="chart-card">
      <h3>Erros por categoria WCAG</h3>
      <div class="chart-legend" id="bar-legend"></div>
      <div style="position:relative;width:100%;height:260px">
        <canvas id="barChart" role="img" aria-label="Gráfico de barras com erros por categoria WCAG"></canvas>
      </div>
    </div>
    <div class="chart-card">
      <h3>Distribuição por impacto</h3>
      <div class="chart-legend" id="pie-legend"></div>
      <div style="position:relative;width:100%;height:260px">
        <canvas id="pieChart" role="img" aria-label="Gráfico de pizza com distribuição por nível de impacto"></canvas>
      </div>
    </div>
  </div>

  <div class="section-title">Erros por categoria WCAG</div>
  <table class="cat-table">
    <thead><tr><th>Categoria</th><th>Critério WCAG</th><th>Total de erros</th></tr></thead>
    <tbody>${catStats}</tbody>
  </table>

  <div class="section-title">Filtrar por categoria</div>
  <div class="filter-bar">
    <button class="filtro-btn filtro-todas active" data-filtro-categoria="todas">
      Todas <span class="filtro-count">${resumo.total_erros}</span>
    </button>
    ${filtroBotoesHtml}
  </div>
  <p id="filtro-empty-msg" class="filtro-empty-msg" hidden>Nenhum erro encontrado para esta categoria.</p>

  <div class="section-title">Páginas analisadas</div>
  ${paginasHtml}
</main>
<footer>Pipeline WCAG · axe-core ${axe.version || "4.x"} + DistilBERT + BLIP (Salesforce)</footer>
<script src="https://cdnjs.cloudflare.com/ajax/libs/Chart.js/4.4.1/chart.umd.js"></script>
<script>
(function() {
  const CAT_COLORS = {
    "wcag-1.1.1":"#e34948","wcag-1.3.1":"#eb6834","wcag-1.4.3":"#2a78d6",
    "wcag-1.4.4":"#1baf7a","wcag-2.1.1":"#eda100","wcag-2.4.1":"#4a3aa7",
    "wcag-2.4.2":"#e87ba4","wcag-2.4.4":"#008300","wcag-3.1.1":"#185fa5",
    "wcag-4.1.1":"#993c1d","wcag-4.1.2":"#854f0b"
  };
  const IMP_COLORS = {critical:"#e34948",serious:"#eb6834",moderate:"#eda100",minor:"#6b7280"};

  const catData = ${JSON.stringify(resumo.por_categoria)};

  const barLabels = catData.map(c => c.categoria);
  const barValues = catData.map(c => c.total);
  const barColors = barLabels.map(l => CAT_COLORS[l] || "#888");

  document.getElementById("bar-legend").innerHTML = barLabels.map((l, i) =>
    \`<span><i style="background:\${barColors[i]}"></i>\${l} (\${barValues[i]})</span>\`
  ).join("");

  new Chart(document.getElementById("barChart"), {
    type: "bar",
    data: {
      labels: barLabels,
      datasets: [{
        label: "Erros",
        data: barValues,
        backgroundColor: barColors,
        borderRadius: 4,
        borderSkipped: false,
      }]
    },
    options: {
      responsive: true,
      maintainAspectRatio: false,
      plugins: {
        legend: { display: false },
        tooltip: { callbacks: { label: ctx => " " + ctx.parsed.y + " erros" } }
      },
      scales: {
        x: { ticks: { font: { size: 11 }, color: "#64748b", maxRotation: 40 }, grid: { display: false } },
        y: { ticks: { font: { size: 11 }, color: "#64748b" }, grid: { color: "#f1f5f9" } }
      }
    }
  });

  const allErros = ${JSON.stringify(
    paginas.flatMap(p => p.erros.map(e => e.impacto))
  )};

  const impCount = { critical: 0, serious: 0, moderate: 0, minor: 0 };
  allErros.forEach(imp => { if (impCount[imp] !== undefined) impCount[imp]++; });

  const pieLabels = Object.keys(impCount).filter(k => impCount[k] > 0);
  const pieValues = pieLabels.map(k => impCount[k]);
  const pieColors = pieLabels.map(k => IMP_COLORS[k]);
  const total = pieValues.reduce((a, b) => a + b, 0);

  document.getElementById("pie-legend").innerHTML = pieLabels.map((l, i) =>
    \`<span><i style="background:\${pieColors[i]}"></i>\${l} (\${pieValues[i]})</span>\`
  ).join("");

  new Chart(document.getElementById("pieChart"), {
    type: "doughnut",
    data: {
      labels: pieLabels,
      datasets: [{
        data: pieValues,
        backgroundColor: pieColors,
        borderWidth: 2,
        borderColor: "#fff"
      }]
    },
    options: {
      responsive: true,
      maintainAspectRatio: false,
      cutout: "58%",
      plugins: {
        legend: { display: false },
        tooltip: {
          callbacks: {
            label: ctx => {
              const pct = total > 0 ? Math.round(ctx.parsed / total * 100) : 0;
              return " " + ctx.parsed + " erros (" + pct + "%)";
            }
          }
        }
      }
    }
  });

  const filtroBotoes  = Array.from(document.querySelectorAll(".filtro-btn"));
  const todasLinhas   = Array.from(document.querySelectorAll("tbody tr[data-categoria]"));
  const todosDetails  = Array.from(document.querySelectorAll("details.page-card"));
  const emptyMsg      = document.getElementById("filtro-empty-msg");

  function aplicarFiltro(categoriaAlvo) {
    let totalRealDoFiltro  = 0;
    let totalVisivelAoUsuario = 0;

    todasLinhas.forEach((linha) => {
      const bate = categoriaAlvo === "todas" || linha.dataset.categoria === categoriaAlvo;
      linha.classList.toggle("filtro-oculto", !bate);
      if (bate) {
        totalRealDoFiltro++;
        if (!linha.classList.contains("pag-oculta")) totalVisivelAoUsuario++;
      }
    });

    todosDetails.forEach((det) => {
      const totalOriginal = parseInt(det.dataset.errosCount || "0", 10);

      if (totalOriginal === 0) {
        det.classList.remove("filtro-oculto");
        return;
      }
      const linhasQueBatemNaPagina = det.querySelectorAll("tbody tr[data-categoria]:not(.filtro-oculto)").length;
      const semResultadoNestaPagina = categoriaAlvo !== "todas" && linhasQueBatemNaPagina === 0;
      det.classList.toggle("filtro-oculto", semResultadoNestaPagina);

      if (!semResultadoNestaPagina && categoriaAlvo !== "todas") {
        const linhasVisivelNaPagina = det.querySelectorAll(
          "tbody tr[data-categoria]:not(.filtro-oculto):not(.pag-oculta)"
        ).length;
        if (linhasVisivelNaPagina === 0) det.open = true;
      }
    });
    emptyMsg.hidden = !(categoriaAlvo !== "todas" && totalRealDoFiltro === 0);

    return totalVisivelAoUsuario;
  }

  filtroBotoes.forEach((btn) => {
    btn.addEventListener("click", () => {
      const categoria = btn.dataset.filtroCategoria;
      filtroBotoes.forEach((b) => b.classList.toggle("active", b === btn));
      aplicarFiltro(categoria);
    });
  });


  document.querySelectorAll(".btn-mostrar-mais").forEach((btn) => {
    btn.addEventListener("click", () => {
      const tabela = btn.closest(".page-body").querySelector("table");
      const ocultas = tabela.querySelectorAll("tr.pag-oculta");
      ocultas.forEach((tr) => tr.classList.remove("pag-oculta"));
      btn.disabled = true;
      const botaoAtivo = filtroBotoes.find((b) => b.classList.contains("active"));
      const categoriaAtiva = botaoAtivo ? botaoAtivo.dataset.filtroCategoria : "todas";
      aplicarFiltro(categoriaAtiva);
    });
  });
})();
</script>
</body>
</html>`;
}

function escapeHtml(str) {
  return String(str)
    .replace(/&/g, "&amp;")
    .replace(/</g, "&lt;")
    .replace(/>/g, "&gt;")
    .replace(/"/g, "&quot;");
}

function gerarDescricoesImagens(errosImagem, analises) {
  const visaoScript = path.join(__dirname, "visao.py");

  if (!fs.existsSync(visaoScript)) {
    console.log("visao.py não encontrado em ./visao.py");
    console.log("Pulando descrição de imagens\n");
    return {};
  }

  const { spawnSync } = require("child_process");
  const depCheck = spawnSync(
    "python3",
    ["-c", "import transformers, torch, PIL, requests; print('ok')"],
    { encoding: "utf8", timeout: 10_000 }
  );
  if (depCheck.status !== 0 || !depCheck.stdout?.includes("ok")) {
    console.log("Dependências Python para visão não instaladas.");
    console.log("Execute: pip install transformers torch Pillow requests sacremoses");
    console.log("Pulando descrição de imagens\n");
    return {};
  }

  const entradas = [];
  const urlRegex = /src=["']([^"']+)["']/i;

  for (const analise of analises) {
    for (const erro of analise.erros) {
      if (erro.categoria !== "wcag-1.1.1") continue;
      const match = urlRegex.exec(erro.html);
      if (!match) continue;
      const imgUrl = match[1];
      if (!imgUrl || imgUrl.startsWith("data:")) continue;
      if (!/^https?:\/\//.test(imgUrl)) continue;          
      if (entradas.find((e) => e.url === imgUrl)) continue; 
      entradas.push({
        url:      imgUrl,
        base_url: typeof analise.url === "string" && analise.url.startsWith("http")
                    ? analise.url : "",
      });
    }
  }

  if (entradas.length === 0) {
    console.log("Nenhuma imagem com URL acessível encontrada para descrever");
    return {};
  }
  const TIMEOUT_TOTAL = entradas.length * 30_000 + 60_000;
  const tmpIn  = path.join(__dirname, ".tmp-visao-input.json");
  const tmpOut = path.join(__dirname, ".tmp-visao-output.json");

  try {
    fs.writeFileSync(tmpIn, JSON.stringify(entradas), "utf8");

    const result = spawnSync(
      "python3",
      [visaoScript, tmpIn, tmpOut],
      { stdio: "inherit", timeout: TIMEOUT_TOTAL }
    );

    if (result.error?.code === "ETIMEDOUT") {
      console.log(`visao.py excedeu o tempo limite (${Math.round(TIMEOUT_TOTAL / 1000)}s) — pulando imagens`);
      return {};
    }

    if (result.status !== 0 || !fs.existsSync(tmpOut)) {
      console.log(`visao.py falhou (código ${result.status}) — pulando imagens`);
      return {};
    }

    const saida = JSON.parse(fs.readFileSync(tmpOut, "utf8"));
    const mapa  = {};
    let ok = 0, erros = 0;

    for (const r of saida) {
      if (r.status !== "erro" && r.alt_sugerido) {
        mapa[r.url] = r;
        ok++;
      } else {
        erros++;
      }
    }
    return mapa;

  } catch (err) {
    console.log(`Erro inesperado no visao.py: ${err.message?.slice(0, 80)}`);
    return {};
  } finally {
    [tmpIn, tmpOut].forEach((f) => { try { fs.unlinkSync(f); } catch {} });
  }
}

function corrigirRapido(html, categoria) {
  try {
    switch (categoria) {
      case "wcag-1.1.1":
        if (/<img(?![^>]*\balt=)[^>]*>/.test(html))
          return html.replace(/<img([^>]*)>/, `<img$1 alt="Imagem descritiva">`);
        if (/alt=["']\s*["']/.test(html))
          return html.replace(/alt=["']\s*["']/, `alt="Imagem descritiva"`);
        break;
      case "wcag-1.3.1":
        if (/<div[^>]*class=["'][^"']*(?:title|heading|header)[^"']*["'][^>]*>/.test(html)) {
          const f = html.replace(/<div([^>]*class=["'][^"']*(?:title|heading|header)[^"']*["'][^>]*)>/, `<h2$1>`);
          return f.replace(/<\/div>/, `</h2>`);
        }
        if (/<div[^>]*class=["'][^"']*list[^"']*["']/.test(html) && !/<[uo]l/.test(html))
          return `<ul>${html}</ul>`;
        if (/<td[^>]*(?:bold|header|heading)/.test(html)) {
          const f = html.replace(/<td([^>]*)>/, `<th$1 scope="col">`);
          return f.replace(/<\/td>/, `</th>`);
        }
        break;
      case "wcag-1.4.3":
        if (/color:\s*#[0-9a-f]{3,6}/i.test(html))
          return html.replace(/color:\s*#[0-9a-fA-F]{3,6}/g, `color: #1a1a1a`);
        return html.replace(
          /(<(?:button|a|span|p|div|td|th|li|h[1-6])(\s[^>]*)?)>/,
          `$1 style="color:#1a1a1a;background-color:#ffffff">`
        );
      case "wcag-1.4.4":
        if (/font-size:\s*\d+px/.test(html))
          return html.replace(/font-size:\s*(\d+)px/g, (_, px) => `font-size: ${(parseInt(px)/16).toFixed(3)}rem`);
        break;
      case "wcag-2.1.1":
        if (/<div[^>]*(?:onclick|onmousedown)[^>]*>/.test(html) && !/tabindex/.test(html))
          return html.replace(/(<div)([^>]*(?:onclick|onmousedown))/, `$1 tabindex="0" role="button"$2`);
        if (/<a(?![^>]*href)(?![^>]*tabindex)[^>]*>/.test(html))
          return html.replace(/<a([^>]*)>/, `<a$1 href="#" tabindex="0">`);
        if (/<span[^>]*(?:onclick|onmousedown)[^>]*>/.test(html) && !/tabindex/.test(html))
          return html.replace(/(<span)([^>]*(?:onclick|onmousedown))/, `$1 tabindex="0" role="button"$2`);
        break;
      case "wcag-2.4.1":
        if (!html.includes('href="#main"'))
          return `<a href="#main" class="skip-link">Ir para o conteúdo principal</a>\n${html}`;
        break;
      case "wcag-2.4.2":
        if (/<title>\s*<\/title>/.test(html))
          return html.replace(/<title>\s*<\/title>/, `<title>Página institucional – UNESP</title>`);
        if (!/<title>/i.test(html) && /<head/i.test(html))
          return html.replace(/<head([^>]*)>/i, `<head$1>\n  <title>Página institucional – UNESP</title>`);
        if (/<title>(Untitled|index|default|home|document)<\/title>/i.test(html))
          return html.replace(/<title>[^<]*<\/title>/, `<title>Página institucional – UNESP</title>`);
        break;
      case "wcag-2.4.4":
        if (/<a[^>]*>\s*<\/a>/.test(html))
          return html.replace(/(<a[^>]*>)\s*(<\/a>)/, `$1Acessar página$2`);
        if (/<a[^>]*><\s*(?:img|svg|i)\b/.test(html) && !/aria-label/.test(html))
          return html.replace(/<a([^>]*)>/, `<a$1 aria-label="Acessar link">`);
        break;
      case "wcag-3.1.1":
        if (!/<html[^>]*lang=/i.test(html))
          return html.replace(/<html([^>]*)>/, `<html$1 lang="pt-BR">`);
        return html.replace(/(lang=["'])[^"']*(['"'])/, `$1pt-BR$2`);
      case "wcag-4.1.1": {
        const ids = [...html.matchAll(/\bid="([^"]+)"/g)];
        const seen = new Set();
        let fixed = html, changed = false;
        for (const m of ids) {
          if (seen.has(m[1])) { fixed = fixed.replace(`id="${m[1]}"`, `id="${m[1]}-dup"`); changed = true; }
          seen.add(m[1]);
        }
        if (changed) return fixed;
        if (/<(input|br|hr|meta|link)([^/>]*[^/])>/.test(html))
          return html.replace(/<(input|br|hr|meta|link)([^/>]*[^/])>/g, `<$1$2 />`);
        break;
      }
      case "wcag-4.1.2":
        if (/<button[^>]*>\s*<i[^>]*><\/i>\s*<\/button>/.test(html) && !/aria-label/.test(html))
          return html.replace(/<button([^>]*)>/, `<button$1 aria-label="Ação">`);
        if (/<button[^>]*>\s*<\/button>/.test(html))
          return html.replace(/<button([^>]*)>\s*<\/button>/, `<button$1 aria-label="Ação">Ação</button>`);
        if (/<input(?![^>]*aria-label)[^>]*>/.test(html) && !/<label/.test(html))
          return html.replace(/(<input)([^>]*)(>)/, `$1$2 aria-label="Campo de entrada"$3`);
        if (/<select(?![^>]*aria-label)[^>]*>/.test(html) && !/<label/.test(html))
          return html.replace(/<select([^>]*)>/, `<select$1 aria-label="Selecione uma opção">`);
        if (/<textarea(?![^>]*aria-label)[^>]*>/.test(html) && !/<label/.test(html))
          return html.replace(/<textarea([^>]*)>/, `<textarea$1 aria-label="Campo de texto">`);
        break;
    }
  } catch {}
  return null;
}
async function main() {
  const args = process.argv.slice(2);
  const modoRelatorios = args.includes("--relatorios");

  let origens = [];

  if (modoRelatorios) {
    if (!fs.existsSync(HTMLS_DIR)) {
      console.error("Pasta /htmls não encontrada. Execute primeiro: node crawler.js");
      process.exit(1);
    }
    const arquivos = fs.readdirSync(HTMLS_DIR).filter((f) => f.endsWith(".html"));
    origens = arquivos.map((f) => ({ tipo: "arquivo", valor: path.join(HTMLS_DIR, f) }));
    console.log(`Modo local: ${origens.length} arquivo(s) HTML\n`);
  } else {
    const urls = args.filter((a) => a.startsWith("http"));
    origens = (urls.length > 0 ? urls : DEFAULT_URLS).map((u) => ({ tipo: "url", valor: u }));
    console.log(`Modo URL: ${origens.length} página(s)\n`);
  }

  const browser = await puppeteer.launch({
    headless: "new",
    args: ["--no-sandbox", "--disable-setuid-sandbox"],
  });
  const page = await browser.newPage();

  const analises = [];

  for (const origem of origens) {
    process.stdout.write(`  ${origem.valor.slice(-60)} ... `);
    const r = origem.tipo === "url"
      ? await analisarUrl(page, origem.valor)
      : await analisarArquivo(page, origem.valor);
    analises.push(r);
    const status = r.status === "ok" ? `${r.erros.length} erro(s)` : `${r.mensagem?.slice(0, 40)}`;
    console.log(status);
  }

  await browser.close();

  const modelDir  = path.join(__dirname, "modelo-wcag");
  const temModelo = fs.existsSync(modelDir) &&
                    fs.existsSync(path.join(modelDir, "config.json")) &&
                    fs.existsSync(path.join(modelDir, "label_encoder.pkl"));

  const todosHtmls = analises.flatMap((a) =>
    a.erros.map((e) => ({ html: e.html }))
  );

  let mlMapa = {};
  if (!temModelo) {
    console.log("Modelo DistilBERT não encontrado em ./modelo-wcag/");
    console.log("Execute: python3 treinar.py");
    console.log("Fase 2 ignorada — detecção axe-core continua normalmente\n");
  } else if (todosHtmls.length > 0) {
    mlMapa = classificarComModelo(todosHtmls);
    const total = Object.keys(mlMapa).length;
    console.log(`${total} HTML(s) classificados\n`);
  }

  const visaoMapa = gerarDescricoesImagens(
    analises.flatMap((a) => a.erros.filter((e) => e.categoria === "wcag-1.1.1")),
    analises
  );
  const totalVisao = Object.keys(visaoMapa).length;
  const urlsUnicasSemDesc = new Set(
    analises
      .flatMap((a) => a.erros.filter((e) => e.categoria === "wcag-1.1.1"))
      .map((e) => { const m = /src=["']([^"']+)["']/i.exec(e.html); return m?.[1]; })
      .filter((u) => u && /^https?:\/\//.test(u) && !visaoMapa[u])
  );
  const totalErroVisao = urlsUnicasSemDesc.size;
  console.log(`${totalVisao} com alt sugerido no relatório${totalErroVisao > 0 ? ` · ${totalErroVisao} imagem(ns) sem descrição (erro ou formato não suportado)` : ""}\n`);

  let mlClassificacoes = 0;
  let visaoDescricoes  = 0;
  const urlRegexPipeline = /src=["']([^"']+)["']/i;

  const paginas = analises.map((analise) => {
    const errosComCorrecao = analise.erros.map((e) => {
      const ml = mlMapa[e.html];
      if (ml) mlClassificacoes++;

      let corrigido = corrigirRapido(e.html, e.categoria);

      let blip_descricao = null;
      let blip_alt       = null;
      let blip_metodo    = null;
      let blip_ocr_texto = null;
      if (e.categoria === "wcag-1.1.1") {
        const match = urlRegexPipeline.exec(e.html);
        if (match) {
          const imgUrl = match[1];
          const visao  = visaoMapa[imgUrl];
          if (visao) {
            visaoDescricoes++;
            blip_descricao = visao.descricao_en || null;
            blip_alt       = (visao.alt_sugerido || "").replace(/"/g, "&quot;");
            blip_metodo    = visao.fonte || (visao.status === "cache" ? "cache" : "blip");
            blip_ocr_texto = blip_metodo === "ocr" ? visao.descricao_en || null : null;

            corrigido = e.html.replace(
              /(<img\b[^>]*?)(\s*\/?>)/i,
              (_, attrs, close) => {
                const semAlt = attrs.replace(/\s+alt=["'][^"']*["']/gi, "");
                return `${semAlt} alt="${blip_alt}"${close}`;
              }
            );
          }
        }
      }

      return {
        ...e,
        ml_categoria:   ml?.categoria   ?? null,
        ml_confianca:   ml?.confianca   ?? null,
        html_corrigido: corrigido,
        blip_descricao,
        blip_alt,
        blip_metodo,
        blip_ocr_texto,
      };
    });

    return {
      url:              analise.url,
      status:           analise.status,
      total_erros:      errosComCorrecao.length,
      total_elementos:  analise.totalElementos || 0,
      score:            calcularScore(errosComCorrecao, analise.totalElementos || 0),
      erros:            errosComCorrecao,
    };
  });

  const totalErros = paginas.reduce((s, p) => s + p.total_erros, 0);
  const scoresMedio = paginas.length > 0
    ? Math.round(paginas.reduce((s, p) => s + p.score, 0) / paginas.length)
    : 100;

  const porCategoria = {};
  for (const p of paginas) {
    for (const e of p.erros) {
      porCategoria[e.categoria] = (porCategoria[e.categoria] || 0) + 1;
    }
  }
  const porCategoriaArr = Object.entries(porCategoria)
    .sort((a, b) => b[1] - a[1])
    .map(([categoria, total]) => ({ categoria, total }));

  const dados = {
    gerado_em:  new Date().toLocaleString("pt-BR"),
    resumo: {
      total_paginas:      paginas.length,
      total_erros:        totalErros,
      score_medio:        scoresMedio,
      paginas_criticas:   paginas.filter((p) => p.score < 50).length,
      ml_classificacoes:  mlClassificacoes,
      visao_descricoes:   totalVisao,
      por_categoria:      porCategoriaArr,
    },
    paginas,
  };

  fs.writeFileSync(OUTPUT_JSON, JSON.stringify(dados, null, 2), "utf8");
  fs.writeFileSync(OUTPUT_HTML, gerarHtml(dados), "utf8");

  console.log(`Pipeline concluído!                                  
Páginas analisadas  : ${String(dados.resumo.total_paginas).padEnd(33)}
Total de erros      : ${String(dados.resumo.total_erros).padEnd(33)}
Score médio         : ${String(dados.resumo.score_medio + "/100").padEnd(33)}
Classificações ML   : ${String(dados.resumo.ml_classificacoes).padEnd(33)}
Imagens descritas   : ${String(dados.resumo.visao_descricoes).padEnd(33)}

`);

  if (porCategoriaArr.length > 0) {
    console.log("Top erros por categoria:");
    for (const { categoria, total } of porCategoriaArr.slice(0, 6)) {
      const barra = "█".repeat(Math.min(20, Math.ceil(total / 2)));
      console.log(`   ${categoria.padEnd(15)} → ${String(total).padStart(3)} ${barra}`);
    }
  }
}

main().catch((err) => {
  console.error("Erro fatal:", err);
  process.exit(1);
});
