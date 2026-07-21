
from datetime import datetime
import os
import re
import html

import pandas as pd
import streamlit as st
import streamlit.components.v1 as components

st.set_page_config(
    page_title="MiaoGo MVP",
    page_icon="M",
    layout="wide",
    initial_sidebar_state="collapsed",
)

@st.cache_data
def load_data():
    df = pd.read_csv("stores.csv")
    df.columns = [c.strip() for c in df.columns]
    return df

stores = load_data()

def safe(row, col, default=""):
    try:
        v = row.get(col, default)
        if pd.isna(v):
            return default
        return str(v)
    except Exception:
        return default

def n(value, default=0):
    try:
        return int(float(value))
    except Exception:
        return default

def esc(x):
    return html.escape(str(x))

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
    score = 0

    for word in re.findall(r"[a-zA-Z\u4e00-\u9fff]+", user_text):
        if len(word) > 2 and word in text:
            score += 3

    try:
        min_b = float(row.get("budget_min_rmb", 0))
        max_b = float(row.get("budget_max_rmb", 999999))
        if min_b <= budget <= max_b:
            score += 7
        elif budget >= min_b * 0.6 and budget <= max_b * 1.5:
            score += 3
    except Exception:
        pass

    category = safe(row, "category").lower()

    if any(x in user_text for x in ["cute", "outfit", "fashion", "style", "casual", "chic", "fancy"]):
        if any(x in category for x in ["fashion", "sportswear", "beauty", "lifestyle"]):
            score += 7

    if any(x in user_text for x in ["shoe", "shoes", "sneaker", "sneakers"]):
        if any(x in text for x in ["shoe", "sneaker", "nike", "sportswear"]):
            score += 8

    if any(x in user_text for x in ["beauty", "makeup", "skincare", "perfume", "lipstick"]):
        if any(x in text for x in ["beauty", "makeup", "skincare", "perfume", "sephora"]):
            score += 8

    if "gift" in user_text:
        if any(x in text for x in ["gift", "toy", "family", "lifestyle", "entertainment"]):
            score += 8

    if "fast" in user_text and n(row.get("estimated_time_min", 20), 20) <= 20:
        score += 5

    return score

def generate_route(df, budget, available_time, style, goal, priority):
    temp = df.copy()
    temp["score"] = temp.apply(lambda r: score_store(r, budget, style, goal, priority), axis=1)
    temp = temp.sort_values("score", ascending=False)

    route = []
    names = set()
    total_time = 0

    for _, row in temp.iterrows():
        name = safe(row, "store_name")
        if name in names:
            continue
        route.append(row)
        names.add(name)
        total_time += n(row.get("estimated_time_min", 20), 20)
        if len(route) == 4:
            break

    while len(route) < 4:
        route.append(df.iloc[len(route)])

    return route, total_time

def adapt_route(change_text, df):
    t = change_text.lower()
    if any(x in t for x in ["nike", "shoe", "shoes", "sneaker", "sneakers"]):
        insight = "MiaoGo detected stronger interest in shoes and sporty styling."
        action = "The route now prioritizes sneaker matching, outfit completion, and a shoe-related reward."
        bonus = "Try two sneaker styles and compare comfort, price, and outfit match."
        reward = "Shoe coupon or bonus journey points."
        mask = df.apply(lambda r: any(x in str(r).lower() for x in ["nike", "shoe", "sneaker", "sportswear"]), axis=1)
    elif any(x in t for x in ["beauty", "makeup", "skincare", "sephora", "perfume", "lipstick"]):
        insight = "MiaoGo detected stronger interest in beauty and skincare."
        action = "The route now adds beauty stops after the main outfit journey."
        bonus = "Compare two beauty products and choose one that matches the outfit or skin need."
        reward = "Beauty sample or skincare coupon."
        mask = df.apply(lambda r: any(x in str(r).lower() for x in ["beauty", "makeup", "skincare", "perfume", "sephora"]), axis=1)
    elif any(x in t for x in ["coffee", "hungry", "tired", "break", "rest"]):
        insight = "MiaoGo detected that the user may need a break."
        action = "The route now adds a short rest stop before continuing."
        bonus = "Take a short break, check in, and continue with the next best store."
        reward = "Coffee break points."
        mask = df.apply(lambda r: any(x in str(r).lower() for x in ["coffee", "food", "drink", "break"]), axis=1)
    else:
        insight = "MiaoGo detected a behavior change."
        action = "The journey is updated based on the user’s current interest."
        bonus = "Complete one adaptive mission based on the current interest."
        reward = "Adaptive journey points."
        mask = df.apply(lambda r: True, axis=1)

    suggested = df[mask].head(3)
    if suggested.empty:
        suggested = df.head(3)
    return insight, action, bonus, reward, suggested

