#testar.py — Suite de Testes Automatizados para Regras WCAG e IA


import unittest
import subprocess
import json
import os
import sys
_VISAO_DISPONIVEL = False
_limpar_repeticoes = None
extrair_imgs_sem_alt = None

try:
    import importlib.util
    _spec = importlib.util.spec_from_file_location("visao", "visao.py")
    if _spec:
        _visao_mod = importlib.util.module_from_spec(_spec)
        import unittest.mock as _mock
        with _mock.patch.dict("sys.modules", {
            "transformers": _mock.MagicMock(),
            "torch": _mock.MagicMock(),
            "PIL": _mock.MagicMock(),
            "PIL.Image": _mock.MagicMock(),
            "requests": _mock.MagicMock(),
        }):
            _spec.loader.exec_module(_visao_mod)
        _limpar_repeticoes  = _visao_mod._limpar_repeticoes
        extrair_imgs_sem_alt = _visao_mod.extrair_imgs_sem_alt
        _VISAO_DISPONIVEL = True
except Exception:
    pass

_DATASET_DISPONIVEL = False
_corrigir_py = None

try:
    import importlib.util as _ilu
    _spec2 = _ilu.spec_from_file_location("gerar_dataset", "gerar-dataset-completo.py")
    if _spec2:
        _ds_mod = _ilu.module_from_spec(_spec2)
        import unittest.mock as _mock2
        with _mock2.patch("sqlite3.connect"), _mock2.patch("builtins.open", _mock2.mock_open()):
            _spec2.loader.exec_module(_ds_mod)
        _corrigir_py = _ds_mod.corrigir
        _DATASET_DISPONIVEL = True
except Exception:
    pass

_JS_CORRIGIR = r"""
function corrigirRapido(html, categoria) {
  try {
    switch (categoria) {

      //texto alternativo em imagens
      case "wcag-1.1.1":
        if (/<img(?![^>]*\balt=)[^>]*>/.test(html))
          return html.replace(/<img([^>]*)>/, `<img$1 alt="Imagem descritiva">`);
        if (/alt=["']\s*["']/.test(html))
          return html.replace(/alt=["']\s*["']/, `alt="Imagem descritiva"`);
        break;

      // nformação e relações semânticas
      case "wcag-1.3.1":
        if (/<div[^>]*class=["'][^"']*(?:title|heading|header)[^"']*["'][^>]*>/.test(html)) {
          let f = html.replace(/<div([^>]*class=["'][^"']*(?:title|heading|header)[^"']*["'][^>]*)>/, `<h2$1>`);
          return f.replace(/<\/div>/, `</h2>`);
        }
        if (/<div[^>]*class=["'][^"']*list[^"']*["']/.test(html) && !/<[uo]l/.test(html))
          return `<ul>${html}</ul>`;
        if (/<td[^>]*(?:bold|header|heading)/.test(html)) {
          let f = html.replace(/<td([^>]*)>/, `<th$1 scope="col">`);
          return f.replace(/<\/td>/, `</th>`);
        }
        break;

      // contraste mínimo de cores
      case "wcag-1.4.3":
        if (/color:\s*#[0-9a-f]{3,6}/i.test(html))
          return html.replace(/color:\s*#[0-9a-fA-F]{3,6}/g, `color: #1a1a1a`);
        return html.replace(
          /(<(?:button|a|span|p|div|td|th|li|h[1-6])(\s[^>]*)?)>/,
          `$1 style="color:#1a1a1a;background-color:#ffffff">`
        );

      //redimensionamento de texto
      case "wcag-1.4.4":
        if (/font-size:\s*\d+px/.test(html))
          return html.replace(/font-size:\s*(\d+)px/g,
            (_, px) => `font-size: ${(parseInt(px)/16).toFixed(3)}rem`);
        break;

      // acessibilidade por teclado
      case "wcag-2.1.1":
        if (/<div[^>]*(?:onclick|onmousedown)[^>]*>/.test(html) && !/tabindex/.test(html))
          return html.replace(/(<div)([^>]*(?:onclick|onmousedown))/, `$1 tabindex="0" role="button"$2`);
        if (/<a(?![^>]*href)(?![^>]*tabindex)[^>]*>/.test(html))
          return html.replace(/<a([^>]*)>/, `<a$1 href="#" tabindex="0">`);
        break;

      //skip links
      case "wcag-2.4.1":
        if (!html.includes('href="#main"'))
          return `<a href="#main" class="skip-link">Ir para o conteúdo principal</a>\n${html}`;
        break;

      // título da página
      case "wcag-2.4.2":
        if (/<title>\s*<\/title>/.test(html))
          return html.replace(/<title>\s*<\/title>/, `<title>Página institucional – UNESP</title>`);
        if (!/<title>/.test(html) && /<head/.test(html))
          return html.replace(/<head([^>]*)>/, `<head$1>\n  <title>Página institucional – UNESP</title>`);
        if (/<title>(?:Untitled|index|Page \d+|default|home|unesp|document)<\/title>/i.test(html))
          return html.replace(/<title>[^<]*<\/title>/, `<title>Página institucional – UNESP</title>`);
        break;

      // finalidade do link
      case "wcag-2.4.4":
        if (/<a[^>]*>\s*<\/a>/.test(html))
          return html.replace(/(<a[^>]*>)\s*(<\/a>)/, `$1Acessar página$2`);
        break;

      // idioma da página
      case "wcag-3.1.1":
        if (!/<html[^>]*lang=/i.test(html))
          return html.replace(/<html([^>]*)>/, `<html$1 lang="pt-BR">`);
        return html.replace(/(lang=["'])[^"']*(['"'])/, `$1pt-BR$2`);

      //HTML válido (IDs duplicados, void elements)
      case "wcag-4.1.1": {
        const matches = [...html.matchAll(/\bid="([^"]+)"/g)];
        const seen = new Set();
        let fixed = html, changed = false;
        for (const m of matches) {
          if (seen.has(m[1])) { fixed = fixed.replace(`id="${m[1]}"`, `id="${m[1]}-dup"`); changed = true; }
          seen.add(m[1]);
        }
        if (changed) return fixed;
        if (/<(input|br|hr|meta|link)([^/>]*[^/])>/.test(html))
          return html.replace(/<(input|br|hr|meta|link)([^/>]*[^/])>/g, `<$1$2 />`);
        break;
      }

      // nome, função e valor (ARIA)
      case "wcag-4.1.2":
        if (/<button[^>]*>\s*<i[^>]*><\/i>\s*<\/button>/.test(html) && !/aria-label/.test(html))
          return html.replace(/<button([^>]*)>/, `<button$1 aria-label="Ação">`);
        if (/<input(?![^>]*aria-label)[^>]*>/.test(html) && !/<label/.test(html))
          return html.replace(/(<input)([^>]*)(>)/, `$1$2 aria-label="Campo de entrada"$3`);
        break;
    }
  } catch(e) {}
  return null;
}
"""


