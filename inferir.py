# inferir.py — testa o modelo treinado em HTMLs novos
#
# Uso:
#   python inferir.py "<button><i class='fa fa-bars'></i></button>"   → um HTML
#   python inferir.py                                                  → modo interativo
#   python inferir.py --batch arquivo.jsonl                            → modo batch
#   python inferir.py --batch arquivo.jsonl --saida resultado.jsonl    → grava predições
#
#   {"html": "<img src='x.jpg'>"}                                  → só classifica
#   {"html": "<img src='x.jpg'>", "categoria": "wcag-1.1.1"}        → classifica + calcula acerto

import sys
import json
import pickle
import argparse
from collections import defaultdict

import torch
from transformers import DistilBertTokenizerFast, DistilBertForSequenceClassification

MODEL_DIR = "modelo-wcag"
MAX_LENGTH = 256

def carregar_modelo():
    print("Carregando modelo...")
    tokenizer = DistilBertTokenizerFast.from_pretrained(MODEL_DIR)
    model = DistilBertForSequenceClassification.from_pretrained(MODEL_DIR)
    model.eval()

    with open(f"{MODEL_DIR}/label_encoder.pkl", "rb") as f:
        le = pickle.load(f)

    return tokenizer, model, le

def classificar(html, tokenizer, model, le):
    texto = f"### ERRO WCAG: \n### HTML com problema:\n{html}"

    enc = tokenizer(
        texto,
        truncation=True,
        padding="max_length",
        max_length=MAX_LENGTH,
        return_tensors="pt",
    )

    with torch.no_grad():
        outputs = model(**enc)
        probs   = torch.softmax(outputs.logits, dim=1)[0]
        pred    = torch.argmax(probs).item()

    categoria   = le.inverse_transform([pred])[0]
    confianca   = probs[pred].item()

    top3_idx    = torch.topk(probs, k=min(3, len(le.classes_))).indices.tolist()
    top3        = [(le.inverse_transform([i])[0], probs[i].item()) for i in top3_idx]

    return categoria, confianca, top3

def _extrair_html_e_categoria(obj: dict) -> tuple[str, str | None]:
    if "html" in obj:
        return obj["html"], obj.get("categoria")

    if "input" in obj:
        texto = obj["input"]
        primeira_linha = texto.split("\n", 1)[0]
        categoria = primeira_linha.replace("### ERRO WCAG:", "").strip() or None
        marcador = "### HTML com problema:\n"
        if marcador in texto:
            html = texto.split(marcador, 1)[1]
        else:
            html = texto
        return html, categoria

    raise ValueError("Linha sem campo 'html' nem 'input' reconhecível")


def processar_batch(jsonl_path: str, saida_path: str | None, tokenizer, model, le):
    linhas_validas, linhas_invalidas = 0, 0
    resultados = []

    with open(jsonl_path, "r", encoding="utf-8") as f:
        for n_linha, linha in enumerate(f, 1):
            linha = linha.strip()
            if not linha:
                continue
            try:
                obj = json.loads(linha)
                html, cat_real = _extrair_html_e_categoria(obj)
            except (json.JSONDecodeError, ValueError) as e:
                linhas_invalidas += 1
                print(f"Linha {n_linha} ignorada: {e}")
                continue

            categoria_pred, confianca, _ = classificar(html, tokenizer, model, le)
            resultados.append({
                "html":            html,
                "categoria_real":  cat_real,
                "categoria_pred":  categoria_pred,
                "confianca":       round(confianca, 4),
                "acertou":         (cat_real == categoria_pred) if cat_real else None,
            })
            linhas_validas += 1

            if linhas_validas % 50 == 0:
                print(f"   [{linhas_validas}] processadas...", end="\r")

    print(f"\nBatch concluído: {linhas_validas} linha(s) processada(s)"
          + (f", {linhas_invalidas} ignorada(s)" if linhas_invalidas else ""))

    if saida_path:
        with open(saida_path, "w", encoding="utf-8") as f:
            for r in resultados:
                f.write(json.dumps(r, ensure_ascii=False) + "\n")
        print(f"Predições gravadas em: {saida_path}")

    com_ground_truth = [r for r in resultados if r["categoria_real"] is not None]

    if not com_ground_truth:
        print("\nNenhuma linha tinha campo 'categoria' — apenas classificação, sem métricas de acerto.")
        return

    total_gt = len(com_ground_truth)
    acertos  = sum(1 for r in com_ground_truth if r["acertou"])
    acuracia = acertos / total_gt

    print(f"\nAcurácia geral : {acuracia:.1%}  ({acertos}/{total_gt} com categoria conhecida)")

    por_categoria = defaultdict(lambda: {"acertos": 0, "total": 0})
    for r in com_ground_truth:
        chave = r["categoria_real"]
        por_categoria[chave]["total"] += 1
        if r["acertou"]:
            por_categoria[chave]["acertos"] += 1

    print("\n   Por categoria:")
    for cat in sorted(por_categoria):
        stats = por_categoria[cat]
        acc_cat = stats["acertos"] / stats["total"] if stats["total"] else 0
        barra = "█" * int(acc_cat * 20)
        print(f"     {cat:<15} {stats['acertos']:>4}/{stats['total']:<4} ({acc_cat:.0%}) {barra}")

    confusoes = defaultdict(int)
    for r in com_ground_truth:
        if not r["acertou"]:
            confusoes[(r["categoria_real"], r["categoria_pred"])] += 1

    if confusoes:
        print("\n Confusões mais frequentes (real → predito):")
        top_confusoes = sorted(confusoes.items(), key=lambda kv: -kv[1])[:5]
        for (real, pred), qtd in top_confusoes:
            print(f"     {real:<15} → {pred:<15} ({qtd}x)")



def main():
    parser = argparse.ArgumentParser(
        description="Testa o modelo DistilBERT WCAG em HTMLs novos.",
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    parser.add_argument("html", nargs="?", default=None,
                        help="HTML único a classificar (modo argumento)")
    parser.add_argument("--batch", metavar="ARQUIVO.jsonl",
                        help="Classifica em lote a partir de um arquivo JSONL")
    parser.add_argument("--saida", metavar="ARQUIVO.jsonl",
                        help="Grava as predições do modo --batch neste arquivo")
    args = parser.parse_args()

    tokenizer, model, le = carregar_modelo()

    if args.batch:
        print(f"\nModo batch: {args.batch}\n")
        processar_batch(args.batch, args.saida, tokenizer, model, le)
        return

    if args.html:
        html = args.html
        categoria, confianca, top3 = classificar(html, tokenizer, model, le)
        print(f"\HTML: {html[:100]}...")
        print(f"Categoria predita : {categoria}")
        print(f"Confiança : {confianca:.1%}")
        print(f"Top 3:")
        for cat, prob in top3:
            barra = "█" * int(prob * 20)
            print(f"     {cat:<15} {prob:.1%} {barra}")
        return

    print("Modo interativo — cole um trecho HTML e pressione Enter")
    print("(digite 'sair' para encerrar)\n")

    while True:
        html = input("HTML > ").strip()
        if html.lower() in ("sair", "exit", "q"):
            break
        if not html:
            continue

        categoria, confianca, top3 = classificar(html, tokenizer, model, le)
        print(f"\nCategoria : {categoria}")
        print(f"Confiança: {confianca:.1%}")
        print(f"Top 3:")
        for cat, prob in top3:
            barra = "█" * int(prob * 20)
            print(f"     {cat:<15} {prob:.1%} {barra}")
        print()

if __name__ == "__main__":
    main()
