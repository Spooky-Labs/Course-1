import backtrader as bt
import torch
from transformers import AutoModelForSequenceClassification, AutoTokenizer
import numpy as np


class Agent(bt.Strategy):
    params = (
        ("model_name", "distilbert-base-uncased"),
        ("seq_length", 10),
        ("threshold", 0.6),
        ("position_size", 0.15),
    )

    def __init__(self):
        # Create lines for storing signals
        self.model_signals = {}

        # Initialize Hugging Face model
        self.device = torch.device("cuda" if torch.cuda.is_available() else "cpu")
        self.tokenizer = AutoTokenizer.from_pretrained(self.params.model_name)
        self.model = AutoModelForSequenceClassification.from_pretrained(
            self.params.model_name, num_labels=3
        ).to(self.device)
        print("Model loaded - classifier warnings are expected")

        # Create lookback buffers
        for i, d in enumerate(self.datas):
            d.lookback = []
            # Store the data index for reference
            self.model_signals[i] = 0  # Simple dict instead of indicator

    def next(self):
        for i, d in enumerate(self.datas):
            d.lookback.append(d.close[0])
            if len(d.lookback) < self.params.seq_length:
                continue

            # Create feature text from recent price data
            recent = d.lookback[-self.params.seq_length :]
            returns = [
                recent[i] / recent[i - 1] - 1 if i > 0 else 0
                for i in range(len(recent))
            ]
            feature_text = f"Price movements: {' '.join([f'{r:.4f}' for r in returns])}"

            # Get prediction
            inputs = self.tokenizer(
                feature_text, return_tensors="pt", truncation=True
            ).to(self.device)
            with torch.no_grad():
                outputs = self.model(**inputs)
                probs = torch.softmax(outputs.logits, dim=1)
                pred = torch.argmax(probs, dim=1).item()
                conf = probs[0][pred].item()

            # Store signal in our dictionary instead of non-existent indicator
            self.model_signals[i] = pred

            # Execute trades based on prediction
            if (
                not self.getposition(d).size
                and pred == 2
                and conf > self.params.threshold
            ):
                size = int(
                    self.broker.getcash() * self.params.position_size / d.close[0]
                )
                if size > 0:  # Ensure we're not trying to buy 0 shares
                    self.close(data=d)
                    print(f"BUY {d._name} at {d.close[0]:.2f}, confidence: {conf:.2f}")
            elif (
                self.getposition(d).size and pred == 0 and conf > self.params.threshold
            ):
                self.buy(data=d, size=size)
                print(f"SELL {d._name} at {d.close[0]:.2f}, confidence: {conf:.2f}")
