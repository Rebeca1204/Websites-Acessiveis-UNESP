// db.js
const initSqlJs = require("sql.js");
const fs = require("fs");
const path = require("path");

const DB_PATH = path.join(__dirname, "wcag.db");

let _db = null;

async function getDb() {
  if (_db) return _db;

  const SQL = await initSqlJs();

  let db;
  if (fs.existsSync(DB_PATH)) {
    const buffer = fs.readFileSync(DB_PATH);
    db = new SQL.Database(buffer);
  } else {
    db = new SQL.Database();
  }

  db.run(`
    CREATE TABLE IF NOT EXISTS analises (
      id        INTEGER PRIMARY KEY AUTOINCREMENT,
      url       TEXT NOT NULL,
      categoria TEXT NOT NULL,
      htmls     TEXT NOT NULL,
      criado_em TEXT DEFAULT (datetime('now'))
    )
  `);

  db.run(`CREATE INDEX IF NOT EXISTS idx_categoria ON analises(categoria)`);

  function salvar() {
    const data = db.export();
    fs.writeFileSync(DB_PATH, Buffer.from(data));
  }

  _db = { db, salvar };
  return _db;
}

module.exports = { getDb };