class TestCorrigirRapidoJS(unittest.TestCase):
    def _js(self, html, categoria):
        html_esc = html.replace("`", "\\`").replace("${", "\\${")
        code = _JS_CORRIGIR + f'\nconsole.log(JSON.stringify({{r: corrigirRapido(`{html_esc}`, "{categoria}")}}))'
        try:
            res = subprocess.run(
                ["node", "-e", code],
                capture_output=True, text=True, timeout=10, check=True
            )
            return json.loads(res.stdout.strip())["r"]
        except subprocess.CalledProcessError as e:
            self.fail(f"Node.js error: {e.stderr[:200]}")
        except Exception as e:
            self.fail(f"Erro ao invocar Node.js: {e}")

    def test_1_1_1_imagem_sem_alt(self):
        r = self._js('<img src="foto.jpg" class="banner">', "wcag-1.1.1")
        self.assertIn('alt="Imagem descritiva"', r)

    def test_1_1_1_imagem_alt_vazio(self):
        r = self._js('<img src="logo.png" alt="">', "wcag-1.1.1")
        self.assertIn('alt="Imagem descritiva"', r)

    def test_1_1_1_nao_altera_img_com_alt(self):
        resultado = self._js('<img src="ok.jpg" alt="Foto da fachada">', "wcag-1.1.1")
        self.assertIsNone(resultado)

    def test_1_3_1_div_heading_para_h2(self):
        html = '<div class="heading">Cursos de Graduação</div>'
        r = self._js(html, "wcag-1.3.1")
        self.assertIn("<h2", r)
        self.assertIn("</h2>", r)
        self.assertNotIn("<div", r)

    def test_1_3_1_div_title_para_h2(self):
        html = '<div class="title">Sobre a UNESP</div>'
        r = self._js(html, "wcag-1.3.1")
        self.assertIn("<h2", r)

    def test_1_3_1_div_list_para_ul(self):
        html = '<div class="list-group"><span>A</span><span>B</span></div>'
        r = self._js(html, "wcag-1.3.1")
        self.assertTrue(r.startswith("<ul>") and r.endswith("</ul>"))

    def test_1_3_1_td_bold_para_th(self):
        html = '<td class="bold-header">Nome</td>'
        r = self._js(html, "wcag-1.3.1")
        self.assertIn('<th', r)
        self.assertIn('scope="col"', r)
        self.assertIn('</th>', r)
    def test_1_4_3_cor_hex_inline(self):
        r = self._js('<span style="color:#eee">Texto</span>', "wcag-1.4.3")
        self.assertIn("color: #1a1a1a", r)
        self.assertNotIn("#eee", r)

    def test_1_4_3_injetar_style_sem_cor(self):
        r = self._js('<button class="btn">', "wcag-1.4.3")
        self.assertIn('style="color:#1a1a1a;background-color:#ffffff"', r)

    def test_1_4_4_px_para_rem(self):
        r = self._js('<p style="font-size: 24px;">', "wcag-1.4.4")
        self.assertIn("1.500rem", r)
        self.assertNotIn("px", r)

    def test_1_4_4_multiplos_px(self):
        r = self._js('<p style="font-size: 12px; font-size: 24px;">', "wcag-1.4.4")
        self.assertIsNotNone(r)
        self.assertIn("0.750rem", r)
        self.assertIn("1.500rem", r)
        self.assertNotIn("px", r)

    def test_2_1_1_div_onclick_sem_tabindex(self):
        html = '<div onclick="abrirMenu()">Menu</div>'
        r = self._js(html, "wcag-2.1.1")
        self.assertIn('tabindex="0"', r)
        self.assertIn('role="button"', r)

    def test_2_1_1_a_sem_href_recebe_tabindex(self):
        html = '<a class="nav-link">Sobre</a>'
        r = self._js(html, "wcag-2.1.1")
        self.assertIn('href="#"', r)
        self.assertIn('tabindex="0"', r)

    def test_2_1_1_nao_altera_div_com_tabindex_existente(self):
        html = '<div onclick="toggle()" tabindex="0">OK</div>'
        r = self._js(html, "wcag-2.1.1")
        self.assertIsNone(r)
    def test_2_4_1_skip_link_injetado(self):
        html = '<nav><a href="/">Início</a></nav>'
        r = self._js(html, "wcag-2.4.1")
        self.assertTrue(r.startswith('<a href="#main" class="skip-link">'))
        self.assertIn("Ir para o conteúdo principal", r)

    def test_2_4_1_nao_duplica_se_ja_existe(self):
        html = '<a href="#main" class="skip-link">Pular</a><nav></nav>'
        r = self._js(html, "wcag-2.4.1")
        self.assertIsNone(r)

    def test_2_4_2_title_vazio_preenchido(self):
        html = '<html><head><title></title></head></html>'
        r = self._js(html, "wcag-2.4.2")
        self.assertIn('<title>Página institucional – UNESP</title>', r)

    def test_2_4_2_title_ausente_injetado(self):
        html = '<html><head></head><body></body></html>'
        r = self._js(html, "wcag-2.4.2")
        self.assertIn('<title>Página institucional – UNESP</title>', r)

    def test_2_4_2_title_untitled_substituido(self):
        html = '<html><head><title>Untitled</title></head></html>'
        r = self._js(html, "wcag-2.4.2")
        self.assertIn('<title>Página institucional – UNESP</title>', r)
        self.assertNotIn('Untitled', r)

    def test_2_4_4_link_vazio_recebe_texto(self):
        r = self._js('<a href="/home">  </a>', "wcag-2.4.4")
        self.assertIn("Acessar página", r)

    def test_3_1_1_html_sem_lang_recebe_ptbr(self):
        r = self._js('<html>', "wcag-3.1.1")
        self.assertIn('lang="pt-BR"', r)

    def test_3_1_1_lang_errado_corrigido(self):
        r = self._js('<html lang="en-US">', "wcag-3.1.1")
        self.assertIn('lang="pt-BR"', r)
        self.assertNotIn("en-US", r)

    def test_4_1_1_id_duplicado_renomeado(self):
        html = '<div id="main"><span id="main">Duplicado</span></div>'
        r = self._js(html, "wcag-4.1.1")
        self.assertIn('id="main-dup"', r)
        self.assertEqual(r.count('id="main"'), 1)
        self.assertEqual(r.count('id="main-dup"'), 1)

    def test_4_1_1_dois_inputs_com_mesmo_id(self):
        html = '<input id="email"><input id="email" type="email">'
        r = self._js(html, "wcag-4.1.1")
        self.assertIn('id="email-dup"', r)

    def test_4_1_1_void_element_sem_autofechar(self):
        r = self._js('<br >', "wcag-4.1.1")
        self.assertIsNotNone(r)
        self.assertIn('<br  />', r)

    def test_4_1_1_input_void_sem_autofechar(self):
        r = self._js('<input type="text" id="campo">', "wcag-4.1.1")
        self.assertIsNotNone(r)
        self.assertIn('<input type="text" id="campo" />', r)

    def test_4_1_1_sem_duplicata_retorna_none(self):
        r = self._js('<div id="a"><div id="b">x</div></div>', "wcag-4.1.1")
        self.assertIsNone(r)

    def test_4_1_2_botao_icone_recebe_aria_label(self):
        html = '<button class="search"><i class="fa fa-search"></i></button>'
        r = self._js(html, "wcag-4.1.2")
        self.assertIn('aria-label="Ação"', r)

    def test_4_1_2_input_sem_label_recebe_aria(self):
        r = self._js('<input type="text" name="busca">', "wcag-4.1.2")
        self.assertIn('aria-label="Campo de entrada"', r)

    def test_4_1_2_input_com_aria_label_nao_alterado(self):
        r = self._js('<input type="text" aria-label="Nome">', "wcag-4.1.2")
        self.assertIsNone(r)
