# Simple stub for core model; replace with LLaMA3 wrapper later
class CoreModel:
    def __init__(self):
        pass

    def generate(self, prompt: str) -> str:
        # Minimal echo with safety phrasing
        return f"[CORE] Processed: {prompt[:200]}"