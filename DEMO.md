# FlowSense demo and validation

From the project directory, activate your Python environment and run:

```bash
python -m pip install -r requirements-dashboard.txt
python -m scripts.generate_data
python -m unittest discover -s tests -v
python -m streamlit run streamlit_demo.py --server.address localhost
```

The dashboard generates its synthetic SQLite dataset on first launch if it is missing.
Streamlit Community Cloud installs the pinned dependencies from `requirements.txt`.
For live Q&A, set
`OPENAI_API_KEY` and `OPENAI_MODEL` in the same terminal **before** starting
Streamlit. See the README for credential setup. The charts work without them.

## Two-minute walkthrough

| Time | Show | Say |
|---|---|---|
| 0:00–0:20 | FlowSense header | “This prototype uses synthetic investor flows across three asset classes and regions. It has no access to actual BNY iFlow.” |
| 0:20–0:55 | US → Equities; switch to Europe and back | “On December 31, 2025, US equities show a synthetic $61.3M outflow but a +0.53 z-score. That means the outflow was smaller than the recent average, not that it was an inflow. The five-day positioning change is +1.22 index points; this is a flow-derived proxy.” |
| 0:55–1:35 | Ask: “What stands out in the latest US equity flows?” | “The model selects which read-only tools to call. Python computes the metrics. The assistant explains the results and cites the tool outputs.” |
| 1:35–2:00 | Expand Evidence | “I can trace the answer to its date, asset, region, and exact numbers. This demonstrates a research workflow, not an investment signal.” |

## Live dashboard acceptance checks

- [ ] US → Equities shows December 31, 2025, −$61.3M net flow, +0.53 z-score,
  and +1.22 positioning points. Both charts update when the selection changes.
- [ ] Submit the demo question. The answer explains that a positive z-score can
  coexist with an outflow. Its cited evidence matches the dashboard metrics.
- [ ] Ask “What were actual BNY iFlow flows today?” The answer says actual
  data is unavailable and does not pass off synthetic data as market data.
- [ ] Rehearse the walkthrough once with your chosen API model.

The automated dashboard tests exercise the real SQLite data and tool loop with
simulated model responses. The three prior live CLI checks do not substitute
for the live dashboard checks above.
