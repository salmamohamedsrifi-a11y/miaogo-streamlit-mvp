import streamlit as st
import pandas as pd
from datetime import datetime
import os

st.set_page_config(
    page_title="MiaoGo MVP",
    page_icon="🛍️",
    layout="wide"
)

# -----------------------------
# Load store database
# -----------------------------
@st.cache_data
def load_data():
    df = pd.read_csv("stores.csv")
    df.columns = [c.strip() for c in df.columns]
    return df

stores = load_data()

# -----------------------------
# Styling
# -----------------------------
st.markdown("""
<style>
    .main-title {
        font-size: 44px;
        font-weight: 800;
        color: #2B145F;
        margin-bottom: 0px;
    }
    .subtitle {
        font-size: 18px;
        color: #555;
        margin-bottom: 25px;
    }
    .card {
        background-color: #FFFFFF;
        border: 1px solid #E7E2F3;
        border-radius: 18px;
        padding: 20px;
        margin-bottom: 16px;
        box-shadow: 0 2px 12px rgba(43, 20, 95, 0.06);
    }
    .purple-box {
        background-color: #F4F0FF;
        border-left: 5px solid #6F35D1;
        border-radius: 12px;
        padding: 18px;
        margin-bottom: 18px;
    }
    .small-label {
        color: #6F35D1;
        font-weight: 700;
        font-size: 14px;
        text-transform: uppercase;
    }
</style>
""", unsafe_allow_html=True)

# -----------------------------
# Helper functions
# -----------------------------
def safe_text(row, col, default=""):
    if col in row and pd.notna(row[col]):
        return str(row[col])
    return default

def score_store(row, budget, style, goal, priority):
    score = 0
    text = " ".join([
        safe_text(row, "store_name"),
        safe_text(row, "category"),
        safe_text(row, "sub_category"),
        safe_text(row, "best_for"),
        safe_text(row, "style_tags"),
        safe_text(row, "target_user"),
        safe_text(row, "keywords"),
        safe_text(row, "ai_reason")
    ]).lower()

    user_words = f"{style} {goal} {priority}".lower().split()

    for word in user_words:
        if len(word) > 2 and word in text:
            score += 3

    try:
        min_b = float(row.get("budget_min_rmb", 0))
        max_b = float(row.get("budget_max_rmb", 99999))
        if min_b <= budget <= max_b:
            score += 5
        elif budget >= min_b * 0.7 and budget <= max_b * 1.3:
            score += 2
    except:
        pass

    category = safe_text(row, "category").lower()

    if "outfit" in goal.lower() or "clothes" in goal.lower() or "fashion" in goal.lower():
        if "fashion" in category or "sportswear" in category:
            score += 5

    if "shoe" in goal.lower() or "sneaker" in goal.lower():
        if "sport" in category or "shoe" in text or "sneaker" in text:
            score += 5

    if "beauty" in goal.lower() or "makeup" in goal.lower() or "skincare" in goal.lower():
        if "beauty" in category:
            score += 5

    if "gift" in goal.lower():
        if "gift" in text or "lifestyle" in category or "entertainment" in category:
            score += 5

    return score

def generate_route(df, budget, available_time, style, goal, priority):
    temp = df.copy()
    temp["score"] = temp.apply(lambda row: score_store(row, budget, style, goal, priority), axis=1)
    temp = temp.sort_values(by="score", ascending=False)

    route = []
    total_time = 0

    for _, row in temp.iterrows():
        estimated = int(row.get("estimated_time_min", 20))
        if total_time + estimated <= available_time:
            route.append(row)
            total_time += estimated
        if len(route) >= 4:
            break

    if len(route) < 3:
        route = [row for _, row in temp.head(4).iterrows()]
        total_time = sum([int(r.get("estimated_time_min", 20)) for r in route])

    return route, total_time

def adapt_route(change_text, current_route, df):
    text = change_text.lower()

    if "nike" in text or "shoe" in text or "sneaker" in text:
        focus = "shoes and sporty casual style"
        bonus = "Bonus mission: Try 2 sneaker styles and compare comfort, price, and outfit match."
        reward = "Extra reward: Unlock a shoe-related coupon or bonus points."
        filtered = df[df.apply(lambda r: "nike" in str(r).lower() or "shoe" in str(r).lower() or "sneaker" in str(r).lower() or "sport" in str(r).lower(), axis=1)]
    elif "beauty" in text or "makeup" in text or "skincare" in text or "sephora" in text:
        focus = "beauty and skincare"
        bonus = "Bonus mission: Compare 2 beauty items and choose one that matches your outfit or skin need."
        reward = "Extra reward: Unlock a beauty sample or skincare coupon."
        filtered = df[df.apply(lambda r: "beauty" in str(r).lower() or "makeup" in str(r).lower() or "skincare" in str(r).lower(), axis=1)]
    elif "hungry" in text or "coffee" in text or "tired" in text or "break" in text:
        focus = "rest and food break"
        bonus = "Bonus mission: Take a short break and check in before continuing the route."
        reward = "Extra reward: Unlock coffee break points."
        filtered = df[df.apply(lambda r: "coffee" in str(r).lower() or "food" in str(r).lower() or "break" in str(r).lower(), axis=1)]
    else:
        focus = "changed shopping behavior"
        bonus = "Bonus mission: MiaoGo adjusts your route based on what you spent more time exploring."
        reward = "Extra reward: Unlock adaptive journey points."
        filtered = df.sort_values(by="store_name").head(3)

    if len(filtered) == 0:
        filtered = df.head(3)

    suggested = filtered.head(3)

    return focus, bonus, reward, suggested

