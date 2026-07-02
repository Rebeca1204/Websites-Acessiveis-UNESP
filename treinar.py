# treinar.py — Fine-tuning do DistilBERT (modo low-memory: 4-8 GB RAM, só CPU)

import json, os, gc, pickle
import numpy as np
import matplotlib
matplotlib.use("Agg")   
import matplotlib.pyplot as plt
import seaborn as sns

from collections import Counter
from sklearn.model_selection import train_test_split
from sklearn.metrics import classification_report, confusion_matrix, f1_score
from sklearn.preprocessing import LabelEncoder

import torch
from torch.utils.data import Dataset, DataLoader
from transformers import (
    DistilBertTokenizerFast,
    DistilBertForSequenceClassification,
    get_linear_schedule_with_warmup,
)

DATASET_PATH  = "dataset-balanced.jsonl"
MODEL_DIR     = "modelo-wcag"
RESULTS_DIR   = "resultados"

MODEL_NAME    = "distilbert-base-uncased"   
MAX_LENGTH    = 64                          
BATCH_SIZE    = 2                          
GRAD_ACCUM    = 4                          
EPOCHS        = 3                         
LEARNING_RATE = 3e-5
EXEMPLOS_POR_CAT = 200                    
TEST_SIZE     = 0.2
SEED          = 42

os.makedirs(RESULTS_DIR, exist_ok=True)
torch.manual_seed(SEED)
np.random.seed(SEED)

device = torch.device("cpu")
print(f"Dispositivo : {device}")
print(f"Modelo      : {MODEL_NAME}")
print(f"Batch size  : {BATCH_SIZE} (acumulação: {GRAD_ACCUM}x → efetivo {BATCH_SIZE*GRAD_ACCUM})")
print(f"max length  : {MAX_LENGTH} tokens")

print(f"\nCarregando dataset (máx {EXEMPLOS_POR_CAT} exemplos/categoria)...")

por_cat   = {}
with open(DATASET_PATH, "r", encoding="utf-8") as f:
    for linha in f:
        linha = linha.strip()
        if not linha:
            continue
        obj = json.loads(linha)
        cat = obj["input"].split("\n")[0].replace("### ERRO WCAG: ", "").strip()
        if cat not in por_cat:
            por_cat[cat] = []
        if len(por_cat[cat]) < EXEMPLOS_POR_CAT:
            por_cat[cat].append(obj["input"])

textos, rotulos = [], []
for cat, exemplos in por_cat.items():
    textos.extend(exemplos)
    rotulos.extend([cat] * len(exemplos))

print(f"   Total de exemplos : {len(textos)}")
for cat, qtd in sorted(Counter(rotulos).items()):
    print(f"   {cat:<15} → {qtd}")

le = LabelEncoder()
rotulos_enc = le.fit_transform(rotulos)
num_classes = len(le.classes_)
print(f"\nClasses ({num_classes}): {list(le.classes_)}")

X_train, X_val, y_train, y_val = train_test_split(
    textos, rotulos_enc,
    test_size=TEST_SIZE,
    random_state=SEED,
    stratify=rotulos_enc,
)
print(f"\nTreino: {len(X_train)}|  Validação: {len(X_val)}")
print(f"\nCarregando tokenizador ({MODEL_NAME})...")
tokenizer = DistilBertTokenizerFast.from_pretrained(MODEL_NAME)

class WCAGDataset(Dataset):
    def __init__(self, textos, rotulos):
        self.textos  = textos
        self.rotulos = rotulos

    def __len__(self):
        return len(self.rotulos)

    def __getitem__(self, idx):
        enc = tokenizer(
            self.textos[idx],
            truncation=True,
            padding="max_length",
            max_length=MAX_LENGTH,
            return_tensors="pt",
        )
        return {
            "input_ids":      enc["input_ids"].squeeze(0),
            "attention_mask": enc["attention_mask"].squeeze(0),
            "labels":         torch.tensor(self.rotulos[idx], dtype=torch.long),
        }

