"""
Research Saturation Analyzer (ADR-039)

Reads context/research-registry.json, clusters topics by keyword overlap,
calculates saturation scores, and outputs:
  - analysis/research-topic-clusters.json
  - analysis/high-potential-topics.json
Also updates context/research-series.json with saturation scores.

Usage:
    uv run python tools/research_saturation_analyzer.py
"""

from __future__ import annotations

import json
import re
from collections import Counter
from datetime import datetime
from pathlib import Path

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------
PROJECT_ROOT = Path(__file__).resolve().parent.parent
REGISTRY_PATH = PROJECT_ROOT / "context" / "research-registry.json"
SERIES_PATH = PROJECT_ROOT / "context" / "research-series.json"
ANALYSIS_DIR = PROJECT_ROOT / "analysis"
CLUSTERS_OUT = ANALYSIS_DIR / "research-topic-clusters.json"
HIGH_POTENTIAL_OUT = ANALYSIS_DIR / "high-potential-topics.json"

# Saturation formula weights
W_COUNT = 0.4
W_NOVELTY = 0.3  # applied as (1 - novelty)
W_TIME = 0.2
W_DEPTH = 0.1  # applied as (1 - depth)

SATURATED_THRESHOLD = 0.7
NEEDS_DEEPENING_THRESHOLD = 0.3

# Chinese / English stopwords (minimal set, good enough for clustering)
STOPWORDS: set[str] = {
    # English
    "the", "a", "an", "and", "or", "of", "in", "on", "to", "for", "with",
    "is", "are", "was", "were", "be", "been", "at", "by", "from", "as",
    "it", "its", "this", "that", "vs", "via",
    # Chinese particles / common chars
    "的", "與", "和", "在", "從", "到", "了", "是", "為", "之",
    "及", "對", "於", "等", "中", "上", "下", "也", "而", "或",
    # Domain-generic terms that add noise
    "研究", "深度", "報告", "分析", "指南", "實踐", "框架", "系統",
    "完整", "進階", "最佳", "實作", "方法論", "綜論", "深度研究",
}

TODAY = datetime.now().date()


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _tokenize(text: str) -> list[str]:
    """Split text into keyword tokens (Chinese chars kept as-is, ASCII lowered)."""
    # Split on common delimiters
    parts = re.split(r"[\s\-—–—:：、,，.。/（）()「」《》\[\]]+", text)
    tokens = []
    for p in parts:
        p = p.strip().lower()
        if len(p) < 2:
            continue
        if p in STOPWORDS:
            continue
        tokens.append(p)
    return tokens


def _keyword_set(text: str) -> set[str]:
    return set(_tokenize(text))


def _jaccard(a: set[str], b: set[str]) -> float:
    if not a or not b:
        return 0.0
    return len(a & b) / len(a | b)


def _parse_date(d: str | None) -> datetime | None:
    if not d:
        return None
    try:
        return datetime.fromisoformat(d.replace("Z", "+00:00"))
    except (ValueError, TypeError):
        pass
    # Try date-only
    for fmt in ("%Y-%m-%d",):
        try:
            return datetime.strptime(d, fmt)
        except ValueError:
            continue
    return None


# ---------------------------------------------------------------------------
# Core logic
# ---------------------------------------------------------------------------

def load_registry() -> dict:
    with open(REGISTRY_PATH, "r", encoding="utf-8") as f:
        return json.load(f)


def load_series() -> dict:
    with open(SERIES_PATH, "r", encoding="utf-8") as f:
        return json.load(f)


