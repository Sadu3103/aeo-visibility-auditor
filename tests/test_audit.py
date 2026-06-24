import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

import audit

ALIASES = {"Northbeacon Analytics": ["Northbeacon"]}
BRANDS = ["Northbeacon Analytics", "Quanta BI", "Lumen Metrics", "Datapeak"]


def test_alias_match_counts_as_mention():
    answer = "Northbeacon leads on AI summaries; Quanta BI is close behind."
    result = audit.audit_prompt(answer, BRANDS, ALIASES)
    assert result["position"]["Northbeacon Analytics"] == 1
    assert result["position"]["Quanta BI"] == 2
    assert "Lumen Metrics" not in result["position"]


def test_ranking_follows_order_of_appearance():
    answer = "Datapeak and Lumen Metrics lead, then Quanta BI."
    order = audit.rank_brands(answer, BRANDS, ALIASES)
    assert order == ["Datapeak", "Lumen Metrics", "Quanta BI"]


def test_word_boundary_avoids_false_positive():
    answer = "Datapeaks of usage are common, but no analytics vendor named here."
    assert audit.find_first_mention(answer, ["Datapeak"]) is None


def test_score_reports_share_of_voice_and_blind_spots():
    results = [
        {"prompt": "a", "audit": audit.audit_prompt("Quanta BI and Datapeak.", BRANDS, ALIASES)},
        {"prompt": "b", "audit": audit.audit_prompt("Northbeacon and Lumen Metrics.", BRANDS, ALIASES)},
    ]
    scored = audit.score(results, BRANDS, "Northbeacon Analytics")
    assert scored["summary"]["Northbeacon Analytics"]["share_of_voice"] == 0.5
    assert scored["summary"]["Quanta BI"]["appearances"] == 1
    assert len(scored["blind_spots"]) == 1
    assert scored["blind_spots"][0]["prompt"] == "a"


def test_demo_run_is_deterministic():
    cfg = audit.load_config(os.path.join(os.path.dirname(__file__), "..", "config.example.json"))
    report = audit.run(cfg, "demo")
    assert report["summary"]["Northbeacon Analytics"]["share_of_voice"] == 0.4
    assert len(report["blind_spots"]) == 3


def _run():
    failures = 0
    for name, fn in sorted(globals().items()):
        if name.startswith("test_") and callable(fn):
            try:
                fn()
                print(f"PASS {name}")
            except AssertionError as exc:
                failures += 1
                print(f"FAIL {name}: {exc}")
    print(f"\n{'all tests passed' if not failures else str(failures) + ' failing'}")
    return 1 if failures else 0


if __name__ == "__main__":
    sys.exit(_run())
