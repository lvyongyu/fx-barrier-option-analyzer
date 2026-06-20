# AI Agent Plan

## Purpose

The AI agent layer should make the analyzer easier to use and harder to misuse.
It should not replace the deterministic probability engine.

Core principle:

```text
Deterministic models calculate probabilities.
AI agents parse, critique, explain, and write analyst-style output.
```

This keeps the system auditable. If a probability looks wrong, we can trace it
back to market data, parameters, model assumptions, and calibration metrics
instead of an opaque language-model answer.

## User Problems To Solve

The current CLI and GitHub Action require users to understand model fields:

- `spot`
- `strike`
- `barrier`
- `barrier_direction`
- `trade_date`
- `expiry_date`
- `pair`

This is too much for normal use. Users usually ask questions like:

```text
Will AUD/USD fall 1.5% in the next 3 months?
Will this Corpay importer trade hit the barrier?
What does this forecast report mean?
Is this 90% probability credible?
```

The AI layer should convert those questions into structured model calls and then
explain the result.

## Non-Goals

The first AI agent version should not:

- Generate the final probability directly from an LLM.
- Override the model result without showing why.
- Treat touch probability as payoff probability.
- Parse PDFs or screenshots without a human review step.
- Execute trades, give financial advice, or recommend entering a product.

## Architecture

```text
User question / trade terms / model report
        |
        v
AI Parameter Assistant
        |
        v
Validated forecast request JSON
        |
        v
Existing deterministic model
        |
        v
Raw forecast JSON + text report
        |
        v
AI Report Reviewer
        |
        v
Final analyst memo
```

## Current Implementation Status

Implemented:

- `src.trades.agent.parse_forecast_request`
- `src.trades.agent.review_forecast_payload`
- `python -m src.cli.agent_cli parse-request`
- `python -m src.cli.agent_cli review-json`
- GitHub Action artifact `agent_review.json`
- deterministic fallback behavior with no API key or network dependency

Not implemented yet:

- OpenAI API integration.
- LLM-authored analyst memo.
- Natural-language request field inside GitHub Actions.
- Automatic conversion from parsed request JSON into a model run.
- Bilateral request parsing that returns both upper and lower barriers in one object.
- Forward-start probability integration.

## Phase A: AI Report Reviewer

This is the safest first AI feature because it does not change the probability
engine.

### Input

```json
{
  "user_question": "What does this result mean?",
  "forecast_request": {
    "pair": "AUD/USD",
    "analysis_date": "2026-06-13",
    "expiry_date": "2026-09-13",
    "spot": 0.704871,
    "strike": 0.704871,
    "barrier": 0.694298,
    "barrier_direction": "down"
  },
  "model_result": {
    "touch_probability": 90.51,
    "historical_baseline": 83.56,
    "volatility_adjusted": 94.24,
    "gbm_probability": 75.47,
    "final_probability": 90.51,
    "gbm_blend_weight": 0.0,
    "sample_count": 1235,
    "touch_count": 1032
  },
  "report_text": "FX BARRIER TOUCH INTELLIGENCE REPORT..."
}
```

### Output

```json
{
  "summary": "The model estimates a high probability that AUD/USD daily low touches 0.6943 within 92 calendar days.",
  "is_result_self_consistent": true,
  "input_warnings": [],
  "model_warnings": [
    "The final estimate assigns 0% weight to GBM and relies on the historical/calibrated baseline.",
    "This is a path-touch probability, not an expiry close or payoff probability."
  ],
  "plain_english_explanation": [
    "The barrier is 1.5% below spot.",
    "The expected 92-day move is larger than the barrier distance.",
    "Historical windows often touched a barrier this close."
  ],
  "suggested_follow_up_questions": [
    "What is the probability of touching both +1.5% and -1.5%?",
    "What is the probability that AUD/USD finishes below the barrier at expiry?",
    "How sensitive is the result to using 10 years of history instead of 5?"
  ]
}
```

### Reviewer Checks

The reviewer should flag:

