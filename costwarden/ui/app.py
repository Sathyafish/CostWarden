import pandas as pd
import streamlit as st

from costwarden.accounts import load_accounts
from costwarden.agents.qa import answer
from costwarden.client import get_client
from costwarden.config import load_settings
from costwarden.llm import get_llm
from costwarden.store import get_store
from costwarden.store.demo import seed_history
from costwarden.ui.view_models import account_rows, savings_trend

st.set_page_config(page_title="CostWarden", layout="wide")


@st.cache_resource
def services():
    s = load_settings()
    store = get_store(s)
    return s, store, get_client(s, store), get_llm(s)


settings, store, client, llm = services()
accounts = load_accounts(settings.accounts_file)

st.title("CostWarden")
st.caption(f"Runtime: {settings.agent_runtime} · Store: {settings.store_backend} · LLM: {settings.llm_provider}")
if settings.store_backend == "memory":
    if st.sidebar.button("Load demo history"):
        st.sidebar.success(f"Seeded {seed_history(store)} cleanups")

tab_dash, tab_ask, tab_run = st.tabs(["Dashboard", "Ask", "Run and approvals"])

# ---- Dashboard ---------------------------------------------------------------
with tab_dash:
    choice = st.selectbox("Account", ["All accounts"] + [f"{a.name} ({a.id})" for a in accounts])
    acct_id = None if choice == "All accounts" else choice.rsplit("(", 1)[1].rstrip(")")
    try:
        m = store.metrics(acct_id)
    except Exception as e:  # noqa: BLE001 - e.g. no AWS credentials or table missing
        st.error(f"Cannot read the history store: {e}")
        st.stop()
    c1, c2, c3, c4 = st.columns(4)
    c1.metric("Cost avoided (monthly run-rate)", f"${m.cost_avoided_monthly:,.2f}")
    c2.metric("Cost avoided (cumulative)", f"${m.cost_avoided_cumulative:,.2f}")
    c3.metric("Cleanups", m.cleanups)
    c4.metric("Open PRs", m.open_prs)
    left, right = st.columns(2)
    with left:
        st.subheader("Accounts")
        st.dataframe(pd.DataFrame(account_rows(store, accounts)), hide_index=True, use_container_width=True)
        st.subheader("Cleanups by status")
        st.bar_chart(pd.Series(m.counts_by_status, name="cleanups"))
    with right:
        st.subheader("Savings by resource type")
        if m.by_resource_type:
            st.bar_chart(pd.DataFrame(m.by_resource_type).T["savings"])
        else:
            st.info("No cleanups recorded yet.")
        st.subheader("Cost avoided over time")
        trend = savings_trend(store, acct_id)
        if trend:
            st.line_chart(pd.DataFrame(trend, columns=["date", "monthly run-rate avoided"]).set_index("date"))
        else:
            st.info("No merged cleanups yet.")

# ---- Ask ---------------------------------------------------------------------
with tab_ask:
    st.write("Ask about past cleanups. Answers come from the history table.")
    cols = st.columns(3)
    examples = ["What was the last cleanup and how much cost was avoided?",
                "How much cost have we avoided in total?", "Which cleanups are still open?"]
    clicked = next((q for c, q in zip(cols, examples) if c.button(q)), None)
    q = st.chat_input("Ask a question") or clicked
    if q:
        with st.chat_message("user"):
            st.write(q)
        with st.chat_message("assistant"):
            a = answer(q, store, llm)
            st.write(a.text)
            if a.tool:
                st.caption(f"Tool: {a.tool}")

# ---- Run and approvals -------------------------------------------------------
with tab_run:
    if st.button("Start cleanup run"):
        with st.spinner("Discovering and planning..."):
            try:
                st.session_state["status"] = client.start()
            except Exception as e:  # noqa: BLE001
                st.error(f"Run failed to start: {e}")
    status = st.session_state.get("status")
    if status:
        run_id = status["run_id"]
        st.write(f"Run `{run_id}`")
        pend = status.get("pending")
        if status.get("errors"):
            st.warning("Errors: " + "; ".join(f"{a}: {e}" for a, e in status["errors"].items()))

        def act(value):
            try:
                st.session_state["status"] = client.resume(run_id, value)
            except Exception as e:  # noqa: BLE001
                st.error(f"Could not continue the run: {e}")
            st.rerun()

        if pend and pend["type"] == "approve_diff":
            st.subheader(f"Approve changes for {pend['account_name']} ({pend['account_id']})")
            st.metric("Estimated savings per month", f"${pend['savings_usd']:,.2f}")
            st.markdown(pend["summary"] or "_No risk summary._")
            exclude = st.multiselect("Exclude resources", [e["resource_id"] for e in pend["edited"]])
            st.code(pend["diff"], language="diff")
            st.caption(pend["validation"])
            if pend["unmapped"]:
                st.warning("Not changed: " + ", ".join(u["finding"]["resource_id"] for u in pend["unmapped"]))
            b1, b2 = st.columns(2)
            if b1.button("Approve and open draft PR", type="primary"):
                act({"approved": True, "exclude": exclude})
            if b2.button("Reject"):
                act({"approved": False})
        elif pend and pend["type"] == "confirm_merge":
            st.subheader(f"Confirm merge for {pend['account_id']}")
            st.markdown(f"Draft PR: {pend['pr_url']}")
            b1, b2 = st.columns(2)
            if b1.button("PR is merged, run plan", type="primary"):
                act({"merged": True})
            if b2.button("Not merged yet"):
                act({"merged": False})
        elif pend and pend["type"] == "handle_error":
            st.error(f"{pend['step']} failed for {pend['account_id']}: {pend['error']}")
            b1, b2 = st.columns(2)
            if b1.button("Retry", type="primary"):
                act({"action": "retry"})
            if b2.button("Skip this account"):
                act({"action": "skip"})
        elif status["done"]:
            st.success("Run complete")
        st.json({"findings": status["findings"], "outcomes": status["outcomes"], "pr_urls": status["pr_urls"],
                 "plans": status["plans"]})
