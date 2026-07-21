import streamlit as st
import pandas as pd
from datetime import datetime
import os

st.set_page_config(
    page_title="MiaoGo MVP",
    page_icon="M",
    layout="wide"
)

@st.cache_data
def load_data():
    df = pd.read_csv("stores.csv")
    df.columns = [c.strip() for c in df.columns]
    return df

stores = load_data()

st.markdown("""
<style>
.stApp {
    background: linear-gradient(135deg, #0b1020 0%, #15122b 45%, #241447 100%);
    color: #F8F7FF;
}

.block-container {
    padding-top: 2rem;
    padding-bottom: 4rem;
    max-width: 1200px;
}

h1, h2, h3, h4, p, label, span, div {
    color: #F8F7FF;
}

.hero {
    padding: 34px 36px;
    border-radius: 28px;
    background: linear-gradient(135deg, rgba(125, 78, 255, 0.35), rgba(255, 255, 255, 0.06));
    border: 1px solid rgba(255,255,255,0.18);
    box-shadow: 0px 18px 45px rgba(0,0,0,0.28);
    margin-bottom: 28px;
}

.logo {
    width: 78px;
    height: 78px;
    border-radius: 22px;
    background: linear-gradient(135deg, #8F5BFF, #FF7AC8);
    display: flex;
    align-items: center;
    justify-content: center;
    font-size: 30px;
    font-weight: 900;
    color: white;
    margin-bottom: 18px;
}

.hero-title {
    font-size: 54px;
    font-weight: 900;
    letter-spacing: -1.5px;
    margin-bottom: 4px;
}

.hero-subtitle {
    font-size: 20px;
    color: #D7D0FF;
    max-width: 850px;
    line-height: 1.5;
}

.section-card {
    background: rgba(255,255,255,0.08);
    border: 1px solid rgba(255,255,255,0.14);
    border-radius: 24px;
    padding: 24px;
    margin: 18px 0;
    box-shadow: 0px 14px 35px rgba(0,0,0,0.22);
}

.route-card {
    background: rgba(255,255,255,0.10);
    border: 1px solid rgba(255,255,255,0.16);
    border-radius: 22px;
    padding: 22px;
    min-height: 260px;
    box-shadow: 0px 10px 28px rgba(0,0,0,0.20);
}

.route-number {
    background: #8F5BFF;
    color: white;
    width: 38px;
    height: 38px;
    border-radius: 12px;
    display: flex;
    align-items: center;
    justify-content: center;
    font-weight: 800;
    margin-bottom: 14px;
}

.store-name {
    font-size: 23px;
    font-weight: 850;
    color: white;
    margin-bottom: 8px;
}

.meta {
    color: #BDB4EA;
    font-size: 14px;
    margin-bottom: 14px;
}

.reason {
    color: #F0EDFF;
    font-size: 15px;
    line-height: 1.45;
}

.mission-card {
    background: rgba(255,255,255,0.09);
    border-left: 5px solid #FF7AC8;
    border-radius: 18px;
    padding: 18px 20px;
    margin-bottom: 14px;
}

.badge {
    display: inline-block;
    padding: 6px 11px;
    border-radius: 999px;
    background: rgba(143, 91, 255, 0.22);
    color: #DCD4FF;
    font-size: 13px;
    font-weight: 700;
    margin-bottom: 10px;
}

.note-box {
    background: rgba(255, 122, 200, 0.12);
    border: 1px solid rgba(255, 122, 200, 0.28);
    border-radius: 18px;
    padding: 18px 20px;
    margin: 16px 0;
}

.metric-box {
    background: rgba(255,255,255,0.08);
    border: 1px solid rgba(255,255,255,0.14);
    border-radius: 18px;
    padding: 16px;
    text-align: center;
}

.metric-num {
    font-size: 30px;
    font-weight: 900;
    color: #FF7AC8;
}

.metric-label {
    color: #D7D0FF;
    font-size: 14px;
}

[data-testid="stMetricValue"] {
    color: #FF7AC8;
}

.stButton > button {
    background: linear-gradient(135deg, #8F5BFF, #FF7AC8);
    color: white;
    border: none;
    border-radius: 14px;
    padding: 0.7rem 1.2rem;
    font-weight: 800;
}

.stButton > button:hover {
    border: none;
    color: white;
    filter: brightness(1.08);
}

div[data-testid="stDataFrame"] {
    background: white;
    border-radius: 16px;
}

input, textarea {
    color: #111 !important;
}

.stSelectbox div, .stNumberInput div, .stTextInput div, .stTextArea div {
    color: #111;
}
</style>
""", unsafe_allow_html=True)


