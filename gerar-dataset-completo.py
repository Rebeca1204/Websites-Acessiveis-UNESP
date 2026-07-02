# gerar-dataset-completo.py
# Lê o SQLite e gera dataset-balanced.jsonl com todas as 11 categorias WCAG.

import sqlite3
import json
import os
import re
import random
from collections import defaultdict

DB_PATH     = os.path.join(os.path.dirname(__file__), "wcag.db")
OUTPUT_PATH = os.path.join(os.path.dirname(__file__), "dataset-balanced.jsonl")
TARGET      = 800   # exemplos por categoria
SEED        = 42

random.seed(SEED)

def corrigir(html, categoria):
    if categoria == "wcag-1.1.1":
        if re.search(r'<img(?![^>]*\balt=)[^>]*>', html):
            return re.sub(r'<img([^>]*)>', r'<img\1 alt="Imagem descritiva">', html, count=1)
        if re.search(r'<input[^>]*type=["\']image["\'][^>]*>', html) and 'alt=' not in html:
            return re.sub(r'(<input[^>]*type=["\']image["\'][^>]*)(>)', r'\1 alt="Botão de imagem"\2', html, count=1)
        if 'role="img"' in html and 'aria-label=' not in html:
            return html.replace('role="img"', 'role="img" aria-label="Elemento gráfico"', 1)
        # alt vazio
        if re.search(r'alt=["\']\s*["\']', html):
            return re.sub(r'alt=["\']\s*["\']', 'alt="Imagem descritiva"', html, count=1)

    elif categoria == "wcag-1.3.1":
        if re.search(r'<div[^>]*class=["\'][^"\']*(?:title|heading|header)[^"\']*["\'][^>]*>', html):
            fixed = re.sub(r'<div([^>]*class=["\'][^"\']*(?:title|heading|header)[^"\']*["\'][^>]*)>', r'<h2\1>', html, count=1)
            return re.sub(r'</div>', '</h2>', fixed, count=1)
        if re.search(r'<div[^>]*class=["\'][^"\']*list[^"\']*["\']', html) and not re.search(r'<[uo]l', html):
            return f'<ul>{html}</ul>'
        if re.search(r'<td[^>]*(?:bold|header|heading)', html):
            fixed = re.sub(r'<td([^>]*)>', r'<th\1 scope="col">', html, count=1)
            return re.sub(r'</td>', '</th>', fixed, count=1)
        if re.search(r'<(div|span)[^>]*class=["\'][^"\']*(?:list|subheading|chapter|section|news|menu|page)[^"\']*["\']', html):
            return re.sub(r'<(div|span)([^>]*)>', r'<h3\2>', html, count=1).replace('</div>', '</h3>').replace('</span>', '</h3>')

    elif categoria == "wcag-1.4.3":
        if re.search(r'color:\s*#(?:[0-9a-f]{3}){1,2}', html, re.I):
            return re.sub(r'color:\s*#[0-9a-fA-F]{3,6}', 'color: #1a1a1a', html)
        if re.search(r'<(button|a|span|p|div|td|th|li|h[1-6])(\s[^>]*)?>', html):
            return re.sub(
                r'(<(?:button|a|span|p|div|td|th|li|h[1-6])(\s[^>]*)?)>',
                r'\1 style="color:#1a1a1a;background-color:#ffffff">',
                html, count=1
            )

    elif categoria == "wcag-1.4.4":
        if re.search(r'font-size:\s*\d+px', html):
            def px_to_rem(m):
                px = int(m.group(1))
                return f'font-size: {px/16:.3f}rem'
            return re.sub(r'font-size:\s*(\d+)px', px_to_rem, html)

    elif categoria == "wcag-2.1.1":
        if re.search(r'<div[^>]*(?:onclick|onmousedown)[^>]*>', html) and 'tabindex' not in html:
            return re.sub(r'(<div)([^>]*(?:onclick|onmousedown))', r'\1 tabindex="0" role="button"\2', html, count=1)
        if re.search(r'<a(?![^>]*href)(?![^>]*tabindex)[^>]*>', html):
            return re.sub(r'<a([^>]*)>', r'<a\1 href="#" tabindex="0">', html, count=1)
        if re.search(r'<span[^>]*(?:onclick|onmousedown)[^>]*>', html) and 'tabindex' not in html:
            return re.sub(r'(<span)([^>]*(?:onclick|onmousedown))', r'\1 tabindex="0" role="button"\2', html, count=1)

    elif categoria == "wcag-2.4.1":
        if 'href="#main"' not in html and 'href="#conteudo"' not in html:
            return f'<a href="#main" class="skip-link">Ir para o conteúdo principal</a>\n{html}'

    elif categoria == "wcag-2.4.4":
        # link completamente vazio: <a ...></a>
        if re.search(r'<a[^>]*>\s*</a>', html):
            return re.sub(r'(<a[^>]*>)\s*(</a>)', r'\1Acessar página\2', html, count=1)
        # link com apenas img/svg/i sem aria-label
        if re.search(r'<a[^>]*><\s*(?:img|svg|i)\b', html) and 'aria-label' not in html:
            return re.sub(r'<a([^>]*)>', r'<a\1 aria-label="Acessar link">', html, count=1)
        # texto genérico
        if re.search(r'<a[^>]*>\s*(?:clique aqui|saiba mais|aqui|leia mais|veja mais|more|click here)\s*</a>', html, re.I):
            return re.sub(
                r'(<a[^>]*>)\s*(clique aqui|saiba mais|aqui|leia mais|veja mais|more|click here)\s*(</a>)',
                r'\1Acesse o conteúdo relacionado\3',
                html, count=1, flags=re.I
            )

    elif categoria == "wcag-2.4.2":
        if re.search(r'<title>\s*</title>', html):
            return re.sub(r'<title>\s*</title>', '<title>Página institucional – UNESP</title>', html)
        if '<title>' not in html and '<head' in html:
            return re.sub(r'<head([^>]*)>', r'<head\1>\n  <title>Página institucional – UNESP</title>', html)
        # título genérico/vazio
        if re.search(r'<title>(Untitled|index|Page \d+|default|home|new page|unesp|portal|www\.|document|-|\.\.\.|null|pagina-sem-nome|   )</title>', html, re.I):
            return re.sub(r'<title>[^<]*</title>', '<title>Página institucional – UNESP</title>', html)

    elif categoria == "wcag-3.1.1":
        if not re.search(r'<html[^>]*lang=', html, re.I):
            return re.sub(r'<html([^>]*)>', r'<html\1 lang="pt-BR">', html, count=1)
        # lang errado
        if re.search(r'<html[^>]*lang=["\'][^"\']*["\']', html, re.I):
            return re.sub(r'(lang=["\'])[^"\']*(["\'])', r'\1pt-BR\2', html, count=1)

    elif categoria == "wcag-4.1.1":
        ids = re.findall(r'\bid="([^"]+)"', html)
        seen = set()
        fixed = html
        changed = False
        for id_val in ids:
            if id_val in seen:
                fixed = fixed.replace(f'id="{id_val}"', f'id="{id_val}-dup"', 1)
                changed = True
            seen.add(id_val)
        if changed:
            return fixed
        # void elements sem fechar
        if re.search(r'<(input|br|hr|meta|link)([^/>]*[^/])>', html):
            return re.sub(r'<(input|br|hr|meta|link)([^/>]*[^/])>', r'<\1\2 />', html)

    elif categoria == "wcag-4.1.2":
        if re.search(r'<button[^>]*>\s*<i[^>]*></i>\s*</button>', html) and 'aria-label' not in html:
            return re.sub(r'<button([^>]*)>', r'<button\1 aria-label="Ação">', html, count=1)
        if re.search(r'<button[^>]*>\s*</button>', html):
            return re.sub(r'<button([^>]*)>\s*</button>', r'<button\1 aria-label="Ação">Ação</button>', html, count=1)
        if re.search(r'<button[^>]*>\s*<svg', html) and 'aria-label' not in html:
            return re.sub(r'<button([^>]*)>', r'<button\1 aria-label="Ação">', html, count=1)
        if re.search(r'<input(?![^>]*aria-label)(?![^>]*aria-labelledby)[^>]*>', html) and '<label' not in html:
            return re.sub(r'(<input)([^>]*)(>)', r'\1\2 aria-label="Campo de entrada"\3', html, count=1)
        if re.search(r'<select(?![^>]*aria-label)[^>]*>', html) and '<label' not in html:
            return re.sub(r'<select([^>]*)>', r'<select\1 aria-label="Selecione uma opção">', html, count=1)
        if re.search(r'<textarea(?![^>]*aria-label)[^>]*>', html) and '<label' not in html:
            return re.sub(r'<textarea([^>]*)>', r'<textarea\1 aria-label="Campo de texto">', html, count=1)
        if re.search(r'role=["\'](?:dialog|alertdialog|navigation|complementary|region)["\']', html) \
                and 'aria-label' not in html and 'aria-labelledby' not in html:
            return re.sub(r'(role=["\'](?:dialog|alertdialog|navigation|complementary|region)["\'])',
                          r'\1 aria-label="Região"', html, count=1)
        if re.search(r'<button(?![^>]*aria-label)[^>]*><img', html):
            return re.sub(r'<button([^>]*)>', r'<button\1 aria-label="Ação">', html, count=1)

    return None


