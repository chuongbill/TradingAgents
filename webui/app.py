"""
TradingAgents Streamlit Web UI
A self-contained web interface that wraps the TradingAgents Python API.
No modifications to the core TradingAgents package are needed.
"""

import os
import sys
import time
import datetime
import threading
from pathlib import Path

import streamlit as st
from streamlit.runtime.scriptrunner import add_script_run_ctx
from dotenv import load_dotenv

# Ensure the project root is on sys.path so tradingagents is importable
PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

load_dotenv(PROJECT_ROOT / ".env")

from tradingagents.graph.trading_graph import TradingAgentsGraph
from tradingagents.default_config import DEFAULT_CONFIG

# ─── Page Config ────────────────────────────────────────────────────────────
st.set_page_config(
    page_title="TradingAgents",
    page_icon="📈",
    layout="wide",
    initial_sidebar_state="expanded",
)

# ─── Authentication Gate ────────────────────────────────────────────────────
_APP_PASSWORD = os.getenv("APP_PASSWORD", "")
if _APP_PASSWORD:
    if not st.session_state.get("authenticated"):
        st.markdown("""
        <div style="display:flex;justify-content:center;align-items:center;min-height:60vh;">
            <div style="text-align:center;max-width:400px;width:100%;">
                <h1 style="font-size:2.5rem;margin-bottom:0.2rem;">📈</h1>
                <h2 style="opacity:0.8;margin-bottom:1.5rem;">TradingAgents</h2>
            </div>
        </div>
        """, unsafe_allow_html=True)
        col1, col2, col3 = st.columns([1, 1, 1])
        with col2:
            pw = st.text_input("🔒 Enter password to continue", type="password", key="login_pw")
            if pw:
                if pw == _APP_PASSWORD:
                    st.session_state.authenticated = True
                    st.rerun()
                else:
                    st.error("Wrong password")
        st.stop()

# ─── Custom CSS ─────────────────────────────────────────────────────────────
st.markdown("""
<style>
    @import url('https://fonts.googleapis.com/css2?family=Inter:wght@300;400;500;600;700&display=swap');
    .stApp { font-family: 'Inter', sans-serif; }
    .main-header {
        background: linear-gradient(135deg, #0f2027 0%, #203a43 50%, #2c5364 100%);
        padding: 1.5rem 2rem; border-radius: 12px; margin-bottom: 1.5rem; color: white;
    }
    .main-header h1 {
        margin: 0; font-size: 1.8rem; font-weight: 700;
        background: linear-gradient(90deg, #00d2ff, #3a7bd5);
        -webkit-background-clip: text; -webkit-text-fill-color: transparent;
    }
    .main-header p { margin: 0.3rem 0 0 0; font-size: 0.9rem; opacity: 0.7; }
    section[data-testid="stSidebar"] .stButton > button {
        width: 100%;
        background: linear-gradient(135deg, #00d2ff, #3a7bd5);
        color: white; border: none; font-weight: 600;
        padding: 0.7rem; border-radius: 8px; font-size: 1rem;
        transition: all 0.3s ease;
    }
    section[data-testid="stSidebar"] .stButton > button:hover {
        transform: translateY(-1px);
        box-shadow: 0 4px 15px rgba(58,123,213,0.4);
    }
</style>
""", unsafe_allow_html=True)

# ─── Constants ──────────────────────────────────────────────────────────────
PROVIDER_OPTIONS = {
    "Custom (OpenAI-compatible)": {
        "url": os.getenv("OPENAI_API_BASE", "https://api.openai.com/v1"),
        "provider_key": "custom",
    },
    "OpenAI": {"url": "https://api.openai.com/v1", "provider_key": "openai"},
    "Google": {"url": "https://generativelanguage.googleapis.com/v1", "provider_key": "google"},
    "Anthropic": {"url": "https://api.anthropic.com/", "provider_key": "anthropic"},
    "xAI": {"url": "https://api.x.ai/v1", "provider_key": "xai"},
    "OpenRouter": {"url": "https://openrouter.ai/api/v1", "provider_key": "openrouter"},
    "Ollama": {"url": "http://localhost:11434/v1", "provider_key": "ollama"},
}