def safe(row, col, default=""):
    try:
        value = row.get(col, default)
        if pd.isna(value):
            return default
        return str(value)
    except Exception:
        return default


def score_store(row, budget, style, goal, priority):
    score = 0
    text = " ".join([
        safe(row, "store_name"),
        safe(row, "category"),
        safe(row, "sub_category"),
        safe(row, "best_for"),
        safe(row, "style_tags"),
        safe(row, "target_user"),
        safe(row, "keywords"),
        safe(row, "ai_reason")
    ]).lower()

    user_text = f"{style} {goal} {priority}".lower()
    for word in user_text.split():
        if len(word) > 2 and word in text:
            score += 3

    try:
        min_b = float(row.get("budget_min_rmb", 0))
        max_b = float(row.get("budget_max_rmb", 99999))
        if min_b <= budget <= max_b:
            score += 6
        elif budget >= min_b * 0.7 and budget <= max_b * 1.35:
            score += 3
    except Exception:
        pass

    category = safe(row, "category").lower()

    if any(x in user_text for x in ["outfit", "clothes", "fashion", "cute", "style"]):
        if any(x in category for x in ["fashion", "sportswear", "beauty"]):
            score += 5

    if any(x in user_text for x in ["shoe", "shoes", "sneaker", "sneakers"]):
        if any(x in text for x in ["shoe", "sneaker", "nike", "sportswear"]):
            score += 6

    if any(x in user_text for x in ["beauty", "makeup", "skincare"]):
        if "beauty" in category or "skincare" in text or "makeup" in text:
            score += 6

    if "gift" in user_text:
        if "gift" in text or "lifestyle" in category or "entertainment" in category:
            score += 6

    return score


def generate_route(df, budget, available_time, style, goal, priority):
    temp = df.copy()
    temp["score"] = temp.apply(lambda row: score_store(row, budget, style, goal, priority), axis=1)
    temp = temp.sort_values("score", ascending=False)

    route = []
    total_time = 0

    for _, row in temp.iterrows():
        estimated = int(row.get("estimated_time_min", 20))
        if total_time + estimated <= available_time:
            route.append(row)
            total_time += estimated
        if len(route) == 4:
            break

    if len(route) < 3:
        route = [row for _, row in temp.head(4).iterrows()]
        total_time = sum(int(r.get("estimated_time_min", 20)) for r in route)

    return route, total_time


def adapt_route(change_text, df):
    text = change_text.lower()

    if any(x in text for x in ["nike", "shoe", "sneaker"]):
        focus = "Shoes and sporty casual style"
        action = "MiaoGo noticed stronger interest in shoes, so it adds a shoe-focused bonus mission and adjusts the next stops."
        bonus = "Try 2 sneaker styles and compare comfort, price, and outfit match."
        reward = "Extra shoe coupon or bonus points"
        mask = df.apply(lambda r: any(x in str(r).lower() for x in ["nike", "shoe", "sneaker", "sportswear"]), axis=1)

    elif any(x in text for x in ["beauty", "makeup", "skincare", "sephora"]):
        focus = "Beauty and skincare"
        action = "MiaoGo detected interest in beauty products and shifts the journey toward matching beauty stops."
        bonus = "Compare 2 beauty items and choose one that matches your outfit or skin need."
        reward = "Beauty sample or skincare coupon"
        mask = df.apply(lambda r: any(x in str(r).lower() for x in ["beauty", "makeup", "skincare", "sephora"]), axis=1)

    elif any(x in text for x in ["tired", "coffee", "hungry", "break"]):
        focus = "Rest and food break"
        action = "MiaoGo detects fatigue and adds a short recovery stop before continuing the route."
        bonus = "Take a short break and check in before continuing."
        reward = "Coffee break points"
        mask = df.apply(lambda r: any(x in str(r).lower() for x in ["coffee", "food", "break", "drink"]), axis=1)

    else:
        focus = "Changed shopping behavior"
        action = "MiaoGo adapts the route based on the user’s real-time behavior."
        bonus = "Complete one adaptive mission based on your current interest."
        reward = "Adaptive journey points"
        mask = df.apply(lambda r: True, axis=1)

    suggested = df[mask].head(3)
    if suggested.empty:
        suggested = df.head(3)

    return focus, action, bonus, reward, suggested