# Streamlit page styling only
st.markdown("""
<style>
@import url('https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600;700;800;900&display=swap');

html, body, [class*="css"] {font-family: Inter, -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif;}
.stApp {
    background:
      radial-gradient(circle at 10% 0%, rgba(255, 214, 236, .72), transparent 28%),
      radial-gradient(circle at 90% 4%, rgba(221, 210, 255, .75), transparent 30%),
      linear-gradient(180deg, #FFFFFF 0%, #FBF8FF 54%, #FFFFFF 100%);
}
.block-container {max-width:1240px; padding-top:1.2rem; padding-bottom:3rem;}
#MainMenu, footer, header {visibility:hidden;}
[data-testid="collapsedControl"] {display:none;}
h1,h2,h3,h4,h5,h6,p,div,span,label {font-family: Inter, -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif; color:#17142B;}
.app-card{background:white;border:1px solid #EDE7F8;border-radius:30px;padding:24px;box-shadow:0 18px 45px rgba(51,34,101,.075);margin-bottom:22px;}
.hero-card{background:rgba(255,255,255,.82);border:1px solid #EDE7F8;border-radius:32px;padding:30px;margin-bottom:22px;box-shadow:0 22px 55px rgba(51,34,101,.09);}
.hero-card h1{font-size:46px;line-height:1.07;letter-spacing:-1.8px;margin:0 0 12px 0;font-weight:950;max-width:850px;}
.hero-card p{font-size:17px;color:#817B97;line-height:1.55;max-width:800px;margin:0;}
.grad{background:linear-gradient(135deg,#7B4DFF,#FF7DBB);-webkit-background-clip:text;-webkit-text-fill-color:transparent;}
.stButton>button{background:linear-gradient(135deg,#7B4DFF,#FF7DBB) !important;color:white !important;border:0 !important;border-radius:999px !important;padding:.75rem 1.5rem !important;font-weight:900 !important;box-shadow:0 13px 28px rgba(123,77,255,.23) !important;}
.stButton>button:hover{color:white !important;filter:brightness(1.04);}
input,textarea{color:#17142B !important;background:white !important;}
div[data-baseweb="select"] span{color:#17142B !important;}
[data-testid="stForm"]{background:white;border:1px solid #EDE7F8;border-radius:30px;padding:24px;box-shadow:0 18px 45px rgba(51,34,101,.075);}
</style>
""", unsafe_allow_html=True)

st.markdown("""
<div style="display:flex;align-items:center;justify-content:space-between;margin-bottom:18px;">
  <div style="display:flex;align-items:center;gap:13px;">
    <div style="width:48px;height:48px;border-radius:16px;background:linear-gradient(135deg,#7B4DFF,#FF7DBB);display:flex;align-items:center;justify-content:center;color:white;font-weight:900;font-size:23px;box-shadow:0 14px 30px rgba(123,77,255,.23);">M</div>
    <div>
      <div style="font-size:27px;font-weight:900;letter-spacing:-.8px;line-height:1;">MiaoGo</div>
      <div style="font-size:13px;color:#817B97;margin-top:3px;">AI shopping journey assistant for Miaojie</div>
    </div>
  </div>
  <div style="background:white;border:1px solid #EDE7F8;border-radius:999px;padding:10px 15px;color:#5D38D6;font-weight:850;font-size:13px;box-shadow:0 10px 25px rgba(51,34,101,.08);">Interactive MVP Demo</div>
</div>

<div class="hero-card">
  <h1>Plan mall journeys that feel personal, useful, and <span class="grad">worth opening the app for.</span></h1>
  <p>MiaoGo lets users enter budget, time, style, and shopping goal. The MVP generates a guided Yintai mall route, shopping missions, rewards, and real-time journey updates using structured store data.</p>
</div>
""", unsafe_allow_html=True)

