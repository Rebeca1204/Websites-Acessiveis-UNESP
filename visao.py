# visao.py — Geração automática de descrições de imagens via BLIP (offline)
import sys
import os
import json
import re
import gc
import hashlib
import time
from pathlib import Path
from urllib.parse import urljoin, urlparse

def _importar_blip():
    try:
        from transformers import BlipProcessor, BlipForConditionalGeneration
        import torch
        from PIL import Image
        import requests
        return BlipProcessor, BlipForConditionalGeneration, torch, Image, requests
    except ImportError as e:
        print(f"Dependência faltando: {e}")
        print(" Instale com: pip install transformers torch Pillow requests")
        sys.exit(1)

def _importar_ocr():
    try:
        import pytesseract
        from PIL import Image
        pytesseract.get_tesseract_version()
        return pytesseract, Image
    except Exception:
        return None, None
MODEL_NAME       = "Salesforce/blip-image-captioning-base"
TRANSLATE_MODEL  = "Helsinki-NLP/opus-mt-tc-big-en-pt"
MAX_IMGS         = 30
TIMEOUT_REQ      = 10
CACHE_DIR        = Path(__file__).parent / ".blip-cache"
CACHE_DIR.mkdir(exist_ok=True)

_TTL_DAYS   = int(os.environ.get("BLIP_CACHE_TTL_DAYS", "7"))
CACHE_TTL_S = _TTL_DAYS * 86400

OCR_MIN_CHARS = 8

def _cache_path(url: str) -> Path:
    return CACHE_DIR / (hashlib.md5(url.encode()).hexdigest() + ".json")

def _img_hash(img_bytes: bytes) -> str:
    return hashlib.md5(img_bytes).hexdigest()

def _cache_get(url: str, img_bytes: bytes | None = None):
    p = _cache_path(url)
    if not p.exists():
        return None, "miss"

    try:
        entrada = json.loads(p.read_text(encoding="utf-8"))
    except Exception:
        return None, "miss"

    descricao  = entrada.get("descricao", "")
    hash_salvo = entrada.get("img_hash", "")
    criado_em  = entrada.get("criado_em", 0.0)

    agora      = time.time()
    ttl_ok     = (agora - criado_em) < CACHE_TTL_S
    hash_atual = _img_hash(img_bytes) if img_bytes else None
    hash_ok    = (hash_atual is None) or (hash_atual == hash_salvo)

    if not hash_ok:
        return None, "miss"

    if ttl_ok:
        return descricao, "hit"

    entrada["criado_em"] = agora
    p.write_text(json.dumps(entrada, ensure_ascii=False), encoding="utf-8")
    return descricao, "renewed"

def _cache_set(url: str, descricao: str, img_bytes: bytes | None = None):
    p = _cache_path(url)
    entrada = {
        "descricao": descricao,
        "img_hash":  _img_hash(img_bytes) if img_bytes else "",
        "criado_em": time.time(),
    }
    p.write_text(json.dumps(entrada, ensure_ascii=False), encoding="utf-8")

def cache_limpar_expirados():
    agora   = time.time()
    removidos = 0
    for p in CACHE_DIR.glob("*.json"):
        try:
            entrada = json.loads(p.read_text(encoding="utf-8"))
            if (agora - entrada.get("criado_em", 0)) >= CACHE_TTL_S:
                p.unlink()
                removidos += 1
        except Exception:
            p.unlink()
            removidos += 1
    print(f"Cache: {removidos} entradas expiradas removidas.")

def _ocr_extrair_texto(img) -> str:
    pytesseract, _ = _importar_ocr()
    if pytesseract is None:
        return ""

    try:
        texto = pytesseract.image_to_string(img, lang="por+eng", config="--psm 3")
    except Exception:
        try:
            texto = pytesseract.image_to_string(img, config="--psm 3")
        except Exception:
            return ""
    linhas = [l.strip() for l in texto.splitlines() if l.strip()]
    texto_limpo = " ".join(linhas)
    chars_uteis = sum(1 for c in texto_limpo if c.isalnum())
    return texto_limpo if chars_uteis >= OCR_MIN_CHARS else ""

def _texto_parece_logo_banner(texto_ocr: str) -> bool:
    if not texto_ocr:
        return False
    if len(texto_ocr) > 200:
        return False
    chars_alfa = sum(1 for c in texto_ocr if c.isalpha())
    if chars_alfa < 4:
        return False
    return True

