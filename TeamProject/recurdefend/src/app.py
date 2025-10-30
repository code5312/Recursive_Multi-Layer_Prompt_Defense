from fastapi import FastAPI
from pydantic import BaseModel
from typing import Optional, List, Dict, Any

from utils.preprocess import preprocess_prompt
from lce.input_lce import RuleInputLCE
from lce.ml_lce import MLLCE  # optional: if not trained yet, comment out
from orchestrator.orchestrator import aggregate, should_escalate
from core_model import CoreModel
from lce.output_lce import RuleOutputLCE

class AskReq(BaseModel):
    prompt: str
    user_id: Optional[str] = None

class AskRes(BaseModel):
    verdict: str
    response: Optional[str] = None
    evidence: List[Dict[str, Any]] = []

app = FastAPI(title="RecurDefend API", version="0.1.0")

# Instantiate
input_rule = RuleInputLCE()
try:
    input_ml = MLLCE(model_name_or_path="distilbert-base-uncased")  # replace with fine-tuned path
except Exception:
    input_ml = None
output_rule = RuleOutputLCE()
core = CoreModel()

@app.post("/api/v1/ask", response_model=AskRes)
def ask(req: AskReq):
    prompt = preprocess_prompt(req.prompt)

    # 1) input LCEs
    results = []
    results.append(input_rule.predict(prompt))
    if input_ml:
        results.append(input_ml.predict(prompt))

    init_verdict = aggregate(results)

    if init_verdict == "block":
        return AskRes(verdict="block", response=None, evidence=results)

    # 2) call core
    response = core.generate(prompt)

    # 3) output LCEs
    out_res = output_rule.predict(response)
    results.append(out_res)
    final = aggregate(results)

    if should_escalate(results):
        # TODO: call stronger LCE / cross-correction
        pass

    if final == "block":
        return AskRes(verdict="block", response=None, evidence=results)
    elif final == "flag":
        return AskRes(verdict="flag", response=None, evidence=results)
    else:
        return AskRes(verdict="allow", response=response, evidence=results)