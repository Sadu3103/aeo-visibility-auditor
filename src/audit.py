"""AEO visibility auditor.

Given a brand, its competitors, and a set of buyer intent prompts, ask an AI
assistant each prompt and measure how often (and how prominently) each brand
shows up in the answers. Output a share of voice report and the prompts where
the client brand is invisible but competitors are not (the content gaps worth
acting on).

Dependency free: standard library only. Runs offline with --demo, or live
against Anthropic or OpenAI with an API key in the environment.
"""

import argparse
import json
import os
import re
import sys
import urllib.error
import urllib.request
from datetime import datetime, timezone


def load_config(path):
    with open(path, "r", encoding="utf-8") as fh:
        cfg = json.load(fh)
    cfg.setdefault("aliases", {})
    cfg.setdefault("model", "")
    for key in ("client", "competitors", "prompts"):
        if not cfg.get(key):
            raise ValueError(f"config is missing required field: {key}")
    return cfg


def brand_aliases(brand, aliases):
    names = {brand}
    names.update(aliases.get(brand, []))
    return sorted(names, key=len, reverse=True)


def find_first_mention(answer, names):
    """Return the character index of the brand's first mention, or None."""
    lowered = answer.lower()
    earliest = None
    for name in names:
        pattern = r"\b" + re.escape(name.lower()) + r"\b"
        match = re.search(pattern, lowered)
        if match and (earliest is None or match.start() < earliest):
            earliest = match.start()
    return earliest


def rank_brands(answer, brands, aliases):
    """Order the brands by where they first appear in the answer."""
    hits = []
    for brand in brands:
        idx = find_first_mention(answer, brand_aliases(brand, aliases))
        if idx is not None:
            hits.append((idx, brand))
    hits.sort()
    return [brand for _, brand in hits]


def audit_prompt(answer, brands, aliases):
    order = rank_brands(answer, brands, aliases)
    position = {brand: rank for rank, brand in enumerate(order, start=1)}
    return {
        "mentioned": order,
        "position": position,
    }


def score(results, brands, client):
    total = len(results) or 1
    summary = {}
    for brand in brands:
        present = [r for r in results if brand in r["audit"]["position"]]
        ranks = [r["audit"]["position"][brand] for r in present]
        summary[brand] = {
            "share_of_voice": round(len(present) / total, 3),
            "appearances": len(present),
            "avg_rank": round(sum(ranks) / len(ranks), 2) if ranks else None,
        }
    blind_spots = [
        {
            "prompt": r["prompt"],
            "competitors_present": [b for b in r["audit"]["mentioned"] if b != client],
        }
        for r in results
        if client not in r["audit"]["position"]
        and any(b != client for b in r["audit"]["mentioned"])
    ]
    return {"summary": summary, "blind_spots": blind_spots}


def demo_answer(prompt, cfg):
    """Canned answers so the tool runs offline and deterministically."""
    p = prompt.lower()
    if "affordable" in p or "early stage" in p or "startup" in p:
        return ("For lean teams, Datapeak and Lumen Metrics are the usual picks "
                "because both have free tiers. Quanta BI is also worth a look.")
    if "enterprise" in p:
        return ("Enterprise buyers tend to shortlist Quanta BI and Lumen Metrics, "
                "with Datapeak showing up for security focused teams.")
    if "ai insights" in p or "ai" in p:
        return ("Northbeacon Analytics leads here, its AI summaries are strong. "
                "Quanta BI and Lumen Metrics have added similar features recently.")
    if "activation" in p or "retention" in p:
        return ("Lumen Metrics and Northbeacon Analytics are both built around "
                "activation and retention funnels. Datapeak covers the basics.")
    return ("The platforms that come up most often are Quanta BI, Lumen Metrics, "
            "and Datapeak. Each is strong for product analytics.")


def call_anthropic(prompt, model, api_key):
    body = json.dumps({
        "model": model or "claude-sonnet-4-6",
        "max_tokens": 600,
        "messages": [{"role": "user", "content": prompt}],
    }).encode("utf-8")
    req = urllib.request.Request(
        "https://api.anthropic.com/v1/messages",
        data=body,
        headers={
            "content-type": "application/json",
            "x-api-key": api_key,
            "anthropic-version": "2023-06-01",
        },
    )
    with urllib.request.urlopen(req, timeout=60) as resp:
        payload = json.loads(resp.read())
    return "".join(block.get("text", "") for block in payload.get("content", []))


def call_openai(prompt, model, api_key):
    body = json.dumps({
        "model": model or "gpt-4o-mini",
        "messages": [{"role": "user", "content": prompt}],
    }).encode("utf-8")
    req = urllib.request.Request(
        "https://api.openai.com/v1/chat/completions",
        data=body,
        headers={
            "content-type": "application/json",
            "authorization": f"Bearer {api_key}",
        },
    )
    with urllib.request.urlopen(req, timeout=60) as resp:
        payload = json.loads(resp.read())
    return payload["choices"][0]["message"]["content"]


