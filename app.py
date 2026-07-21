import os
import re
from datetime import datetime

import pandas as pd
import streamlit as st

st.set_page_config(
    page_title="MiaoGo MVP",
    page_icon="M",
    layout="wide",
    initial_sidebar_state="collapsed"
)

# -----------------------------
# Data
# -----------------------------
@st.cache_data
def load_data():
    df = pd.read_csv("stores.csv")
    df.columns = [c.strip() for c in df.columns]
    return df

stores = load_data()


def safe(row, col, default=""):
    try:
        value = row.get(col, default)
        if pd.isna(value):
            return default
        return str(value)
    except Exception:
        return default


def num(value, default=0):
    try:
        return int(float(value))
    except Exception:
        return default


def score_store(row, budget, style, goal, priority):
    text = " ".join([
        safe(row, "store_name"),
        safe(row, "category"),
        safe(row, "sub_category"),
        safe(row, "best_for"),
        safe(row, "style_tags"),
        safe(row, "target_user"),
        safe(row, "keywords"),
        safe(row, "ai_reason"),
        safe(row, "mission"),
        safe(row, "reward"),
    ]).lower()

    user_text = f"{style} {goal} {priority}".lower()
    words = re.findall(r"[a-zA-Z\u4e00-\u9fff]+", user_text)
    score = 0

    for word in words:
        if len(word) > 2 and word in text:
            score += 3

    try:
        min_b = float(row.get("budget_min_rmb", 0))
        max_b = float(row.get("budget_max_rmb", 999999))
        if min_b <= budget <= max_b:
            score += 8
        elif budget >= min_b * 0.6 and budget <= max_b * 1.5:
            score += 4
    except Exception:
        pass

    category = safe(row, "category").lower()

    if any(x in user_text for x in ["cute", "outfit", "clothes", "fashion", "style", "casual", "chic"]):
        if any(x in category for x in ["fashion", "sportswear", "beauty", "lifestyle"]):
            score += 8

    if any(x in user_text for x in ["shoe", "shoes", "sneaker", "sneakers"]):
        if any(x in text for x in ["shoe", "shoes", "sneaker", "nike", "sportswear"]):
            score += 8

    if any(x in user_text for x in ["beauty", "makeup", "skincare", "perfume"]):
        if any(x in text for x in ["beauty", "makeup", "skincare", "perfume", "sephora"]):
            score += 8

    if "gift" in user_text:
        if any(x in text for x in ["gift", "toy", "family", "lifestyle", "entertainment"]):
            score += 8

    if "fast" in user_text and num(row.get("estimated_time_min", 20), 20) <= 20:
        score += 4

    if any(x in user_text for x in ["premium", "high-end", "luxury"]):
        if any(x in safe(row, "price_level").lower() for x in ["high", "luxury", "premium"]):
            score += 5

    return score


def generate_route(df, budget, available_time, style, goal, priority):
    temp = df.copy()
    temp["score"] = temp.apply(lambda r: score_store(r, budget, style, goal, priority), axis=1)
    temp = temp.sort_values("score", ascending=False)

    route = []
    total_time = 0

    for _, row in temp.iterrows():
        est = num(row.get("estimated_time_min", 20), 20)
        if total_time + est <= available_time or len(route) < 3:
            route.append(row)
            total_time += est
        if len(route) >= 4:
            break

    if len(route) < 4:
        for _, row in temp.iterrows():
            if safe(row, "store_name") not in [safe(r, "store_name") for r in route]:
                route.append(row)
                total_time += num(row.get("estimated_time_min", 20), 20)
            if len(route) >= 4:
                break

    return route[:4], total_time


