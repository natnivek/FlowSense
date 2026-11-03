"""Build the model note with ReportLab (optional document dependency)."""

from pathlib import Path

from reportlab.lib import colors
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.lib.enums import TA_LEFT
from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle, PageBreak


OUTPUT = Path("output/pdf/flowsense_synthetic_model.pdf")
styles = getSampleStyleSheet()
styles.add(ParagraphStyle(name="TitleNote", fontName="Helvetica-Bold", fontSize=24, leading=29, textColor=colors.HexColor("#17324d"), spaceAfter=15))
styles.add(ParagraphStyle(name="BodyNote", fontName="Helvetica", fontSize=10, leading=13.5, spaceAfter=7))
styles.add(ParagraphStyle(name="HeadingNote", fontName="Helvetica-Bold", fontSize=13, leading=17, spaceBefore=12, spaceAfter=7, textColor=colors.HexColor("#17324d")))
styles.add(ParagraphStyle(name="EquationNote", fontName="Courier", fontSize=9, leading=14, leftIndent=10, spaceBefore=4, spaceAfter=10))
styles.add(ParagraphStyle(name="SmallNote", fontName="Helvetica", fontSize=9, leading=12, spaceAfter=6))
story = []


def p(text, style="BodyNote"):
    story.append(Paragraph(text, styles[style]))


def h(text):
    p(text, "HeadingNote")


def eq(text):
    p(text, "EquationNote")


def table(rows, widths):
    cells = [[Paragraph(str(cell), styles["SmallNote"]) for cell in row] for row in rows]
    t = Table(cells, colWidths=widths, repeatRows=1, hAlign="LEFT")
    t.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#e9eff5")),
        ("VALIGN", (0, 0), (-1, -1), "TOP"),
        ("LINEBELOW", (0, 0), (-1, 0), 0.6, colors.HexColor("#9aaaba")),
        ("LINEBELOW", (0, 1), (-1, -1), 0.3, colors.HexColor("#d5dde5")),
        ("LEFTPADDING", (0, 0), (-1, -1), 7),
        ("RIGHTPADDING", (0, 0), (-1, -1), 7),
        ("TOPPADDING", (0, 0), (-1, -1), 6),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 5),
    ]))
    story.append(t)


