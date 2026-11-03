# import streamlit as st

# st.title("My first Streamlit app")

# region = st.selectbox("Choose a region", ["US", "Europe", "Asia"])
# st.write(f"Selected region: {region}")

from pathlib import Path

import streamlit as st

from flowsense.analytics import calculate_metrics, load_flows

st.title("FlowSense")
st.caption("Synthetic data — not actual BNY iFlow")

database = Path(__file__).resolve().parent / "data" / "flowsense.sqlite"

if not database.is_file():
    st.error("Dataset not found. Run `python -m scripts.generate_data` first.")
    st.stop()


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
latest = series.iloc[-1]

st.subheader(f"{region} · {asset_labels[asset]}")
st.caption(f"Latest observation: {latest['date']:%B %d, %Y}")

flow, z_score = st.columns(2)
flow.metric("Daily net flow", f"{latest['net_flow']:+,.1f} million USD equivalent")
z_score.metric("Flow z-score", f"{latest['flow_zscore']:+.2f}")

st.caption(
    "Negative net flow means an outflow. The z-score compares that day's flow "
    "with the previous 20 business days."
)