def adapt_route(change_text, df):
    t = change_text.lower()

    if any(x in t for x in ["nike", "shoe", "shoes", "sneaker", "sneakers"]):
        title = "MiaoGo updated your route"
        insight = "You spent extra time around shoes, so the journey now focuses on sneaker matching and outfit completion."
        mission = "Try two sneaker styles and compare comfort, price, and outfit match."
        reward = "Unlock a shoe-focused coupon or bonus journey points."
        mask = df.apply(lambda r: any(x in str(r).lower() for x in ["nike", "shoe", "shoes", "sneaker", "sportswear"]), axis=1)
    elif any(x in t for x in ["beauty", "makeup", "skincare", "sephora", "perfume"]):
        title = "MiaoGo updated your route"
        insight = "You showed stronger interest in beauty, so the next stops shift toward skincare, makeup, and matching add-ons."
        mission = "Compare two beauty products and choose one that matches your outfit or skin need."
        reward = "Unlock a beauty sample or skincare coupon."
        mask = df.apply(lambda r: any(x in str(r).lower() for x in ["beauty", "makeup", "skincare", "perfume", "sephora"]), axis=1)
    elif any(x in t for x in ["coffee", "hungry", "tired", "break", "rest"]):
        title = "MiaoGo updated your route"
        insight = "You may need a short break, so the journey adds a rest stop before continuing."
        mission = "Take a short break, check in, and continue with the next best store."
        reward = "Unlock coffee break points."
        mask = df.apply(lambda r: any(x in str(r).lower() for x in ["coffee", "food", "drink", "break"]), axis=1)
    else:
        title = "MiaoGo updated your route"
        insight = "Your behavior changed, so MiaoGo adjusts the journey and recommends the next best stops."
        mission = "Complete one adaptive mission based on your current interest."
        reward = "Unlock adaptive journey points."
        mask = df.apply(lambda r: True, axis=1)

    suggested = df[mask].head(3)
    if suggested.empty:
        suggested = df.head(3)

    return title, insight, mission, reward, suggested


