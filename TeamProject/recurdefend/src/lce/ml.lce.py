from .base_lce import BaseLCE
from transformers import AutoTokenizer, AutoModelForSequenceClassification
import torch, torch.nn.functional as F, time

class MLLCE(BaseLCE):
    def __init__(self, model_name_or_path="distilbert-base-uncased"):
        super().__init__(name="ml_lce")
        self.tokenizer = AutoTokenizer.from_pretrained(model_name_or_path)
        self.model = AutoModelForSequenceClassification.from_pretrained(model_name_or_path)
        self.model.eval()

    def predict(self, text, context=None):
        t0 = time.time()
        inputs = self.tokenizer(text or "", truncation=True, padding=True, return_tensors="pt", max_length=256)
        with torch.no_grad():
            logits = self.model(**inputs).logits
            probs = F.softmax(logits, dim=-1)[0].tolist()
        # labels: [allow, block] OR [allow, flag, block] depending on training; assume 2 for template
        if len(probs) == 2:
            risk = probs[1]
        else:
            risk = probs[2]  # if 3-class
        verdict = "block" if risk > 0.8 else ("flag" if risk > 0.35 else "allow")
        res = {"verdict": verdict, "score": float(risk), "labels": [], "evidence": []}
        return self._with_latency(res, t0)
