import os
import json
import csv
import math
import torch
import torch.nn as nn
from torch.utils.data import Dataset, DataLoader
import sys

sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '../../')))
import config

class CustomMathDataset(Dataset):
    def __init__(self, data_path, vocab):
        self.data = []
        self.vocab = vocab
        if not os.path.exists(data_path):
            raise FileNotFoundError(f"Data not found: {data_path}")
        with open(data_path, 'r', encoding='utf-8') as f:
            for line in f:
                item = json.loads(line)
                text = f"Câu hỏi: {item['question']} Giải: {item['answer']}"
                self.data.append(text)

    def __len__(self):
        return len(self.data)

    def __getitem__(self, idx):
        text = self.data[idx]
        tokens = [self.vocab.get(char, self.vocab.get("<UNK>", 0)) for char in text]
        max_len = 128
        if len(tokens) > max_len:
            tokens = tokens[:max_len]
        else:
            tokens += [self.vocab.get("<PAD>", 0)] * (max_len - len(tokens))

        x = torch.tensor(tokens[:-1], dtype=torch.long)
        y = torch.tensor(tokens[1:], dtype=torch.long)
        return x, y

class PositionalEncoding(nn.Module):
    def __init__(self, d_model, max_len=5000):
        super(PositionalEncoding, self).__init__()
        pe = torch.zeros(max_len, d_model)
        position = torch.arange(0, max_len, dtype=torch.float).unsqueeze(1)
        div_term = torch.exp(torch.arange(0, d_model, 2).float() * (-math.log(10000.0) / d_model))
        pe[:, 0::2] = torch.sin(position * div_term)
        pe[:, 1::2] = torch.cos(position * div_term)
        pe = pe.unsqueeze(0)
        self.register_buffer('pe', pe)

    def forward(self, x):
        return x + self.pe[:, :x.size(1)]

class TransformerDecoderModel(nn.Module):
    def __init__(self, vocab_size, d_model=256, nhead=8, num_layers=4, dim_feedforward=512):
        super(TransformerDecoderModel, self).__init__()
        self.embedding = nn.Embedding(vocab_size, d_model)
        self.pos_encoder = PositionalEncoding(d_model)
        decoder_layer = nn.TransformerDecoderLayer(d_model, nhead, dim_feedforward, batch_first=True)
        self.transformer_decoder = nn.TransformerDecoder(decoder_layer, num_layers)
        self.fc = nn.Linear(d_model, vocab_size)
        self.d_model = d_model

    def generate_square_subsequent_mask(self, sz):
        mask = (torch.triu(torch.ones(sz, sz)) == 1).transpose(0, 1)
        mask = mask.float().masked_fill(mask == 0, float('-inf')).masked_fill(mask == 1, float(0.0))
        return mask

    def forward(self, x):
        seq_len = x.size(1)
        tgt_mask = self.generate_square_subsequent_mask(seq_len).to(x.device)

        embedded = self.embedding(x) * math.sqrt(self.d_model)
        embedded = self.pos_encoder(embedded)

        # Self-attention decoder memory can be same as embedded for pure decoder LM
        output = self.transformer_decoder(embedded, embedded, tgt_mask=tgt_mask)
        prediction = self.fc(output)
        return prediction

def build_vocab(data_path):
    vocab = {"<PAD>": 0, "<UNK>": 1}
    idx = 2
    if not os.path.exists(data_path):
        return vocab
    with open(data_path, 'r', encoding='utf-8') as f:
        for line in f:
            item = json.loads(line)
            text = f"Câu hỏi: {item['question']} Giải: {item['answer']}"
            for char in text:
                if char not in vocab:
                    vocab[char] = idx
                    idx += 1
    return vocab

def train():
    data_path = os.path.join(config.DATA_PROCESSED_DIR, "train.jsonl")

    print("Building vocabulary for M2 Transformer...")
    vocab = build_vocab(data_path)
    vocab_path = os.path.join(config.MODELS_DIR, "m2_transformer/vocab.json")
    os.makedirs(os.path.dirname(vocab_path), exist_ok=True)
    with open(vocab_path, 'w', encoding='utf-8') as f:
        json.dump(vocab, f, ensure_ascii=False)

    dataset = CustomMathDataset(data_path, vocab)
    dataloader = DataLoader(dataset, batch_size=config.TRAIN_BATCH_SIZE, shuffle=True)

    model = TransformerDecoderModel(len(vocab))
    device = torch.device('cuda' if torch.cuda.is_available() else 'cpu')
    model.to(device)

    criterion = nn.CrossEntropyLoss(ignore_index=vocab.get("<PAD>", 0))
    optimizer = torch.optim.Adam(model.parameters(), lr=0.0001)

    num_epochs = 5

    csv_log_path = os.path.join(config.MODELS_DIR, "m2_transformer/logs/training_log.csv")
    os.makedirs(os.path.dirname(csv_log_path), exist_ok=True)
    with open(csv_log_path, mode='w', newline='') as f:
        writer = csv.writer(f)
        writer.writerow(['step', 'epoch', 'loss', 'learning_rate'])

    print("Starting training M2 Transformer...")
    model.train()
    global_step = 0
    for epoch in range(num_epochs):
        for batch_idx, (x, y) in enumerate(dataloader):
            x, y = x.to(device), y.to(device)

            optimizer.zero_grad()
            output = model(x)

            output = output.view(-1, len(vocab))
            y = y.view(-1)

            loss = criterion(output, y)
            loss.backward()
            optimizer.step()

            global_step += 1
            if global_step % 10 == 0:
                print(f"Epoch {epoch}, Step {global_step}, Loss: {loss.item():.4f}")
                with open(csv_log_path, mode='a', newline='') as f:
                    writer = csv.writer(f)
                    writer.writerow([global_step, epoch, round(loss.item(), 4), optimizer.param_groups[0]['lr']])

    final_output_dir = os.path.join(config.MODELS_DIR, "m2_transformer/final")
    os.makedirs(final_output_dir, exist_ok=True)
    torch.save(model.state_dict(), os.path.join(final_output_dir, "model.pt"))
    print(f"Training complete. Model saved to {final_output_dir}")

if __name__ == "__main__":
    train()
