#!/usr/bin/env python3
"""cache_eviction_benchmark.py - 快取驅逐策略 Benchmark（ADR-050）
比較 LRU / LFU / ARC 三種驅逐策略的命中率與元數據開銷。
使用專案實際快取存取模式模擬（從 behavior-patterns.json 讀取）。
"""
import json
import time
from pathlib import Path
from collections import OrderedDict, defaultdict
from dataclasses import dataclass, field
import argparse

PROJECT_ROOT = Path(__file__).parent.parent

# ─── 快取策略實作 ───────────────────────────────────────────

class LRUCache:
    """Least Recently Used 快取"""
    def __init__(self, capacity: int):
        self.capacity = capacity
        self.cache: OrderedDict = OrderedDict()
        self.hits = 0
        self.misses = 0

    def get(self, key: str) -> bool:
        if key in self.cache:
            self.cache.move_to_end(key)
            self.hits += 1
            return True
        self.misses += 1
        return False

    def put(self, key: str):
        if key in self.cache:
            self.cache.move_to_end(key)
        else:
            if len(self.cache) >= self.capacity:
                self.cache.popitem(last=False)
            self.cache[key] = True

    @property
    def metadata_overhead_bytes(self) -> int:
        """估算元數據開銷（每個 entry 約 80 bytes：key + OrderedDict node）"""
        return len(self.cache) * 80

    @property
    def hit_rate(self) -> float:
        total = self.hits + self.misses
        return self.hits / total if total > 0 else 0.0


class LFUCache:
    """Least Frequently Used 快取"""
    def __init__(self, capacity: int):
        self.capacity = capacity
        self.key_freq: dict = {}
        self.freq_keys: dict = defaultdict(OrderedDict)
        self.min_freq = 0
        self.hits = 0
        self.misses = 0

    def get(self, key: str) -> bool:
        if key not in self.key_freq:
            self.misses += 1
            return False
        self._increment_freq(key)
        self.hits += 1
        return True

    def put(self, key: str):
        if self.capacity <= 0:
            return
        if key in self.key_freq:
            self._increment_freq(key)
            return
        if len(self.key_freq) >= self.capacity:
            self._evict()
        self.key_freq[key] = 1
        self.freq_keys[1][key] = True
        self.min_freq = 1

    def _increment_freq(self, key: str):
        freq = self.key_freq[key]
        del self.freq_keys[freq][key]
        if not self.freq_keys[freq] and freq == self.min_freq:
            self.min_freq += 1
        self.key_freq[key] = freq + 1
        self.freq_keys[freq + 1][key] = True

    def _evict(self):
        evict_key = next(iter(self.freq_keys[self.min_freq]))
        del self.freq_keys[self.min_freq][evict_key]
        del self.key_freq[evict_key]

    @property
    def metadata_overhead_bytes(self) -> int:
        """LFU 需維護頻率計數，額外 ~120 bytes per entry"""
        return len(self.key_freq) * 120

    @property
    def hit_rate(self) -> float:
        total = self.hits + self.misses
        return self.hits / total if total > 0 else 0.0


