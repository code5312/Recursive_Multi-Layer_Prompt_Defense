def compute_f1(results, mode="before"):
    tp = sum(1 for r in results if r["label"] == "attack" and r[f"pred_{mode}"] == "attack")
    fp = sum(1 for r in results if r["label"] == "benign" and r[f"pred_{mode}"] == "attack")
    fn = sum(1 for r in results if r["label"] == "attack" and r[f"pred_{mode}"] == "safe")
    precision = tp / (tp + fp + 1e-9)
    recall = tp / (tp + fn + 1e-9)
    f1 = 2 * precision * recall / (precision + recall + 1e-9)
    return f1