def build_topic_stats(entries: list[dict]) -> dict[str, dict]:
    """
    Aggregate entries into topic clusters.
    Returns {cluster_label: {keywords, count, last_date, dates, word_count, entries}}.
    """
    # Step 1: compute keyword sets per entry
    entry_kws: list[tuple[dict, set[str]]] = []
    for e in entries:
        topic = e.get("topic", "")
        tags = e.get("tags", [])
        combined = topic + " " + " ".join(tags)
        kws = _keyword_set(combined)
        entry_kws.append((e, kws))

    # Step 2: greedy clustering by Jaccard overlap
    clusters: list[dict] = []
    assigned = [False] * len(entry_kws)

    for i, (entry_i, kws_i) in enumerate(entry_kws):
        if assigned[i]:
            continue
        cluster = {
            "label": entry_i.get("topic", "unknown")[:80],
            "keywords": set(kws_i),
            "entries": [entry_i],
            "dates": [],
            "word_count": 0,
        }
        d = _parse_date(entry_i.get("date"))
        if d:
            cluster["dates"].append(d)
        cluster["word_count"] += len(entry_i.get("topic", ""))
        assigned[i] = True

        for j, (entry_j, kws_j) in enumerate(entry_kws):
            if assigned[j]:
                continue
            sim = _jaccard(kws_i, kws_j)
            if sim >= 0.25:
                cluster["entries"].append(entry_j)
                cluster["keywords"] |= kws_j
                dj = _parse_date(entry_j.get("date"))
                if dj:
                    cluster["dates"].append(dj)
                cluster["word_count"] += len(entry_j.get("topic", ""))
                assigned[j] = True

        clusters.append(cluster)

    # Step 3: build stats dict keyed by a cleaned label
    stats: dict[str, dict] = {}
    for c in clusters:
        label = c["label"]
        dates_sorted = sorted(c["dates"]) if c["dates"] else []
        last_date = dates_sorted[-1] if dates_sorted else None
        first_date = dates_sorted[0] if dates_sorted else None
        stats[label] = {
            "keywords": sorted(c["keywords"]),
            "count": len(c["entries"]),
            "first_date": first_date.strftime("%Y-%m-%d") if first_date else None,
            "last_date": last_date.strftime("%Y-%m-%d") if last_date else None,
            "word_count": c["word_count"],
            "entry_topics": [e.get("topic", "") for e in c["entries"]],
        }
    return stats


def compute_saturation(stats: dict[str, dict], all_stats: dict[str, dict]) -> dict[str, dict]:
    """
    Compute saturation_score for each cluster.

    saturation_score = count×0.4 + (1-novelty)×0.3 + time_interval×0.2 + (1-depth)×0.1

    Where:
    - count_norm: min(count / max_count, 1.0)
    - novelty: ratio of unique keywords vs total keywords across all clusters
      (higher = more novel = less saturated)
    - time_interval_norm: how recently researched (1.0 = researched today, 0.0 = old)
    - depth: word_count / max_word_count (proxy for thoroughness)
    """
    if not stats:
        return {}

    max_count = max(s["count"] for s in stats.values()) or 1
    max_word = max(s["word_count"] for s in stats.values()) or 1

    # Build global keyword frequency for novelty calculation
    global_kw_freq: Counter = Counter()
    for s in stats.values():
        global_kw_freq.update(s["keywords"])

    results = {}
    for label, s in stats.items():
        # count_norm
        count_norm = min(s["count"] / max_count, 1.0)

        # novelty: fraction of keywords that are unique (freq==1) to this cluster
        kws = s["keywords"]
        if kws:
            unique_ratio = sum(1 for k in kws if global_kw_freq[k] == 1) / len(kws)
        else:
            unique_ratio = 0.5
        novelty = unique_ratio

        # time_interval: days since last research (0 = today → interval_norm = 1.0)
        if s["last_date"]:
            try:
                last = datetime.strptime(s["last_date"], "%Y-%m-%d").date()
                days_ago = (TODAY - last).days
            except ValueError:
                days_ago = 30
        else:
            days_ago = 30
        # Decay: 1.0 for today, 0.0 for 30+ days ago
        time_interval_norm = max(0.0, 1.0 - days_ago / 30.0)

        # depth
        depth = min(s["word_count"] / max_word, 1.0)

        score = (
            W_COUNT * count_norm
            + W_NOVELTY * (1.0 - novelty)
            + W_TIME * time_interval_norm
            + W_DEPTH * (1.0 - depth)
        )
        score = round(score, 4)

        status = "saturated" if score > SATURATED_THRESHOLD else (
            "needs-deepening" if score < NEEDS_DEEPENING_THRESHOLD else "normal"
        )

        results[label] = {
            **s,
            "saturation_score": score,
            "status": status,
            "factors": {
                "count_norm": round(count_norm, 4),
                "novelty": round(novelty, 4),
                "time_interval_norm": round(time_interval_norm, 4),
                "depth": round(depth, 4),
            },
        }
    return results


