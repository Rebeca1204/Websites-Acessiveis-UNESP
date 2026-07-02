// crawler.js — visita páginas da UNESP e salva os HTMLs em disco
//
// Saída: pasta /htmls com um arquivo .html por página visitada
//        arquivo urls-visitadas.json com o log
//
// Uso: node crawler.js

const puppeteer = require("puppeteer");
const fs = require("fs");
const path = require("path");

const SEED_URLS = [
  "https://www.unesp.br",
  "https://www.unesp.br/portal#!/noticia",
  "https://www.unesp.br/portal#!/graduacao",
  "https://www.unesp.br/portal#!/pos-graduacao",
  "https://www.unesp.br/portal#!/pesquisa",
  "https://www.unesp.br/portal#!/extensao",
  "https://www.unesp.br/portal#!/internacional",
  "https://www.unesp.br/portal#!/sobre",
  "https://www.unesp.br/portal#!/campi",
  "https://www.unesp.br/portal#!/acesso-informacao",
];

const MAX_PAGINAS       = 30;        
const MAX_PROFUNDIDADE  = 3;          
const TIMEOUT_MS        = 15000;       
const OUTPUT_DIR        = path.join(__dirname, "htmls");
const LOG_PATH          = path.join(__dirname, "urls-visitadas.json");

function slugify(url) {
  return url
    .replace(/https?:\/\//, "")
    .replace(/[^a-z0-9]/gi, "_")
    .slice(0, 100);
}

async function crawl() {
  if (!fs.existsSync(OUTPUT_DIR)) fs.mkdirSync(OUTPUT_DIR);

  const browser = await puppeteer.launch({
    headless: "new",
    args: ["--no-sandbox", "--disable-setuid-sandbox"],
  });

  const page = await browser.newPage();
  await page.setViewport({ width: 1280, height: 800 });
  await page.setUserAgent(
    "Mozilla/5.0 (compatible; WCAG-Crawler/1.0; +academic-research)"
  );

  const visitadas = new Set();
  const fila      = SEED_URLS.map((url) => ({ url, profundidade: 0 }));
  const naFila    = new Set(SEED_URLS);
  const log       = [];

  console.log(`Iniciando crawler — máximo ${MAX_PAGINAS} páginas, profundidade máxima ${MAX_PROFUNDIDADE}\n`);

  while (fila.length > 0 && visitadas.size < MAX_PAGINAS) {
    const { url, profundidade } = fila.shift();
    naFila.delete(url);
    if (visitadas.has(url)) continue;
    visitadas.add(url);

    process.stdout.write(`[${visitadas.size}/${MAX_PAGINAS}] (prof. ${profundidade}) ${url} ... `);

    try {
      await page.goto(url, {
        waitUntil: "networkidle2",
        timeout: TIMEOUT_MS,
      });

      const html = await page.content();

      const arquivo = path.join(OUTPUT_DIR, `${slugify(url)}.html`);
      fs.writeFileSync(arquivo, html, "utf8");

      log.push({ url, arquivo: path.basename(arquivo), profundidade, status: "ok" });

      if (profundidade >= MAX_PROFUNDIDADE) {
        continue;
      }

      const links = await page.$$eval("a[href]", (els) =>
        els.map((el) => el.href)
      );

      for (const link of links) {
        if (
          typeof link === "string" &&
          link.startsWith("https://www.unesp.br") &&
          /^https:\/\/www\.unesp\.br/.test(link) &&
          !link.startsWith("https://www.unesp.br#") &&
          !visitadas.has(link) &&
          !naFila.has(link)
        ) {
          fila.push({ url: link, profundidade: profundidade + 1 });
          naFila.add(link);
        }
      }
    } catch (err) {
      console.log(`Erro: ${err.message}`);
      log.push({ url, profundidade, status: "erro", mensagem: err.message });
    }
  }

  await browser.close();

  fs.writeFileSync(LOG_PATH, JSON.stringify(log, null, 2), "utf8");

  console.log(`\n✅ Crawler finalizado.`);
  console.log(`Páginas salvas : ${log.filter((l) => l.status === "ok").length}`);
  console.log(`Erros          : ${log.filter((l) => l.status === "erro").length}`);
  console.log(`HTMLs em       : ${OUTPUT_DIR}`);
}

crawl().catch((err) => {
  console.error("Erro no crawler:", err);
  process.exit(1);
});