p("FlowSense", "TitleNote")
p("Synthetic investor flow model", "TitleNote")
p("Methodology note | 3 November 2026 | Prototype milestone 01", "SmallNote")
h("Abstract and purpose")
p("The generator creates controlled, reproducible test data for an investor flow analytics prototype. It combines persistent daily flows, shared market shocks, changing volatility, and predefined risk scenarios. The purpose is to test calculations and software behavior before connecting a real data source. It is not a fitted economic model, a forecast, or a reconstruction of actual investor activity.")
p("<b>Provenance:</b> The particular equations, scenario windows, and numerical settings were constructed for FlowSense. No external paper or BNY methodology supplied the target-flow formula. Statistical ingredients such as autoregression and exponential smoothing are general methods; their use does not validate this calibration.")
h("1. Coverage and notation")
p("The calendar contains 523 Monday-Friday dates from 1 January 2024 through 31 December 2025. Three asset classes (equities, government bonds, FX) and three regions (US, Europe, Asia) produce nine series and 4,707 rows. Local market holidays are not excluded. Flows use invented USD-equivalent millions per day.")
p("Let F[a,r,t] be daily net flow for asset a, region r, date t; s[a] the asset scale; q[r] the regional multiplier; b[a] the regime loading; and R[t] the scenario indicator (+1 risk-on, -1 risk-off, 0 neutral).")
h("2. Regime target and persistent flows")
eq("mu[a,r,t] = 1.5 * b[a] * R[t] * s[a] * q[r]<br/>F[a,r,t] = 0.60 * F[a,r,t-1] + 0.40 * mu[a,r,t]<br/>             + s[a] * q[r] * V[t] * e[a,r,t]")
p("The target mu is an assumed equilibrium daily flow for the current scenario, not a historical average or observed benchmark. With an unchanged target, the expected flow approaches mu because 0.40 = 1 - 0.60. The previous-flow value before the first date is zero; the first observed flow already contains a random innovation.")
p("This is an autoregressive model with a deterministic regime-dependent intercept, 0.40 * mu, and time-varying volatility. A standard constant-intercept AR(1) is only a special case. Persistence of 0.60 creates runs of inflows or outflows and gradual responses without making the series too smooth. It is illustrative, not estimated.")
story.append(PageBreak())
h("3. Asset scales, loadings, and episode strength")
table([["Asset", "Scale s[a]", "Loading b[a]"], ["Equities", "110", "+1.0"], ["Government bonds", "85", "-0.8"], ["FX", "65", "+0.5"]], [200, 130, 150])
p("Regional multipliers q[r] are US = 1.2, Europe = 1.0, and Asia = 0.8. These differences create distinct synthetic magnitudes; they are not evidence that Asian investors move less money. FX denotes an invented regional risk-sensitive basket, not a specified currency pair or net global FX investment.")
p("<b>Scale versus loading.</b> Asset and region scales multiply both the target and the random innovation. Loading affects only the regime target: its sign sets the direction, and its magnitude sets sensitivity. Thus bonds have positive targets during risk-off, while equities and this stylized FX basket have negative targets.")
p("<b>Why 1.5?</b> This hand-chosen factor makes episodes visible relative to ordinary daily noise. At V = 1, an equity target has magnitude 1.5 times its base innovation standard deviation. It is not a statistical significance level or an empirically selected optimum. Today's expected adjustment is only 40% of that target. Increasing 1.5 strengthens scenario separation; decreasing it makes episodes subtler.")
eq("US equity risk-on target = 1.5 * 1 * 1 * 110 * 1.2 = 198<br/>US equity risk-on intercept = 0.40 * 198 = 79.2")
h("4. Shared shocks and changing uncertainty")
eq("e[a,r,t] = 0.45 * G[t] + 0.45 * A[a,t]<br/>             + sqrt(1 - 2 * 0.45^2) * I[a,r,t]")
p("G, A, and I are mutually independent standard-normal draws, independent across dates. The global draw is shared by all series; the asset draw is shared by that asset's regions; the final draw is independent for each series. The squared weights sum to one, so e has variance one. Before volatility scaling, innovation correlations are 0.405 for different regions of the same asset and 0.2025 for different assets. These are imposed dependencies, not estimated correlations of observed flows.")
eq("L[0] = 0<br/>L[t] = 0.96 * L[t-1] + u[t],  u[t] ~ Normal(0, 0.10^2)<br/>V[t] = exp(L[t]) * (1.8 if risk-off, otherwise 1)")
p("Persistent log volatility creates quiet and turbulent clusters; exponentiation ensures a positive multiplier. The additional 1.8 amplifies innovation standard deviation during risk-off (variance by 3.24 at the same L). This is a scenario assumption. Symmetric Gaussian shocks and a common volatility factor keep the model simple but omit many real-market features.")
story.append(PageBreak())
h("5. Scenario windows")
table([["Inclusive start", "Inclusive end", "Regime"], ["2024-03-04", "2024-04-12", "Risk-on"], ["2024-08-05", "2024-09-13", "Risk-off"], ["2025-02-03", "2025-03-14", "Risk-on"], ["2025-09-01", "2025-10-10", "Risk-off"]], [160, 160, 160])
p("Every other date is neutral. The same scenario applies across all regions and assets, with responses determined by loadings. Windows are fictional fixtures, not historical event classifications or inferred market states. Their abrupt boundaries make detection tests interpretable; persistence carries their effects beyond the boundaries. An individual day can still move against the episode direction.")
h("6. Cumulative flow and positioning proxy")
eq("C[a,r,t] = sum of F[a,r,j] from first date through t<br/>x[a,r,t] = F[a,r,t] / (s[a] * q[r])<br/>P[a,r,t] = 0.97 * P[a,r,t-1] + 0.03 * x[a,r,t]<br/>PositioningProxy[a,r,t] = 100 * tanh(P[a,r,t])")
p("Cumulative flow retains the entire simulated history, starting from zero before the first observation. P is an exponentially weighted average of normalized flow, also initialized at zero before the first date. The 3% update weight emphasizes sustained activity rather than isolated shocks: past influence halves after approximately 23 business days. Normalization removes the deliberately assigned asset and regional magnitude factors, not all differences in behavior or volatility.")
p("<b>Why tanh?</b> It preserves sign, maps zero to zero, treats positive and negative inputs symmetrically, and smoothly compresses extremes into (-100, 100). Near zero, tanh(P) is approximately P. These properties make a compact signed indicator. A proxy of +50 does not mean a 50% portfolio allocation, a 50% long position, or a percentile.")
p("There is no claimed industry standard or financial superiority behind this choice. A centered logistic can be exactly equivalent: with sigmoid(z) = 1 / (1 + exp(-z)), <b>100 * tanh(P) = 200 * sigmoid(2P) - 100</b>. Using sigmoid(P) instead would change the slope and saturation speed. A scaled arctangent or clipping would also bound values, but would compress extremes differently; clipping introduces hard cutoffs.")
p("The proxy is a deterministic transformation of past and current flows. It adds a convenient summary, not independent information about holdings. Changes in it can reflect the chosen smoothing and saturation, rather than a measured change in real investor exposure.")
h("7. Initialization and reproducibility")
p("NumPy's default random generator uses seed 42, with fixed asset/region iteration order. The initial log-volatility and pre-observation flow/position states are zero; no burn-in is discarded. Early observations therefore reflect initialization. Pinned dependencies are NumPy 2.3.5 and Pandas 2.2.3. Reproducibility concerns data values for the same code, configuration, and environment, not byte-identical SQLite files.")
story.append(PageBreak())
h("8. Storage and validation")
p("SQLite table <b>flows</b> uses (date, asset_class, region) as its primary key. All columns are required. Dates are ISO text; numeric measures are REAL values. Generation transactionally replaces this table's rows while retaining unrelated tables.")
table([["Column", "Meaning"], ["date, asset_class, region", "Observation key"], ["net_flow", "Daily signed synthetic flow in USD-equivalent millions"], ["cumulative_flow", "Within-series running total, same flow units"], ["positioning_proxy", "Bounded unitless flow-derived indicator"], ["regime", "Known simulator scenario label"], ["volatility_multiplier", "Known latent simulator volatility state"]], [190, 290])
p("Generator tests check weekday coverage, row counts, schema, required fields, unique keys, finite values, cumulative sums, proxy bounds, deterministic regeneration, SQLite round trips, positive autocorrelation, scenario-average flow direction, and higher average risk-off volatility. These checks establish internal consistency and intended behavior, not realism or investment value.")
h("9. Assumptions and practical limits")
p("The model imposes a synchronous scenario across all markets, constant loadings, Gaussian innovation draws, a single common volatility path, fixed regional magnitudes, and prescribed episode dates. It does not model investor types, market size, settlement, exchange calendars, asset prices, FX conversion, liquidity, structural breaks in parameters, or accounting constraints across markets. Government bonds are not guaranteed safe in real stress events, and FX behavior depends on the currency and investor perspective.")
p("<b>No BNY representation.</b> No BNY iFlow data, investor accounts, proprietary definitions, or calibration were used. Coverage, units, region assignments, flow magnitudes, positioning, and dependencies are invented for this prototype. Results must not be presented as representative of BNY iFlow or actual investor behavior.")
p("Known scenario and volatility labels are useful for offline validation but expose hidden simulator state. The milestone 02 analytics engine excludes them from calculations. Successful detection of constructed patterns does not demonstrate predictive skill on real markets.")
h("10. Rationale and next validation step")
p("The design prioritizes simplicity, modularity, reproducibility, and interpretable test cases. Exact settings are scenario controls rather than financial estimates. Before making empirical claims, use an appropriately licensed real source, define comparable flow measures, estimate and diagnose persistence and dependence, test sensitivity to alternative parameters and proxy transforms, and evaluate results out of sample. Do not assume the proxy measures actual positioning without separate validation.")
h("Implementation source")
p("Primary source: FlowSense's local <b>flowsense/generator.py</b>; supporting definitions: <b>README.md</b>; validation: <b>tests/test_generator.py</b>. This note describes the implementation inspected on 3 November 2026. It does not attribute the custom model to an external publication.", "SmallNote")


def footer(canvas, doc):
    canvas.setStrokeColor(colors.HexColor("#d5dde5"))
    canvas.line(54, 42, 558, 42)
    canvas.setFont("Helvetica", 8)
    canvas.setFillColor(colors.HexColor("#526477"))
    canvas.drawString(54, 29, "FlowSense | Synthetic model methodology | Illustrative, not calibrated")
    canvas.drawRightString(558, 29, str(doc.page))


if __name__ == "__main__":
    OUTPUT.parent.mkdir(parents=True, exist_ok=True)
    SimpleDocTemplate(str(OUTPUT), pagesize=(612, 792), leftMargin=54, rightMargin=54,
                      topMargin=36, bottomMargin=50,
                      title="FlowSense: Synthetic Investor Flow Model", author="FlowSense").build(
                          story, onFirstPage=footer, onLaterPages=footer)
    print(OUTPUT)