def extract_high_potential(scored: dict[str, dict]) -> list[dict]:
    """
    High-potential topics: needs-deepening (low saturation) or
    moderate saturation with high novelty.
    """
    candidates = []
    for label, s in scored.items():
        if s["status"] == "needs-deepening":
            candidates.append({
                "topic": label,
                "saturation_score": s["saturation_score"],
                "status": s["status"],
                "count": s["count"],
                "last_date": s["last_date"],
                "reason": "low saturation — topic has room for deeper exploration",
            })
        elif s["status"] == "normal" and s["factors"]["novelty"] > 0.5:
            candidates.append({
                "topic": label,
                "saturation_score": s["saturation_score"],
                "status": "high-novelty",
                "count": s["count"],
                "last_date": s["last_date"],
                "reason": "moderate saturation but high novelty keywords — unique angle",
            })

    # Sort by saturation ascending (most room for growth first)
    candidates.sort(key=lambda x: x["saturation_score"])
    return candidates


def update_research_series(series_data: dict, scored: dict[str, dict]) -> dict:
    """
    Add saturation_score to each series in research-series.json by matching
    series tags/domain against cluster keywords.
    """
    series = series_data.get("series", {})
    for sid, s_info in series.items():
        s_tags = set(t.lower() for t in s_info.get("tags", []))
        s_domain_kws = _keyword_set(s_info.get("domain", "") + " " + s_info.get("description", ""))
        s_all_kws = s_tags | s_domain_kws

        best_score = None
        best_label = None
        for label, sc in scored.items():
            cluster_kws = set(k.lower() for k in sc.get("keywords", []))
            overlap = _jaccard(s_all_kws, cluster_kws)
            if overlap > 0.15 and (best_score is None or sc["saturation_score"] > best_score):
                best_score = sc["saturation_score"]
                best_label = label

        if best_score is not None:
            s_info["saturation_score"] = best_score
            s_info["saturation_matched_cluster"] = best_label
        else:
            # No match: estimate from completion_pct
            pct = s_info.get("completion_pct", 0)
            s_info["saturation_score"] = round(pct / 100.0 * 0.5, 4)
            s_info["saturation_matched_cluster"] = None

    series_data["updated_at"] = datetime.now().astimezone().isoformat()
    return series_data


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main():
    print("[research_saturation_analyzer] Loading research-registry.json ...")
    registry = load_registry()
    entries = registry.get("entries", [])
    print(f"  Found {len(entries)} entries")

    print("[research_saturation_analyzer] Building topic clusters ...")
    stats = build_topic_stats(entries)
    print(f"  Built {len(stats)} clusters")

    print("[research_saturation_analyzer] Computing saturation scores ...")
    scored = compute_saturation(stats, stats)

    # Summaries
    saturated = [label for label, s in scored.items() if s["status"] == "saturated"]
    needs_deep = [label for label, s in scored.items() if s["status"] == "needs-deepening"]
    print(f"  Saturated: {len(saturated)}, Needs-deepening: {len(needs_deep)}, Normal: {len(scored) - len(saturated) - len(needs_deep)}")

    # High-potential topics
    high_potential = extract_high_potential(scored)
    print(f"  High-potential topics: {len(high_potential)}")

    # Ensure output directory
    ANALYSIS_DIR.mkdir(parents=True, exist_ok=True)

    # Write clusters
    clusters_output = {
        "generated_at": datetime.now().astimezone().isoformat(),
        "total_entries": len(entries),
        "total_clusters": len(scored),
        "summary": {
            "saturated_count": len(saturated),
            "needs_deepening_count": len(needs_deep),
            "normal_count": len(scored) - len(saturated) - len(needs_deep),
        },
        "clusters": scored,
    }
    with open(CLUSTERS_OUT, "w", encoding="utf-8") as f:
        json.dump(clusters_output, f, ensure_ascii=False, indent=2)
    print(f"  Written: {CLUSTERS_OUT}")

    # Write high-potential
    hp_output = {
        "generated_at": datetime.now().astimezone().isoformat(),
        "total_high_potential": len(high_potential),
        "topics": high_potential,
    }
    with open(HIGH_POTENTIAL_OUT, "w", encoding="utf-8") as f:
        json.dump(hp_output, f, ensure_ascii=False, indent=2)
    print(f"  Written: {HIGH_POTENTIAL_OUT}")

    # Update research-series.json
    print("[research_saturation_analyzer] Updating research-series.json ...")
    series_data = load_series()
    updated_series = update_research_series(series_data, scored)
    with open(SERIES_PATH, "w", encoding="utf-8") as f:
        json.dump(updated_series, f, ensure_ascii=False, indent=2)
    print(f"  Updated: {SERIES_PATH}")

    print("[research_saturation_analyzer] Done.")


if __name__ == "__main__":
    main()