- Spot already beyond barrier.
- Direction mismatch, such as a down scenario accidentally entered as `up`.
- `strike` confused with `spot`.
- `barrier_direction` confused with `Importer` or `Exporter`.
- `GBM/historical blend` where GBM weight is 0.
- Low historical sample count.
- Model disagreement, such as historical 90% versus GBM 40%.
- Touch probability being interpreted as payoff probability.

## Phase B: AI Parameter Assistant

This agent converts natural language into a structured forecast request.

### Example 1

User:

```text
想预测一下未来3个月audusd是否跌1.5%
```

Assistant JSON:

```json
{
  "intent": "relative_touch_forecast",
  "pair": "AUD/USD",
  "horizon_days": 92,
  "move_pct": -1.5,
  "barrier_direction": "down",
  "spot_source": "latest_market_close",
  "strike_source": "spot_placeholder",
  "needs_model_call": true
}
```

The application then resolves the latest spot and computes:

```text
barrier = spot * (1 - 0.015)
expiry_date = analysis_date + 92 days
```

### Example 2

User:

```text
Will EUR/USD touch 1.10 before July 13?
```

Assistant JSON:

```json
{
  "intent": "absolute_touch_forecast",
  "pair": "EUR/USD",
  "barrier": 1.1,
  "expiry_date": "2026-07-13",
  "barrier_direction": "up",
  "spot_source": "latest_market_close",
  "strike_source": "spot_placeholder",
  "needs_model_call": true
}
```

### Example 3

User:

```text
从9月30到12月30 AUD/USD 会不会跌破0.6935？
```

Assistant JSON:

```json
{
  "intent": "forward_start_touch_forecast",
  "pair": "AUD/USD",
  "forward_start_date": "2026-09-30",
  "expiry_date": "2026-12-30",
  "barrier": 0.6935,
  "barrier_direction": "down",
  "spot_source": "project_forward_start_distribution",
  "needs_forward_start_model": true
}
```

This is not supported by the current model yet. The agent should say that the
system needs a forward-start distribution, not ask the user to provide a future
spot.

## Forecast Request Schema

```json
{
  "type": "object",
  "required": ["pair", "barrier_direction"],
  "properties": {
    "pair": {
      "type": "string",
      "description": "FX pair such as AUD/USD, EUR/USD, USD/JPY"
    },
    "analysis_date": {
      "type": ["string", "null"],
      "description": "Model as-of date. If null, use latest market date."
    },
    "expiry_date": {
      "type": ["string", "null"],
      "description": "Barrier expiry date."
    },
    "horizon_days": {
      "type": ["integer", "null"],
      "description": "Alternative to expiry_date for relative horizon requests."
    },
    "spot": {
      "type": ["number", "null"],
      "description": "Manual spot override. Usually null."
    },
    "strike": {
      "type": ["number", "null"],
      "description": "Contract strike. Can default to spot for non-product scenarios."
    },
    "barrier": {
      "type": ["number", "null"],
      "description": "Absolute barrier level."
    },
    "move_pct": {
      "type": ["number", "null"],
      "description": "Relative move. Positive means up, negative means down."
    },
    "barrier_direction": {
      "type": "string",
      "enum": ["up", "down"]
    },
    "product_type": {
      "type": ["string", "null"]
    },
    "client_direction": {
      "type": ["string", "null"],
      "enum": ["Importer", "Exporter", null]
    }
  }
}
```

## Prompt Draft: Parameter Assistant

```text
You convert user requests about FX barrier or move forecasts into structured JSON.

Rules:
- Do not calculate the final probability.
- pair must be normalized as BASE/QUOTE, e.g. AUD/USD.
- "rise", "涨", "up", "higher", "above" imply barrier_direction = up.
- "fall", "跌", "down", "lower", "below" imply barrier_direction = down.
- A relative move such as "跌1.5%" should set move_pct = -1.5.
- A relative move such as "涨1.5%" should set move_pct = 1.5.
- If the user asks about a future start date after the analysis date, do not invent spot.
  Set intent = forward_start_touch_forecast and spot_source = project_forward_start_distribution.
- strike is a contract rate, not spot. If the user is not describing a structured product,
  set strike_source = spot_placeholder.
- Importer/Exporter is business direction, not barrier direction.
- Return only valid JSON.
```