PRESET_MODELS = {
    "openai": {"quick": ["gpt-5-mini", "gpt-5-nano", "gpt-5.4", "gpt-4.1"], "deep": ["gpt-5.4", "gpt-5.2", "gpt-5-mini", "gpt-5.4-pro"]},
    "anthropic": {"quick": ["claude-sonnet-4-6", "claude-haiku-4-5", "claude-sonnet-4-5"], "deep": ["claude-opus-4-6", "claude-opus-4-5", "claude-sonnet-4-6"]},
    "google": {"quick": ["gemini-3-flash-preview", "gemini-2.5-flash", "gemini-2.5-flash-lite"], "deep": ["gemini-3.1-pro-preview", "gemini-3-flash-preview", "gemini-2.5-pro"]},
    "xai": {"quick": ["grok-4-1-fast-non-reasoning", "grok-4-fast-non-reasoning"], "deep": ["grok-4-0709", "grok-4-1-fast-reasoning"]},
    "openrouter": {"quick": ["nvidia/nemotron-3-nano-30b-a3b:free"], "deep": ["z-ai/glm-4.5-air:free"]},
    "ollama": {"quick": ["qwen3:latest", "gpt-oss:latest"], "deep": ["glm-4.7-flash:latest", "gpt-oss:latest"]},
}

ANALYST_LABELS = {"market": "📊 Market Analyst", "social": "💬 Social Media Analyst", "news": "📰 News Analyst", "fundamentals": "📋 Fundamentals Analyst"}
DEPTH_OPTIONS = {"Shallow (1 round)": 1, "Medium (3 rounds)": 3, "Deep (5 rounds)": 5}
ANALYST_AGENT_MAP = {"market": "Market Analyst", "social": "Social Analyst", "news": "News Analyst", "fundamentals": "Fundamentals Analyst"}
ANALYST_REPORT_KEYS = {"market": "market_report", "social": "sentiment_report", "news": "news_report", "fundamentals": "fundamentals_report"}

# ─── Session State Init ────────────────────────────────────────────────────
defaults = {"running": False, "error": None, "agent_status": {}, "reports": {}, "decision": None}
for k, v in defaults.items():
    if k not in st.session_state:
        st.session_state[k] = v

# ─── Header ─────────────────────────────────────────────────────────────────
st.markdown('<div class="main-header"><h1>📈 TradingAgents</h1><p>Multi-Agent LLM Financial Trading Framework</p></div>', unsafe_allow_html=True)

# ─── Sidebar ────────────────────────────────────────────────────────────────
with st.sidebar:
    st.markdown("## ⚙️ Configuration")
    ticker = st.text_input("Ticker Symbol", value="SPY", placeholder="e.g. SPY, AAPL, NVDA")
    analysis_date = st.date_input("Analysis Date", value=datetime.date.today(), max_value=datetime.date.today())

    st.markdown("#### Analyst Team")
    selected_analysts = [k for k, label in ANALYST_LABELS.items() if st.checkbox(label, value=True, key=f"analyst_{k}")]

    depth_label = st.selectbox("Research Depth", list(DEPTH_OPTIONS.keys()), index=0)
    research_depth = DEPTH_OPTIONS[depth_label]

    st.markdown("---")
    st.markdown("#### LLM Provider")
    provider_name = st.selectbox("Provider", list(PROVIDER_OPTIONS.keys()), index=0)
    provider_info = PROVIDER_OPTIONS[provider_name]
    provider_key = provider_info["provider_key"]
    st.caption(f"URL: `{provider_info['url']}`")

    st.markdown("#### Models")
    if provider_key == "custom":
        quick_model = st.text_input("Quick-Thinking Model", value="gemini-3-flash", placeholder="Model name on your proxy")
        deep_model = st.text_input("Deep-Thinking Model", value="gemini-3.1-pro-high", placeholder="Model name on your proxy")
    elif provider_key in PRESET_MODELS:
        presets = PRESET_MODELS[provider_key]
        quick_model = st.selectbox("Quick-Thinking Model", presets["quick"], index=0)
        deep_model = st.selectbox("Deep-Thinking Model", presets["deep"], index=0)
    else:
        quick_model = st.text_input("Quick-Thinking Model", value="gpt-5-mini")
        deep_model = st.text_input("Deep-Thinking Model", value="gpt-5.2")

    st.markdown("---")
    can_run = len(selected_analysts) > 0 and len(ticker.strip()) > 0
    run_clicked = st.button(
        "🚀 Run Analysis" if not st.session_state.running else "⏳ Running...",
        disabled=st.session_state.running or not can_run,
        use_container_width=True,
    )