train_dataset = WCAGDataset(X_train, y_train)
val_dataset   = WCAGDataset(X_val,   y_val)

train_loader = DataLoader(train_dataset, batch_size=BATCH_SIZE, shuffle=True,  num_workers=0)
val_loader   = DataLoader(val_dataset,   batch_size=BATCH_SIZE, shuffle=False, num_workers=0)
print(f"\nCarregando modelo ({MODEL_NAME})...")
model = DistilBertForSequenceClassification.from_pretrained(
    MODEL_NAME,
    num_labels=num_classes,
)
model.to(device)

contagens = np.bincount(y_train)
pesos     = (1.0 / contagens) / (1.0 / contagens).sum() * num_classes
criterion = torch.nn.CrossEntropyLoss(
    weight=torch.tensor(pesos, dtype=torch.float).to(device)
)

optimizer     = torch.optim.AdamW(model.parameters(), lr=LEARNING_RATE, weight_decay=0.01)
total_steps   = (len(train_loader) // GRAD_ACCUM) * EPOCHS
scheduler     = get_linear_schedule_with_warmup(
    optimizer,
    num_warmup_steps=max(1, int(0.1 * total_steps)),
    num_training_steps=total_steps,
)

print(f"\nTreinando ({EPOCHS} épocas × {len(train_loader)} batches)...")
print(f"Estimativa: ~{EPOCHS * len(train_loader) * 2 // 60 + 1} min na CPU\n")

historico   = {"train_loss": [], "val_loss": [], "val_f1": []}
melhor_f1   = 0.0
melhor_epoca = 0

for epoca in range(1, EPOCHS + 1):
    model.train()
    train_loss_total = 0.0
    optimizer.zero_grad()

    for i, batch in enumerate(train_loader):
        input_ids      = batch["input_ids"].to(device)
        attention_mask = batch["attention_mask"].to(device)
        labels         = batch["labels"].to(device)

        outputs = model(input_ids=input_ids, attention_mask=attention_mask)
        loss    = criterion(outputs.logits, labels) / GRAD_ACCUM
        loss.backward()

        train_loss_total += loss.item() * GRAD_ACCUM

        if (i + 1) % GRAD_ACCUM == 0 or (i + 1) == len(train_loader):
            torch.nn.utils.clip_grad_norm_(model.parameters(), 1.0)
            optimizer.step()
            scheduler.step()
            optimizer.zero_grad()

        if (i + 1) % 50 == 0 or (i + 1) == len(train_loader):
            media = train_loss_total / (i + 1)
            print(f"   Época {epoca}/{EPOCHS} | Batch {i+1}/{len(train_loader)} | Loss: {media:.4f}", end="\r")

    avg_train = train_loss_total / len(train_loader)

    model.eval()
    val_loss_total, preds_all, labels_all = 0.0, [], []

    with torch.no_grad():
        for batch in val_loader:
            input_ids      = batch["input_ids"].to(device)
            attention_mask = batch["attention_mask"].to(device)
            labels         = batch["labels"].to(device)

            outputs = model(input_ids=input_ids, attention_mask=attention_mask)
            loss    = criterion(outputs.logits, labels)
            val_loss_total += loss.item()

            preds_all.extend(torch.argmax(outputs.logits, dim=1).cpu().numpy())
            labels_all.extend(labels.cpu().numpy())

    avg_val  = val_loss_total / len(val_loader)
    macro_f1 = f1_score(labels_all, preds_all, average="macro")

    historico["train_loss"].append(avg_train)
    historico["val_loss"].append(avg_val)
    historico["val_f1"].append(macro_f1)

    print(f"\nÉpoca {epoca}/{EPOCHS} — Train: {avg_train:.4f} | Val: {avg_val:.4f} | F1: {macro_f1:.4f}")

    if macro_f1 > melhor_f1:
        melhor_f1    = macro_f1
        melhor_epoca = epoca
        model.save_pretrained(MODEL_DIR)
        tokenizer.save_pretrained(MODEL_DIR)
        print(f"Novo melhor modelo salvo (F1={melhor_f1:.4f})")

    gc.collect() 

print(f"\nMelhor: época {melhor_epoca} — Macro F1 = {melhor_f1:.4f}")

print("\nAvaliação final...")

model = DistilBertForSequenceClassification.from_pretrained(MODEL_DIR)
model.to(device)
model.eval()

preds_final, labels_final = [], []
with torch.no_grad():
    for batch in val_loader:
        outputs = model(
            input_ids=batch["input_ids"].to(device),
            attention_mask=batch["attention_mask"].to(device),
        )
        preds_final.extend(torch.argmax(outputs.logits, dim=1).cpu().numpy())
        labels_final.extend(batch["labels"].numpy())

nomes = list(le.classes_)
print("\n" + classification_report(labels_final, preds_final, target_names=nomes))

with open(os.path.join(RESULTS_DIR, "metricas.json"), "w", encoding="utf-8") as f:
    json.dump(
        classification_report(labels_final, preds_final, target_names=nomes, output_dict=True),
        f, indent=2, ensure_ascii=False
    )

cm = confusion_matrix(labels_final, preds_final)
plt.figure(figsize=(10, 8))
sns.heatmap(cm, annot=True, fmt="d", cmap="Blues", xticklabels=nomes, yticklabels=nomes)
plt.title("Matriz de Confusão — Classificador WCAG (absoluta)")
plt.ylabel("Real"); plt.xlabel("Predito")
plt.xticks(rotation=45, ha="right"); plt.tight_layout()
plt.savefig(os.path.join(RESULTS_DIR, "matriz_confusao.png"), dpi=150)
plt.close()

cm_norm = confusion_matrix(labels_final, preds_final, normalize="true")
plt.figure(figsize=(10, 8))
sns.heatmap(
    cm_norm, annot=True, fmt=".0%", cmap="Blues",
    xticklabels=nomes, yticklabels=nomes,
    vmin=0, vmax=1,
)
plt.title("Matriz de Confusão — Classificador WCAG (normalizada por classe real)")
plt.ylabel("Real"); plt.xlabel("Predito")
plt.xticks(rotation=45, ha="right"); plt.tight_layout()
plt.savefig(os.path.join(RESULTS_DIR, "matriz_confusao_normalizada.png"), dpi=150)
plt.close()

epocas = list(range(1, EPOCHS + 1))
fig, (ax1, ax2) = plt.subplots(1, 2, figsize=(12, 4))
ax1.plot(epocas, historico["train_loss"], marker="o", label="Train Loss")
ax1.plot(epocas, historico["val_loss"],   marker="o", label="Val Loss")
ax1.set_title("Loss por Época"); ax1.set_xlabel("Época"); ax1.legend(); ax1.grid(alpha=.3)
ax2.plot(epocas, historico["val_f1"], marker="o", color="green", label="Macro F1")
ax2.set_title("Macro F1 por Época"); ax2.set_xlabel("Época"); ax2.set_ylim(0, 1); ax2.legend(); ax2.grid(alpha=.3)
plt.suptitle("Treinamento DistilBERT — Classificação WCAG")
plt.tight_layout()
plt.savefig(os.path.join(RESULTS_DIR, "treinamento.png"), dpi=150)
plt.close()

with open(os.path.join(MODEL_DIR, "label_encoder.pkl"), "wb") as f:
    pickle.dump(le, f)
import hashlib, pathlib

hash_md5 = hashlib.md5(
    open(DATASET_PATH, "rb").read()
).hexdigest()

pathlib.Path(os.path.join(MODEL_DIR, "dataset_hash.txt")).write_text(hash_md5)
print(f"   💾 Hash do dataset gravado : {hash_md5[:12]}...")

print(f"""Treinamento concluído!                           
Macro F1 final : {melhor_f1:.4f}                        
Modelo em      : {MODEL_DIR:<35}
Resultados em  : {RESULTS_DIR:<35}
""")
