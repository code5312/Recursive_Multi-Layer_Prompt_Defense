# Training script for LCE (DistilBERT-based classifier)
# Usage:
#   python src/lce/train_lce.py --data data/processed/train.jsonl --output models/lce --model distilbert-base-uncased
import argparse, pathlib
from datasets import load_dataset
from transformers import AutoTokenizer, AutoModelForSequenceClassification, TrainingArguments, Trainer
import numpy as np
import sklearn.metrics as skm

def parse_args():
    p = argparse.ArgumentParser()
    p.add_argument('--data', required=True)
    p.add_argument('--model', default='distilbert-base-uncased')
    p.add_argument('--output', default='models/lce')
    p.add_argument('--epochs', type=int, default=3)
    p.add_argument('--batch', type=int, default=16)
    return p.parse_args()

def compute_metrics(p):
    preds = np.argmax(p.predictions, axis=1)
    labels = p.label_ids
    prec, rec, f1, _ = skm.precision_recall_fscore_support(labels, preds, average='macro')
    acc = skm.accuracy_score(labels, preds)
    return {'accuracy': acc, 'precision': prec, 'recall': rec, 'f1': f1}

def main():
    args = parse_args()
    raw = load_dataset('json', data_files={'train': args.data})['train']
    def map_label(ex):
        return {'label': 0 if (ex.get('attack_label') or 'none') == 'none' else 1}
    raw = raw.map(map_label)

    tok = AutoTokenizer.from_pretrained(args.model)
    def tok_fn(ex): return tok(ex['prompt'], truncation=True, padding='max_length', max_length=256)
    raw = raw.map(tok_fn, batched=True)
    raw = raw.rename_column('label', 'labels')
    raw.set_format(type='torch', columns=['input_ids','attention_mask','labels'])

    model = AutoModelForSequenceClassification.from_pretrained(args.model, num_labels=2)
    targs = TrainingArguments(output_dir=args.output, per_device_train_batch_size=args.batch,
                              num_train_epochs=args.epochs, evaluation_strategy='no',
                              save_strategy='epoch', logging_steps=10)
    trainer = Trainer(model=model, args=targs, train_dataset=raw, compute_metrics=compute_metrics)
    trainer.train()
    trainer.save_model(args.output)
    print('Saved model to', args.output)

if __name__ == '__main__':
    main()
