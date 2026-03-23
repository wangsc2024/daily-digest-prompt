#!/usr/bin/env python
"""
tools/score_skill_candidates.py
Behavior Pattern → Skill 演化候選評分工具（ADR-20260323-044）

使用方式：
    uv run python tools/score_skill_candidates.py
    uv run python tools/score_skill_candidates.py --top 10
    uv run python tools/score_skill_candidates.py --min-score 5.0
"""
from __future__ import annotations

import argparse
import json
import re
from datetime import datetime, timezone, timedelta
from pathlib import Path

# ──────────────────────────────────────────────
# Complexity helpers（v2 新增）
# ──────────────────────────────────────────────

_SIMPLE_BASH_PREFIXES = ("date ", "rm ", "mkdir ", "cat ", "echo ", "cp ", "mv ", "ls ", "pwd")
_HEALTH_CHECK_RE = re.compile(r"curl -s --max-time \d+ http://localhost:\d+/api/health")


def _is_complexity_excluded(pattern: dict) -> bool:
    """簡單 Bash 命令（無業務邏輯）→ True，應排除出 Skill 候選。"""
    if pattern.get("tool") != "Bash":
        return False
    s = str(pattern.get("summary_sample", ""))
    if any(s.startswith(p) for p in _SIMPLE_BASH_PREFIXES):
        return True
    if _HEALTH_CHECK_RE.search(s):
        return True
    # 短命令且無換行無管道 → 視為簡單命令
    if len(s) <= 80 and "|" not in s and "&&" not in s and "\\n" not in s and "\n" not in s:
        return True
    return False


def _score_complexity(pattern: dict) -> float:
    """計算 Bash 命令複雜度分數（0-3）。非 Bash 工具預設給 2 分（假設有業務邏輯）。"""
    if pattern.get("tool") != "Bash":
        return 2.0
    s = str(pattern.get("summary_sample", ""))
    pipes = s.count("|") + s.count("&&") + s.count(";")
    has_logic = any(k in s for k in ("if ", "for ", "while ", "pwsh", "\\n", "\n", "$env", "switch"))
    raw = pipes + (1 if has_logic else 0)
    if len(s) > 200 or raw >= 3:
        return 3.0
    if len(s) > 100 or raw >= 1:
        return 2.0
    if len(s) > 50:
        return 1.0
    return 0.0


# ──────────────────────────────────────────────
# Config
# ──────────────────────────────────────────────

def _load_config() -> dict:
    p = Path("config/skill-candidate-scoring.yaml")
    if not p.exists():
        raise FileNotFoundError(f"Config not found: {p}")
    import re
    text = p.read_text(encoding="utf-8")
    # Minimal YAML parsing for numeric thresholds
    cfg: dict = {}
    # Extract exclude_tools list（處理行尾註解）
    tools_match = re.search(r"exclude_tools:.*?\n((?:\s+- \w+.*?\n)+)", text)
    exclude_tools = []
    if tools_match:
        exclude_tools = re.findall(r"-\s+(\w+)", tools_match.group(1))

    # Extract thresholds
    def extract_thresholds(section: str) -> dict:
        t: dict = {}
        for m in re.finditer(r"(\w+):\s*([\d.]+)\s+#", section):
            t[m.group(1)] = float(m.group(2))
        return t

    cfg["exclude_tools"] = exclude_tools
    cfg["frequency_thresholds"] = extract_thresholds(
        text[text.find("  frequency:"):text.find("  confidence:")]
    )
    cfg["confidence_thresholds"] = extract_thresholds(
        text[text.find("  confidence:"):text.find("  reusability:")]
    )
    cfg["reusability_thresholds"] = extract_thresholds(
        text[text.find("  reusability:"):text.find("  complexity:")]
    )

    # Candidate thresholds
    def extract_val(key: str) -> float:
        m = re.search(rf"{key}:\s*([\d.]+)", text)
        return float(m.group(1)) if m else 0.0

    cfg["min_score"] = extract_val("min_score")
    cfg["min_confidence"] = extract_val("min_confidence")
    cfg["min_frequency"] = extract_val("min_frequency")
    cfg["min_complexity_score"] = extract_val("min_complexity_score")
    cfg["top_n"] = int(extract_val("top_n"))

    return cfg


# ──────────────────────────────────────────────
# Scoring
# ──────────────────────────────────────────────

def _score_frequency(count: int, thresholds: dict) -> float:
    if count >= thresholds.get("high", 500):
        return 3.0
    if count >= thresholds.get("medium", 100):
        return 2.0
    if count >= thresholds.get("low", 20):
        return 1.0
    return 0.0


def _score_confidence(conf: float, thresholds: dict) -> float:
    if conf >= thresholds.get("high", 0.85):
        return 3.0
    if conf >= thresholds.get("medium", 0.65):
        return 2.0
    if conf >= thresholds.get("low", 0.50):
        return 1.0
    return 0.0


def _score_reusability(count: int, conf: float, thresholds: dict) -> float:
    proxy = count * conf
    if proxy >= thresholds.get("high", 300):
        return 3.0
    if proxy >= thresholds.get("medium", 80):
        return 2.0
    if proxy >= thresholds.get("low", 20):
        return 1.0
    return 0.0


