# src/core_model.py
from __future__ import annotations
import os
from typing import Any, Dict, List, Optional

# --- OpenAI-compatible client (for providers exposing OpenAI-style /v1/chat/completions)
try:
    from openai import OpenAI  # pip install openai
except Exception:
    OpenAI = None  # optional

# --- Hugging Face Transformers client (local/offline)
try:
    import torch  # optional, may be heavy
    from transformers import AutoModelForCausalLM, AutoTokenizer
except Exception:
    torch = None
    AutoModelForCausalLM = None
    AutoTokenizer = None


class BaseLLMClient:
    def generate(self, messages: List[Dict[str, str]], *, temperature: float = 0.2,
                 max_tokens: int = 512, stop: Optional[List[str]] = None) -> str:
        raise NotImplementedError


# ------------------------------
# OpenAI-compatible backend
# ------------------------------
class OpenAICompatLLM(BaseLLMClient):
    def __init__(self, model: str, api_key: str, base_url: Optional[str] = None):
        if OpenAI is None:
            raise RuntimeError("openai package is not installed. pip install openai")
        self.client = OpenAI(api_key=api_key, base_url=base_url) if base_url else OpenAI(api_key=api_key)
        self.model = model

    def generate(self, messages: List[Dict[str, str]], *, temperature: float = 0.2,
                 max_tokens: int = 512, stop: Optional[List[str]] = None) -> str:
        resp = self.client.chat.completions.create(
            model=self.model,
            messages=messages,
            temperature=temperature,
            max_tokens=max_tokens,
            stop=stop,
        )
        return (resp.choices[0].message.content or "").strip()


# ------------------------------
# Hugging Face local backend
# ------------------------------
class HFLocalLLM(BaseLLMClient):
    def __init__(self, model_name: str = "meta-llama/Meta-Llama-3-8B-Instruct",
                 dtype: str = "bfloat16", device: Optional[str] = None, attn_impl: Optional[str] = None):
        if AutoModelForCausalLM is None or AutoTokenizer is None:
            raise RuntimeError("transformers/torch not available. pip install transformers torch --extra-index-url https://download.pytorch.org/whl/cu121")
        self.tokenizer = AutoTokenizer.from_pretrained(model_name, use_fast=True)
        torch_dtype = getattr(torch, dtype) if dtype and hasattr(torch, dtype) else torch.float16
        kwargs: Dict[str, Any] = {"torch_dtype": torch_dtype}
        if attn_impl:
            kwargs["attn_implementation"] = attn_impl
        self.model = AutoModelForCausalLM.from_pretrained(model_name, low_cpu_mem_usage=True, **kwargs)
        self.device = device or ("cuda" if torch.cuda.is_available() else "cpu")
        self.model.to(self.device)
        self.model.eval()

    def generate(self, messages: List[Dict[str, str]], *, temperature: float = 0.2,
                 max_tokens: int = 512, stop: Optional[List[str]] = None) -> str:
        # simple chat template (system+user+assistant…)
        prompt = _to_simple_prompt(messages)
        inputs = self.tokenizer(prompt, return_tensors="pt").to(self.device)
        gen_ids = self.model.generate(
            **inputs,
            do_sample=(temperature > 0.0),
            temperature=temperature,
            max_new_tokens=max_tokens,
            eos_token_id=self._eos_ids(stop),
        )
        out = self.tokenizer.decode(gen_ids[0], skip_special_tokens=True)
        return _strip_prompt(out, prompt)

    def _eos_ids(self, stop: Optional[List[str]]) -> Optional[int]:
        # leave None; stop sequences are not trivially supported without custom logits processors
        return self.tokenizer.eos_token_id


# ------------------------------
# Factory
# ------------------------------
def get_llm_from_env() -> Optional[BaseLLMClient]:
    """
    우선순위:
      1) OPENAI_COMPAT_API_KEY (+ OPENAI_COMPAT_MODEL, OPENAI_COMPAT_BASE_URL)
      2) HF_LOCAL_MODEL (transformers 로컬)
      3) 없으면 None (규칙기반 fallback)
    """
    api_key = os.getenv("OPENAI_COMPAT_API_KEY")
    model = os.getenv("OPENAI_COMPAT_MODEL", "llama3-8b-instruct")
    base_url = os.getenv("OPENAI_COMPAT_BASE_URL")  # 옵션

    if api_key:
        try:
            return OpenAICompatLLM(model=model, api_key=api_key, base_url=base_url)
        except Exception:
            pass  # 환경은 있으나 패키지 미설치 등 → 아래 HF 시도

    hf_model = os.getenv("HF_LOCAL_MODEL")
    if hf_model:
        try:
            return HFLocalLLM(model_name=hf_model,
                              dtype=os.getenv("HF_LOCAL_DTYPE", "bfloat16"),
                              device=os.getenv("HF_LOCAL_DEVICE"),
                              attn_impl=os.getenv("HF_LOCAL_ATTN_IMPL"))
        except Exception:
            pass

    return None


# ------------------------------
# helpers
# ------------------------------
def _to_simple_prompt(messages: List[Dict[str, str]]) -> str:
    """
    매우 단순한 chat → prompt 변환 (system, user, assistant 순환)
    """
    parts = []
    for m in messages:
        role = m.get("role", "user")
        content = (m.get("content") or "").strip()
        if role == "system":
            parts.append(f"<<SYS>>\n{content}\n<</SYS>>")
        elif role == "assistant":
            parts.append(f"Assistant: {content}")
        else:
            parts.append(f"User: {content}")
    parts.append("Assistant:")
    return "\n".join(parts)

def _strip_prompt(full: str, prompt: str) -> str:
    if full.startswith(prompt):
        return full[len(prompt):].strip()
    return full.strip()