# ─── Analysis Runner ────────────────────────────────────────────────────────
def run_analysis(ticker, date_str, analysts, depth, pkey, backend_url, qmodel, dmodel):
    """Background thread — uses add_script_run_ctx so st.session_state works."""
    try:
        config = DEFAULT_CONFIG.copy()
        config["llm_provider"] = pkey
        config["backend_url"] = backend_url
        config["quick_think_llm"] = qmodel
        config["deep_think_llm"] = dmodel
        config["max_debate_rounds"] = depth
        config["max_risk_discuss_rounds"] = depth

        graph = TradingAgentsGraph(selected_analysts=analysts, config=config, debug=True)

        # Init agent statuses
        agent_names = [ANALYST_AGENT_MAP[a] for a in analysts]
        agent_names += ["Bull Researcher", "Bear Researcher", "Research Manager",
                        "Trader", "Aggressive Analyst", "Conservative Analyst",
                        "Neutral Analyst", "Portfolio Manager"]
        st.session_state.agent_status = {n: "pending" for n in agent_names}
        st.session_state.reports = {}
        st.session_state.decision = None
        if analysts:
            st.session_state.agent_status[ANALYST_AGENT_MAP[analysts[0]]] = "running"

        init_state = graph.propagator.create_initial_state(ticker, date_str)
        args = graph.propagator.get_graph_args()
        analyst_order = [a for a in ["market", "social", "news", "fundamentals"] if a in analysts]
        trace = []

        for chunk in graph.graph.stream(init_state, **args):
            if not st.session_state.running:
                break

            # Analyst reports
            for akey in analyst_order:
                rkey = ANALYST_REPORT_KEYS[akey]
                aname = ANALYST_AGENT_MAP[akey]
                if chunk.get(rkey):
                    st.session_state.reports[rkey] = chunk[rkey]
                    st.session_state.agent_status[aname] = "done"
                    idx = analyst_order.index(akey)
                    if idx + 1 < len(analyst_order):
                        nxt = ANALYST_AGENT_MAP[analyst_order[idx + 1]]
                        if st.session_state.agent_status.get(nxt) == "pending":
                            st.session_state.agent_status[nxt] = "running"

            # All analysts done -> research
            if all(st.session_state.agent_status.get(ANALYST_AGENT_MAP[a]) == "done" for a in analyst_order):
                if st.session_state.agent_status.get("Bull Researcher") == "pending":
                    st.session_state.agent_status["Bull Researcher"] = "running"
                    st.session_state.agent_status["Bear Researcher"] = "running"

            # Research team
            if chunk.get("investment_debate_state"):
                d = chunk["investment_debate_state"]
                if d.get("bull_history", "").strip():
                    st.session_state.reports["bull_research"] = d["bull_history"]
                    st.session_state.agent_status["Bull Researcher"] = "done"
                if d.get("bear_history", "").strip():
                    st.session_state.reports["bear_research"] = d["bear_history"]
                    st.session_state.agent_status["Bear Researcher"] = "done"
                if d.get("judge_decision", "").strip():
                    st.session_state.reports["research_decision"] = d["judge_decision"]
                    st.session_state.agent_status["Research Manager"] = "done"
                    st.session_state.agent_status["Trader"] = "running"

            # Trader
            if chunk.get("trader_investment_plan"):
                st.session_state.reports["trader_plan"] = chunk["trader_investment_plan"]
                st.session_state.agent_status["Trader"] = "done"
                st.session_state.agent_status["Aggressive Analyst"] = "running"

            # Risk team
            if chunk.get("risk_debate_state"):
                r = chunk["risk_debate_state"]
                if r.get("aggressive_history", "").strip():
                    st.session_state.reports["risk_aggressive"] = r["aggressive_history"]
                    st.session_state.agent_status["Aggressive Analyst"] = "done"
                if r.get("conservative_history", "").strip():
                    st.session_state.reports["risk_conservative"] = r["conservative_history"]
                    st.session_state.agent_status["Conservative Analyst"] = "done"
                if r.get("neutral_history", "").strip():
                    st.session_state.reports["risk_neutral"] = r["neutral_history"]
                    st.session_state.agent_status["Neutral Analyst"] = "done"
                if r.get("judge_decision", "").strip():
                    st.session_state.reports["portfolio_decision"] = r["judge_decision"]
                    st.session_state.agent_status["Portfolio Manager"] = "done"

            if chunk.get("final_trade_decision"):
                st.session_state.decision = chunk["final_trade_decision"]

            trace.append(chunk)

        # Final signal
        if trace and trace[-1].get("final_trade_decision"):
            st.session_state.decision = graph.process_signal(trace[-1]["final_trade_decision"])

        # Mark all done
        for n in st.session_state.agent_status:
            if st.session_state.agent_status[n] != "error":
                st.session_state.agent_status[n] = "done"

    except Exception as e:
        import traceback
        traceback.print_exc()
        st.session_state.error = str(e)
    finally:
        st.session_state.running = False