def _alt_do_ocr(texto_ocr: str, url_imagem: str) -> str:
    nome_arquivo = urlparse(url_imagem).path.lower().split("/")[-1]
    prefixo = "Imagem com texto"
    if any(k in nome_arquivo for k in ("logo", "banner", "header", "marca", "brand")):
        prefixo = "Logo ou banner"
    elif any(k in nome_arquivo for k in ("icon", "icone", "ico")):
        prefixo = "Ícone"
    return f"{prefixo}: {texto_ocr[:120]}"

_modelo_cache = {}

def carregar_modelo():
    if _modelo_cache:
        return _modelo_cache["processor"], _modelo_cache["model"], _modelo_cache["torch"], _modelo_cache["Image"]

    BlipProcessor, BlipForConditionalGeneration, torch, Image, _ = _importar_blip()

    print("Carregando modelo BLIP... ")
    processor = BlipProcessor.from_pretrained(MODEL_NAME)
    model     = BlipForConditionalGeneration.from_pretrained(MODEL_NAME, torch_dtype=torch.float32)
    model.eval()

    _modelo_cache["processor"] = processor
    _modelo_cache["model"]     = model
    _modelo_cache["torch"]     = torch
    _modelo_cache["Image"]     = Image
    print("BLIP carregado\n")
    return processor, model, torch, Image

_tradutor_cache = {}

def carregar_tradutor():
    if _tradutor_cache:
        return _tradutor_cache["tokenizer"], _tradutor_cache["model"], _tradutor_cache["torch"]

    try:
        from transformers import MarianMTModel, MarianTokenizer
        import torch
    except ImportError:
        return None, None, None
    tokenizer = MarianTokenizer.from_pretrained(TRANSLATE_MODEL)
    model     = MarianMTModel.from_pretrained(TRANSLATE_MODEL)
    model.eval()

    _tradutor_cache["tokenizer"] = tokenizer
    _tradutor_cache["model"]     = model
    _tradutor_cache["torch"]     = torch
    print("Tradutor carregado\n")
    return tokenizer, model, torch

def traduzir_para_ptbr(texto_en: str) -> str:
    if not texto_en:
        return texto_en

    tokenizer, model, torch = carregar_tradutor()

    if tokenizer is None:
        return texto_en[0].upper() + texto_en[1:] if texto_en else texto_en

    try:
        inputs = tokenizer(texto_en, return_tensors="pt", padding=True, truncation=True, max_length=128)
        with torch.no_grad():
            translated = model.generate(**inputs, num_beams=4, max_new_tokens=80)
        resultado = tokenizer.decode(translated[0], skip_special_tokens=True).strip()
        resultado = re.sub(r"^>>[\w-]+<<\s*", "", resultado)
        return resultado if resultado else texto_en
    except Exception:
        return texto_en[0].upper() + texto_en[1:] if texto_en else texto_en

def _abrir_imagem(img_bytes: bytes, url: str, Image) -> tuple:
    import io

    ext = url.rsplit(".", 1)[-1].lower().split("?")[0]
    if ext == "svg":
        return None, (
            "SVG não suportado pelo Pillow sem plugin externo (cairosvg). "
            "Instale: pip install cairosvg"
        )

    try:
        buf = io.BytesIO(img_bytes)
        img = Image.open(buf)
        if getattr(img, "is_animated", False) or img.format in ("GIF", "WEBP"):
            try:
                img.seek(0)
            except EOFError:
                pass 

        return img.convert("RGB"), None

    except Exception as e:
        nome_exc = type(e).__name__
        if nome_exc == "UnidentifiedImageError" or "cannot identify" in str(e).lower():
            return None, (
                f"Formato de imagem não reconhecido pelo Pillow "
                f"(URL: {url.rsplit('/', 1)[-1]!r}). "
                "Verifique se o arquivo é uma imagem válida ou instale plugins adicionais."
            )
        return None, f"Erro ao abrir imagem ({nome_exc}): {str(e)[:100]}"

