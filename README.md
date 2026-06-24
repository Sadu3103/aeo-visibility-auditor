# AEO Visibility Auditor

Buyers now ask ChatGPT, Gemini, Claude, and Perplexity questions like "best B2B
product analytics platforms" before they ever land on a website. Answer Engine
Optimization (AEO) is about whether your brand shows up in those answers. This
tool measures it.

Give it a brand, its competitors, and a list of buyer intent prompts. It asks an
AI assistant each prompt, reads the answers, and reports:

- **Share of voice** per brand: how often each one appears across the answers, and how high up.
- **Blind spots**: the prompts where your brand is missing but competitors are recommended. Those are the content gaps worth acting on first.

It ships two ways to run the same logic: a dependency free Python engine (tested,
runs offline) and an n8n workflow (the same audit as a no code automation a team
can trigger on a schedule).

## Quickstart

No API key needed. The demo uses bundled answers so the output is deterministic:

```bash
python3 src/audit.py --demo
```

This writes `examples/sample-report.md` and `examples/sample-report.json`. Here is
the demo result:

```
| Brand                         | Share of voice | Appearances | Avg rank |
| ---                           | ---            | ---         | ---      |
| Lumen Metrics                 | 100%           | 5/5         | 2.0      |
| Quanta BI                     | 80%            | 4/5         | 1.75     |
| Datapeak                      | 80%            | 4/5         | 2.5      |
| Northbeacon Analytics (you)   | 40%            | 2/5         | 1.5      |
```

Northbeacon is invisible for three of five buyer intent prompts (general "best
platforms", "affordable for startups", and "enterprise grade") while every
competitor shows up. Those three prompts are the audit's recommended priorities.

## Run it live

Point it at a real model. Set a key and pick a provider:

```bash
export ANTHROPIC_API_KEY=sk-...        # or OPENAI_API_KEY or GEMINI_API_KEY
python3 src/audit.py --provider anthropic --config config.example.json
python3 src/audit.py --provider gemini  --config config.example.json
python3 src/audit.py --provider openai  --config config.example.json
```

Edit `config.example.json` to audit your own brand:

```json
{
  "client": "Your Brand",
  "competitors": ["Rival A", "Rival B"],
  "aliases": { "Your Brand": ["Brand Inc", "YourBrand"] },
  "prompts": ["best ... for ...", "top ... tools", "..."]
}
```

## Run it in n8n

`workflow/ai-visibility-audit.json` is the same audit as an n8n workflow:

`Run audit -> Build audit items -> Ask AI assistant -> Score mentions -> Aggregate share of voice`

1. In n8n, choose Import from File and select the JSON.
2. Add an HTTP Header Auth credential named `x-api-key` holding your Anthropic key, and attach it to the **Ask AI assistant** node.
3. Edit the brand, competitors, and prompts in the **Build audit items** node, then run.

The Code nodes carry the same mention detection and scoring as the Python engine,
so both paths produce the same numbers.

## How scoring works

- An answer "mentions" a brand when the brand name (or one of its aliases) appears as a whole word. Matching normalizes punctuation so `Quanta BI.` and `Quanta-BI` both count, and substrings like `Datapeaks` do not produce a false positive.
- **Rank** is the order of first appearance inside a single answer. Appearing first is stronger than appearing last.
- **Share of voice** is the fraction of audited prompts where the brand appears at all.
- A **blind spot** is any prompt where the client brand is absent but at least one competitor is present.

## Tests

```bash
python3 tests/test_audit.py
```

Covers alias matching, appearance ranking, the word boundary guard against false
positives, share of voice math, and a deterministic end to end demo run.

## Layout

```
src/audit.py                     engine: query, detect, score, render
config.example.json              brand, competitors, aliases, prompts
workflow/ai-visibility-audit.json  the same audit as an n8n workflow
examples/                        generated sample report (md + json)
tests/test_audit.py              dependency free test suite
```

Built by Samuel Adu.