# -----------------------------
# CSS
# -----------------------------
st.markdown("""
<style>
@import url('https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600;700;800;900&display=swap');

:root{
    --ink:#222037;
    --muted:#7E7892;
    --line:#EEE8F7;
    --purple:#7D4CFF;
    --purple2:#9F74FF;
    --pink:#FF7DBB;
    --gold:#FFB832;
    --bg:#FBF8FF;
    --card:#FFFFFF;
}

html, body, [class*="css"] {
    font-family: Inter, -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif;
}

.stApp {
    background:
        radial-gradient(circle at 12% 5%, rgba(255, 218, 238, 0.68), transparent 30%),
        radial-gradient(circle at 88% 2%, rgba(219, 205, 255, 0.75), transparent 28%),
        linear-gradient(180deg, #FFFDFC 0%, #FAF6FF 48%, #FFFFFF 100%);
}

.block-container {
    max-width: 1320px;
    padding-top: 1.1rem;
    padding-bottom: 3rem;
}

#MainMenu, footer, header {visibility: hidden;}
[data-testid="collapsedControl"] {display: none;}

h1, h2, h3, h4, h5, h6, p, label, span, div {
    font-family: Inter, -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif;
    color: var(--ink);
}

.topbar{
    height:66px;
    display:flex;
    align-items:center;
    justify-content:space-between;
    margin-bottom:18px;
}

.brand{
    display:flex;
    align-items:center;
    gap:13px;
}

.logo{
    width:45px;
    height:45px;
    border-radius:15px;
    background:linear-gradient(135deg,var(--purple),var(--pink));
    display:flex;
    align-items:center;
    justify-content:center;
    color:white;
    font-weight:900;
    font-size:22px;
    box-shadow:0 13px 28px rgba(125,76,255,.25);
}

.brand-title{
    font-size:25px;
    font-weight:900;
    letter-spacing:-.6px;
    line-height:1;
}

.brand-sub{
    font-size:13px;
    color:var(--muted);
    margin-top:3px;
}

.top-pill{
    border:1px solid var(--line);
    background:rgba(255,255,255,.8);
    backdrop-filter: blur(10px);
    border-radius:999px;
    padding:10px 15px;
    font-size:13px;
    font-weight:800;
    color:#5D3BD8;
    box-shadow:0 10px 30px rgba(55,34,109,.08);
}

.hero{
    background:rgba(255,255,255,.78);
    border:1px solid var(--line);
    border-radius:34px;
    padding:32px;
    box-shadow:0 24px 60px rgba(55,34,109,.10);
    margin-bottom:22px;
    overflow:hidden;
    position:relative;
}

.hero:after{
    content:"";
    position:absolute;
    width:360px;
    height:360px;
    right:-120px;
    top:-150px;
    border-radius:50%;
    background:linear-gradient(135deg,rgba(125,76,255,.14),rgba(255,125,187,.14));
}

.hero h1{
    font-size:55px;
    line-height:1.03;
    letter-spacing:-2.1px;
    margin:0 0 13px 0;
    font-weight:950;
    max-width:840px;
}

.gradient-text{
    background:linear-gradient(135deg,var(--purple),var(--pink));
    -webkit-background-clip:text;
    -webkit-text-fill-color:transparent;
}

.hero p{
    max-width:800px;
    color:var(--muted);
    font-size:18px;
    line-height:1.58;
    margin:0;
}

.input-card{
    background:white;
    border:1px solid var(--line);
    border-radius:30px;
    padding:24px;
    box-shadow:0 18px 45px rgba(55,34,109,.08);
    margin-bottom:24px;
}

.stButton>button{
    border:0 !important;
    border-radius:999px !important;
    background:linear-gradient(135deg,var(--purple),var(--pink)) !important;
    color:white !important;
    font-weight:900 !important;
    padding:.75rem 1.45rem !important;
    box-shadow:0 14px 28px rgba(125,76,255,.22) !important;
}

.stButton>button:hover{
    filter:brightness(1.04);
    color:white !important;
}

input, textarea{
    color:#222037 !important;
}

div[data-baseweb="select"] span{
    color:#222037 !important;
}

.phone-stage{
    display:flex;
    justify-content:center;
    padding:4px 0 22px 0;
}

.phone{
    width:414px;
    min-height:850px;
    background:#FFFDFD;
    border:13px solid #17151E;
    border-radius:58px;
    padding:22px;
    box-shadow:
        0 38px 80px rgba(33,20,74,.26),
        inset 0 0 0 1px rgba(255,255,255,.35);
    position:relative;
    overflow:hidden;
}

.phone:before{
    content:"";
    position:absolute;
    width:142px;
    height:31px;
    border-radius:0 0 20px 20px;
    top:0;
    left:50%;
    transform:translateX(-50%);
    background:#17151E;
    z-index:20;
}

.status{
    display:flex;
    align-items:center;
    justify-content:space-between;
    padding:1px 11px 17px 11px;
    font-size:13px;
    font-weight:800;
}

.signal{
    display:flex;
    gap:5px;
    align-items:center;
}

.dotline{
    width:18px;
    height:10px;
    border-radius:999px;
    background:#17151E;
    opacity:.15;
}

.greeting{
    display:flex;
    align-items:center;
    justify-content:space-between;
    margin-bottom:17px;
}

.person{
    display:flex;
    align-items:center;
    gap:11px;
}

.avatar{
    width:45px;
    height:45px;
    border-radius:50%;
    background:
        radial-gradient(circle at 50% 24%, #FFD7E8 0 18%, transparent 19%),
        radial-gradient(circle at 50% 78%, #7D4CFF 0 33%, transparent 34%),
        linear-gradient(135deg,#F4EFFF,#FFDDEC);
    border:1px solid #EFE7FF;
}

.hello{
    font-size:20px;
    font-weight:900;
    letter-spacing:-.3px;
}

.hello-sub{
    font-size:12px;
    color:var(--muted);
    margin-top:2px;
}

.points{
    background:#FFF8E8;
    border:1px solid #FFE9B4;
    color:#A76600;
    font-weight:900;
    border-radius:999px;
    padding:8px 12px;
    font-size:14px;
}

.section-row{
    display:flex;
    align-items:center;
    justify-content:space-between;
    margin:14px 0 9px 0;
}

.section-title{
    font-size:16px;
    font-weight:900;
    letter-spacing:-.2px;
}

.link{
    color:var(--purple);
    font-weight:800;
    font-size:12px;
}

.pref-grid{
    display:grid;
    grid-template-columns:repeat(3,1fr);
    gap:10px;
    margin-bottom:15px;
}

.pref{
    background:white;
    border:1px solid var(--line);
    border-radius:18px;
    padding:12px 10px;
    box-shadow:0 8px 18px rgba(55,34,109,.055);
    min-height:82px;
}

.pref-icon{
    width:25px;
    height:25px;
    border-radius:9px;
    background:linear-gradient(135deg,#EEF8EE,#D9F7E6);
    margin-bottom:5px;
}

.pref:nth-child(2) .pref-icon{
    background:linear-gradient(135deg,#EEF5FF,#DDE8FF);
}

.pref:nth-child(3) .pref-icon{
    background:linear-gradient(135deg,#F7EFFF,#F1DFFF);
}

.pref-label{
    color:var(--muted);
    font-size:11px;
    font-weight:800;
}

.pref-value{
    font-weight:950;
    font-size:17px;
    letter-spacing:-.5px;
}

.map{
    background:
        linear-gradient(rgba(255,255,255,.80),rgba(255,255,255,.80)),
        radial-gradient(circle at 20% 20%, #DCD2FF 0 8%, transparent 9%),
        radial-gradient(circle at 80% 70%, #FFD9E9 0 9%, transparent 10%),
        linear-gradient(135deg,#F7F2FF,#FFF7FB);
    border:1px solid var(--line);
    border-radius:25px;
    height:298px;
    padding:13px;
    position:relative;
    overflow:hidden;
    box-shadow:inset 0 0 0 1px rgba(255,255,255,.65);
}

.map:before{
    content:"";
    position:absolute;
    inset:0;
    background:
        linear-gradient(90deg, transparent 0 16%, rgba(125,76,255,.07) 16% 17%, transparent 17% 44%, rgba(125,76,255,.07) 44% 45%, transparent 45% 70%, rgba(125,76,255,.07) 70% 71%, transparent 71%),
        linear-gradient(0deg, transparent 0 18%, rgba(125,76,255,.07) 18% 19%, transparent 19% 42%, rgba(125,76,255,.07) 42% 43%, transparent 43% 68%, rgba(125,76,255,.07) 68% 69%, transparent 69%);
    opacity:.9;
}

.route-svg{
    position:absolute;
    left:0;
    top:0;
    width:100%;
    height:100%;
    z-index:1;
    pointer-events:none;
}

.pin{
    position:absolute;
    z-index:3;
    background:white;
    border:1px solid #E7DFFF;
    border-radius:17px;
    padding:9px 11px;
    box-shadow:0 13px 28px rgba(77,51,133,.14);
    width:156px;
}

.pin .pin-title{
    display:flex;
    align-items:center;
    gap:7px;
    font-size:12px;
    font-weight:950;
}

.pin-num{
    width:25px;
    height:25px;
    border-radius:9px 9px 9px 2px;
    transform:rotate(45deg);
    background:linear-gradient(135deg,var(--purple),var(--purple2));
    display:inline-flex;
    align-items:center;
    justify-content:center;
    color:white;
    font-size:12px;
    font-weight:950;
    flex:none;
}

.pin-num span{
    transform:rotate(-45deg);
    color:white;
}

.pin-meta{
    color:var(--muted);
    font-size:10px;
    margin-top:4px;
    padding-left:33px;
}

.pin1{left:90px;top:54px;}
.pin2{right:24px;top:102px;}
.pin3{left:38px;bottom:64px;}
.pin4{right:34px;bottom:34px;}

.start{
    position:absolute;
    z-index:4;
    left:28px;
    top:84px;
    font-size:10px;
    font-weight:900;
    color:#2F2B50;
    text-align:center;
}

.start-bubble{
    width:29px;
    height:29px;
    margin:auto;
    border-radius:50% 50% 50% 5px;
    background:#17151E;
    transform:rotate(-45deg);
    display:flex;
    align-items:center;
    justify-content:center;
    color:white;
}

.start-bubble span{
    transform:rotate(45deg);
    color:white;
    font-size:13px;
}

.end{
    position:absolute;
    z-index:4;
    right:18px;
    bottom:14px;
    font-size:9px;
    font-weight:850;
    color:#2F2B50;
    text-align:center;
}

.end-dot{
    width:20px;
    height:20px;
    margin:auto;
    border-radius:50%;
    background:#23213B;
    border:4px solid white;
    box-shadow:0 4px 12px rgba(0,0,0,.18);
}

.mission-grid{
    display:grid;
    grid-template-columns:repeat(4,1fr);
    gap:8px;
}

.mission{
    background:white;
    border:1px solid var(--line);
    border-radius:17px;
    padding:11px 8px;
    min-height:116px;
    text-align:center;
    box-shadow:0 8px 18px rgba(55,34,109,.055);
}

.mission-visual{
    width:36px;
    height:36px;
    border-radius:13px;
    margin:2px auto 8px;
    background:linear-gradient(135deg,#E9E2FF,#FFF0F8);
    position:relative;
}

.mission-title{
    font-size:11px;
    font-weight:850;
    line-height:1.22;
    min-height:30px;
}

.mission-points{
    color:#C97A00;
    font-size:10px;
    font-weight:850;
    margin-top:8px;
}

.done{
    color:var(--purple);
    font-size:11px;
    font-weight:900;
    margin-top:5px;
}

.reward-row{
    display:grid;
    grid-template-columns:repeat(3,1fr);
    gap:9px;
}

.reward{
    background:white;
    border:1px solid var(--line);
    border-radius:17px;
    padding:12px 8px;
    box-shadow:0 8px 18px rgba(55,34,109,.055);
}

.reward-num{
    color:#302858;
    font-size:19px;
    font-weight:950;
    letter-spacing:-.4px;
}

.reward-label{
    color:var(--muted);
    font-size:10px;
    font-weight:750;
}

.nav{
    margin-top:15px;
    border-top:1px solid var(--line);
    padding-top:12px;
    display:grid;
    grid-template-columns:repeat(5,1fr);
    text-align:center;
    font-size:10px;
    color:var(--muted);
    font-weight:800;
}

.nav-active{
    color:var(--purple);
}

.panel{
    background:#201D33;
    color:white;
    border-radius:31px;
    padding:23px;
    box-shadow:0 23px 55px rgba(33,20,74,.18);
}

.panel h3,.panel p,.panel div{
    color:white;
}

.panel p{
    color:#C7C0DC;
    font-size:13px;
    line-height:1.5;
}

.kpi{
    background:rgba(255,255,255,.08);
    border:1px solid rgba(255,255,255,.10);
    border-radius:19px;
    padding:15px;
    margin-bottom:12px;
}

.kpi-val{
    font-size:29px;
    font-weight:950;
    color:white;
    letter-spacing:-.8px;
}

.kpi-lab{
    color:#C7C0DC !important;
    font-size:12px;
    font-weight:650;
}

.ai-card{
    margin-top:14px;
    background:linear-gradient(135deg,rgba(125,76,255,.28),rgba(255,125,187,.13));
    border:1px solid rgba(255,255,255,.11);
    border-radius:20px;
    padding:16px;
}

.white-card{
    background:white;
    border:1px solid var(--line);
    border-radius:30px;
    padding:24px;
    box-shadow:0 18px 45px rgba(55,34,109,.08);
    margin-top:22px;
}

.detail-card{
    background:#fff;
    border:1px solid var(--line);
    border-radius:20px;
    padding:16px;
    min-height:176px;
    box-shadow:0 8px 18px rgba(55,34,109,.055);
}

.detail-index{
    color:var(--purple);
    font-weight:950;
    font-size:12px;
}

.detail-title{
    font-weight:950;
    font-size:17px;
    margin:5px 0 5px;
}

.detail-meta{
    color:var(--muted);
    font-size:12px;
    margin-bottom:8px;
}

.detail-copy{
    color:#34304E;
    font-size:12.5px;
    line-height:1.45;
}

.adapt-result{
    background:linear-gradient(135deg,#F4EEFF,#FFF4FA);
    border:1px solid #E8DDFF;
    border-radius:22px;
    padding:18px;
    margin-top:14px;
}

.adapt-result p{
    color:#5F5974;
}

.download-btn{
    margin-top:10px;
}

[data-testid="stForm"]{
    background:white;
    border:1px solid var(--line);
    border-radius:30px;
    padding:23px;
    box-shadow:0 18px 45px rgba(55,34,109,.08);
}

@media(max-width:900px){
    .hero h1{font-size:38px;}
    .phone{width:360px;padding:18px;border-radius:48px;}
    .mission-grid{grid-template-columns:repeat(2,1fr);}
    .pref-grid{grid-template-columns:1fr;}
}
</style>
""", unsafe_allow_html=True)