st.markdown('<div class="app-card">', unsafe_allow_html=True)
st.subheader("Create a test journey")
a, b, c = st.columns(3)
with a:
    budget = st.number_input("Budget / RMB", min_value=50, max_value=5000, value=200, step=50)
with b:
    available_time = st.slider("Available time / minutes", 30, 240, 150, 15)
with c:
    priority = st.selectbox("Main priority", ["Trendy style", "Best value", "Beauty and skincare", "Gift shopping", "Fast route", "High-end experience"])
d, e = st.columns(2)
with d:
    style = st.text_input("Style", value="casual chic")
with e:
    goal = st.text_input("Shopping goal", value="cute weekend outfit and shoes")
generate = st.button("Generate AI mall journey", type="primary")
st.markdown('</div>', unsafe_allow_html=True)

if generate or "route" not in st.session_state:
    route, total_time = generate_route(stores, budget, available_time, style, goal, priority)
    st.session_state["route"] = route
    st.session_state["total_time"] = total_time
else:
    route = st.session_state["route"]
    total_time = st.session_state["total_time"]

names = [esc(safe(r, "store_name", f"Store {i+1}")) for i, r in enumerate(route)]
cats = [esc(safe(r, "category", "Store")) for r in route]
times = [esc(safe(r, "estimated_time_min", "20")) for r in route]
missions = [esc(safe(r, "mission", "Complete a store mission.")) for r in route]