## Prompt Draft: Report Reviewer

```text
You review FX barrier forecast outputs for clarity, self-consistency, and misuse risk.

Rules:
- Do not change the probability unless there is a clear input or logic error.
- Explain touch probability as a path event, not expiry close probability.
- If spot is already beyond the barrier in the selected direction, flag ALREADY_BREACHED.
- If GBM weight is 0, explain that the final estimate relies on historical/calibrated baseline.
- If models disagree materially, call that out.
- If sample count is low, call that out.
- Do not give investment advice.
- Return concise analyst-style language.
```

## Phase C: Trade Term Extractor

This should come after Phase A/B.

Input sources:

- Corpay screenshots.
- Corpay option confirmations.
- Manually pasted trade terms.

Output:

```json
{
  "product_type": "Ratio Convertible Forward",
  "client_direction": "Importer",
  "pair": "AUD/USD",
  "protected_amount": 500000,
  "ratio_amount": 1000000,
  "amount_currency": "USD",
  "strike": 0.685,
  "barrier": 0.6935,
  "barrier_direction": "up",
  "barrier_level_period": "continuous",
  "expiry_date": "2026-12-30",
  "requires_human_review": true
}
```

Human review is required because OCR can confuse:

- `0.6935` with `0.6835`
- `≤` with `>=`
- `strike` with `spot`
- expiry dates across multiple scheduled legs

## Phase D: External Research Agent

This agent can summarize market context but should not directly overwrite the
probability engine.

Possible sources:

- DXY
- VIX
- RBA/Fed policy expectations
- commodity proxies such as iron ore or copper
- bank forecasts
- technical levels

Output should be separated:

```text
External qualitative tilt: bearish AUD/USD
Confidence: medium
Reason: DXY momentum and weak Australia growth data
Impact on model: context only, not directly included in final probability
```

## Implementation Roadmap

### Step 1: Add JSON output contract

Current CLI already supports JSON. Stabilize a smaller `forecast_payload` object
that the AI reviewer can consume.

### Step 2: Add offline agent prompts

Create prompt templates and tests that validate expected JSON structure using
static sample inputs. No network/API dependency yet.

### Step 3: Add optional OpenAI integration

Add an optional module:

```text
src/agent.py
```

It should:

- Read `OPENAI_API_KEY`.
- Be disabled by default.
- Accept model name from config or CLI.
- Return structured JSON.
- Fail closed: if the LLM call fails, the deterministic report still works.

### Step 4: Add CLI wrapper

Add:

```bash
python -m src.cli.agent_cli review-report forecast_report.txt
python -m src.cli.agent_cli parse-request "未来3个月AUD/USD是否跌1.5%"
```

### Step 5: Add GitHub Action mode

The existing manual Action can add an optional field:

```text
natural_language_question
```

If provided, the parameter assistant parses it. If not, the structured inputs
continue to work exactly as today.

## Risk Controls

- Keep deterministic model output visible.
- Keep LLM output clearly labeled as interpretation.
- Log parsed parameters before running the model.
- Require human confirmation for PDF/screenshot extraction.
- Never hide model disagreement.
- Never call touch probability "profit probability".
- Never let LLM invent future spot for a forward-start window.

## Recommended Next Build

Build in this order:

1. Add a bilateral request schema for "涨跌 3%" style questions.
2. Add deterministic bilateral parser output:
   - upper move
   - lower move
   - horizon
   - pair
3. Add optional OpenAI client wrapper for parser/reviewer only.
4. Add GitHub Action optional `natural_language_question`.
5. Add LLM memo artifact only when `OPENAI_API_KEY` is present.
6. Keep deterministic `agent_review.json` artifact in all runs.

The next shippable user value should be:

```text
User asks "AUD/CNH up or down 3% in 3 months"
-> agent parses bilateral request
-> engine runs both sides
-> report explains upper/lower/either/both probabilities
```
