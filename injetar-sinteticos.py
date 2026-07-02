# injetar-sinteticos.py
# Injeta HTMLs sintéticos para as categorias com poucos ou nenhum exemplo no banco

import sqlite3
import json
import os

DB_PATH = os.path.join(os.path.dirname(__file__), "wcag.db")

SINTETICOS = {
    "wcag-1.1.1": [
        '<img src="foto.jpg">',
        '<img src="banner.png" alt="">',
        '<img src="logo.svg">',
        '<input type="image" src="submit.png">',
        '<span role="img"></span>',
        '<img src="grafico.jpg" title="Gráfico">',
        '<img src="avatar.png" alt="  ">',
        '<img src="icone.gif">',
        '<img src="capa.webp">',
        '<figure><img src="foto2.jpg"></figure>',
        '<img src="slide1.jpg" alt="">',
        '<img src="mapa.png">',
        '<input type="image" src="btn.png" value="Enviar">',
        '<div role="img" class="banner"></div>',
        '<img src="produto.jpg" alt="">',
        '<img src="news.jpg">',
        '<img src="icon.svg">',
        '<img src="thumb.jpg" alt=" ">',
        '<img src="chart.png">',
        '<img src="photo.jpg" alt="">',
    ],
    "wcag-1.3.1": [
        '<div class="title">Sobre a UNESP</div>',
        '<div class="heading">Cursos de Graduação</div>',
        '<div class="list-item">Física</div>',
        '<td class="bold-header">Nome</td>',
        '<div class="header">Pesquisa</div>',
        '<div class="list">Química · Biologia · Matemática</div>',
        '<td style="font-weight:bold">Departamento</td>',
        '<div class="title-section">Extensão</div>',
        '<span class="heading">Contato</span>',
        '<div class="list-group">Item 1 Item 2 Item 3</div>',
        '<div class="subheading">Pós-Graduação</div>',
        '<div class="chapter-header">Capítulo 1</div>',
        '<td class="header-cell">Data</td>',
        '<div class="section-title">Internacional</div>',
        '<div class="list-container"><span>A</span><span>B</span></div>',
        '<div class="heading-main">Campi</div>',
        '<div class="news-title">Notícia do Dia</div>',
        '<td class="col-header">Curso</td>',
        '<div class="page-title">Acesso à Informação</div>',
        '<div class="menu-heading">Navegar</div>',
    ],
    "wcag-1.4.3": [
        '<p style="color: #aaa;">Texto em cinza claro</p>',
        '<span style="color: #ccc; background: #fff;">Texto fraco</span>',
        '<a style="color: #bbb;">Link pouco visível</a>',
        '<div style="color: #999;">Descrição do curso</div>',
        '<p style="color: #c0c0c0;">Informação secundária</p>',
        '<button style="color: #aaa; background: #fff;">Cancelar</button>',
        '<td style="color: #bbb;">Dado da tabela</td>',
        '<h3 style="color: #ddd;">Subtítulo fraco</h3>',
        '<li style="color: #ccc;">Item de lista</li>',
        '<span style="color: #b0b0b0;">Nota de rodapé</span>',
        '<p style="color: #ababab; background-color: #ffffff;">Parágrafo</p>',
        '<a href="#" style="color: #aaaaaa;">Clique aqui</a>',
        '<div style="color: #c8c8c8; background: #fff;">Card de notícia</div>',
        '<button>Enviar</button>',
        '<a href="/sobre">Sobre</a>',
        '<span class="label">Status</span>',
        '<p class="secondary-text">Texto complementar</p>',
        '<div class="caption">Legenda da imagem</div>',
        '<td class="light">Valor</td>',
        '<h4 class="muted">Seção</h4>',
    ],
    "wcag-1.4.4": [
        '<p style="font-size: 12px;">Texto pequeno</p>',
        '<span style="font-size: 10px;">Nota</span>',
        '<div style="font-size: 11px;">Rodapé</div>',
        '<li style="font-size: 13px;">Item</li>',
        '<td style="font-size: 11px;">Célula</td>',
        '<h3 style="font-size: 14px;">Subtítulo</h3>',
        '<p style="font-size: 9px;">Aviso legal</p>',
        '<button style="font-size: 10px;">OK</button>',
        '<a style="font-size: 11px;">Link</a>',
        '<caption style="font-size: 12px;">Tabela de cursos</caption>',
        '<label style="font-size: 10px;">Nome</label>',
        '<small style="font-size: 9px;">Direitos reservados</small>',
        '<p style="font-size: 13px; line-height: 1.2;">Parágrafo denso</p>',
        '<div style="font-size: 12px;">Descrição</div>',
        '<span style="font-size: 11px; color: #333;">Detalhe</span>',
        '<p style="font-size: 10px;">Referência</p>',
        '<td style="font-size: 12px;">Dado</td>',
        '<li style="font-size: 9px;">Sub-item</li>',
        '<h4 style="font-size: 13px;">Título menor</h4>',
        '<a style="font-size: 10px;">Ver mais</a>',
    ],
    "wcag-2.1.1": [
        '<div onclick="abrirMenu()">Menu</div>',
        '<div onmousedown="selecionar()">Selecionar</div>',
        '<a class="nav-link">Sobre</a>',
        '<div onclick="toggle()">Expandir</div>',
        '<span onmousedown="fechar()">×</span>',
        '<div onclick="submit()">Confirmar</div>',
        '<a>Voltar</a>',
        '<div onclick="filtrar()">Filtrar</div>',
        '<span onclick="copiar()">Copiar</span>',
        '<div onmousedown="arrastar()">Arrastar</div>',
        '<a class="btn">Cadastrar</a>',
        '<div onclick="zoom()">+</div>',
        '<span onmousedown="play()">▶</span>',
        '<div onclick="deletar()">Excluir</div>',
        '<a class="action">Baixar</a>',
        '<div onclick="share()">Compartilhar</div>',
        '<span onclick="like()">♥</span>',
        '<div onmousedown="resize()">↕</div>',
        '<a id="nav-home">Início</a>',
        '<div onclick="next()">Próximo</div>',
    ],
    "wcag-2.4.1": [
        '<header><nav><a href="/">Início</a></nav></header><main>Conteúdo</main>',
        '<nav id="menu"><ul><li><a href="/">Home</a></li></ul></nav><div id="content">Texto</div>',
        '<header><ul><li><a href="/sobre">Sobre</a></li></ul></header><article>Artigo</article>',
        '<div class="navbar"><a href="/">Logo</a></div><div class="page">Página</div>',
        '<nav class="top-nav"><a href="/">UNESP</a></nav><section>Seção</section>',
        '<header role="banner"><nav>...</nav></header><div role="main">...</div>',
        '<div id="header"><nav>...</nav></div><div id="main-content">...</div>',
        '<nav aria-label="Principal"><ul>...</ul></nav><main id="conteudo">...</main>',
        '<header><div class="menu">...</div></header><div class="wrapper">...</div>',
        '<nav class="primary"><ul>...</ul></nav><div class="content-area">...</div>',
        '<div class="site-header"><nav>...</nav></div><div class="site-body">...</div>',
        '<header><div id="navigation">...</div></header><div id="body">...</div>',
        '<nav id="main-nav">...</nav><div id="page-content">...</div>',
        '<div role="navigation">...</div><div role="main">...</div>',
        '<header class="fixed-top"><nav>...</nav></header><section class="hero">...</section>',
        '<nav class="breadcrumb">...</nav><main class="container">...</main>',
        '<div id="top-bar"><nav>...</nav></div><div id="wrapper">...</div>',
        '<nav><ul><li><a href="/">Início</a></li></ul></nav><div>Conteúdo principal</div>',
        '<header><nav class="navbar">...</nav></header><main class="main-area">...</main>',
        '<div class="top-navigation">...</div><div class="main-body">...</div>',
    ],
    "wcag-2.4.2": [
        '<html><head><title></title></head><body></body></html>',
        '<html><head></head><body><h1>UNESP</h1></body></html>',
        '<html><head><title>   </title></head><body></body></html>',
        '<html><head><title>Untitled</title></head><body></body></html>',
        '<html><head><title>Página</title></head><body></body></html>',
        '<html><head><title>index</title></head><body></body></html>',
        '<html><head><title>Page 1</title></head><body></body></html>',
        '<html><head><title>default</title></head><body></body></html>',
        '<html><head><title>home</title></head><body></body></html>',
        '<html><head><title>new page</title></head><body></body></html>',
        '<html><head><title>unesp</title></head><body></body></html>',
        '<html><head></head><body><main>...</main></body></html>',
        '<html><head><title>-</title></head><body></body></html>',
        '<html><head><title>portal</title></head><body></body></html>',
        '<html><head><title>www.unesp.br</title></head><body></body></html>',
        '<html><head><title>document</title></head><body></body></html>',
        '<html><head></head><body><p>Conteúdo da página</p></body></html>',
        '<html><head><title>pagina-sem-nome</title></head><body></body></html>',
        '<html><head><title>...</title></head><body></body></html>',
        '<html><head><title>null</title></head><body></body></html>',
    ],
    "wcag-3.1.1": [
        '<html><head></head><body></body></html>',
        '<html lang=""><head></head><body></body></html>',
        '<html lang="en"><head></head><body>Texto em português</body></html>',
        '<html lang="es"><head></head><body>Conteúdo UNESP</body></html>',
        '<html lang="fr"><head></head><body>Portal da UNESP</body></html>',
        '<html lang="de"><head></head><body>Graduação</body></html>',
        '<html lang="it"><head></head><body>Pesquisa</body></html>',
        '<html><body><p>Parágrafo sem idioma definido</p></body></html>',
        '<html lang="xx"><head></head><body></body></html>',
        '<html lang="pt"><head></head><body></body></html>',
        '<html lang="EN"><head></head><body></body></html>',
        '<html LANG="en-US"><head></head><body></body></html>',
        '<html lang="zh"><head></head><body>Página em português</body></html>',
        '<html lang="ar"><head></head><body>Conteúdo</body></html>',
        '<html lang="ru"><head></head><body>Portal</body></html>',
        '<html lang="ja"><head></head><body>UNESP</body></html>',
        '<html lang="ko"><head></head><body>Universidade</body></html>',
        '<html lang=""><body>Notícias</body></html>',
        '<html lang="pt-"><body>Campi</body></html>',
        '<html><body><h1>Bem-vindo</h1></body></html>',
    ],
    "wcag-4.1.1": [
        '<div id="main"><span id="main">Duplicado</span></div>',
        '<input id="email"><input id="email" type="email">',
        '<div id="header"><div id="header">Nav</div></div>',
        '<input id="nome"><label for="nome">Nome</label><input id="nome" type="text">',
        '<button id="btn-submit">Enviar</button><a id="btn-submit">Link</a>',
        '<input id="campo"><select id="campo"><option>A</option></select>',
        '<br>',
        '<hr>',
        '<img src="x.jpg">',
        '<input type="text" id="x"><div id="x">Label</div>',
        '<div id="sidebar"><nav id="sidebar">Menu</nav></div>',
        '<span id="tooltip"></span><div id="tooltip">Dica</div>',
        '<div id="modal"><div id="modal"><p>Conteúdo</p></div></div>',
        '<a id="link1">A</a><a id="link1">B</a>',
        '<td id="cell1">1</td><td id="cell1">2</td>',
        '<input id="pass" type="password"><input id="pass" type="text">',
        '<section id="sobre"><article id="sobre">Texto</article></section>',
        '<h1 id="titulo">Título</h1><h2 id="titulo">Subtítulo</h2>',
        '<div id="footer"><p id="footer">Rodapé</p></div>',
        '<label id="lbl">Nome</label><span id="lbl">Obrigatório</span>',
    ],
    "wcag-4.1.2": [
        '<button><i class="fa fa-bars"></i></button>',
        '<button></button>',
        '<button><svg viewBox="0 0 24 24"><path d="M3 12h18"/></svg></button>',
        '<input type="text">',
        '<select><option>Selecione</option></select>',
        '<textarea></textarea>',
        '<div role="dialog"><p>Conteúdo</p></div>',
        '<nav role="navigation"><ul><li><a href="/">Início</a></li></ul></nav>',
        '<button><i class="fa fa-search"></i></button>',
        '<button><img src="icon.png"></button>',
        '<input type="email" placeholder="email@unesp.br">',
        '<select name="curso"><option value="">Curso</option></select>',
        '<div role="alertdialog"><p>Erro!</p></div>',
        '<button><span class="icon-close"></span></button>',
        '<input type="tel">',
        '<textarea name="mensagem" placeholder="Digite aqui"></textarea>',
        '<button><i class="material-icons">menu</i></button>',
        '<div role="complementary"><p>Sidebar</p></div>',
        '<input type="search" name="q">',
        '<button type="submit"><i class="fa fa-send"></i></button>',
    ],
}