def descrever_imagem(url_imagem: str, base_url: str = "") -> dict:
    BlipProcessor, BlipForConditionalGeneration, torch, Image, requests_mod = _importar_blip()

    if base_url and not url_imagem.startswith("http"):
        url_imagem = urljoin(base_url, url_imagem)

    if not url_imagem.startswith("http"):
        return {"url": url_imagem, "descricao_en": "", "alt_sugerido": "",
                "fonte": "", "status": "erro", "erro": "URL inválida"}
    try:
        resp = requests_mod.get(url_imagem, timeout=TIMEOUT_REQ)
        resp.raise_for_status()
        content_type = resp.headers.get("content-type", "")
        if not content_type.startswith("image/"):
            return {"url": url_imagem, "descricao_en": "", "alt_sugerido": "",
                    "fonte": "", "status": "erro",
                    "erro": f"Não é imagem ({content_type})"}
        img_bytes = resp.content
    except Exception as e:
        return {"url": url_imagem, "descricao_en": "", "alt_sugerido": "",
                "fonte": "", "status": "erro", "erro": str(e)[:100]}
                
    descricao_cached, cache_status = _cache_get(url_imagem, img_bytes)
    if cache_status in ("hit", "renewed"):
        return {
            "url":          url_imagem,
            "descricao_en": descricao_cached,
            "alt_sugerido": descricao_cached,   
            "fonte":        "cache",
            "status":       "cache" if cache_status == "hit" else "renovado",
            "erro":         None,
        }

    import io
    img, erro_abertura = _abrir_imagem(img_bytes, url_imagem, Image)
    if img is None:
        return {"url": url_imagem, "descricao_en": "", "alt_sugerido": "",
                "fonte": "", "status": "erro", "erro": erro_abertura}

    texto_ocr = _ocr_extrair_texto(img)
    if _texto_parece_logo_banner(texto_ocr):
        alt_final = _alt_do_ocr(texto_ocr, url_imagem)
        _cache_set(url_imagem, alt_final, img_bytes)
        del img
        gc.collect()
        return {
            "url":          url_imagem,
            "descricao_en": texto_ocr,
            "alt_sugerido": alt_final,
            "fonte":        "ocr",
            "status":       "ok",
            "erro":         None,
        }

    processor, model, torch, _ = carregar_modelo()

    inputs = processor(img, return_tensors="pt")
    with torch.no_grad():
        out = model.generate(
            **inputs,
            max_new_tokens=40,
            num_beams=4,
            repetition_penalty=2.5,
            no_repeat_ngram_size=3,
            length_penalty=0.8,
        )

    descricao_en = processor.decode(out[0], skip_special_tokens=True).strip()
    descricao_en = _limpar_repeticoes(descricao_en)

    alt_final = traduzir_para_ptbr(descricao_en)
    _cache_set(url_imagem, alt_final, img_bytes)

    del img, inputs, out
    gc.collect()

    return {
        "url":          url_imagem,
        "descricao_en": descricao_en,
        "alt_sugerido": alt_final,
        "fonte":        "blip",
        "status":       "ok",
        "erro":         None,
    }

def _limpar_repeticoes(texto: str) -> str:
    if not texto:
        return texto
    palavras = texto.split()
    if len(palavras) <= 6:
        return texto
    meio = len(palavras) // 2
    primeira = " ".join(palavras[:meio]).lower()
    segunda  = " ".join(palavras[meio:]).lower()
    if primeira[:20] in segunda or segunda[:20] in primeira:
        return " ".join(palavras[:meio]).strip(" ,.")
    resultado, anterior, repeticoes = [], None, 0
    for p in palavras:
        if p.lower() == (anterior or "").lower():
            repeticoes += 1
            if repeticoes >= 2:
                continue
        else:
            repeticoes = 0
        resultado.append(p)
        anterior = p
    return " ".join(resultado).strip(" ,.")

def extrair_imgs_sem_alt(html_content: str, base_url: str = "") -> list[str]:
    # img sem alt
    sem_alt = re.findall(
        r'<img(?![^>]*\balt=)[^>]+src=["\']([^"\']+)["\'][^>]*>',
        html_content, re.I
    )
    alt_vazio = re.findall(
        r'<img[^>]+src=["\']([^"\']+)["\'][^>]*\balt=["\']\s*["\'][^>]*>',
        html_content, re.I
    )

    urls = list(dict.fromkeys(sem_alt + alt_vazio))

    if base_url:
        urls = [urljoin(base_url, u) if not u.startswith("http") else u for u in urls]

    urls = [
        u for u in urls
        if re.match(r'^https?://', u)
        and not u.lower().endswith(".svg")
        and "svg" not in u.lower().split("?")[0].split("/")[-1]
    ]

    return urls[:MAX_IMGS]