def call_gemini(prompt, model, api_key):
    model_id = model or "gemini-1.5-flash"
    body = json.dumps({
        "contents": [{"parts": [{"text": prompt}]}],
        "generationConfig": {"maxOutputTokens": 600},
    }).encode("utf-8")
    url = (f"https://generativelanguage.googleapis.com/v1beta/models/"
           f"{model_id}:generateContent?key={api_key}")
    req = urllib.request.Request(
        url,
        data=body,
        headers={"content-type": "application/json"},
    )
    with urllib.request.urlopen(req, timeout=60) as resp:
        payload = json.loads(resp.read())
    return payload["candidates"][0]["content"]["parts"][0]["text"]


def get_answer(prompt, cfg, provider):
    if provider == "demo":
        return demo_answer(prompt, cfg)
    key_map = {"anthropic": "ANTHROPIC_API_KEY", "openai": "OPENAI_API_KEY", "gemini": "GEMINI_API_KEY"}
    key_env = key_map[provider]
    api_key = os.environ.get(key_env)
    if not api_key:
        raise SystemExit(f"set {key_env} in the environment, or run with --demo")
    caller = {"anthropic": call_anthropic, "openai": call_openai, "gemini": call_gemini}[provider]
    return caller(prompt, cfg.get("model", ""), api_key)


def run(cfg, provider):
    brands = [cfg["client"], *cfg["competitors"]]
    results = []
    for prompt in cfg["prompts"]:
        answer = get_answer(prompt, cfg, provider)
        results.append({
            "prompt": prompt,
            "answer": answer,
            "audit": audit_prompt(answer, brands, cfg["aliases"]),
        })
    scored = score(results, brands, cfg["client"])
    return {
        "generated_at": datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC"),
        "provider": provider,
        "client": cfg["client"],
        "competitors": cfg["competitors"],
        "prompts_audited": len(cfg["prompts"]),
        "summary": scored["summary"],
        "blind_spots": scored["blind_spots"],
        "detail": results,
    }


def render_markdown(report):
    client = report["client"]
    lines = [
        f"# AI Visibility Audit: {client}",
        "",
        f"Generated {report['generated_at']} via {report['provider']} over "
        f"{report['prompts_audited']} buyer intent prompts.",
        "",
        "## Share of voice",
        "",
        "| Brand | Share of voice | Appearances | Avg rank |",
        "| --- | --- | --- | --- |",
    ]
    ordered = sorted(
        report["summary"].items(),
        key=lambda kv: kv[1]["share_of_voice"],
        reverse=True,
    )
    for brand, stats in ordered:
        flag = " (you)" if brand == client else ""
        rank = stats["avg_rank"] if stats["avg_rank"] is not None else "n/a"
        lines.append(
            f"| {brand}{flag} | {int(stats['share_of_voice'] * 100)}% | "
            f"{stats['appearances']}/{report['prompts_audited']} | {rank} |"
        )
    lines += ["", "## Blind spots (act on these first)", ""]
    if not report["blind_spots"]:
        lines.append(f"{client} appeared in every audited answer. No blind spots.")
    else:
        lines.append(
            f"Prompts where {client} is absent but competitors are recommended:"
        )
        lines.append("")
        for spot in report["blind_spots"]:
            comps = ", ".join(spot["competitors_present"])
            lines.append(f"- **{spot['prompt']}** -> visible: {comps}")
    lines.append("")
    return "\n".join(lines)


def main(argv=None):
    parser = argparse.ArgumentParser(description="Audit AI answer visibility for a brand.")
    parser.add_argument("--config", default="config.example.json")
    parser.add_argument("--provider", choices=["demo", "anthropic", "openai", "gemini"], default="demo")
    parser.add_argument("--demo", action="store_true", help="force offline demo mode")
    parser.add_argument("--out-dir", default="examples")
    parser.add_argument("--quiet", action="store_true")
    args = parser.parse_args(argv)

    provider = "demo" if args.demo else args.provider
    cfg = load_config(args.config)
    report = run(cfg, provider)

    os.makedirs(args.out_dir, exist_ok=True)
    md = render_markdown(report)
    with open(os.path.join(args.out_dir, "sample-report.md"), "w", encoding="utf-8") as fh:
        fh.write(md)
    with open(os.path.join(args.out_dir, "sample-report.json"), "w", encoding="utf-8") as fh:
        json.dump(report, fh, indent=2)

    if not args.quiet:
        print(md)
    return 0


if __name__ == "__main__":
    sys.exit(main())