def variacoes(html):
    """
    Gera variações do HTML base que diversificam o SINAL DE ENTRADA para o modelo,
    mantendo o mesmo ERRO WCAG no miolo.
    """
    ATTRS = [
        "",
        ' class="img-fluid"',
        ' class="banner"',
        ' id="elemento-principal"',
        ' style="max-width:100%"',
        ' loading="lazy"',
    ]
    ANTES = [
        "",
        "<p>Conteúdo relacionado:</p>\n",
        "<h2>Seção</h2>\n",
        "<!-- elemento -->\n",
    ]
    DEPOIS = [
        "",
        "\n<small>Fonte: acervo institucional</small>",
        "\n<!-- fim -->",
    ]

    vistos = set()
    resultado = []
    import re as _re
    for attr in ATTRS:
        if attr:
            var = _re.sub(r'(<[a-zA-Z][a-zA-Z0-9]*)(\s|>|/>)', rf'\1{attr}\2', html, count=1)
        else:
            var = html
        if var not in vistos:
            vistos.add(var)
            resultado.append(var)

    for antes in ANTES:
        for depois in DEPOIS:
            if antes or depois:
                var = f"{antes}{html}{depois}"
                if var not in vistos:
                    vistos.add(var)
                    resultado.append(var)

    for tag in ("div", "section", "article", "li"):
        var = f"<{tag}>{html}</{tag}>"
        if var not in vistos:
            vistos.add(var)
            resultado.append(var)

    return resultado