# -----------------------------
# Page
# -----------------------------
st.markdown("""
<div class="topbar">
  <div class="brand">
    <div class="logo">M</div>
    <div>
      <div class="brand-title">MiaoGo</div>
      <div class="brand-sub">AI shopping journey assistant for Miaojie</div>
    </div>
  </div>
  <div class="top-pill">Interactive MVP Demo</div>
</div>

<div class="hero">
  <h1>Personalized mall journeys that turn app opens into <span class="gradient-text">visits, missions, and repurchase.</span></h1>
  <p>
    MiaoGo lets users enter their budget, time, style, and shopping goal.
    The MVP generates a mall route, shopping missions, rewards, and real-time journey updates using structured mall data.
  </p>
</div>
""", unsafe_allow_html=True)

st.markdown('<div class="input-card">', unsafe_allow_html=True)
st.subheader("Create a test journey")

c1, c2, c3 = st.columns(3)
with c1:
    budget = st.number_input("Budget / RMB", min_value=50, max_value=5000, value=200, step=50)
with c2:
    available_time = st.slider("Available time / minutes", 30, 240, 150, 15)
with c3:
    priority = st.selectbox(
        "Main priority",
        ["Trendy style", "Best value", "Beauty and skincare", "Gift shopping", "Fast route", "High-end experience"]
    )

