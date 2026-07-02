// salvar.js — lê os relatórios JSON e persiste no SQLite
const fs      = require("fs");
const path    = require("path");
const { getDb } = require("./db.js");

const RELATORIOS_DIR = path.join(__dirname, "relatorios");

async function salvar() {
  const arquivos = fs
    .readdirSync(RELATORIOS_DIR)
    .filter((f) => f.endsWith(".json"));

  if (arquivos.length === 0) {
    console.error("Nenhum relatório encontrado em /relatorios");
    console.error("Execute primeiro: node analisar.js");
    process.exit(1);
  }

  const { db, salvar: salvarDisco } = await getDb();

  console.log("Limpando dados anteriores");
  db.run("DELETE FROM analises");

  const agrupado = {};
  let totalLidos = 0;

  for (const arquivo of arquivos) {
    const filePath = path.join(RELATORIOS_DIR, arquivo);
    const conteudo = JSON.parse(fs.readFileSync(filePath, "utf8"));
    const url      = conteudo.url || arquivo;

    for (const erro of conteudo.erros || []) {
      if (!erro.html || !erro.categoria) continue;
      const chave = `${url}||${erro.categoria}`;
      if (!agrupado[chave]) {
        agrupado[chave] = { url, categoria: erro.categoria, htmls: [] };
      }
      agrupado[chave].htmls.push(erro.html);
      totalLidos++;
    }
  }

  const stmt = db.prepare(
    "INSERT INTO analises (url, categoria, htmls) VALUES (?, ?, ?)"
  );

  for (const { url, categoria, htmls } of Object.values(agrupado)) {
    stmt.run([url, categoria, JSON.stringify(htmls)]);
  }
  stmt.free();
  salvarDisco();

  const stats = db.exec(
    "SELECT categoria, COUNT(*) as linhas FROM analises GROUP BY categoria ORDER BY linhas DESC"
  );

  console.log(`\nDados salvos no banco.`);
  console.log(`Erros lidos     : ${totalLidos}`);
  console.log(`Linhas no banco : ${Object.keys(agrupado).length}`);
  console.log(`\nDistribuição por categoria:`);

  if (stats.length > 0) {
    const [cols, ...rows2] = [stats[0].columns, ...stats[0].values];
    for (const row of stats[0].values) {
      console.log(`   ${String(row[0]).padEnd(15)} → ${row[1]} linha(s)`);
    }
  }
}

salvar().catch((err) => {
  console.error("Erro:", err);
  process.exit(1);
});
