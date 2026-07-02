// analisar.js — roda axe-core em cima dos HTMLs salvos pelo crawler
//
// Entrada : pasta /htmls  (gerada pelo crawler.js)
// Saída   : pasta /relatorios com um .json por página
//
// Uso: node analisar.js

const puppeteer = require("puppeteer");
const axe       = require("axe-core");
const fs        = require("fs");
const path      = require("path");

const HTML_DIR      = path.join(__dirname, "htmls");
const OUTPUT_DIR    = path.join(__dirname, "relatorios");
const TIMEOUT_MS    = 20000;

const VIEWPORTS = [
  { nome: "desktop", width: 1280, height: 800, isMobile: false, hasTouch: false },
  { nome: "mobile", width: 375, height: 667, isMobile: true, hasTouch: true }
];

const RULE_TO_WCAG = {
  "image-alt":               "wcag-1.1.1",
  "input-image-alt":         "wcag-1.1.1",
  "role-img-alt":            "wcag-1.1.1",
  "td-headers-attr":         "wcag-1.3.1",
  "th-has-data-cells":       "wcag-1.3.1",
  "list":                    "wcag-1.3.1",
  "listitem":                "wcag-1.3.1",
  "color-contrast":          "wcag-1.4.3",
  "meta-viewport":           "wcag-1.4.4",
  "keyboard":                "wcag-2.1.1",
  "tabindex":                "wcag-2.1.1",
  "bypass":                  "wcag-2.4.1",
  "document-title":          "wcag-2.4.2",
  "link-name":               "wcag-2.4.4",
  "html-has-lang":           "wcag-3.1.1",
  "html-lang-valid":         "wcag-3.1.1",
  "duplicate-id":            "wcag-4.1.1",
  "duplicate-id-active":     "wcag-4.1.1",
  "duplicate-id-aria":       "wcag-4.1.1",
  "button-name":             "wcag-4.1.2",
  "label":                   "wcag-4.1.2",
  "select-name":             "wcag-4.1.2",
  "textarea-name":           "wcag-4.1.2",
  "aria-required-attr":      "wcag-4.1.2",
  "aria-required-children":  "wcag-4.1.2",
  "aria-roles":              "wcag-4.1.2",
};

function extrairHtmlDoNo(no) {
  if (no.html) return no.html;
  if (no.target && no.target[0]) return `<!-- seletor: ${no.target[0]} -->`;
  return "";
}

async function analisar() {
  if (!fs.existsSync(OUTPUT_DIR)) fs.mkdirSync(OUTPUT_DIR);

  const arquivos = fs
    .readdirSync(HTML_DIR)
    .filter((f) => f.endsWith(".html"));

  if (arquivos.length === 0) {
    console.error("Nenhum arquivo .html encontrado em /htmls");
    console.error("Execute primeiro: node crawler.js");
    process.exit(1);
  }

  const browser = await puppeteer.launch({
    headless: "new",
    args: ["--no-sandbox", "--disable-setuid-sandbox"],
  });

  console.log(`Analisando ${arquivos.length} página(s)...\n`);

  let totalErros = 0;

  for (const arquivo of arquivos) {
    const filePath = path.join(HTML_DIR, arquivo);
    const fileUrl  = `file://${filePath}`;
    const nomeBase = arquivo.replace(".html", "");

    process.stdout.write(`  ${arquivo} ... `);

    try {
      const page = await browser.newPage();
      await page.goto(fileUrl, { waitUntil: "domcontentloaded", timeout: TIMEOUT_MS });

      const errosConsolidados = [];
      const chavesVistas = new Set();

      for (const vp of VIEWPORTS) {
        await page.setViewport({
          width: vp.width,
          height: vp.height,
          isMobile: vp.isMobile,
          hasTouch: vp.hasTouch
        });
        
        await page.evaluate(() => window.dispatchEvent(new Event('resize')));

        await page.evaluate(() => { if (window.axe) delete window.axe; });
        await page.addScriptTag({ content: axe.source });
        const resultado = await page.evaluate(async () => {
          return await window.axe.run(document, { resultTypes: ["violations"] });
        });

        for (const violacao of resultado.violations) {
          const categoria = RULE_TO_WCAG[violacao.id];
          if (!categoria) continue;

          for (const no of violacao.nodes) {
            const html = extrairHtmlDoNo(no);
            if (!html || html.length < 5) continue;

            const seletor = no.target?.[0] || "";
            const chaveUnica = `${violacao.id}|${seletor}|${html}`;

            if (chavesVistas.has(chaveUnica)) continue;
            chavesVistas.add(chaveUnica);

            errosConsolidados.push({
              categoria,
              regra: violacao.id,
              impacto: violacao.impact,
              html,
              mensagem: `${violacao.description} (Detectado em: ${vp.nome})`,
            });
          }
        }
      }

    await page.close();

    const relatorio = {
      arquivo,
      url: fileUrl,
      totalErros: errosConsolidados.length,
      erros: errosConsolidados,
    };

    const saida = path.join(OUTPUT_DIR, `${nomeBase}.json`);
    fs.writeFileSync(saida, JSON.stringify(relatorio, null, 2), "utf8");

    totalErros += errosConsolidados.length;
    console.log(`${errosConsolidados.length} erro(s) consolidados`);
  } catch (err) {
    console.log(`Erro: ${err.message}`);
  }
}

  await browser.close();

  console.log(`\nAnálise concluída.`);
  console.log(`Total de erros encontrados : ${totalErros}`);
  console.log(`Relatórios em             : ${OUTPUT_DIR}`);
}

analisar().catch((err) => {
  console.error("Erro:", err);
  process.exit(1);
});