c4, c5 = st.columns(2)
with c4:
    style = st.text_input("Style", value="casual chic")
with c5:
    goal = st.text_input("Shopping goal", value="cute weekend outfit and shoes")

generate = st.button("Generate AI mall journey", type="primary")
st.markdown('</div>', unsafe_allow_html=True)

if generate:
    route, total_time = generate_route(stores, budget, available_time, style, goal, priority)
    st.session_state["route"] = route
    st.session_state["total_time"] = total_time
    st.session_state["generated"] = True

if "route" not in st.session_state:
    route, total_time = generate_route(stores, budget, available_time, style, goal, priority)
    st.session_state["route"] = route
    st.session_state["total_time"] = total_time
else:
    route = st.session_state["route"]
    total_time = st.session_state["total_time"]

# Guard
while len(route) < 4:
    route.append(stores.iloc[len(route)])

rnames = [safe(r, "store_name", f"Store {i+1}") for i, r in enumerate(route[:4])]
rcats = [safe(r, "category", "Store") for r in route[:4]]
rtimes = [safe(r, "estimated_time_min", "20") for r in route[:4]]
missions = [safe(r, "mission", "Complete this mission.") for r in route[:4]]

main_left, main_right = st.columns([1.06, .94], gap="large")

with main_left:
    st.markdown('<div class="phone-stage"><div class="phone">', unsafe_allow_html=True)

    st.markdown(f"""
    <div class="status">
        <div>9:41</div>
        <div class="signal"><div class="dotline"></div><div class="dotline"></div></div>
    </div>

    <div class="greeting">
        <div class="person">
            <div class="avatar"></div>
            <div>
                <div class="hello">Hi, Mia</div>
                <div class="hello-sub">Let's plan your perfect mall trip</div>
            </div>
        </div>
        <div class="points">2,480</div>
    </div>

    <div class="section-row">
        <div class="section-title">Your preferences</div>
        <div class="link">Edit</div>
    </div>

    <div class="pref-grid">
        <div class="pref">
            <div class="pref-icon"></div>
            <div class="pref-label">Budget</div>
            <div class="pref-value">¥{budget}</div>
        </div>
        <div class="pref">
            <div class="pref-icon"></div>
            <div class="pref-label">Time</div>
            <div class="pref-value">{round(available_time/60, 1)}h</div>
        </div>
        <div class="pref">
            <div class="pref-icon"></div>
            <div class="pref-label">Style</div>
            <div class="pref-value" style="font-size:14px;">{style.title()}</div>
        </div>
    </div>

    <div class="section-row">
        <div class="section-title">Your AI Mall Journey</div>
        <div class="link">Est. {round(total_time/60,1)}h</div>
    </div>

    <div class="map">
        <svg class="route-svg" viewBox="0 0 414 298" preserveAspectRatio="none">
            <path d="M62 110 C95 70, 132 76, 158 95 S220 122, 266 111 S345 88, 360 142 S310 218, 250 210 S146 182, 104 221"
                  fill="none" stroke="#7D4CFF" stroke-width="4" stroke-linecap="round"
                  stroke-dasharray="9 8" opacity=".82"/>
        </svg>
        <div class="start"><div class="start-bubble"><span>S</span></div>Start<br>Main entrance</div>

        <div class="pin pin1">
            <div class="pin-title"><div class="pin-num"><span>1</span></div>{rnames[0]}</div>
            <div class="pin-meta">{rcats[0]} · {rtimes[0]} min</div>
        </div>
        <div class="pin pin2">
            <div class="pin-title"><div class="pin-num"><span>2</span></div>{rnames[1]}</div>
            <div class="pin-meta">{rcats[1]} · {rtimes[1]} min</div>
        </div>
        <div class="pin pin3">
            <div class="pin-title"><div class="pin-num"><span>3</span></div>{rnames[2]}</div>
            <div class="pin-meta">{rcats[2]} · {rtimes[2]} min</div>
        </div>
        <div class="pin pin4">
            <div class="pin-title"><div class="pin-num"><span>4</span></div>{rnames[3]}</div>
            <div class="pin-meta">{rcats[3]} · {rtimes[3]} min</div>
        </div>

        <div class="end"><div class="end-dot"></div>End<br>South exit</div>
    </div>

    <div class="section-row">
        <div class="section-title">AI Shopping Missions</div>
        <div class="link">4/4</div>
    </div>

    <div class="mission-grid">
        <div class="mission">
            <div class="mission-visual"></div>
            <div class="mission-title">{missions[0][:42]}</div>
            <div class="mission-points">+200 pts</div>
            <div class="done">Done</div>
        </div>
        <div class="mission">
            <div class="mission-visual"></div>
            <div class="mission-title">{missions[1][:42]}</div>
            <div class="mission-points">+100 pts</div>
            <div class="done">Done</div>
        </div>
        <div class="mission">
            <div class="mission-visual"></div>
            <div class="mission-title">{missions[2][:42]}</div>
            <div class="mission-points">+80 pts</div>
            <div class="done">Done</div>
        </div>
        <div class="mission">
            <div class="mission-visual"></div>
            <div class="mission-title">Unlock a journey coupon</div>
            <div class="mission-points">+120 pts</div>
            <div class="done">Done</div>
        </div>
    </div>

    <div class="section-title">Your Rewards</div>
    <div class="reward-row">
        <div class="reward"><div class="reward-num">2,480</div><div class="reward-label">Points</div></div>
        <div class="reward"><div class="reward-num">3</div><div class="reward-label">Coupons</div></div>
        <div class="reward"><div class="reward-num">5</div><div class="reward-label">Check-ins</div></div>
    </div>

    <div class="nav">
        <div class="nav-active">Home</div>
        <div>Missions</div>
        <div>Map</div>
        <div>Rewards</div>
        <div>Me</div>
    </div>
    """, unsafe_allow_html=True)

    st.markdown('</div></div>', unsafe_allow_html=True)