def injetar():
    conn = sqlite3.connect(DB_PATH)
    cur = conn.cursor()

    cur.execute("""
        CREATE TABLE IF NOT EXISTS analises (
            id        INTEGER PRIMARY KEY AUTOINCREMENT,
            url       TEXT NOT NULL,
            categoria TEXT NOT NULL,
            htmls     TEXT NOT NULL,
            criado_em TEXT DEFAULT (datetime('now'))
        )
    """)

    total_injetado = 0

    for categoria, htmls in SINTETICOS.items():
        cur.execute(
            "DELETE FROM analises WHERE url = ? AND categoria = ?",
            ("sintetico://gerado", categoria)
        )
        chunk = 5
        for i in range(0, len(htmls), chunk):
            bloco = htmls[i:i+chunk]
            cur.execute(
                "INSERT INTO analises (url, categoria, htmls) VALUES (?, ?, ?)",
                ("sintetico://gerado", categoria, json.dumps(bloco))
            )
            total_injetado += len(bloco)

    conn.commit()

    print("Injeção concluída.\n")
    cur.execute("SELECT categoria, COUNT(*) FROM analises GROUP BY categoria ORDER BY 2 DESC")
    print("Distribuição atual no banco:")
    for row in cur.fetchall():
        total_htmls = 0
        cur2 = conn.cursor()
        cur2.execute("SELECT htmls FROM analises WHERE categoria = ?", (row[0],))
        for (h,) in cur2.fetchall():
            try:
                total_htmls += len(json.loads(h))
            except:
                pass
        print(f"   {row[0]:<15} → {row[1]} linha(s) / ~{total_htmls} HTML(s)")
    print(f"\n   Total injetado : {total_injetado} HTMLs sintéticos")

    conn.close()

if __name__ == "__main__":
    injetar()