# ─── Start Analysis ─────────────────────────────────────────────────────────
if run_clicked and not st.session_state.running:
    st.session_state.running = True
    st.session_state.error = None
    st.session_state.reports = {}
    st.session_state.decision = None
    st.session_state.agent_status = {}

    t = threading.Thread(
        target=run_analysis,
        args=(ticker.strip().upper(), analysis_date.strftime("%Y-%m-%d"),
              selected_analysts, research_depth, provider_key,
              provider_info["url"], quick_model, deep_model),
        daemon=True,
    )
    add_script_run_ctx(t)  # Give the thread Streamlit's context
    t.start()
    st.rerun()

# ─── Display ────────────────────────────────────────────────────────────────
if st.session_state.error:
    st.error(f"❌ Analysis failed: {st.session_state.error}")

if st.session_state.running or st.session_state.agent_status:
    st.markdown("### 🔄 Agent Progress")
    teams = {
        "📊 Analyst Team": ["Market Analyst", "Social Analyst", "News Analyst", "Fundamentals Analyst"],
        "🔬 Research Team": ["Bull Researcher", "Bear Researcher", "Research Manager"],
        "💹 Trading Team": ["Trader"],
        "⚠️ Risk Mgmt": ["Aggressive Analyst", "Conservative Analyst", "Neutral Analyst"],
        "📁 Portfolio": ["Portfolio Manager"],
    }
    cols = st.columns(len(teams))
    for col, (team, agents) in zip(cols, teams.items()):
        with col:
            st.markdown(f"**{team}**")
            for agent in agents:
                if agent not in st.session_state.agent_status:
                    continue
                status = st.session_state.agent_status[agent]
                icon = {"pending": "⏳", "running": "🔄", "done": "✅", "error": "❌"}.get(status, "⏳")
                st.markdown(f"{icon} {agent}")

    st.markdown("---")
    st.markdown("### 📋 Analysis Reports")
    reps = st.session_state.reports

    # Analyst reports
    ar_titles = {"market_report": "📊 Market Analysis", "sentiment_report": "💬 Social Sentiment", "news_report": "📰 News Analysis", "fundamentals_report": "📋 Fundamentals Analysis"}
    ar = {k: v for k, v in ar_titles.items() if k in reps}
    if ar:
        st.markdown("#### I. Analyst Team Reports")
        for k, title in ar.items():
            with st.expander(title, expanded=False):
                st.markdown(reps[k])

    # Research
    rr = {"bull_research": "🐂 Bull Researcher", "bear_research": "🐻 Bear Researcher", "research_decision": "⚖️ Research Manager"}
    rr_found = {k: v for k, v in rr.items() if k in reps}
    if rr_found:
        st.markdown("#### II. Research Team Decision")
        for k, title in rr_found.items():
            with st.expander(title, expanded=False):
                st.markdown(reps[k])

    # Trader
    if "trader_plan" in reps:
        st.markdown("#### III. Trading Team Plan")
        with st.expander("💹 Trader", expanded=False):
            st.markdown(reps["trader_plan"])

    # Risk
    risk = {"risk_aggressive": "🔥 Aggressive", "risk_conservative": "🛡️ Conservative", "risk_neutral": "⚖️ Neutral"}
    risk_found = {k: v for k, v in risk.items() if k in reps}
    if risk_found:
        st.markdown("#### IV. Risk Management")
        for k, title in risk_found.items():
            with st.expander(title, expanded=False):
                st.markdown(reps[k])

    # Portfolio
    if "portfolio_decision" in reps:
        st.markdown("#### V. Portfolio Manager Decision")
        with st.expander("📁 Portfolio Manager", expanded=True):
            st.markdown(reps["portfolio_decision"])

    # Final decision
    if st.session_state.decision:
        st.markdown("---")
        st.markdown("### 🎯 Final Decision")
        dec = st.session_state.decision
        if isinstance(dec, dict):
            c1, c2, c3 = st.columns(3)
            with c1: st.metric("Action", str(dec.get("action", "N/A")).upper())
            with c2: st.metric("Confidence", dec.get("confidence", "N/A"))
            with c3: st.metric("Reasoning", str(dec.get("reasoning", "N/A"))[:50])
        else:
            st.info(str(dec))

    # Auto-refresh
    if st.session_state.running:
        time.sleep(2)
        st.rerun()

elif not st.session_state.agent_status:
    st.markdown("""
    <div style="text-align: center; padding: 3rem 1rem;">
        <h2 style="opacity: 0.8;">Welcome to TradingAgents Web UI</h2>
        <p style="opacity: 0.5; font-size: 1.1rem;">
            Configure your analysis in the sidebar and click <strong>Run Analysis</strong> to begin.
        </p>
        <div style="margin-top: 2rem; opacity: 0.4;">
            <p>I. Analyst Team → II. Research Team → III. Trader → IV. Risk Management → V. Portfolio Manager</p>
        </div>
    </div>
    """, unsafe_allow_html=True)