def modo_pipeline(input_path: str, output_path: str):
    with open(input_path, "r", encoding="utf-8") as f:
        entradas = json.load(f)

    ocr_disponivel = _importar_ocr()[0] is not None
    print(f"Processando {len(entradas)} imagem(ns)... (OCR: {'ok' if ocr_disponivel else 'não disponível — instale pytesseract'})")
    resultados = []

    for i, entrada in enumerate(entradas, 1):
        url      = entrada.get("url", "")
        base_url = entrada.get("base_url", "")
        print(f"   [{i}/{len(entradas)}] {url[-55:]}", end="\r")
        r = descrever_imagem(url, base_url)
        resultados.append(r)

    print()

    with open(output_path, "w", encoding="utf-8") as f:
        json.dump(resultados, f, ensure_ascii=False, indent=2)

    ok      = sum(1 for r in resultados if r["status"] in ("ok", "cache", "renovado"))
    cache   = sum(1 for r in resultados if r["status"] == "cache")
    renovado = sum(1 for r in resultados if r["status"] == "renovado")
    ocr     = sum(1 for r in resultados if r.get("fonte") == "ocr")
    blip    = sum(1 for r in resultados if r.get("fonte") == "blip")
    erros   = sum(1 for r in resultados if r["status"] == "erro")
    print(f"{ok} descrições ({cache} cache | {renovado} renovado | {ocr} OCR | {blip} BLIP) | {erros} erros")
def modo_standalone(alvo: str):

    if alvo == "--limpar-cache":
        cache_limpar_expirados()
        return

    _, _, _, _, requests_mod = _importar_blip()

    if any(alvo.lower().endswith(ext) for ext in (".jpg", ".jpeg", ".png", ".gif", ".webp")):
        print(f"\nDescrevendo imagem: {alvo}")
        r = descrever_imagem(alvo)
        _imprimir_resultado(r)
        return

    html_content = ""
    base_url     = ""

    if alvo.startswith("http"):
        print(f"Buscando página: {alvo}")
        try:
            resp = requests_mod.get(alvo, timeout=15)
            html_content = resp.text
            base_url     = alvo
        except Exception as e:
            print(f"Erro ao buscar página: {e}")
            return
    elif os.path.exists(alvo):
        print(f"Lendo arquivo: {alvo}")
        with open(alvo, "r", encoding="utf-8", errors="ignore") as f:
            html_content = f.read()
    else:
        print(f"Argumento não reconhecido: {alvo}")
        print("Uso: python visao.py <URL> | <arquivo.html> | <url-de-imagem>")
        return

    urls = extrair_imgs_sem_alt(html_content, base_url)
    print(f"Encontradas {len(urls)} imagem(ns) sem alt (máx {MAX_IMGS})\n")

    if not urls:
        print("Nenhuma imagem sem alt encontrada.")
        return

    for i, url in enumerate(urls, 1):
        print(f"[{i}/{len(urls)}] {url[-70:]}")
        r = descrever_imagem(url, base_url)
        _imprimir_resultado(r)
        print()

def _imprimir_resultado(r: dict):
    status_icon = {"ok": "✅", "cache": "♻️ ", "renovado": "🔄", "erro": "❌"}.get(r["status"], "?")
    fonte_tag   = {"ocr": "[OCR]", "blip": "[BLIP]", "cache": "[cache]"}.get(r.get("fonte",""), "")
    print(f"  {status_icon} Status      : {r['status']} {fonte_tag}")
    if r["status"] == "erro":
        print(f"     Erro       : {r['erro']}")
    else:
        if r.get("fonte") == "ocr":
            print(f"     Texto OCR  : {r['descricao_en']}")
        else:
            print(f"     BLIP (EN)  : {r['descricao_en']}")
        print(f"     Alt suger. : {r['alt_sugerido']}")
        print(f"     HTML fix   : <img src=\"...\" alt=\"{r['alt_sugerido']}\">")

if __name__ == "__main__":
    args = sys.argv[1:]

    if len(args) == 2 and args[0].endswith(".json") and args[1].endswith(".json"):
        modo_pipeline(args[0], args[1])
    elif len(args) >= 1:
        modo_standalone(args[0])
    else:
        print("visao.py — Geração automática de descrições de imagens (BLIP + OCR)\n")

        print(f"\nCache TTL: {_TTL_DAYS} dia(s) (ajuste via BLIP_CACHE_TTL_DAYS=N)")
        ocr_ok = _importar_ocr()[0] is not None
        print(f"OCR:       {'pytesseract disponível' if ocr_ok else 'ão disponível (pip install pytesseract + apt install tesseract-ocr)'}")