with main_right:
    st.markdown(f"""
    <div class="panel">
        <h3>Merchant impact</h3>
        <p>Prototype dashboard showing how Yintai and merchants could measure the effect of AI-guided journeys.</p>
        <div class="kpi"><div class="kpi-val">+28%</div><div class="kpi-lab">Route-start uplift simulation</div></div>
        <div class="kpi"><div class="kpi-val">18.7%</div><div class="kpi-lab">Coupon redemption simulation</div></div>
        <div class="kpi"><div class="kpi-val">{len(route[:4])}</div><div class="kpi-lab">Recommended journey stops</div></div>
        <div class="kpi"><div class="kpi-val">{total_time}</div><div class="kpi-lab">Estimated journey minutes</div></div>
        <div class="ai-card">
            <h4>AI logic</h4>
            <p>Uses budget, time, style, shopping goal, store category, reward type, and mission fit to generate a guided mall journey.</p>
        </div>
    </div>
    """, unsafe_allow_html=True)

    st.markdown("""
    <div class="white-card">
        <h3>What users are testing</h3>
        <p style="color:#7E7892;line-height:1.55;">
        Users can generate a route, view missions and rewards, test a real-time behavior update, and submit feedback for the MVP validation report.
        </p>
    </div>
    """, unsafe_allow_html=True)

