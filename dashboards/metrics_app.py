# dashboards/metrics_app.py
# 실행: streamlit run dashboards/metrics_app.py
from __future__ import annotations
import json, glob, os
from pathlib import Path
from typing import Dict, Any, List, Optional

import pandas as pd
import streamlit as st

RESULTS_DIR = Path("results")
ABLATION_DIR = RESULTS_DIR / "ablation"

METRIC_KEYS = [
    "precision", "recall", "f1_score", "bypass_rate",
    "alignment_success_rate", "latency_ms"
]

def load_json(path: Path) -> Optional[Dict[str, Any]]:
    try:
        with open(path, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return None

def load_metrics() -> pd.DataFrame:
    rows: List[Dict[str, Any]] = []

    # 1) 단일 최신 결과
    m = load_json(RESULTS_DIR / "metrics.json")
    if m:
        rows.append({"exp": "current", **{k: m.get(k) for k in METRIC_KEYS}})

    # 2) ablation 결과들
    for p in sorted(glob.glob(str(ABLATION_DIR / "metrics_*.json"))):
        name = Path(p).stem.replace("metrics_", "")
        m = load_json(Path(p))
        if not m: 
            continue
        rows.append({"exp": name, **{k: m.get(k) for k in METRIC_KEYS}})

    df = pd.DataFrame(rows)
    if not df.empty:
        # 숫자형 보정
        for k in METRIC_KEYS:
            if k in df.columns:
                df[k] = pd.to_numeric(df[k], errors="coerce")
    return df

def load_cases() -> pd.DataFrame:
    path = RESULTS_DIR / "cases.jsonl"
    if not path.exists(): 
        return pd.DataFrame()
    rows = []
    with open(path, "r", encoding="utf-8") as f:
        for line in f:
            line=line.strip()
            if not line: 
                continue
            try:
                rows.append(json.loads(line))
            except Exception:
                continue
    return pd.DataFrame(rows)

def main():
    st.set_page_config(page_title="RecurDefend: Metrics Dashboard", layout="wide")
    st.title("🛡️ RecurDefend — Evaluation Dashboard")
    st.caption("Recursive CoT & Cross-Correction Against IPI, Deep Defense Framework for LLaMA3")

    # 사이드바
    st.sidebar.header("Options")
    show_latency = st.sidebar.checkbox("Show Latency (ms)", value=True)
    show_alignment = st.sidebar.checkbox("Show Alignment Success", value=True)
    st.sidebar.markdown("---")
    st.sidebar.write("**Data folders**")
    st.sidebar.code(f"results/\nresults/ablation/")

    # 메트릭 로딩
    df = load_metrics()
    if df.empty:
        st.warning("결과 파일이 없습니다. 먼저 `src/evaluation/evaluate.py` 또는 `scripts/run_eval_ablation.sh`를 실행하세요.")
        st.stop()

    # 표시 메트릭 선택
    base_metrics = ["precision", "recall", "f1_score", "bypass_rate"]
    extra = []
    if show_alignment: extra.append("alignment_success_rate")
    if show_latency: extra.append("latency_ms")
    cols = base_metrics + extra
    cols = [c for c in cols if c in df.columns]

    st.subheader("📊 Metrics Table")
    st.dataframe(df.set_index("exp")[cols].sort_index(), use_container_width=True)

    # 시각화
    st.subheader("📈 Metric Comparison")
    selected_metric = st.selectbox("Select metric to plot", cols, index=cols.index("f1_score") if "f1_score" in cols else 0)
    plot_df = df[["exp", selected_metric]].sort_values(selected_metric, ascending=(selected_metric=="bypass_rate"))
    st.bar_chart(plot_df.set_index("exp"))

    # 2축: 품질(F1) vs 비용(Latency)
    if "f1_score" in df.columns and "latency_ms" in df.columns:
        st.subheader("⚖️ Quality vs Latency")
        scatter = df[["exp", "f1_score", "latency_ms"]].dropna()
        if not scatter.empty:
            st.scatter_chart(scatter, x="latency_ms", y="f1_score", color="exp", size=None)
        else:
            st.info("f1_score 또는 latency_ms 데이터가 부족합니다.")

    # 세부 케이스
    st.subheader("🧪 Cases (latest run)")
    cases = load_cases()
    if not cases.empty:
        # 간단 필터
        status_opt = st.multiselect("Filter by status", options=sorted(cases["status"].unique()), default=list(cases["status"].unique()))
        st.dataframe(cases[cases["status"].isin(status_opt)].reset_index(drop=True), use_container_width=True)
    else:
        st.info("`results/cases.jsonl`이 없습니다. 배치 평가를 먼저 실행하세요.")

    st.markdown("---")
    st.caption("Tips: `scripts/run_eval_ablation.sh`로 다양한 설정을 자동 평가하고, 이 화면에서 비교하세요.")

if __name__ == "__main__":
    main()