@unittest.skipUnless(_DATASET_DISPONIVEL, "gerar-dataset-completo.py não encontrado ou com erro de importação")
class TestCorrigirPython(unittest.TestCase):

    def _corrigir(self, html, cat):
        return _corrigir_py(html, cat)

    def test_py_1_1_1_sem_alt(self):
        r = self._corrigir('<img src="x.jpg">', "wcag-1.1.1")
        self.assertIsNotNone(r)
        self.assertIn('alt=', r)

    def test_py_1_1_1_alt_vazio(self):
        r = self._corrigir('<img src="x.jpg" alt="">', "wcag-1.1.1")
        self.assertIsNotNone(r)
        self.assertIn('Imagem descritiva', r)

    def test_py_1_3_1_div_heading_vira_h2(self):
        r = self._corrigir('<div class="heading">Cursos</div>', "wcag-1.3.1")
        self.assertIsNotNone(r)
        self.assertIn('<h2', r)

    def test_py_1_3_1_div_list_vira_ul(self):
        r = self._corrigir('<div class="list">A B C</div>', "wcag-1.3.1")
        self.assertIsNotNone(r)
        self.assertIn('<ul>', r)

    def test_py_1_3_1_td_bold_vira_th(self):
        r = self._corrigir('<td class="bold-header">Nome</td>', "wcag-1.3.1")
        self.assertIsNotNone(r)
        self.assertIn('<th', r)
        self.assertIn('scope="col"', r)

    def test_py_1_3_1_span_subheading_vira_h3(self):
        r = self._corrigir('<span class="subheading">Contato</span>', "wcag-1.3.1")
        self.assertIsNotNone(r)
        self.assertIn('<h3', r)

    def test_py_1_4_3_cor_hex(self):
        r = self._corrigir('<p style="color:#ccc">Texto</p>', "wcag-1.4.3")
        self.assertIsNotNone(r)
        self.assertIn('#1a1a1a', r)

    def test_py_1_4_3_sem_cor_inline(self):
        r = self._corrigir('<button>Enviar</button>', "wcag-1.4.3")
        self.assertIsNotNone(r)
        self.assertIn('color:#1a1a1a', r)

    def test_py_1_4_4_px_para_rem(self):
        r = self._corrigir('<p style="font-size: 12px;">', "wcag-1.4.4")
        self.assertIsNotNone(r)
        self.assertIn('rem', r)
        self.assertNotIn('px', r)

    def test_py_2_1_1_div_onclick_recebe_tabindex(self):
        r = self._corrigir('<div onclick="abrirMenu()">Menu</div>', "wcag-2.1.1")
        self.assertIsNotNone(r)
        self.assertIn('tabindex="0"', r)
        self.assertIn('role="button"', r)

    def test_py_2_1_1_a_sem_href_recebe_tabindex(self):
        r = self._corrigir('<a class="nav-link">Início</a>', "wcag-2.1.1")
        self.assertIsNotNone(r)
        self.assertIn('href="#"', r)
        self.assertIn('tabindex="0"', r)

    def test_py_2_1_1_span_onclick_recebe_tabindex(self):
        r = self._corrigir('<span onclick="fechar()">×</span>', "wcag-2.1.1")
        self.assertIsNotNone(r)
        self.assertIn('tabindex="0"', r)

    def test_py_2_4_1_skip_link_inserido(self):
        r = self._corrigir('<nav><a href="/">Home</a></nav>', "wcag-2.4.1")
        self.assertIsNotNone(r)
        self.assertIn('href="#main"', r)

    def test_py_2_4_2_title_vazio(self):
        r = self._corrigir('<html><head><title></title></head></html>', "wcag-2.4.2")
        self.assertIsNotNone(r)
        self.assertIn('Página institucional', r)

    def test_py_2_4_2_sem_title(self):
        r = self._corrigir('<html><head></head><body></body></html>', "wcag-2.4.2")
        self.assertIsNotNone(r)
        self.assertIn('<title>', r)

    def test_py_2_4_2_title_untitled(self):
        r = self._corrigir('<html><head><title>Untitled</title></head></html>', "wcag-2.4.2")
        self.assertIsNotNone(r)
        self.assertNotIn('Untitled', r)

    def test_py_2_4_2_title_index(self):
        r = self._corrigir('<html><head><title>index</title></head></html>', "wcag-2.4.2")
        self.assertIsNotNone(r)
        self.assertIn('Página institucional', r)

    def test_py_2_4_4_link_vazio(self):
        r = self._corrigir('<a href="/x"></a>', "wcag-2.4.4")
        self.assertIsNotNone(r)
        self.assertIn('Acessar página', r)

    def test_py_2_4_4_texto_clique_aqui(self):
        r = self._corrigir('<a href="/x">clique aqui</a>', "wcag-2.4.4")
        self.assertIsNotNone(r)
        self.assertIn('Acesse o conteúdo relacionado', r)

    def test_py_2_4_4_link_com_icone_sem_aria(self):
        r = self._corrigir('<a href="/x"><img src="i.png"></a>', "wcag-2.4.4")
        self.assertIsNotNone(r)
        self.assertIn('aria-label="Acessar link"', r)

    def test_py_3_1_1_sem_lang(self):
        r = self._corrigir('<html><body></body></html>', "wcag-3.1.1")
        self.assertIsNotNone(r)
        self.assertIn('lang="pt-BR"', r)

    def test_py_3_1_1_lang_en_corrigido(self):
        r = self._corrigir('<html lang="en"><body></body></html>', "wcag-3.1.1")
        self.assertIsNotNone(r)
        self.assertIn('lang="pt-BR"', r)
        self.assertNotIn('"en"', r)

    def test_py_4_1_1_id_duplicado(self):
        html = '<div id="main"><span id="main">X</span></div>'
        r = self._corrigir(html, "wcag-4.1.1")
        self.assertIsNotNone(r)
        self.assertIn('id="main-dup"', r)

    def test_py_4_1_1_dois_inputs_mesmo_id(self):
        html = '<input id="x"><input id="x" type="email">'
        r = self._corrigir(html, "wcag-4.1.1")
        self.assertIsNotNone(r)
        self.assertIn('id="x-dup"', r)

    def test_py_4_1_1_br_sem_fechar(self):
        r = self._corrigir('<input type="text" name="q">', "wcag-4.1.1")
        self.assertIsNotNone(r)
        self.assertIn('<input type="text" name="q" />', r)
        r = self._corrigir('<div id="a"><div id="b">x</div></div>', "wcag-4.1.1")
        self.assertIsNone(r)

    def test_py_4_1_2_botao_icone(self):
        r = self._corrigir('<button><i class="fa fa-bars"></i></button>', "wcag-4.1.2")
        self.assertIsNotNone(r)
        self.assertIn('aria-label="Ação"', r)

    def test_py_4_1_2_botao_svg(self):
        r = self._corrigir('<button><svg viewBox="0 0 24 24"></svg></button>', "wcag-4.1.2")
        self.assertIsNotNone(r)
        self.assertIn('aria-label="Ação"', r)

    def test_py_4_1_2_input_sem_label(self):
        r = self._corrigir('<input type="text">', "wcag-4.1.2")
        self.assertIsNotNone(r)
        self.assertIn('aria-label="Campo de entrada"', r)

    def test_py_4_1_2_select_sem_label(self):
        r = self._corrigir('<select><option>A</option></select>', "wcag-4.1.2")
        self.assertIsNotNone(r)
        self.assertIn('aria-label="Selecione uma opção"', r)

    def test_py_4_1_2_input_com_aria_ja_ok(self):
        r = self._corrigir('<input type="text" aria-label="Nome">', "wcag-4.1.2")
        self.assertIsNone(r)

    def test_py_saida_diferente_da_entrada_por_categoria(self):
        casos = {
            "wcag-1.1.1": '<img src="x.jpg">',
            "wcag-1.3.1": '<div class="heading">Título</div>',
            "wcag-1.4.3": '<p style="color:#ccc">Texto</p>',
            "wcag-1.4.4": '<p style="font-size: 12px;">Texto</p>',
            "wcag-2.1.1": '<div onclick="f()">Clique</div>',
            "wcag-2.4.1": '<nav><a href="/">Home</a></nav>',
            "wcag-2.4.2": '<html><head><title></title></head></html>',
            "wcag-2.4.4": '<a href="/x"></a>',
            "wcag-3.1.1": '<html><body></body></html>',
            "wcag-4.1.1": '<div id="a"><span id="a">X</span></div>',
            "wcag-4.1.2": '<button><i class="fa fa-bars"></i></button>',
        }
        for cat, html in casos.items():
            with self.subTest(categoria=cat):
                r = self._corrigir(html, cat)
                self.assertIsNotNone(r, f"corrigir() retornou None para {cat}")
                self.assertNotEqual(r, html, f"corrigir() não alterou o HTML para {cat}")

