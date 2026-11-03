# FlowSense: synthetic flow intelligence prototype

A small, reproducible Python fixture for macro quantitative research prototyping.
It generates 2024–2025 observations for equities, government bonds, and FX in
the US, Europe, and Asia. Includes a descriptive analytics engine and a tool-backed
LLM question-answering CLI. No Streamlit dashboard is included yet.

## Run

Use Python 3.11 or newer, with SSL support for dependency installation:

```sh
python3 -m venv .venv
source .venv/bin/activate
python -m pip install -r requirements.txt
python -m scripts.generate_data
python -m unittest discover -s tests -v
```

The default output is `data/flowsense.sqlite`. Override it with
`python -m scripts.generate_data --output /path/to/flows.sqlite --seed 42`.
Generation replaces the `flows` table contents transactionally; unrelated tables
are retained. Validation uses temporary databases and does not alter the output.

## Quantitative engine (milestone 02)

With the environment activated and the database generated, run:

```sh
python -m scripts.analyze_data
python -m unittest discover -s tests -v
```

Optional settings:

```sh
python -m scripts.analyze_data --database data/flowsense.sqlite --window 20 --position-lag 5 --output-dir data/analytics
```

The command reads SQLite without modifying it, prints the latest per-series
metrics, and overwrites two CSVs in the output directory:
`flow_metrics.csv` and `cross_asset_divergences.csv`. Use these Python functions
directly for subsequent agent/dashboard work:

```python
from flowsense.analytics import load_flows, calculate_metrics, calculate_divergences

metrics = calculate_metrics(load_flows("data/flowsense.sqlite"), window=20, position_lag=5)
divergences = calculate_divergences(metrics)
```

Calculations are independent within each asset–region series, sorted by date:

| Metric | Definition |
| --- | --- |
| prior_flow_mean | Mean of the previous `window` daily flows, excluding today |
| prior_flow_std | Sample standard deviation of those same flows (`ddof=1`) |
| flow_zscore | `(today's net_flow - prior_flow_mean) / prior_flow_std` |
| cumulative_flow | Running sum from the first input date, recomputed from daily flows |
| rolling_net_flow | Sum of `window` daily flows ending today, including today |
| position_change_1d | Today's positioning proxy minus the prior business day's proxy |
| position_change | Today's proxy minus its value `position_lag` business days earlier |

Default settings are 20 observations and a five-observation positioning lag.
The output retains the proxy and raw flow, plus `window` and `position_lag` for
traceability. Position changes are index-point differences, not percentage returns.
Z-scores use only prior observations for the baseline: the first 20 dates are
unavailable with default settings. A zero baseline standard deviation also produces
an unavailable z-score, including when today's flow is nonzero. Rolling sums and
position changes similarly require their full history. These intentional missing
outputs appear as empty CSV cells; raw input values must never be missing.

Cross-asset comparisons cover equities–government bonds, equities–FX, and government
bonds–FX within each region and date. Each row includes both z-scores, their signed
spread (`zscore_a - zscore_b`), and `opposite_flow_direction` (strictly opposite
signs of raw flows; zero is not opposite). A positive spread means asset A's flow
is stronger relative to its own recent history than asset B's; it does not
necessarily mean A has inflows or that B has outflows. Missing z-scores produce a
missing spread. The spread is descriptive, not itself a standardized z-score or
a trading signal; no significance or investment threshold is asserted.

The engine accepts available asset–region series but requires each to cover the
same complete Monday–Friday date range. It rejects duplicate keys, invalid assets
or regions, nonfinite inputs, missing dates, and out-of-range positioning. Subsets
of history reset the cumulative-flow starting point. Simulator regime labels and
latent volatility are excluded from analytics to avoid using hidden scenario state.

Analytics tests use hand-calculated examples, check group isolation and zero
variance, confirm future observations cannot alter past metrics, and exercise the
SQLite-to-analytics path. Passing them verifies calculations, not predictive value.

## AI research assistant (milestone 03)