st.markdown('<div class="white-card">', unsafe_allow_html=True)
st.subheader("AI recommendation details")
dcols = st.columns(4)
for i, row in enumerate(route[:4]):
    with dcols[i]:
        st.markdown(f"""
        <div class="detail-card">
            <div class="detail-index">STOP {i+1}</div>
            <div class="detail-title">{safe(row, "store_name")}</div>
            <div class="detail-meta">{safe(row, "category")} · {safe(row, "zone")} · {safe(row, "floor")}</div>
            <div class="detail-copy">{safe(row, "ai_reason", safe(row, "best_for"))}</div>
        </div>
        """, unsafe_allow_html=True)
st.markdown('</div>', unsafe_allow_html=True)

st.markdown('<div class="white-card">', unsafe_allow_html=True)
st.subheader("Real-time AI adaptation")
change_text = st.text_input("Test a live behavior change", value="I spent 25 minutes in Nike because I liked the shoes.")

if st.button("Update journey based on behavior"):
    title, insight, bonus_mission, reward, suggested = adapt_route(change_text, stores)
    st.markdown(f"""
    <div class="adapt-result">
        <h3>{title}</h3>
        <p>{insight}</p>
        <p><b>New bonus mission:</b> {bonus_mission}</p>
        <p><b>New reward:</b> {reward}</p>
    </div>
    """, unsafe_allow_html=True)

    scols = st.columns(3)
    for col, (_, row) in zip(scols, suggested.iterrows()):
        with col:
            st.markdown(f"""
            <div class="detail-card">
                <div class="detail-title">{safe(row, "store_name")}</div>
                <div class="detail-meta">{safe(row, "category")} · {safe(row, "estimated_time_min", "20")} min</div>
                <div class="detail-copy"><b>Mission:</b> {safe(row, "mission")}<br><br><b>Reward:</b> {safe(row, "reward")}</div>
            </div>
            """, unsafe_allow_html=True)

st.markdown('</div>', unsafe_allow_html=True)

st.subheader("Tester feedback")
with st.form("feedback_form"):
    f1, f2 = st.columns(2)
    with f1:
        rating = st.slider("Overall rating", 1, 5, 4)
        would_use = st.radio("Would you use this inside Miaojie?", ["Yes", "Maybe", "No"], horizontal=True)
    with f2:
        open_more = st.radio("Would this make you open Miaojie more often?", ["Yes", "Maybe", "No"], horizontal=True)
        useful_part = st.selectbox(
            "Most useful part",
            ["AI route", "Missions", "Rewards and coupons", "Real-time adaptation", "Repurchase reminder", "Merchant value"]
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

with st.expander("Structured MVP dataset"):
    st.dataframe(stores, use_container_width=True)