app_html = f"""
<!DOCTYPE html>
<html>
<head>
<meta charset="UTF-8">
<link href="https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600;700;800;900&display=swap" rel="stylesheet">
<style>
*{{box-sizing:border-box;}}
body{{
  margin:0;
  font-family:Inter,-apple-system,BlinkMacSystemFont,"Segoe UI",sans-serif;
  background:transparent;
  color:#17142B;
}}
.wrap{{
  display:grid;
  grid-template-columns: minmax(0,1.55fr) minmax(320px,.45fr);
  gap:28px;
  align-items:start;
}}
.shell{{
  background:white;
  border:1px solid #EDE7F8;
  border-radius:30px;
  padding:24px;
  box-shadow:0 18px 45px rgba(51,34,101,.075);
}}
.top{{
  display:flex;align-items:center;justify-content:space-between;margin-bottom:20px;
}}
.person{{display:flex;align-items:center;gap:12px;}}
.avatar{{width:50px;height:50px;border-radius:50%;background:linear-gradient(135deg,#F2E9FF,#FFE1EF);border:1px solid #EEE5FF;position:relative;}}
.avatar:before{{content:"";position:absolute;width:14px;height:14px;border-radius:50%;background:#FFD0E1;top:9px;left:18px;}}
.avatar:after{{content:"";position:absolute;width:30px;height:22px;border-radius:20px 20px 14px 14px;background:#7B4DFF;bottom:5px;left:10px;}}
.greet{{font-size:25px;font-weight:950;letter-spacing:-.5px;}}
.sub{{font-size:14px;color:#817B97;margin-top:2px;}}
.points{{background:#FFF8E7;border:1px solid #FFE6A9;border-radius:999px;padding:10px 16px;color:#AA6A00;font-size:17px;font-weight:950;}}
.sec{{display:flex;align-items:center;justify-content:space-between;margin:18px 0 12px;}}
.sec b{{font-size:22px;font-weight:950;}}
.sec span{{font-size:14px;font-weight:850;color:#7B4DFF;}}
.prefgrid{{display:grid;grid-template-columns:repeat(3,1fr);gap:14px;}}
.pref{{background:white;border:1px solid #EDE7F8;border-radius:22px;padding:18px;min-height:116px;box-shadow:0 10px 24px rgba(51,34,101,.055);}}
.ico{{width:34px;height:34px;border-radius:12px;background:#DDF7E8;margin-bottom:14px;}}
.pref:nth-child(2) .ico{{background:#E6F0FF;}}
.pref:nth-child(3) .ico{{background:#F1E2FF;}}
.lab{{font-size:13px;color:#817B97;font-weight:850;}}
.val{{font-size:25px;font-weight:950;letter-spacing:-.8px;margin-top:2px;}}
.map{{
  height:360px;border:1px solid #EDE7F8;border-radius:28px;background:
    linear-gradient(rgba(255,255,255,.72),rgba(255,255,255,.72)),
    repeating-linear-gradient(90deg, transparent 0 92px, rgba(123,77,255,.08) 92px 100px),
    repeating-linear-gradient(0deg, transparent 0 82px, rgba(123,77,255,.08) 82px 90px),
    linear-gradient(135deg,#F5EFFF,#FFF6FA);
  position:relative;overflow:hidden;margin-bottom:18px;box-shadow:inset 0 0 0 1px rgba(255,255,255,.7);
}}
svg{{position:absolute;inset:0;z-index:1;pointer-events:none;}}
.pin{{position:absolute;z-index:3;background:white;border:1px solid #E5DBFF;border-radius:19px;padding:12px 13px;width:210px;box-shadow:0 18px 38px rgba(73,45,140,.15);}}
.ptitle{{font-size:14px;font-weight:950;display:flex;align-items:center;gap:8px;}}
.num{{width:31px;height:31px;background:linear-gradient(135deg,#7B4DFF,#A879FF);border-radius:11px 11px 11px 3px;transform:rotate(45deg);display:inline-flex;align-items:center;justify-content:center;flex:none;}}
.num span{{transform:rotate(-45deg);color:white;font-weight:950;}}
.pmeta{{font-size:12px;color:#817B97;margin-top:6px;padding-left:40px;}}
.pin1{{left:250px;top:58px;}}
.pin2{{right:88px;top:126px;}}
.pin3{{left:90px;bottom:82px;}}
.pin4{{right:170px;bottom:42px;}}
.start{{position:absolute;left:48px;top:94px;z-index:4;text-align:center;font-size:12px;color:#312B57;font-weight:850;}}
.startdot{{width:36px;height:36px;border-radius:50%;background:#17142B;color:white;display:flex;align-items:center;justify-content:center;font-weight:950;margin:0 auto 5px;}}
.end{{position:absolute;right:36px;bottom:18px;z-index:4;text-align:center;font-size:11px;color:#312B57;font-weight:850;}}
.enddot{{width:24px;height:24px;border-radius:50%;background:#17142B;border:5px solid white;margin:0 auto 4px;box-shadow:0 5px 14px rgba(0,0,0,.18);}}
.missiongrid{{display:grid;grid-template-columns:repeat(4,1fr);gap:14px;margin-bottom:18px;}}
.mission{{background:white;border:1px solid #EDE7F8;border-radius:22px;padding:16px;min-height:165px;text-align:center;box-shadow:0 10px 24px rgba(51,34,101,.055);}}
.mico{{width:48px;height:48px;border-radius:17px;background:linear-gradient(135deg,#EFE7FF,#FFF0F7);margin:0 auto 13px;}}
.mtitle{{font-size:14px;font-weight:900;line-height:1.25;min-height:55px;}}
.mpoints{{font-size:14px;color:#C97900;font-weight:950;margin-top:10px;}}
.mstate{{display:inline-block;margin-top:8px;padding:6px 10px;border-radius:999px;background:#F0EAFF;color:#7B4DFF;font-size:12px;font-weight:900;}}
.rewardgrid{{display:grid;grid-template-columns:repeat(3,1fr);gap:14px;}}
.reward{{background:white;border:1px solid #EDE7F8;border-radius:22px;padding:18px;box-shadow:0 10px 24px rgba(51,34,101,.055);}}
.rnum{{font-size:31px;font-weight:950;color:#2B244D;letter-spacing:-.8px;}}
.rlab{{font-size:14px;color:#817B97;font-weight:800;}}
.nav{{display:grid;grid-template-columns:repeat(5,1fr);border-top:1px solid #EDE7F8;padding-top:15px;text-align:center;font-size:13px;font-weight:900;color:#5F5875;}}
.nav div:first-child{{color:#7B4DFF;}}
.panel{{background:white;border:1px solid #EDE7F8;border-radius:30px;padding:24px;box-shadow:0 18px 45px rgba(51,34,101,.075);}}
.panel h3{{margin-top:0;font-size:25px;}}
.panel p{{color:#817B97;line-height:1.5;font-size:14px;}}
.kpi{{background:#FAF7FF;border:1px solid #EDE7F8;border-radius:20px;padding:16px;margin-bottom:13px;}}
.kval{{font-size:31px;font-weight:950;color:#2B244D;}}
.klab{{font-size:13px;color:#817B97;font-weight:750;}}
@media(max-width:900px){{
  .wrap{{grid-template-columns:1fr;}}
  .prefgrid,.missiongrid,.rewardgrid{{grid-template-columns:1fr;}}
  .map{{height:auto;padding:70px 14px;}}
  .pin{{position:relative;left:auto!important;right:auto!important;top:auto!important;bottom:auto!important;margin:10px 0;width:auto;}}
}}
</style>
</head>
<body>
<div class="wrap">
  <div class="shell">
    <div class="top">
      <div class="person">
        <div class="avatar"></div>
        <div><div class="greet">Hi, Mia</div><div class="sub">Let's plan your perfect mall trip</div></div>
      </div>
      <div class="points">2,480 pts</div>
    </div>

    <div class="sec"><b>Your preferences</b><span>Edit</span></div>
    <div class="prefgrid">
      <div class="pref"><div class="ico"></div><div class="lab">Budget</div><div class="val">¥{budget}</div></div>
      <div class="pref"><div class="ico"></div><div class="lab">Time</div><div class="val">{round(available_time/60,1)}h</div></div>
      <div class="pref"><div class="ico"></div><div class="lab">Style</div><div class="val" style="font-size:20px;">{esc(style.title())}</div></div>
    </div>

    <div class="sec"><b>Your AI Mall Journey</b><span>Est. {round(total_time/60,1)}h</span></div>
    <div class="map">
      <svg viewBox="0 0 900 360" preserveAspectRatio="none">
        <path d="M90 145 C170 60, 295 70, 385 125 S585 170, 680 118 S845 130, 808 225 S625 318, 480 278 S255 246, 166 300"
          fill="none" stroke="#7B4DFF" stroke-width="6" stroke-linecap="round" stroke-dasharray="14 13" opacity=".88"/>
      </svg>
      <div class="start"><div class="startdot">S</div>Start<br>Main entrance</div>
      <div class="pin pin1"><div class="ptitle"><div class="num"><span>1</span></div>{names[0]}</div><div class="pmeta">{cats[0]} · {times[0]} min</div></div>
      <div class="pin pin2"><div class="ptitle"><div class="num"><span>2</span></div>{names[1]}</div><div class="pmeta">{cats[1]} · {times[1]} min</div></div>
      <div class="pin pin3"><div class="ptitle"><div class="num"><span>3</span></div>{names[2]}</div><div class="pmeta">{cats[2]} · {times[2]} min</div></div>
      <div class="pin pin4"><div class="ptitle"><div class="num"><span>4</span></div>{names[3]}</div><div class="pmeta">{cats[3]} · {times[3]} min</div></div>
      <div class="end"><div class="enddot"></div>End<br>South exit</div>
    </div>

    <div class="sec"><b>AI Shopping Missions</b><span>Ready to test</span></div>
    <div class="missiongrid">
      <div class="mission"><div class="mico"></div><div class="mtitle">{missions[0][:70]}</div><div class="mpoints">+200 pts</div><div class="mstate">Available</div></div>
      <div class="mission"><div class="mico"></div><div class="mtitle">{missions[1][:70]}</div><div class="mpoints">+100 pts</div><div class="mstate">Available</div></div>
      <div class="mission"><div class="mico"></div><div class="mtitle">{missions[2][:70]}</div><div class="mpoints">+80 pts</div><div class="mstate">Available</div></div>
      <div class="mission"><div class="mico"></div><div class="mtitle">{missions[3][:70]}</div><div class="mpoints">+120 pts</div><div class="mstate">Available</div></div>
    </div>

    <div class="sec"><b>Your Rewards</b><span>Prototype</span></div>
    <div class="rewardgrid">
      <div class="reward"><div class="rnum">2,480</div><div class="rlab">Points</div></div>
      <div class="reward"><div class="rnum">3</div><div class="rlab">Coupons</div></div>
      <div class="reward"><div class="rnum">5</div><div class="rlab">Check-ins</div></div>
    </div>
    <br>
    <div class="nav"><div>Home</div><div>Missions</div><div>Map</div><div>Rewards</div><div>Me</div></div>
  </div>

  <div class="panel">
    <h3>Merchant impact</h3>
    <p>Prototype dashboard for Yintai and stores to measure AI-guided journeys.</p>
    <div class="kpi"><div class="kval">+28%</div><div class="klab">Route-start uplift simulation</div></div>
    <div class="kpi"><div class="kval">18.7%</div><div class="klab">Coupon redemption simulation</div></div>
    <div class="kpi"><div class="kval">{len(route)}</div><div class="klab">Recommended journey stops</div></div>
    <div class="kpi"><div class="kval">{total_time}</div><div class="klab">Estimated journey minutes</div></div>
  </div>
</div>
</body>
</html>
"""

