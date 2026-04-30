import os
import json
import csv
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
                # simple mock preprocessing
                text = f"Câu hỏi: {item['question']} Giải: {item['answer']}"
                self.data.append(text)

    def __len__(self):
        return len(self.data)

    def __getitem__(self, idx):
        # Mock encoding logic
        text = self.data[idx]
        tokens = [self.vocab.get(char, self.vocab.get("<UNK>", 0)) for char in text]
        # Pad or truncate
        max_len = 128
        if len(tokens) > max_len:
            tokens = tokens[:max_len]
        else:
            tokens += [self.vocab.get("<PAD>", 0)] * (max_len - len(tokens))

        x = torch.tensor(tokens[:-1], dtype=torch.long)
        y = torch.tensor(tokens[1:], dtype=torch.long)
        return x, y

class LSTMModel(nn.Module):
    def __init__(self, vocab_size, embed_dim, hidden_dim):
        super(LSTMModel, self).__init__()
        self.embedding = nn.Embedding(vocab_size, embed_dim)
        self.lstm = nn.LSTM(embed_dim, hidden_dim, batch_first=True)
        self.fc = nn.Linear(hidden_dim, vocab_size)

    def forward(self, x):
        embedded = self.embedding(x)
        output, (hidden, cell) = self.lstm(embedded)
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

    print("Building vocabulary for M1 LSTM...")
    vocab = build_vocab(data_path)
    vocab_path = os.path.join(config.MODELS_DIR, "m1_lstm/vocab.json")
    os.makedirs(os.path.dirname(vocab_path), exist_ok=True)
    with open(vocab_path, 'w', encoding='utf-8') as f:
        json.dump(vocab, f, ensure_ascii=False)

    dataset = CustomMathDataset(data_path, vocab)
    dataloader = DataLoader(dataset, batch_size=config.TRAIN_BATCH_SIZE, shuffle=True)

    model = LSTMModel(len(vocab), embed_dim=256, hidden_dim=512)
    device = torch.device('cuda' if torch.cuda.is_available() else 'cpu')
    model.to(device)

    criterion = nn.CrossEntropyLoss(ignore_index=vocab.get("<PAD>", 0))
    optimizer = torch.optim.Adam(model.parameters(), lr=0.001)

    num_epochs = 5

    csv_log_path = os.path.join(config.MODELS_DIR, "m1_lstm/logs/training_log.csv")
    os.makedirs(os.path.dirname(csv_log_path), exist_ok=True)
    with open(csv_log_path, mode='w', newline='') as f:
        writer = csv.writer(f)
        writer.writerow(['step', 'epoch', 'loss', 'learning_rate'])

    print("Starting training M1 LSTM...")
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

    final_output_dir = os.path.join(config.MODELS_DIR, "m1_lstm/final")
    os.makedirs(final_output_dir, exist_ok=True)
    torch.save(model.state_dict(), os.path.join(final_output_dir, "model.pt"))
    print(f"Training complete. Model saved to {final_output_dir}")

if __name__ == "__main__":
    train()