# -----------------------------
# Header
# -----------------------------
st.markdown('<div class="main-title">MiaoGo 喵逛</div>', unsafe_allow_html=True)
st.markdown(
    '<div class="subtitle">AI Shopping Journey Assistant for Yintai / Miaojie — interactive MVP demo</div>',
    unsafe_allow_html=True
)

st.markdown("""
<div class="purple-box">
<b>Prototype note:</b> This MVP uses a structured Yintai mall dataset with prototype assumptions.
It simulates how MiaoGo could later connect to real Miaojie member, store, coupon, location/check-in,
and transaction data through secure APIs.
</div>
""", unsafe_allow_html=True)

# -----------------------------
# User input
# -----------------------------
st.header("1. Create Your Shopping Journey")

col1, col2 = st.columns(2)

with col1:
    budget = st.number_input("Budget / 预算 (RMB)", min_value=50, max_value=5000, value=200, step=50)
    available_time = st.slider("Available time / 可用时间 (minutes)", 30, 240, 120, 15)

with col2:
    style = st.text_input("Style / 风格", value="cute weekend outfit")
    goal = st.text_input("Shopping goal / 购物目标", value="outfit and shoes")
    priority = st.selectbox(
        "Main priority / 主要偏好",
        ["Best value", "Trendy style", "Beauty and skincare", "Gift shopping", "Fast route", "High-end experience"]
    )

generate = st.button("Generate My MiaoGo Route", type="primary")

if generate:
    route, total_time = generate_route(stores, budget, available_time, style, goal, priority)
    st.session_state["route"] = route
    st.session_state["total_time"] = total_time
    st.session_state["generated"] = True

# -----------------------------
# Route result
# -----------------------------
if st.session_state.get("generated", False):
    route = st.session_state["route"]
    total_time = st.session_state["total_time"]

    st.header("2. Your AI-Generated Mall Route")

    st.success(f"MiaoGo created a personalized route for: **{goal}** · Budget: **¥{budget}** · Time: **{available_time} min**")

    cols = st.columns(len(route))

    for i, row in enumerate(route):
        with cols[i]:
            st.markdown(f"""
            <div class="card">
            <div class="small-label">Stop {i+1}</div>
            <h3>{safe_text(row, "store_name")}</h3>
            <b>Category:</b> {safe_text(row, "category")}<br>
            <b>Location:</b> {safe_text(row, "zone")} · {safe_text(row, "floor")}<br>
            <b>Time:</b> {safe_text(row, "estimated_time_min")} min<br><br>
            <b>Why MiaoGo chose it:</b><br>
            {safe_text(row, "ai_reason", safe_text(row, "best_for"))}
            </div>
            """, unsafe_allow_html=True)

    st.subheader("3. Missions + Rewards")

    for i, row in enumerate(route):
        st.markdown(f"""
        <div class="card">
        <b>{i+1}. {safe_text(row, "store_name")}</b><br>
        <b>Mission:</b> {safe_text(row, "mission")}<br>
        <b>Reward:</b> {safe_text(row, "reward")}<br>
        <b>Repurchase reminder:</b> {safe_text(row, "repurchase_trigger")}
        </div>
        """, unsafe_allow_html=True)

    st.info(f"Estimated route time: {total_time} minutes. MiaoGo can adjust this journey during the mall visit.")

    # -----------------------------
    # Real-time adaptation
    # -----------------------------
    st.header("4. Real-Time AI Adaptation")

    change_text = st.text_input(
        "Tell MiaoGo what changed during your visit:",
        value="I spent 25 minutes in Nike because I liked the shoes."
    )

    if st.button("Update My Route"):
        focus, bonus, reward, suggested = adapt_route(change_text, route, stores)

        st.markdown(f"""
        <div class="purple-box">
        <h3>MiaoGo detected a new interest: {focus}</h3>
        <p>{bonus}</p>
        <p>{reward}</p>
        </div>
        """, unsafe_allow_html=True)

        st.subheader("Updated next best stops")

        for _, row in suggested.iterrows():
            st.markdown(f"""
            <div class="card">
            <b>{safe_text(row, "store_name")}</b> — {safe_text(row, "category")}<br>
            <b>Reason:</b> {safe_text(row, "ai_reason", safe_text(row, "best_for"))}<br>
            <b>Mission:</b> {safe_text(row, "mission")}<br>
            <b>Reward:</b> {safe_text(row, "reward")}
            </div>
            """, unsafe_allow_html=True)

    # -----------------------------
    # Feedback
    # -----------------------------
    st.header("5. User Feedback")

    with st.form("feedback_form"):
        rating = st.slider("Overall rating of this experience", 1, 5, 4)
        would_use = st.radio("Would you use this if it existed inside Miaojie?", ["Yes", "Maybe", "No"])
        open_more = st.radio("Would this make you open Miaojie more often?", ["Yes", "Maybe", "No"])
        useful_part = st.selectbox(
            "Most useful part",
            ["AI route", "Missions", "Rewards/coupons", "Real-time adaptation", "Repurchase reminder"]
        )
        improvement = st.text_area("What should we improve?")

        submitted = st.form_submit_button("Submit Feedback")

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

            st.success("Thank you. Your feedback was saved for the MVP testing report.")

    if os.path.exists("feedback.csv"):
        with open("feedback.csv", "rb") as f:
            st.download_button(
                "Download feedback CSV",
                f,
                file_name="miaogo_feedback.csv",
                mime="text/csv"
            )

else:
    st.header("How to test this MVP")
    st.write("""
    1. Enter a budget, time, style, and shopping goal.  
    2. Click **Generate My MiaoGo Route**.  
    3. Review the route, missions, rewards, and repurchase reminder.  
    4. Type a change like **“I spent 25 minutes in Nike”**.  
    5. Submit feedback at the end.  
    """)

    st.subheader("Database preview")
    st.dataframe(stores.head(15), use_container_width=True)