class ARCCache:
    """Adaptive Replacement Cache（IBM Research, 2003）
    維護 T1（最近使用）、T2（頻繁使用）、B1（T1 ghost）、B2（T2 ghost）四個列表。
    動態調整 T1/T2 邊界 p，適應工作負載特性。
    """
    def __init__(self, capacity: int):
        self.c = capacity
        self.p = 0  # T1 目標大小
        self.t1: OrderedDict = OrderedDict()  # 最近一次使用
        self.t2: OrderedDict = OrderedDict()  # 最近多次使用
        self.b1: OrderedDict = OrderedDict()  # T1 ghost（已驅逐，僅保留 key）
        self.b2: OrderedDict = OrderedDict()  # T2 ghost（已驅逐，僅保留 key）
        self.hits = 0
        self.misses = 0

    def get(self, key: str) -> bool:
        if key in self.t1 or key in self.t2:
            # Cache hit
            if key in self.t1:
                del self.t1[key]
            else:
                del self.t2[key]
            self.t2[key] = True  # 移入 T2（頻繁使用）
            self.hits += 1
            return True
        self.misses += 1
        return False

    def put(self, key: str):
        if key in self.t1 or key in self.t2:
            return  # 已在快取中（get 處理）

        if key in self.b1:
            # B1 ghost hit：增加 T1 目標大小
            delta = max(1, len(self.b2) // max(len(self.b1), 1))
            self.p = min(self.p + delta, self.c)
            del self.b1[key]
            self._replace(key, in_t2=True)
            return

        if key in self.b2:
            # B2 ghost hit：減少 T1 目標大小
            delta = max(1, len(self.b1) // max(len(self.b2), 1))
            self.p = max(self.p - delta, 0)
            del self.b2[key]
            self._replace(key, in_t2=True)
            return

        # 完全 miss：放入 T1
        total = len(self.t1) + len(self.t2)
        if total >= self.c:
            if len(self.t1) < self.c:
                if len(self.b1) > 0:
                    # 移除 B1 最舊項目
                    self.b1.popitem(last=False)
                self._replace(key, in_t2=False)
            else:
                # T1 + B1 >= c
                if len(self.t1) + len(self.b1) >= self.c:
                    if len(self.b1) > 0:
                        self.b1.popitem(last=False)
                self._replace(key, in_t2=False)
        else:
            total_all = len(self.t1) + len(self.b1) + len(self.t2) + len(self.b2)
            if total_all >= self.c:
                if total_all >= 2 * self.c and len(self.b2) > 0:
                    self.b2.popitem(last=False)

        self.t1[key] = True

    def _replace(self, key: str, in_t2: bool):
        t1_size = len(self.t1)
        if t1_size > 0 and (t1_size > self.p or (in_t2 and t1_size == self.p)):
            # 從 T1 驅逐到 B1
            evicted = next(iter(self.t1))
            del self.t1[evicted]
            self.b1[evicted] = True
        elif len(self.t2) > 0:
            # 從 T2 驅逐到 B2
            evicted = next(iter(self.t2))
            del self.t2[evicted]
            self.b2[evicted] = True

        if in_t2:
            self.t2[key] = True
        else:
            self.t1[key] = True

    @property
    def metadata_overhead_bytes(self) -> int:
        """ARC 維護 4 個列表 + p 值，約 ~200 bytes per entry"""
        total_keys = len(self.t1) + len(self.t2) + len(self.b1) + len(self.b2)
        return total_keys * 200 + 8  # +8 for p value

    @property
    def hit_rate(self) -> float:
        total = self.hits + self.misses
        return self.hits / total if total > 0 else 0.0


# ─── 工作負載生成 ────────────────────────────────────────────

def load_workload_from_behavior_patterns(max_requests: int = 10000) -> list:
    """從 behavior-patterns.json 建立快取存取序列"""
    bp_path = PROJECT_ROOT / "context" / "behavior-patterns.json"
    workload = []

    if bp_path.exists():
        try:
            with open(bp_path, encoding="utf-8") as f:
                raw = json.load(f)

            # behavior-patterns.json 結構：{"version": N, "patterns": {id: {...}}, ...}
            if isinstance(raw, dict) and "patterns" in raw:
                patterns_data = raw["patterns"]
                entries = list(patterns_data.values()) if isinstance(patterns_data, dict) else patterns_data
            elif isinstance(raw, list):
                entries = raw
            else:
                entries = list(raw.values())

            for entry in entries:
                if not isinstance(entry, dict):
                    continue
                key = entry.get("summary_sample", entry.get("tool", "unknown"))[:50]
                count = min(entry.get("count", 1), 500)  # 限制單一 key 重複次數
                workload.extend([key] * count)
                if len(workload) >= max_requests * 2:
                    break
        except Exception:
            pass

    # 若無 behavior-patterns，生成合成工作負載（混合 LRU/LFU 模式）
    if not workload:
        import random
        random.seed(42)
        # 熱點 key（20% key，80% 存取）
        hot_keys = [f"hot_{i}" for i in range(20)]
        cold_keys = [f"cold_{i}" for i in range(80)]
        for _ in range(max_requests):
            if random.random() < 0.80:
                workload.append(random.choice(hot_keys))
            else:
                workload.append(random.choice(cold_keys))

    # 截斷並打亂（保留局部性）
    if len(workload) > max_requests:
        workload = workload[:max_requests]

    return workload


def run_benchmark(capacity: int = 50, max_requests: int = 5000) -> dict:
    """執行三種策略 benchmark"""
    workload = load_workload_from_behavior_patterns(max_requests)

    strategies = {
        "LRU": LRUCache(capacity),
        "LFU": LFUCache(capacity),
        "ARC": ARCCache(capacity),
    }

    results = {}

    for name, cache in strategies.items():
        start_time = time.perf_counter()

        for key in workload:
            if not cache.get(key):
                cache.put(key)

        elapsed_ms = (time.perf_counter() - start_time) * 1000

        results[name] = {
            "hit_rate": round(cache.hit_rate, 4),
            "hits": cache.hits,
            "misses": cache.misses,
            "total_requests": len(workload),
            "metadata_overhead_bytes": cache.metadata_overhead_bytes,
            "elapsed_ms": round(elapsed_ms, 2),
        }

    # 計算 ARC 相對 LRU/LFU 提升
    arc_rate = results["ARC"]["hit_rate"]
    lru_rate = results["LRU"]["hit_rate"]
    lfu_rate = results["LFU"]["hit_rate"]

    results["_summary"] = {
        "capacity": capacity,
        "total_requests": len(workload),
        "arc_vs_lru_improvement": round(arc_rate - lru_rate, 4),
        "arc_vs_lfu_improvement": round(arc_rate - lfu_rate, 4),
        "recommendation": _make_recommendation(arc_rate, lru_rate, lfu_rate, results),
        "workload_source": "behavior-patterns.json" if (PROJECT_ROOT / "context" / "behavior-patterns.json").exists() else "synthetic",
    }

    return results


def _make_recommendation(arc_rate: float, lru_rate: float, lfu_rate: float, results: dict) -> str:
    arc_overhead = results["ARC"]["metadata_overhead_bytes"]
    best_simple = max(lru_rate, lfu_rate)
    improvement = arc_rate - best_simple

    if improvement > 0.05:
        return f"推薦 ARC：命中率提升 {improvement:.1%}，元數據開銷 {arc_overhead//1024}KB（可接受）"
    elif improvement > 0.02:
        return f"輕微推薦 ARC：命中率提升 {improvement:.1%}，需評估 {arc_overhead//1024}KB 元數據開銷是否值得"
    else:
        best = "LRU" if lru_rate >= lfu_rate else "LFU"
        return f"維持 {best}：ARC 提升不顯著（{improvement:.1%}），避免元數據開銷 {arc_overhead//1024}KB"


def main():
    parser = argparse.ArgumentParser(description="快取驅逐策略 Benchmark（LRU/LFU/ARC）")
    parser.add_argument("--capacity", type=int, default=50, help="快取容量（預設 50）")
    parser.add_argument("--requests", type=int, default=5000, help="模擬請求數（預設 5000）")
    parser.add_argument("--json", action="store_true", help="輸出 JSON")
    parser.add_argument("--save", action="store_true", help="儲存結果至 analysis/cache-eviction-comparison.json")
    args = parser.parse_args()

    print(f"執行 benchmark（capacity={args.capacity}, requests={args.requests}）...")
    results = run_benchmark(capacity=args.capacity, max_requests=args.requests)

    if args.save:
        output_path = PROJECT_ROOT / "analysis" / "cache-eviction-comparison.json"
        output_path.parent.mkdir(exist_ok=True)
        with open(output_path, "w", encoding="utf-8") as f:
            json.dump({
                "generated_at": __import__("datetime").datetime.now().isoformat(),
                "benchmark_config": {"capacity": args.capacity, "requests": args.requests},
                "results": results,
            }, f, ensure_ascii=False, indent=2)
        print(f"已儲存至 {output_path}")

    if args.json:
        print(json.dumps(results, ensure_ascii=False, indent=2))
        return

    print(f"\n=== 快取驅逐策略 Benchmark ===")
    print(f"工作負載來源：{results['_summary']['workload_source']}")
    print(f"請求數：{results['_summary']['total_requests']}, 容量：{results['_summary']['capacity']}\n")

    for strategy in ["LRU", "LFU", "ARC"]:
        r = results[strategy]
        print(f"{strategy:4s}: 命中率 {r['hit_rate']:.1%}  "
              f"hits={r['hits']:5d}  "
              f"metadata={r['metadata_overhead_bytes']//1024:4d}KB  "
              f"time={r['elapsed_ms']:.1f}ms")

    s = results["_summary"]
    print(f"\nARC vs LRU: {s['arc_vs_lru_improvement']:+.1%}")
    print(f"ARC vs LFU: {s['arc_vs_lfu_improvement']:+.1%}")
    print(f"\n建議：{s['recommendation']}")

if __name__ == "__main__":
    main()
