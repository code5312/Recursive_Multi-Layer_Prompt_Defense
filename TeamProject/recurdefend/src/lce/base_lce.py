from abc import ABC, abstractmethod
import time

class BaseLCE(ABC):
    def __init__(self, name="base"):
        self.name = name

    @abstractmethod
    def predict(self, text, context=None):
        """
        Return dict:
        {
          "verdict": "allow|flag|block",
          "score": 0.0,
          "labels": [...],
          "evidence": [...],
          "meta": {"latency_ms": int, "model": "name"}
        }
        """
        pass

    def _with_latency(self, res: dict, t0: float) -> dict:
        import time
        res.setdefault("meta", {})["latency_ms"] = int((time.time() - t0) * 1000)
        res["meta"]["model"] = self.name
        return res