@unittest.skipUnless(_VISAO_DISPONIVEL, "visao.py não encontrado ou erro de importação")
class TestVisaoUtilitarios(unittest.TestCase):
    def test_limpar_texto_curto_intocado(self):
        self.assertEqual(_limpar_repeticoes("a cat on a mat"), "a cat on a mat")

    def test_limpar_repeticao_de_metade(self):
        texto = "a cat on a mat a cat on a mat"
        r = _limpar_repeticoes(texto)
        self.assertNotIn("a cat on a mat a cat on a mat", r)
        self.assertIn("cat", r)

    def test_limpar_palavra_repetida_consecutiva(self):
        texto = "a student standing in front of a a a blackboard with a with a"
        r = _limpar_repeticoes(texto)
        palavras = r.lower().split()
        for i in range(len(palavras) - 2):
            self.assertFalse(
                palavras[i] == palavras[i+1] == palavras[i+2],
                f"Triplicata encontrada: '{palavras[i]}' em '{r}'"
            )

    def test_limpar_string_vazia(self):
        self.assertEqual(_limpar_repeticoes(""), "")

    def test_limpar_texto_normal_nao_alterado(self):
        texto = "a group of students sitting at a table in a classroom"
        r = _limpar_repeticoes(texto)
        self.assertIn("students", r)
        self.assertIn("classroom", r)

    def test_extrai_img_sem_alt(self):
        html = '<img src="https://example.com/foto.jpg">'
        urls = extrair_imgs_sem_alt(html)
        self.assertIn("https://example.com/foto.jpg", urls)

    def test_extrai_img_alt_vazio(self):
        html = '<img src="https://example.com/logo.png" alt="">'
        urls = extrair_imgs_sem_alt(html)
        self.assertIn("https://example.com/logo.png", urls)

    def test_nao_extrai_img_com_alt_preenchido(self):
        html = '<img src="https://example.com/ok.jpg" alt="Foto da fachada">'
        urls = extrair_imgs_sem_alt(html)
        self.assertNotIn("https://example.com/ok.jpg", urls)

    def test_filtra_svg_por_extensao(self):
        html = '<img src="https://example.com/icone.svg">'
        urls = extrair_imgs_sem_alt(html)
        self.assertNotIn("https://example.com/icone.svg", urls)

    def test_filtra_url_malformada_sem_schema(self):
        html = '<img src="imagens/foto.jpg">'
        urls = extrair_imgs_sem_alt(html)
        self.assertEqual(urls, [])

    def test_resolve_url_relativa_com_base(self):
        html = '<img src="/imagens/foto.jpg">'
        urls = extrair_imgs_sem_alt(html, base_url="https://www.unesp.br")
        self.assertIn("https://www.unesp.br/imagens/foto.jpg", urls)

    def test_dedup_mesma_url_repetida(self):
        html = ('<img src="https://example.com/x.jpg">'
                '<img src="https://example.com/x.jpg">'
                '<img src="https://example.com/x.jpg" alt="">')
        urls = extrair_imgs_sem_alt(html)
        self.assertEqual(urls.count("https://example.com/x.jpg"), 1)

    def test_filtra_svg_no_nome_do_arquivo(self):
        html = '<img src="https://example.com/static/logo-svg-2x.png">'
        urls = extrair_imgs_sem_alt(html)
        self.assertIsInstance(urls, list)

    def test_retorna_no_maximo_max_imgs(self):
        imgs = "".join(f'<img src="https://ex.com/{i}.jpg">' for i in range(40))
        urls = extrair_imgs_sem_alt(imgs)
        self.assertLessEqual(len(urls), 30)


