import json
import os
from pathlib import Path
from tempfile import TemporaryDirectory

import pandas as pd

import streamlit as st

from flowsense.agent import AnalyticsTools, ask
from flowsense.analytics import calculate_metrics, load_flows
from flowsense.generator import generate_data, save_to_sqlite

st.set_page_config(page_title="FlowSense", layout="wide")
st.title("FlowSense")
st.caption("Synthetic data — not actual BNY iFlow")

database = Path(__file__).resolve().parent / "data" / "flowsense.sqlite"

if not database.is_file():
    database.parent.mkdir(parents=True, exist_ok=True)
    with TemporaryDirectory(dir=database.parent) as temporary:
        staged = Path(temporary) / database.name
        save_to_sqlite(generate_data(), staged)
        # Publish the completed database without overwriting another session's copy.
        try:
            database.hardlink_to(staged)
        except FileExistsError:
            pass


@st.cache_data(max_entries=2)
def load_metrics(path, modified_at):
    return calculate_metrics(load_flows(path))


metrics = load_metrics(database, database.stat().st_mtime_ns)

region = st.selectbox("Region", ["US", "Europe", "Asia"])
asset_labels = {
    "equities": "Equities",
    "government_bonds": "Government bonds",
    "fx": "FX",
}
asset = st.selectbox("Asset class", list(asset_labels), format_func=asset_labels.get)

series = metrics[
    (metrics["region"] == region) & (metrics["asset_class"] == asset)
]
if series.empty:
    st.info("No observations for this selection.")
    st.stop()
latest = series.iloc[-1]

st.subheader(f"{region} · {asset_labels[asset]}")
st.caption(f"Latest observation: {latest['date']:%B %d, %Y}")

def signed(value, places, unit=""):
    return "Unavailable" if pd.isna(value) else f"{value:+,.{places}f}{unit}"


flow, z_score, position = st.columns(3)
flow.metric("Daily net flow", f"{latest['net_flow']:+,.1f} million USD equivalent")
z_score.metric("Flow z-score", signed(latest["flow_zscore"], 2))
position.metric(
    "5-day positioning change",
    signed(latest["position_change"], 2, " index points"),
    help="Change in the synthetic positioning proxy; this does not measure holdings.",
)

st.caption(
    "Negative net flow means an outflow. The z-score compares that day's flow "
    "with the previous 20 business days."
)

st.header("Flow history")
chart_columns = st.columns(2)
with chart_columns[0]:
    st.subheader("Daily net flow")
    st.bar_chart(
        series, x="date", y="net_flow", x_label="Date",
        y_label="Synthetic USD-equivalent millions",
        alt=f"Daily net flow for {region} {asset_labels[asset]}",
    )
with chart_columns[1]:
    st.subheader("Cumulative net flow")
    st.line_chart(
        series, x="date", y="cumulative_flow", x_label="Date",
        y_label="Synthetic USD-equivalent millions",
        alt=f"Cumulative net flow for {region} {asset_labels[asset]}",
    )


def evidence_fields(value, path=""):
    """Keep every field, including empty containers and null values."""
    if isinstance(value, dict) and value:
        for key, child in value.items():
            yield from evidence_fields(child, f"{path}.{key}" if path else key)
    elif isinstance(value, list) and value:
        for index, child in enumerate(value):
            yield from evidence_fields(child, f"{path}[{index}]")
    else:
        yield {"Field": path, "Value": json.dumps(value, ensure_ascii=False)}


st.header("Ask FlowSense")
st.caption("Questions can cover the entire synthetic dataset, regardless of the chart filters.")
model = os.getenv("OPENAI_MODEL")
ready = bool(model and os.getenv("OPENAI_API_KEY"))
if not ready:
    st.info("To enable Q&A, set OPENAI_API_KEY and OPENAI_MODEL in the terminal that starts Streamlit, then restart the app.")

st.session_state.setdefault("flow_answer", None)
with st.form("flow_question"):
    question = st.text_area(
        "Question", placeholder="What stands out in the latest US equity flows?",
        max_chars=8000, disabled=not ready,
    )
    submitted = st.form_submit_button("Ask", disabled=not ready)

if submitted:
    st.session_state.flow_answer = None
    if not question.strip():
        st.warning("Enter a question first.")
    else:
        try:
            with st.spinner("Checking the flow data…"):
                st.session_state.flow_answer = ask(question.strip(), AnalyticsTools(database), model)
        except (RuntimeError, ValueError) as error:
            st.error(str(error))

result = st.session_state.flow_answer
if result is not None:
    st.text(result["question"])
    answer = result["answer"]
    st.subheader("Observations")
    if not answer["observations"]:
        st.text("No supported data observation returned.")
    for observation in answer["observations"]:
        citations = ", ".join(observation["evidence_ids"])
        st.text(f"• {observation['text']} [{citations}]")
    for heading, key in (("Hypotheses (unverified)", "hypotheses"), ("Limitations", "limitations")):
        st.subheader(heading)
        for item in answer[key]:
            st.text(f"• {item}")

    with st.expander("Evidence · exact tool outputs"):
        if not result["evidence"]:
            st.caption("No tool evidence was returned.")
        for entry in result["evidence"]:
            label = f"{entry['evidence_id']} · {entry['tool']}"
            st.markdown(f"**{label}**")
            st.dataframe(
                list(evidence_fields(entry)), hide_index=True,
                alt=f"Exact evidence fields for {label}",
            )