components.html(app_html, height=1120, scrolling=False)

st.markdown('<div class="app-card">', unsafe_allow_html=True)
st.subheader("AI recommendation details")
cols = st.columns(4)
for i, row in enumerate(route):
    with cols[i]:
        st.markdown(
            f"""
            <div style="background:white;border:1px solid #EDE7F8;border-radius:22px;padding:17px;min-height:185px;box-shadow:0 10px 24px rgba(51,34,101,.055);">
                <div style="font-size:12px;color:#7B4DFF;font-weight:950;">STOP {i+1}</div>
                <div style="font-size:18px;font-weight:950;margin:6px 0;">{esc(safe(row, "store_name"))}</div>
                <div style="font-size:12px;color:#817B97;margin-bottom:9px;">{esc(safe(row, "category"))} · {esc(safe(row, "zone"))} · {esc(safe(row, "floor"))}</div>
                <div style="font-size:13px;line-height:1.45;color:#423D5D;">{esc(safe(row, "ai_reason", safe(row, "best_for")))}</div>
            </div>
            """,
            unsafe_allow_html=True,
        )
st.markdown('</div>', unsafe_allow_html=True)

st.markdown('<div class="app-card">', unsafe_allow_html=True)
st.subheader("Real-time AI adaptation")
change_text = st.text_input("Test a behavior change", value="I spent 25 minutes in Nike because I liked the shoes.")
if st.button("Update journey based on behavior"):
    insight, action, bonus, reward, suggested = adapt_route(change_text, stores)
    st.markdown(
        f"""
        <div style="background:linear-gradient(135deg,#F3EEFF,#FFF5FA);border:1px solid #E6DAFF;border-radius:22px;padding:18px;margin-top:14px;">
            <h3>MiaoGo updated the journey</h3>
            <p style="color:#5F5875;">{esc(insight)} {esc(action)}</p>
            <p><b>New bonus mission:</b> {esc(bonus)}</p>
            <p><b>New reward:</b> {esc(reward)}</p>
        </div>
        """,
        unsafe_allow_html=True,
    )
    scols = st.columns(3)
    for col, (_, row) in zip(scols, suggested.iterrows()):
        with col:
            st.markdown(
                f"""
                <div style="background:white;border:1px solid #EDE7F8;border-radius:22px;padding:17px;min-height:170px;box-shadow:0 10px 24px rgba(51,34,101,.055);">
                    <div style="font-size:18px;font-weight:950;margin-bottom:4px;">{esc(safe(row, "store_name"))}</div>
                    <div style="font-size:12px;color:#817B97;margin-bottom:9px;">{esc(safe(row, "category"))} · {esc(safe(row, "estimated_time_min", "20"))} min</div>
                    <div style="font-size:13px;line-height:1.45;color:#423D5D;"><b>Mission:</b> {esc(safe(row, "mission"))}<br><br><b>Reward:</b> {esc(safe(row, "reward"))}</div>
                </div>
                """,
                unsafe_allow_html=True,
            )
st.markdown('</div>', unsafe_allow_html=True)

st.subheader("Mission test")
st.write("Testers can mark which missions they would actually do.")
for i, row in enumerate(route):
    st.checkbox(f"{safe(row, 'store_name')}: {safe(row, 'mission')}", key=f"mission_{i}")

st.subheader("Tester feedback")
with st.form("feedback_form"):
    f1, f2 = st.columns(2)
    with f1:
        rating = st.slider("Overall rating", 1, 5, 4)
        would_use = st.radio("Would you use this inside Miaojie?", ["Yes", "Maybe", "No"], horizontal=True)
    with f2:
        open_more = st.radio("Would this make you open Miaojie more often?", ["Yes", "Maybe", "No"], horizontal=True)
        useful_part = st.selectbox("Most useful part", ["AI route", "Missions", "Rewards and coupons", "Real-time adaptation", "Repurchase reminder", "Merchant value"])
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