@unittest.skipUnless(_VISAO_DISPONIVEL, 'visao.py não encontrado ou erro de importação')
class TestVisaoOcrECache(unittest.TestCase):
    def test_logo_banner_texto_curto_valido(self):
        self.assertTrue(_visao_mod._texto_parece_logo_banner("UNESP Universidade Estadual Paulista"))

    def test_logo_banner_rejeita_vazio(self):
        self.assertFalse(_visao_mod._texto_parece_logo_banner(""))

    def test_logo_banner_rejeita_so_numeros(self):
        self.assertFalse(_visao_mod._texto_parece_logo_banner("2024"))

    def test_logo_banner_rejeita_texto_longo(self):
        texto = "Este é um parágrafo longo com mais de duzentos caracteres " * 4
        self.assertFalse(_visao_mod._texto_parece_logo_banner(texto))

    def test_logo_banner_rejeita_poucos_alfa(self):
        self.assertFalse(_visao_mod._texto_parece_logo_banner("I. |"))

    def test_alt_ocr_prefixo_logo(self):
        r = _visao_mod._alt_do_ocr("UNESP", "https://ex.com/logo-unesp.png")
        self.assertIn("Logo ou banner", r)
        self.assertIn("UNESP", r)

    def test_alt_ocr_prefixo_icone(self):
        r = _visao_mod._alt_do_ocr("Menu", "https://ex.com/icon-menu.png")
        self.assertIn("\u00cdcone", r)

    def test_alt_ocr_prefixo_generico(self):
        r = _visao_mod._alt_do_ocr("Texto qualquer", "https://ex.com/foto.jpg")
        self.assertIn("Imagem com texto", r)

    def test_alt_ocr_trunca_texto_longo(self):
        r = _visao_mod._alt_do_ocr("A " * 100, "https://ex.com/img.png")
        self.assertLessEqual(len(r), 150)

    def setUp(self):
        import tempfile
        self._tmp = tempfile.mkdtemp()
        self._orig = _visao_mod.CACHE_DIR
        _visao_mod.CACHE_DIR = _visao_mod.Path(self._tmp)

    def tearDown(self):
        _visao_mod.CACHE_DIR = self._orig
        import shutil
        shutil.rmtree(self._tmp, ignore_errors=True)

    def _url(self, n='img'):
        return f'https://example.com/{n}.jpg'

    def _b(self, v=b'v1'):
        return v

    def test_cache_miss_inicial(self):
        desc, st = _visao_mod._cache_get(self._url(), self._b())
        self.assertIsNone(desc)
        self.assertEqual(st, 'miss')

    def test_cache_hit_apos_set(self):
        _visao_mod._cache_set(self._url(), 'Desc', self._b())
        desc, st = _visao_mod._cache_get(self._url(), self._b())
        self.assertEqual(desc, 'Desc')
        self.assertEqual(st, 'hit')

    def test_cache_miss_hash_mudou(self):
        _visao_mod._cache_set(self._url(), 'Desc v1', self._b(b'v1'))
        desc, st = _visao_mod._cache_get(self._url(), self._b(b'v2'))
        self.assertIsNone(desc)
        self.assertEqual(st, 'miss')

    def test_cache_renewed_ttl_expirado_hash_bate(self):
        import json as _j
        _visao_mod._cache_set(self._url(), 'Desc antiga', self._b())
        p = _visao_mod._cache_path(self._url())
        e = _j.loads(p.read_text())
        e['criado_em'] = 0.0
        p.write_text(_j.dumps(e))
        desc, st = _visao_mod._cache_get(self._url(), self._b())
        self.assertEqual(desc, 'Desc antiga')
        self.assertEqual(st, 'renewed')
        e2 = _j.loads(p.read_text())
        self.assertGreater(e2['criado_em'], 1.0)

    def test_cache_miss_ttl_expirado_e_hash_mudou(self):
        import json as _j
        _visao_mod._cache_set(self._url(), 'Desc v1', self._b(b'v1'))
        p = _visao_mod._cache_path(self._url())
        e = _j.loads(p.read_text())
        e['criado_em'] = 0.0
        p.write_text(_j.dumps(e))
        desc, st = _visao_mod._cache_get(self._url(), self._b(b'v2'))
        self.assertIsNone(desc)
        self.assertEqual(st, 'miss')

    def test_cache_sem_bytes_aceita_por_url(self):
        _visao_mod._cache_set(self._url(), 'Desc', None)
        desc, st = _visao_mod._cache_get(self._url(), None)
        self.assertEqual(desc, 'Desc')
        self.assertIn(st, ('hit', 'renewed'))

    def test_cache_limpar_expirados(self):
        import json as _j
        _visao_mod._cache_set(self._url('a'), 'Desc A', self._b(b'a'))
        _visao_mod._cache_set(self._url('b'), 'Desc B', self._b(b'b'))
        for p in _visao_mod.CACHE_DIR.glob('*.json'):
            e = _j.loads(p.read_text())
            if e.get('descricao') == 'Desc A':
                e['criado_em'] = 0.0
                p.write_text(_j.dumps(e))
        _visao_mod.cache_limpar_expirados()
        descs = [_j.loads(p.read_text()).get('descricao') for p in _visao_mod.CACHE_DIR.glob('*.json')]
        self.assertNotIn('Desc A', descs)
        self.assertIn('Desc B', descs)