def score_pattern(pid: str, pattern: dict, cfg: dict) -> dict | None:
    tool = pattern.get("tool", "")
    if tool in cfg["exclude_tools"]:
        return None

    # v2: 複雜度排除（簡單 Bash 命令直接跳過）
    if _is_complexity_excluded(pattern):
        return None

    count = pattern.get("count", 0)
    conf = pattern.get("confidence", 0.0)
    success = pattern.get("success_count", 0)

    if count < cfg["min_frequency"] or conf < cfg["min_confidence"]:
        return None

    f_score = _score_frequency(count, cfg["frequency_thresholds"])
    c_score = _score_confidence(conf, cfg["confidence_thresholds"])
    r_score = _score_reusability(count, conf, cfg["reusability_thresholds"])
    cx_score = _score_complexity(pattern)

    # v2: 四維度加權（weights: 0.30, 0.25, 0.20, 0.25 → 乘以3讓總分與門檻6.0相容）
    total = f_score * 0.30 * 3 + c_score * 0.25 * 3 + r_score * 0.20 * 3 + cx_score * 0.25 * 3

    # 複雜度低於門檻直接排除
    min_cx = cfg.get("min_complexity_score", 0.0)
    if cx_score < min_cx:
        return None

    return {
        "pattern_id": pid,
        "tool": tool,
        "summary_sample": str(pattern.get("summary_sample", ""))[:80],
        "count": count,
        "confidence": round(conf, 3),
        "success_count": success,
        "scores": {
            "frequency": round(f_score, 2),
            "confidence": round(c_score, 2),
            "reusability": round(r_score, 2),
            "complexity": round(cx_score, 2),
            "total": round(total, 2),
        },
        "first_seen": pattern.get("first_seen", ""),
        "last_seen": pattern.get("last_seen", ""),
    }


# ──────────────────────────────────────────────
# Main
# ──────────────────────────────────────────────

def main() -> None:
    parser = argparse.ArgumentParser(description="Score Skill evolution candidates")
    parser.add_argument("--top", type=int, default=0, help="Override top_n from config")
    parser.add_argument("--min-score", type=float, default=0, help="Override min_score")
    args = parser.parse_args()

    cfg = _load_config()
    if args.top:
        cfg["top_n"] = args.top
    if args.min_score:
        cfg["min_score"] = args.min_score

    # Load behavior patterns
    bp_path = Path("context/behavior-patterns.json")
    if not bp_path.exists():
        print("ERROR: context/behavior-patterns.json not found")
        return

    bp = json.loads(bp_path.read_text(encoding="utf-8"))
    patterns = bp.get("patterns", {})
    if isinstance(patterns, list):
        patterns = {str(i): p for i, p in enumerate(patterns)}

    # Score each pattern
    candidates = []
    skipped_tool = skipped_threshold = 0
    for pid, pat in patterns.items():
        tool = pat.get("tool", "")
        if tool in cfg["exclude_tools"]:
            skipped_tool += 1
            continue
        result = score_pattern(pid, pat, cfg)
        if result is None:
            skipped_threshold += 1
            continue
        if result["scores"]["total"] >= cfg["min_score"]:
            candidates.append(result)

    # Sort by total score desc
    candidates.sort(key=lambda x: (-x["scores"]["total"], -x["count"]))
    top_candidates = candidates[: cfg["top_n"]]

    tz = timezone(timedelta(hours=8))
    output = {
        "agent": "score_skill_candidates",
        "generated_at": datetime.now(tz).isoformat(),
        "source": "context/behavior-patterns.json",
        "total_patterns": len(patterns),
        "skipped_tool_ops": skipped_tool,
        "skipped_below_threshold": skipped_threshold,
        "candidates_found": len(candidates),
        "top_n": cfg["top_n"],
        "min_score": cfg["min_score"],
        "candidates": top_candidates,
        "summary": (
            f"從 {len(patterns)} 個行為模式中識別 {len(candidates)} 個 Skill 候選，"
            f"前 {len(top_candidates)} 個得分 >= {cfg['min_score']}"
        ),
    }

    out_path = Path("analysis/skill-candidates.json")
    out_path.parent.mkdir(exist_ok=True)
    out_path.write_text(json.dumps(output, ensure_ascii=False, indent=2), encoding="utf-8")

    print(f"Total patterns: {len(patterns)}")
    print(f"Skipped (tool ops): {skipped_tool}")
    print(f"Skipped (below threshold): {skipped_threshold}")
    print(f"Candidates >= {cfg['min_score']}: {len(candidates)}")
    print()
    if top_candidates:
        print(f"Top {len(top_candidates)} candidates:")
        for c in top_candidates:
            s = c["scores"]
            print(
                f"  [{s['total']:.2f}] tool={c['tool']:20} cnt={c['count']:4d} "
                f"conf={c['confidence']:.2f} | {c['summary_sample'][:50]}"
            )
    else:
        print("No candidates found above threshold.")
        print("Top Bash patterns (any confidence):")
        bash_pats = [
            (pid, pat)
            for pid, pat in patterns.items()
            if pat.get("tool") == "Bash"
        ]
        bash_pats.sort(key=lambda x: -x[1].get("count", 0))
        for pid, pat in bash_pats[:5]:
            print(
                f"  cnt={pat.get('count',0):4d} conf={pat.get('confidence',0):.2f} "
                f"| {str(pat.get('summary_sample',''))[:60]}"
            )

    print(f"\nReport written: {out_path}")


if __name__ == "__main__":
    main()