def gerar():
    conn = sqlite3.connect(DB_PATH)
    cur = conn.cursor()
    cur.execute("SELECT url, categoria, htmls FROM analises WHERE htmls IS NOT NULL AND categoria IS NOT NULL")
    rows = cur.fetchall()
    conn.close()

    por_cat = defaultdict(list)
    for url, cat, htmls_str in rows:
        try:
            htmls = json.loads(htmls_str)
        except:
            continue
        if isinstance(htmls, list):
            por_cat[cat].extend(htmls)

    cats = sorted(por_cat.keys())
    print(f"Categorias no banco: {len(cats)}")
    for c in cats:
        print(f"{c:<15} → {len(por_cat[c])} HTML(s) base")

    todos = []
    dist = {}

    for cat in cats:
        base = por_cat[cat]
        exemplos = []
        i = 0
        tentativas = 0
        max_tent = TARGET * 20

        while len(exemplos) < TARGET and tentativas < max_tent:
            html_base = base[i % len(base)]
            for var in variacoes(html_base):
                if len(exemplos) >= TARGET:
                    break
                corrigido = corrigir(var, cat)
                if corrigido and corrigido != var:
                    exemplos.append({
                        "input":  f"### ERRO WCAG: {cat}\n### HTML com problema:\n{var}",
                        "output": corrigido,
                    })
            i += 1
            tentativas += 1

        dist[cat] = len(exemplos)
        todos.extend(exemplos)

    random.shuffle(todos)

    with open(OUTPUT_PATH, "w", encoding="utf-8") as f:
        for ex in todos:
            f.write(json.dumps(ex, ensure_ascii=False) + "\n")

    print(f"\nDataset gerado: {OUTPUT_PATH}")
    print(f"\n   Total: {len(todos)} exemplos")

    with open(OUTPUT_PATH) as f:
        for i, line in enumerate(f):
            if i >= 3:
                break
            obj = json.loads(line)
            cat = obj["input"].split("\n")[0].replace("### ERRO WCAG: ", "")
            print(f"{cat} — {obj['input'][20:80].replace(chr(10),' ')}...")

if __name__ == "__main__":
    gerar()
