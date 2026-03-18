from scripts.long_term_memory_perf import (
    run_million_scale_retrieval_benchmark,
    run_performance_test,
)


def test_long_term_memory_performance_stays_under_200ms():
    report = run_performance_test(summary_count=100)

    assert report["summary_count"] == 100
    assert report["write_p95_ms"] <= 200
    assert report["search_p95_ms"] <= 200
    assert report["within_200ms"] is True


def test_million_scale_retrieval_benchmark_stays_under_200ms():
    report = run_million_scale_retrieval_benchmark(record_count=1_000_000, hot_bucket_size=256)

    assert report["record_count"] == 1_000_000
    assert report["candidate_count"] > 0
    assert report["search_p95_ms"] <= 200
    assert report["within_200ms"] is True