st.markdown("""
<div class="hero">
    <div class="logo">M</div>
    <div class="hero-title">MiaoGo 喵逛</div>
    <div class="hero-subtitle">
        An interactive AI shopping journey MVP for Yintai / Miaojie. 
        Users enter a budget, time, style, and shopping goal. MiaoGo generates a mall route, missions, rewards, and real-time journey updates.
    </div>
</div>
""", unsafe_allow_html=True)

with st.container():
    st.markdown('<div class="section-card">', unsafe_allow_html=True)
    st.subheader("Create your shopping journey")

    col1, col2, col3 = st.columns(3)
    with col1:
        budget = st.number_input("Budget / RMB", min_value=50, max_value=5000, value=200, step=50)
    with col2:
        available_time = st.slider("Available time", 30, 240, 120, 15)
    with col3:
        priority = st.selectbox(
            "Main priority",
            ["Best value", "Trendy style", "Beauty and skincare", "Gift shopping", "Fast route", "High-end experience"]
        )

    col4, col5 = st.columns(2)
    with col4:
        style = st.text_input("Style", value="cute weekend outfit")
    with col5:
        goal = st.text_input("Shopping goal", value="outfit and shoes")

    generate = st.button("Generate my MiaoGo route", type="primary")
    st.markdown('</div>', unsafe_allow_html=True)

if generate:
    route, total_time = generate_route(stores, budget, available_time, style, goal, priority)
    st.session_state["route"] = route
    st.session_state["total_time"] = total_time
    st.session_state["generated"] = True