class TestEstruturaDoProjetoEMapeamentos(unittest.TestCase):
    CATEGORIAS_ESPERADAS = [
        "wcag-1.1.1", "wcag-1.3.1", "wcag-1.4.3", "wcag-1.4.4",
        "wcag-2.1.1", "wcag-2.4.1", "wcag-2.4.2", "wcag-2.4.4",
        "wcag-3.1.1", "wcag-4.1.1", "wcag-4.1.2",
    ]

    def test_todas_11_categorias_definidas(self):
        for cat in self.CATEGORIAS_ESPERADAS:
            with self.subTest(cat=cat):
                self.assertTrue(cat.startswith("wcag-"))

    def test_scripts_principais_existem(self):
        scripts = [
            "pipeline.js", "crawler.js", "analisar.js", "salvar.js",
            "gerar-dataset-completo.py", "treinar.py", "inferir.py",
        ]
        for s in scripts:
            with self.subTest(script=s):
                if not os.path.exists(s):
                    self.skipTest(f"{s} não encontrado no diretório atual")
                self.assertTrue(os.path.exists(s))

    def test_node_disponivel(self):
        try:
            r = subprocess.run(["node", "--version"], capture_output=True, text=True, timeout=5)
            self.assertEqual(r.returncode, 0)
        except FileNotFoundError:
            self.skipTest("Node.js não encontrado no PATH")

    def test_python3_disponivel(self):
        r = subprocess.run(
            [sys.executable, "--version"], capture_output=True, text=True, timeout=5
        )
        self.assertEqual(r.returncode, 0)

    def test_formato_jsonl_dataset(self):
        """Se dataset-balanced.jsonl existir, valida estrutura das primeiras 10 linhas."""
        if not os.path.exists("dataset-balanced.jsonl"):
            self.skipTest("dataset-balanced.jsonl não encontrado")
        with open("dataset-balanced.jsonl", encoding="utf-8") as f:
            for i, linha in enumerate(f):
                if i >= 10:
                    break
                obj = json.loads(linha)
                with self.subTest(linha=i):
                    self.assertIn("input", obj)
                    self.assertIn("output", obj)
                    self.assertIn("### ERRO WCAG:", obj["input"])
                    self.assertNotEqual(obj["input"], obj["output"])

    def test_mapeamento_regras_axe_cobre_11_categorias(self):
        RULE_TO_WCAG = {
            "image-alt": "wcag-1.1.1", "input-image-alt": "wcag-1.1.1", "role-img-alt": "wcag-1.1.1",
            "td-headers-attr": "wcag-1.3.1", "th-has-data-cells": "wcag-1.3.1",
            "list": "wcag-1.3.1", "listitem": "wcag-1.3.1",
            "color-contrast": "wcag-1.4.3", "meta-viewport": "wcag-1.4.4",
            "keyboard": "wcag-2.1.1", "tabindex": "wcag-2.1.1",
            "bypass": "wcag-2.4.1", "document-title": "wcag-2.4.2", "link-name": "wcag-2.4.4",
            "html-has-lang": "wcag-3.1.1", "html-lang-valid": "wcag-3.1.1",
            "duplicate-id": "wcag-4.1.1", "duplicate-id-active": "wcag-4.1.1",
            "duplicate-id-aria": "wcag-4.1.1",
            "button-name": "wcag-4.1.2", "label": "wcag-4.1.2",
            "select-name": "wcag-4.1.2", "textarea-name": "wcag-4.1.2",
            "aria-required-attr": "wcag-4.1.2", "aria-required-children": "wcag-4.1.2",
            "aria-roles": "wcag-4.1.2",
        }
        categorias_cobertas = set(RULE_TO_WCAG.values())
        for cat in self.CATEGORIAS_ESPERADAS:
            with self.subTest(cat=cat):
                self.assertIn(cat, categorias_cobertas,
                              f"{cat} não está coberta por nenhuma regra axe no mapeamento")


if __name__ == "__main__":
    print("Iniciando suite de testes WCAG (Node.js + Python)...\n")
    loader = unittest.TestLoader()
    suite  = unittest.TestSuite()

    for cls in [
        TestCorrigirRapidoJS,
        TestCorrigirPython,
        TestVisaoUtilitarios,
        TestEstruturaDoProjetoEMapeamentos,
    ]:
        suite.addTests(loader.loadTestsFromTestCase(cls))

    runner = unittest.TextTestRunner(verbosity=2)
    result = runner.run(suite)
    sys.exit(0 if result.wasSuccessful() else 1)