The assistant uses the OpenAI Responses API and three predefined read-only tools:
`describe_dataset`, `get_metrics`, and `get_divergences`. It has no SQL execution,
Python execution, database modification, web search, or simulator-state tools.
HTTPS uses the Python standard library, so no additional SDK dependency is needed.
The implementation follows the [official function-calling guide](https://developers.openai.com/api/docs/guides/function-calling).

First verify the tool layer offline (does not call an LLM or require credentials):

```sh
source .venv/bin/activate
python -m scripts.ask_flowsense --check-tools
python -m unittest discover -s tests -v
```

For live Q&A, configure a model available to your OpenAI API project that supports
Responses function calling and structured JSON outputs. Set `OPENAI_MODEL` to that
model's identifier, or pass `--model`. No model is hardcoded or silently substituted.
In zsh, enter your API key without placing its literal value in shell history:

```sh
read -rs 'OPENAI_API_KEY?OpenAI API key: '; echo
export OPENAI_API_KEY
export OPENAI_MODEL='YOUR_AVAILABLE_MODEL_ID'
python -m scripts.ask_flowsense "What stands out in the latest US equity flows?"
python -m scripts.ask_flowsense "Compare equities and government bonds in Europe on 2025-12-31."
python -m scripts.ask_flowsense "What do Asia FX flows show on 2024-01-05?" --output data/answers/example.json
```

The key must be supplied locally; never put it in source files or chat. `.env`
files are ignored by Git, but the CLI does not automatically load them. Live
questions send the question and selected synthetic tool evidence to OpenAI and
incur API usage. The source SQLite database stays local and read-only. Requests
set `store=false`; this does not override the API provider's other data policies.

`--database`, `--window`, and `--position-lag` select the source and calculation
settings. Each question is a fresh, independent session. Responses are limited
to six API rounds, 12 tool calls, at most 3,000 output tokens per round, and a 45-second HTTP
timeout. There are no automatic retries. The optional output JSON stores the
question, model identifier, structured answer, tool arguments, and numeric evidence;
it never stores API credentials.

### Evidence and interpretation

The model chooses tool calls; Python validates their arguments, executes existing
analytics, and returns evidence IDs. Results include dates, window, position lag,
matching/returned row counts, and a truncation flag. Queries return at most 60
rows, newest date first; absent dates default to the latest date in the dataset,
not the current wall-clock date. No full-period aggregates or rankings are exposed.
The agent must say when the requested analysis exceeds these tools.

Final output separates observations, unverified hypotheses, and limitations. Every
observation must cite successful tool evidence from the current question; unknown
citations are rejected. The terminal appends the actual tool output values so
numbers can be independently checked. Null metrics remain unavailable, never zero.
The assistant is instructed not to infer causes, real holdings, investment merit,
or actual BNY activity from fabricated flows.

Citation checks establish that evidence exists, **not that the model's prose is
entailed by it**. Qualitative interpretations and hypothesis labeling still require
review. Prompt instructions are not a guarantee against hallucinations. Raw tool
values are the authoritative numeric record. Do not use answers for investment
decisions. Unsupported questions should receive a limitation, not invented evidence.

### Validation status

Offline tests use a scripted fake API transport to check the tool loop, exact
engine-to-tool values, dates, filters, truncation, null handling, invalid requests,
fabricated citations, recovery, incomplete responses, and round limits. They do
not exercise a real model or measure language-answer quality. At implementation
time no API key was configured, so live model quality, model compatibility, and
credential/network success remain unverified. Before demoing, run the three sample
questions above, a causal question ("Why did flows change?"), and an unsupported
request ("What were actual BNY flows today?"); inspect observations against the
printed evidence and ensure unsupported claims are declined or clearly qualified.

## Schema

SQLite table `flows` contains one row per date, asset class, and region.
All fields are required. The composite primary key is `(date, asset_class, region)`.

| Column | SQLite type | Meaning |
| --- | --- | --- |
| date | TEXT | ISO date, YYYY-MM-DD |
| asset_class | TEXT | equities, government_bonds, or fx |
| region | TEXT | US, Europe, or Asia |
| net_flow | REAL | Daily signed synthetic USD-equivalent millions |
| cumulative_flow | REAL | Running sum of net flows within each asset–region series, starting from zero before the first observation |
| positioning_proxy | REAL | Unitless proxy bounded between -100 and 100 |
| regime | TEXT | neutral, risk_on, or risk_off |
| volatility_multiplier | REAL | Positive shared latent volatility multiplier |

There are 523 Monday–Friday dates and 4,707 observations. Local exchange holidays
are deliberately included; this is a weekday calendar, not a trading calendar.

## Simulation assumptions

- NumPy's default random generator uses seed 42. Pinned NumPy/Pandas versions
  support reproducibility. Tests compare values, not SQLite file bytes.
- Each flow is an AR(1) process with coefficient 0.60 around a regime target.
  Innovations mix a global shock, an asset shock, and independent regional noise.
- A shared log-volatility AR(1) process has persistence 0.96 and innovation
  standard deviation 0.10. Risk-off dates multiply volatility by 1.8.
- Equities, bonds, and FX have base daily shock scales of 110, 85, and 65
  synthetic millions. Regional multipliers are 1.2, 1.0, and 0.8 respectively
  for US, Europe, and Asia. These are illustrative, not estimated.
- Regime flow targets use loadings 1.0, -0.8, and 0.5 for equities, bonds, and FX.
  Risk-on favors equities and the stylized FX basket; risk-off favors bonds.
  FX represents an invented regional risk-sensitive basket, not net flows
  across the global FX market or a specified currency pair.
- Positioning is an exponentially smoothed normalized flow (weight 0.03),
  mapped through `100 * tanh(value)`. It is not holdings, exposure, or an
  investor position measured from real accounts.

The inclusive, fixed episode windows are:

| Start | End | Regime |
| --- | --- | --- |
| 2024-03-04 | 2024-04-12 | risk_on |
| 2024-08-05 | 2024-09-13 | risk_off |
| 2025-02-03 | 2025-03-14 | risk_on |
| 2025-09-01 | 2025-10-10 | risk_off |

These dates are fictional scenario choices, not historical event classifications.
Tests check schema and primary keys, complete calendars, missing/nonfinite values,
cumulative sums, bounds, repeat generation, SQLite round trips, autocorrelation,
episode direction, and elevated risk-off volatility.

## Synthetic data limitations

This dataset is entirely fabricated and is **not representative of actual BNY
iFlow data**. It uses no BNY data, proprietary methodology, investor records, or
calibration to iFlow distributions. The asset taxonomy, regional aggregation,
units, coverage, flow definitions, positioning proxy, and cross-market behavior
are assumptions made for this prototype; they do not describe BNY's product.
Do not use it to infer actual investor activity, assess investment performance,
or claim that a research signal will work on real data. Regime and volatility
labels expose simulator state and should not be treated as observable predictors
in a realistic backtest.