if st.session_state.get("generated", False):
    route = st.session_state["route"]
    total_time = st.session_state["total_time"]

    st.markdown('<div class="section-card">', unsafe_allow_html=True)
    st.subheader("Your personalized AI route")

    m1, m2, m3, m4 = st.columns(4)
    m1.markdown(f'<div class="metric-box"><div class="metric-num">{len(route)}</div><div class="metric-label">Stops</div></div>', unsafe_allow_html=True)
    m2.markdown(f'<div class="metric-box"><div class="metric-num">{total_time}</div><div class="metric-label">Minutes</div></div>', unsafe_allow_html=True)
    m3.markdown(f'<div class="metric-box"><div class="metric-num">¥{budget}</div><div class="metric-label">Budget</div></div>', unsafe_allow_html=True)
    m4.markdown(f'<div class="metric-box"><div class="metric-num">AI</div><div class="metric-label">Adaptive route</div></div>', unsafe_allow_html=True)

    st.markdown("<br>", unsafe_allow_html=True)

    cols = st.columns(4)
    for i, row in enumerate(route):
        with cols[i]:
            st.markdown(f"""
            <div class="route-card">
                <div class="route-number">{i+1}</div>
                <div class="store-name">{safe(row, "store_name")}</div>
                <div class="meta">{safe(row, "category")} · {safe(row, "zone")} · {safe(row, "floor")} · {safe(row, "estimated_time_min")} min</div>
                <div class="reason">{safe(row, "ai_reason", safe(row, "best_for"))}</div>
            </div>
            """, unsafe_allow_html=True)

    st.markdown('</div>', unsafe_allow_html=True)

    st.markdown('<div class="section-card">', unsafe_allow_html=True)
    st.subheader("Missions and rewards")

    for i, row in enumerate(route):
        st.markdown(f"""
        <div class="mission-card">
            <div class="badge">Mission {i+1}</div>
            <h4>{safe(row, "store_name")}</h4>
            <p><b>Mission:</b> {safe(row, "mission")}</p>
            <p><b>Reward:</b> {safe(row, "reward")}</p>
            <p><b>Repurchase reminder:</b> {safe(row, "repurchase_trigger")}</p>
        </div>
        """, unsafe_allow_html=True)

    st.markdown('</div>', unsafe_allow_html=True)

    st.markdown('<div class="section-card">', unsafe_allow_html=True)
    st.subheader("Real-time AI adaptation")

    change_text = st.text_input(
        "Tell MiaoGo what changed during the visit",
        value="I spent 25 minutes in Nike because I liked the shoes."
    )

    if st.button("Update route"):
        focus, action, bonus, reward, suggested = adapt_route(change_text, stores)

        st.markdown(f"""
        <div class="note-box">
            <h3>{focus}</h3>
            <p>{action}</p>
            <p><b>Bonus mission:</b> {bonus}</p>
            <p><b>New reward:</b> {reward}</p>
        </div>
        """, unsafe_allow_html=True)

        st.write("Updated next best stops")

        c1, c2, c3 = st.columns(3)
        for col, (_, row) in zip([c1, c2, c3], suggested.iterrows()):
            with col:
                st.markdown(f"""
                <div class="route-card">
                    <div class="store-name">{safe(row, "store_name")}</div>
                    <div class="meta">{safe(row, "category")} · {safe(row, "estimated_time_min")} min</div>
                    <div class="reason">{safe(row, "ai_reason", safe(row, "best_for"))}</div>
                    <br>
                    <div class="reason"><b>Mission:</b> {safe(row, "mission")}</div>
                </div>
                """, unsafe_allow_html=True)

    st.markdown('</div>', unsafe_allow_html=True)

    st.markdown('<div class="section-card">', unsafe_allow_html=True)
    st.subheader("Feedback after testing")

    with st.form("feedback_form"):
        rating = st.slider("Overall rating", 1, 5, 4)
        would_use = st.radio("Would you use this if it existed inside Miaojie?", ["Yes", "Maybe", "No"], horizontal=True)
        open_more = st.radio("Would this make you open Miaojie more often?", ["Yes", "Maybe", "No"], horizontal=True)
        useful_part = st.selectbox(
            "Most useful part",
            ["AI route", "Missions", "Rewards/coupons", "Real-time adaptation", "Repurchase reminder"]
        )
        improvement = st.text_area("What should be improved?")
        submitted = st.form_submit_button("Submit feedback")

        if submitted:
            feedback = pd.DataFrame([{
                "timestamp": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
                "budget": budget,
                "time": available_time,
                "style": style,
                "goal": goal,
                "priority": priority,
                "rating": rating,
                "would_use": would_use,
                "open_more": open_more,
                "useful_part": useful_part,
                "improvement": improvement
            }])

            file_exists = os.path.exists("feedback.csv")
            feedback.to_csv("feedback.csv", mode="a", header=not file_exists, index=False)
            st.success("Feedback saved. Thank you for testing MiaoGo.")

    if os.path.exists("feedback.csv"):
        with open("feedback.csv", "rb") as f:
            st.download_button("Download feedback CSV", f, file_name="miaogo_feedback.csv", mime="text/csv")

    st.markdown('</div>', unsafe_allow_html=True)

else:
    st.markdown("""
    <div class="section-card">
        <h3>How to test the MVP</h3>
        <p>Enter a shopping goal, generate a route, review the missions and rewards, then test real-time adaptation by typing something like: <b>I spent 25 minutes in Nike.</b></p>
    </div>
    """, unsafe_allow_html=True)

    with st.expander("Preview structured mall dataset"):
        st.dataframe(stores.head(20), use_container_width=True)
