from datetime import datetime
import os
import re
import json
import html
import urllib.request
import urllib.error

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

def esc(x):
    return html.escape(str(x))

def to_int(v, default=0):
    try:
        return int(float(v))
    except Exception:
        return default

def text_of(row):
    return " ".join([
        safe(row, "store_name"), safe(row, "category"), safe(row, "sub_category"),
        safe(row, "best_for"), safe(row, "style_tags"), safe(row, "target_user"),
        safe(row, "keywords"), safe(row, "ai_reason"), safe(row, "mission"),
        safe(row, "reward"), safe(row, "repurchase_trigger"), safe(row, "price_level")
    ]).lower()

def detect_intents(style, goal, priority, free_text):
    text = f"{style} {goal} {priority} {free_text}".lower()
    return {
        "halloween": any(x in text for x in ["halloween", "scary", "creepy", "costume", "goth", "dark", "witch", "vampire"]),
        "fashion": any(x in text for x in ["outfit", "dress", "clothes", "fashion", "style", "cute", "casual", "chic", "fancy", "look", "fit"]),
        "shoes": any(x in text for x in ["shoe", "shoes", "sneaker", "sneakers", "nike", "boots"]),
        "beauty": any(x in text for x in ["beauty", "makeup", "skincare", "perfume", "lipstick", "sephora", "colorist"]),
        "gift": any(x in text for x in ["gift", "present", "friend", "family"]),
        "food": any(x in text for x in ["coffee", "food", "drink", "hungry", "tired", "break", "rest", "kfc"]),
        "budget": any(x in text for x in ["cheap", "budget", "affordable", "value", "student", "not expensive"]),
        "premium": any(x in text for x in ["premium", "luxury", "high-end", "high end", "fancy"]),
        "fast": any(x in text for x in ["fast", "quick", "short", "rush"]),
    }

def rank_stores(df, budget, time_minutes, style, goal, priority, free_text):
    intents = detect_intents(style, goal, priority, free_text)
    user_text = f"{style} {goal} {priority} {free_text}".lower()

    def score(row):
        t = text_of(row)
        s = 0
        reasons = []

        for word in re.findall(r"[a-zA-Z\u4e00-\u9fff]+", user_text):
            if len(word) > 2 and word in t:
                s += 3

        try:
            min_b = float(row.get("budget_min_rmb", 0))
            max_b = float(row.get("budget_max_rmb", 999999))
            if min_b <= budget <= max_b:
                s += 8
                reasons.append("budget fit")
            elif budget >= min_b * 0.65 and budget <= max_b * 1.4:
                s += 4
                reasons.append("near budget")
        except Exception:
            pass

        est = to_int(row.get("estimated_time_min", 20), 20)
        if est <= max(20, time_minutes / 4):
            s += 4
            reasons.append("time fit")

        # Hard correction: Halloween needs fashion/beauty/accessories, not random sports.
        if intents["halloween"]:
            if any(x in t for x in ["sportswear", "nike", "adidas", "sneaker"]) and not intents["shoes"]:
                s -= 40
            if any(x in t for x in ["fashion", "dress", "outfit", "clothes", "style", "ledin", "only", "mango", "urban revivo", "uniqlo"]):
                s += 22
                reasons.append("Halloween outfit base")
            if any(x in t for x in ["beauty", "makeup", "lipstick", "color", "sephora", "colorist", "perfume"]):
                s += 24
                reasons.append("Halloween makeup/detail")
            if any(x in t for x in ["accessory", "gift", "miniso", "lifestyle", "toy"]):
                s += 16
                reasons.append("accessory/detail")
        else:
            if intents["fashion"] and any(x in t for x in ["fashion", "dress", "outfit", "clothes", "style", "sportswear"]):
                s += 12
                reasons.append("outfit match")
            if intents["shoes"] and any(x in t for x in ["shoe", "sneaker", "nike", "adidas", "sportswear"]):
                s += 14
                reasons.append("shoe match")

        if intents["beauty"] and any(x in t for x in ["beauty", "makeup", "skincare", "perfume", "lipstick", "sephora", "colorist"]):
            s += 14
            reasons.append("beauty match")

        if intents["gift"] and any(x in t for x in ["gift", "toy", "family", "lifestyle", "entertainment", "miniso"]):
            s += 12
            reasons.append("gift match")

        if intents["food"] and any(x in t for x in ["coffee", "food", "drink", "break", "kfc"]):
            s += 14
            reasons.append("break/food match")

        if intents["budget"] and any(x in safe(row, "price_level").lower() for x in ["low", "medium"]):
            s += 8
            reasons.append("value fit")

        if intents["premium"] and any(x in safe(row, "price_level").lower() for x in ["high", "luxury", "premium"]):
            s += 8
            reasons.append("premium fit")

        return pd.Series({"ai_score": s, "match_reasons": ", ".join(reasons[:3]) if reasons else "general match"})

    temp = df.copy()
    scored = temp.apply(score, axis=1)
    temp["ai_score"] = scored["ai_score"]
    temp["match_reasons"] = scored["match_reasons"]
    return temp.sort_values("ai_score", ascending=False)

def add_first(route, used, ranked, words, avoid_words=None):
    avoid_words = avoid_words or []
    for _, row in ranked.iterrows():
        name = safe(row, "store_name")
        t = text_of(row)
        if name in used:
            continue
        if any(a in t for a in avoid_words):
            continue
        if any(w in t for w in words):
            route.append(row)
            used.add(name)
            return True
    return False

def build_local_journey(df, budget, time_minutes, style, goal, priority, free_text):
    intents = detect_intents(style, goal, priority, free_text)
    ranked = rank_stores(df, budget, time_minutes, style, goal, priority, free_text)
    route, used = [], set()

    if intents["halloween"]:
        avoid_sports = ["sportswear", "nike", "adidas", "sneaker"]
        add_first(route, used, ranked, ["fashion", "dress", "outfit", "clothes", "style", "ledin", "only", "mango", "urban revivo", "uniqlo"], avoid_sports)
        add_first(route, used, ranked, ["beauty", "makeup", "lipstick", "color", "sephora", "colorist", "perfume"], [])
        add_first(route, used, ranked, ["accessory", "miniso", "lifestyle", "gift"], avoid_sports)
        add_first(route, used, ranked, ["fashion", "dress", "outfit", "clothes", "style"], avoid_sports)
    else:
        if intents["fashion"]:
            add_first(route, used, ranked, ["fashion", "dress", "outfit", "clothes", "style"], [])
        if intents["shoes"]:
            add_first(route, used, ranked, ["shoe", "sneaker", "nike", "adidas", "sportswear"], [])
        if intents["beauty"]:
            add_first(route, used, ranked, ["beauty", "makeup", "skincare", "perfume", "sephora", "colorist"], [])
        if intents["gift"]:
            add_first(route, used, ranked, ["gift", "toy", "lifestyle", "entertainment", "miniso"], [])
        if intents["food"]:
            add_first(route, used, ranked, ["coffee", "food", "drink", "break", "kfc"], [])

    for _, row in ranked.iterrows():
        if len(route) >= 4:
            break
        name = safe(row, "store_name")
        t = text_of(row)
        if name in used:
            continue
        if intents["halloween"] and not intents["shoes"] and any(x in t for x in ["adidas", "nike", "sportswear", "sneaker"]):
            continue
        route.append(row)
        used.add(name)

    for _, row in ranked.iterrows():
        if len(route) >= 4:
            break
        name = safe(row, "store_name")
        if name not in used:
            route.append(row)
            used.add(name)

    stops = []
    for row in route[:4]:
        name = safe(row, "store_name")
        category = safe(row, "category")
        t = text_of(row)

        if intents["halloween"]:
            if any(x in t for x in ["beauty", "makeup", "lipstick", "color", "sephora", "colorist", "perfume"]):
                mission = "Create one scary makeup, dark lip, scent, or color detail that completes the Halloween look."
                reason = "This helps turn the outfit into a real Halloween look through makeup, color, or beauty detail."
                match = "Halloween makeup/detail"
            elif any(x in t for x in ["accessory", "miniso", "lifestyle", "gift"]):
                mission = "Find one low-cost prop or accessory that makes the outfit look more Halloween-ready."
                reason = "This adds a small but visible detail so the look feels themed, not just normal clothes."
                match = "Halloween accessory"
            else:
                mission = "Find one dark, dramatic, or layered piece that can work as the base of a Halloween outfit."
                reason = "This is a realistic fashion stop for building the core Halloween outfit from available mall stores."
                match = "Halloween outfit base"
        else:
            mission = safe(row, "mission", "Complete one store mission that fits your shopping goal.")
            reason = safe(row, "ai_reason", safe(row, "best_for", "Selected because it matches the route goal."))
            match = safe(row, "match_reasons", "AI match")

        stops.append({
            "store_name": name,
            "category": category,
            "zone": safe(row, "zone"),
            "floor": safe(row, "floor"),
            "estimated_time_min": to_int(row.get("estimated_time_min", 20), 20),
            "reason": reason,
            "mission": mission,
            "reward": safe(row, "reward", "Unlock journey points or a coupon."),
            "repurchase_reminder": safe(row, "repurchase_trigger", "Follow up with matching products later."),
            "match": match
        })

    total_time = sum(s["estimated_time_min"] for s in stops)

    if intents["halloween"]:
        summary = (
            "MiaoGo understood this as a Halloween/scary outfit request. Because the MVP dataset does not include a dedicated costume store, "
            "it builds the closest realistic mall route using fashion for the base outfit, beauty for makeup/color, and accessories for a themed detail. "
            "Sportswear is avoided unless the user specifically asks for sneakers or shoes."
        )
    else:
        summary = (
            "MiaoGo matched the request against the mall database using budget, available time, style, category fit, mission value, rewards, and repurchase triggers."
        )

    return {
        "summary": summary,
        "route_name": "Personalized MiaoGo Journey",
        "estimated_total_time": total_time,
        "stops": stops,
        "overall_reward": "Journey points, coupons, and check-in rewards.",
        "repurchase_strategy": "After the visit, MiaoGo can send refill, replacement, or matching-product reminders based on selected items.",
        "limits": "This MVP uses structured prototype data. Real deployment would connect to Miaojie store, coupon, event, check-in, and transaction APIs."
    }, ranked

def short_context(ranked, max_rows=35):
    cols = ["store_name","mall_name","zone","floor","category","sub_category","price_level","budget_min_rmb","budget_max_rmb","best_for","style_tags","target_user","estimated_time_min","mission","reward","coupon_type","repurchase_trigger","ai_reason","keywords","ai_score","match_reasons"]
    existing = [c for c in cols if c in ranked.columns]
    return ranked[existing].head(max_rows).to_dict(orient="records")

def call_gemini(prompt, timeout=14):
    api_key = st.secrets.get("GEMINI_API_KEY", "")
    model = st.secrets.get("GEMINI_MODEL", "gemini-3-flash-preview")
    if not api_key:
        return None, "No Gemini key"

    url = f"https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent?key={api_key}"
    payload = {
        "contents": [{"role": "user", "parts": [{"text": prompt}]}],
        "generationConfig": {"temperature": 0.25, "topP": 0.9, "maxOutputTokens": 1600}
    }
    try:
        req = urllib.request.Request(
            url,
            data=json.dumps(payload).encode("utf-8"),
            headers={"Content-Type": "application/json"},
            method="POST"
        )
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            obj = json.loads(resp.read().decode("utf-8"))
            return obj["candidates"][0]["content"]["parts"][0]["text"], None
    except Exception as e:
        return None, str(e)

def parse_json(text):
    text = (text or "").strip().replace("```json", "").replace("```", "").strip()
    start, end = text.find("{"), text.rfind("}")
    if start >= 0 and end > start:
        text = text[start:end+1]
    return json.loads(text)

def postprocess_journey(data, local, style, goal, priority, free_text):
    intents = detect_intents(style, goal, priority, free_text)
    if not intents["halloween"] or intents["shoes"]:
        return data

    bad = ["adidas", "nike", "sportswear", "sneaker"]
    stops = data.get("stops", [])
    has_bad = any(any(b in json.dumps(s, ensure_ascii=False).lower() for b in bad) for s in stops)
    if has_bad:
        return local
    return data

def build_journey(df, budget, time_minutes, style, goal, priority, free_text):
    local, ranked = build_local_journey(df, budget, time_minutes, style, goal, priority, free_text)
    context = short_context(ranked)

    prompt = f"""
You are MiaoGo, an AI shopping journey planner for Yintai/Miaojie.
Use ONLY the store database. Do not invent stores.
Return ONLY valid JSON, no markdown.

User inputs:
budget RMB: {budget}
time minutes: {time_minutes}
style: {style}
goal: {goal}
priority: {priority}
free text: {free_text}

Store database ranked by local relevance:
{json.dumps(context, ensure_ascii=False)}

JSON schema:
{{
 "summary":"specific explanation of what the user wants and how route was built",
 "route_name":"short name",
 "estimated_total_time":90,
 "stops":[
   {{"store_name":"exact database store","category":"category","zone":"zone","floor":"floor","estimated_time_min":20,"reason":"specific reason","mission":"specific action user can do","reward":"specific reward","repurchase_reminder":"follow-up reminder","match":"short match label"}}
 ],
 "overall_reward":"overall reward",
 "repurchase_strategy":"how app brings user back",
 "limits":"honest MVP limitation"
}}

Rules:
- Exactly 4 stops.
- If the user asks Halloween/scary/creepy/costume, do NOT choose Adidas/Nike/sportswear unless user explicitly asks for shoes/sneakers. Build fashion + beauty/makeup + accessory/lifestyle route.
- If the database has no costume store, say that in the summary and create the closest practical route.
- Use budget and time.
- Missions must be specific, not generic.
"""

    text, err = call_gemini(prompt)
    if err:
        return local, ranked, False, "Smart local AI active. Gemini unavailable."

    try:
        data = parse_json(text)
        if len(data.get("stops", [])) < 4:
            raise ValueError("not enough stops")
        data["stops"] = data["stops"][:4]
        data = postprocess_journey(data, local, style, goal, priority, free_text)
        return data, ranked, True, "Gemini + rule guardrails active."
    except Exception:
        return local, ranked, False, "Smart local AI active. Gemini returned unstructured output."

def instant_adaptation(change_text, stores):
    text = change_text.lower()
    if any(x in text for x in ["kfc", "hungry", "food", "eat", "tired", "coffee", "break", "rest"]):
        detected = "food or rest need"
        logic = "MiaoGo pauses the shopping route and adds a nearby food or coffee break before continuing."
        mission = "Take a short break, check in, then decide whether to continue the route or skip the lowest-priority stop."
        reward = "Food or coffee break points."
        words = ["food", "coffee", "drink", "break", "kfc"]
    elif any(x in text for x in ["nike", "shoe", "sneaker", "shoes", "boots"]):
        detected = "shoe interest"
        logic = "MiaoGo shifts the route toward shoe matching and outfit completion."
        mission = "Try two shoe styles and compare comfort, price, and outfit match."
        reward = "Shoe coupon or bonus journey points."
        words = ["shoe", "sneaker", "nike", "adidas", "sportswear"]
    elif any(x in text for x in ["beauty", "makeup", "sephora", "lipstick", "perfume", "skincare"]):
        detected = "beauty interest"
        logic = "MiaoGo adds a beauty stop to complete the look."
        mission = "Choose one makeup, fragrance, or skincare item that matches the outfit mood."
        reward = "Beauty sample or skincare coupon."
        words = ["beauty", "makeup", "sephora", "perfume", "skincare", "colorist"]
    elif any(x in text for x in ["expensive", "cheap", "budget", "price", "save"]):
        detected = "budget concern"
        logic = "MiaoGo replaces expensive stops with better-value alternatives."
        mission = "Find one item inside budget and compare it with one cheaper alternative."
        reward = "Budget-friendly coupon."
        words = ["low", "medium", "budget", "value", "affordable"]
    else:
        detected = "new behavior signal"
        logic = "MiaoGo updates the route using the new behavior signal."
        mission = "Complete one adaptive mission based on your current interest."
        reward = "Adaptive journey points."
        words = []

    candidates = stores
    if words:
        mask = stores.apply(lambda r: any(w in text_of(r) for w in words), axis=1)
        candidates = stores[mask]
    if candidates.empty:
        candidates = stores.head(3)

    next_stops = []
    for _, row in candidates.head(3).iterrows():
        next_stops.append({
            "store_name": safe(row, "store_name"),
            "reason": safe(row, "ai_reason", safe(row, "best_for")),
            "mission": safe(row, "mission", mission)
        })
    return detected, logic, mission, reward, next_stops

# -----------------------------
# Force full light UI
# -----------------------------
st.markdown("""
<style>
@import url('https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600;700;800;900&display=swap');

html, body, [class*="css"] {font-family: Inter, -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif;}
.stApp, [data-testid="stAppViewContainer"], .main, section.main, [data-testid="stHeader"], [data-testid="stToolbar"] {
    background:
      radial-gradient(circle at 10% 0%, rgba(255, 220, 238, .72), transparent 28%),
      radial-gradient(circle at 90% 4%, rgba(221, 210, 255, .75), transparent 30%),
      linear-gradient(180deg, #FFFFFF 0%, #FBF8FF 54%, #FFFFFF 100%) !important;
}
.block-container {max-width:1240px; padding-top:1.2rem; padding-bottom:3rem;}
#MainMenu, footer, header {visibility:hidden;}
[data-testid="collapsedControl"] {display:none;}
h1,h2,h3,h4,h5,h6,p,div,span,label {font-family: Inter, -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif; color:#17142B !important;}
.app-card{background:white;border:1px solid #EDE7F8;border-radius:30px;padding:24px;box-shadow:0 18px 45px rgba(51,34,101,.075);margin-bottom:22px;}
.hero-card{background:rgba(255,255,255,.92);border:1px solid #EDE7F8;border-radius:32px;padding:30px;margin-bottom:22px;box-shadow:0 22px 55px rgba(51,34,101,.09);}
.hero-card h1{font-size:46px;line-height:1.07;letter-spacing:-1.8px;margin:0 0 12px 0;font-weight:950;max-width:850px;}
.hero-card p{font-size:17px;color:#817B97 !important;line-height:1.55;max-width:830px;margin:0;}
.grad{background:linear-gradient(135deg,#7B4DFF,#FF7DBB);-webkit-background-clip:text;-webkit-text-fill-color:transparent;}
.stButton>button{background:linear-gradient(135deg,#7B4DFF,#FF7DBB) !important;color:white !important;border:0 !important;border-radius:999px !important;padding:.75rem 1.5rem !important;font-weight:900 !important;box-shadow:0 13px 28px rgba(123,77,255,.23) !important;}
.stButton>button:hover{color:white !important;filter:brightness(1.04);}
input, textarea, [data-baseweb="input"] input, [data-baseweb="textarea"] textarea {
    color:#17142B !important;
    background:white !important;
    -webkit-text-fill-color:#17142B !important;
}
div[role="radiogroup"] label {background:white !important;border:1px solid #EDE7F8 !important;border-radius:999px !important;padding:8px 12px !important;margin-right:8px !important;}
div[role="radiogroup"] label p {color:#17142B !important;font-weight:700 !important;}
[data-testid="stForm"]{background:white !important;border:1px solid #EDE7F8;border-radius:30px;padding:24px;box-shadow:0 18px 45px rgba(51,34,101,.075);}
.ai-box{background:linear-gradient(135deg,#F4EFFF,#FFF5FA);border:1px solid #E5DAFF;border-radius:22px;padding:18px;margin:10px 0 16px 0;}
.ai-box p{color:#5F5875 !important;line-height:1.5;margin:.35rem 0;}
.badge{display:inline-block;background:#F0EAFF;color:#7B4DFF !important;border-radius:999px;padding:6px 10px;font-size:12px;font-weight:900;margin-bottom:8px;}
.detail-card{background:white;border:1px solid #EDE7F8;border-radius:22px;padding:17px;min-height:235px;box-shadow:0 10px 24px rgba(51,34,101,.055);}
.detail-small{font-size:12px;color:#817B97 !important;margin-bottom:9px;}
.detail-copy{font-size:13px;line-height:1.45;color:#423D5D !important;}
.adapt-box{background:linear-gradient(135deg,#F3EEFF,#FFF5FA);border:1px solid #E6DAFF;border-radius:22px;padding:18px;margin-top:14px;}
.adapt-box p{color:#5F5875 !important;}
</style>
""", unsafe_allow_html=True)

# Header
st.markdown("""
<div style="display:flex;align-items:center;justify-content:space-between;margin-bottom:18px;">
  <div style="display:flex;align-items:center;gap:13px;">
    <div style="width:48px;height:48px;border-radius:16px;background:linear-gradient(135deg,#7B4DFF,#FF7DBB);display:flex;align-items:center;justify-content:center;color:white!important;font-weight:900;font-size:23px;box-shadow:0 14px 30px rgba(123,77,255,.23);">M</div>
    <div>
      <div style="font-size:27px;font-weight:900;letter-spacing:-.8px;line-height:1;">MiaoGo</div>
      <div style="font-size:13px;color:#817B97!important;margin-top:3px;">AI shopping journey assistant for Miaojie</div>
    </div>
  </div>
  <div style="background:white;border:1px solid #EDE7F8;border-radius:999px;padding:10px 15px;color:#5D38D6!important;font-weight:850;font-size:13px;box-shadow:0 10px 25px rgba(51,34,101,.08);">AI MVP Demo</div>
</div>

<div class="hero-card">
  <h1>Plan mall journeys that feel personal, useful, and <span class="grad">worth opening the app for.</span></h1>
  <p>MiaoGo uses a guarded AI recommendation engine with structured mall data. It avoids nonsensical matches, explains limitations, creates missions users can actually test, and updates the journey instantly.</p>
</div>
""", unsafe_allow_html=True)

# Inputs
st.markdown('<div class="app-card">', unsafe_allow_html=True)
st.subheader("Create a test journey")
c1, c2 = st.columns(2)
with c1:
    budget = st.number_input("Budget / RMB", min_value=50, max_value=5000, value=200, step=50)
with c2:
    available_time = st.slider("Available time / minutes", 30, 240, 150, 15)

style = st.text_input("Style", value="casual chic")
goal = st.text_input("Shopping goal", value="cute weekend outfit and shoes")
priority = st.radio("Main priority", ["Trendy style", "Best value", "Beauty and skincare", "Gift shopping", "Fast route", "High-end experience"], horizontal=True)
free_text = st.text_area("Tell MiaoGo what you want in normal language", value="I want a cute weekend outfit with shoes, not too expensive, and I might want one beauty add-on.", height=90)
generate = st.button("Generate AI mall journey", type="primary")
st.markdown('</div>', unsafe_allow_html=True)

if generate or "journey_v2" not in st.session_state:
    with st.spinner("MiaoGo is reading the mall database and building your route..."):
        journey, ranked, used_ai, ai_status = build_journey(stores, budget, available_time, style, goal, priority, free_text)
    st.session_state["journey_v2"] = journey
    st.session_state["ranked_v2"] = ranked
    st.session_state["used_ai_v2"] = used_ai
    st.session_state["ai_status_v2"] = ai_status
else:
    journey = st.session_state["journey_v2"]
    ranked = st.session_state["ranked_v2"]
    used_ai = st.session_state.get("used_ai_v2", False)
    ai_status = st.session_state.get("ai_status_v2", "Smart local AI active")

st.markdown(f"""
<div class="ai-box">
    <span class="badge">{'Gemini + guardrails active' if used_ai else 'Smart local AI active'}</span>
    <p><b>AI journey summary:</b> {esc(journey.get("summary", ""))}</p>
    <p><b>Status:</b> {esc(ai_status)}</p>
</div>
""", unsafe_allow_html=True)

stops = journey.get("stops", [])[:4]
while len(stops) < 4:
    stops.append({"store_name":"Store","category":"Category","zone":"","floor":"","estimated_time_min":20,"reason":"","mission":"Complete a store mission.","reward":"Journey points.","match":"AI match"})

names = [esc(s.get("store_name", f"Store {i+1}")) for i, s in enumerate(stops)]
cats = [esc(s.get("category", "Store")) for s in stops]
times = [esc(s.get("estimated_time_min", "20")) for s in stops]
missions = [esc(s.get("mission", "Complete a mission.")) for s in stops]
matches = [esc(s.get("match", "AI match")) for s in stops]
total_time = to_int(journey.get("estimated_total_time", sum(to_int(s.get("estimated_time_min", 20), 20) for s in stops)), 90)

# Visual app component
app_html = f"""
<!DOCTYPE html>
<html>
<head>
<meta charset="UTF-8">
<link href="https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600;700;800;900&display=swap" rel="stylesheet">
<style>
*{{box-sizing:border-box;}}
body{{margin:0;font-family:Inter,-apple-system,BlinkMacSystemFont,"Segoe UI",sans-serif;background:transparent;color:#17142B;}}
.wrap{{display:grid;grid-template-columns:minmax(0,1.55fr) minmax(320px,.45fr);gap:28px;align-items:start;}}
.shell,.panel{{background:white;border:1px solid #EDE7F8;border-radius:30px;padding:24px;box-shadow:0 18px 45px rgba(51,34,101,.075);}}
.top{{display:flex;align-items:center;justify-content:space-between;margin-bottom:20px;}}
.person{{display:flex;align-items:center;gap:12px;}}
.avatar{{width:50px;height:50px;border-radius:50%;background:linear-gradient(135deg,#F2E9FF,#FFE1EF);border:1px solid #EEE5FF;position:relative;}}
.avatar:before{{content:"";position:absolute;width:14px;height:14px;border-radius:50%;background:#FFD0E1;top:9px;left:18px;}}
.avatar:after{{content:"";position:absolute;width:30px;height:22px;border-radius:20px 20px 14px 14px;background:#7B4DFF;bottom:5px;left:10px;}}
.greet{{font-size:25px;font-weight:950;letter-spacing:-.5px;}}
.sub,.lab,.pmeta,.klab,.rlab{{color:#817B97;}}
.sub{{font-size:14px;margin-top:2px;}}
.points{{background:#FFF8E7;border:1px solid #FFE6A9;border-radius:999px;padding:10px 16px;color:#AA6A00;font-size:17px;font-weight:950;}}
.sec{{display:flex;align-items:center;justify-content:space-between;margin:18px 0 12px;}}
.sec b{{font-size:22px;font-weight:950;}}
.sec span{{font-size:14px;font-weight:850;color:#7B4DFF;}}
.prefgrid{{display:grid;grid-template-columns:repeat(3,1fr);gap:14px;}}
.pref{{background:white;border:1px solid #EDE7F8;border-radius:22px;padding:18px;min-height:116px;box-shadow:0 10px 24px rgba(51,34,101,.055);}}
.ico{{width:34px;height:34px;border-radius:12px;background:#DDF7E8;margin-bottom:14px;}}
.pref:nth-child(2) .ico{{background:#E6F0FF;}}
.pref:nth-child(3) .ico{{background:#F1E2FF;}}
.lab{{font-size:13px;font-weight:850;}}
.val{{font-size:25px;font-weight:950;letter-spacing:-.8px;margin-top:2px;}}
.map{{height:360px;border:1px solid #EDE7F8;border-radius:28px;background:
    linear-gradient(rgba(255,255,255,.72),rgba(255,255,255,.72)),
    repeating-linear-gradient(90deg, transparent 0 92px, rgba(123,77,255,.08) 92px 100px),
    repeating-linear-gradient(0deg, transparent 0 82px, rgba(123,77,255,.08) 82px 90px),
    linear-gradient(135deg,#F5EFFF,#FFF6FA);
position:relative;overflow:hidden;margin-bottom:18px;box-shadow:inset 0 0 0 1px rgba(255,255,255,.7);}}
svg{{position:absolute;inset:0;z-index:1;pointer-events:none;}}
.pin{{position:absolute;z-index:3;background:white;border:1px solid #E5DBFF;border-radius:19px;padding:12px 13px;width:210px;box-shadow:0 18px 38px rgba(73,45,140,.15);}}
.ptitle{{font-size:14px;font-weight:950;display:flex;align-items:center;gap:8px;}}
.num{{width:31px;height:31px;background:linear-gradient(135deg,#7B4DFF,#A879FF);border-radius:11px 11px 11px 3px;transform:rotate(45deg);display:inline-flex;align-items:center;justify-content:center;flex:none;}}
.num span{{transform:rotate(-45deg);color:white;font-weight:950;}}
.pmeta{{font-size:12px;margin-top:6px;padding-left:40px;}}
.reason{{font-size:10.5px;color:#7B4DFF;padding-left:40px;margin-top:4px;font-weight:850;}}
.pin1{{left:250px;top:58px;}} .pin2{{right:88px;top:126px;}} .pin3{{left:90px;bottom:82px;}} .pin4{{right:170px;bottom:42px;}}
.start{{position:absolute;left:48px;top:94px;z-index:4;text-align:center;font-size:12px;color:#312B57;font-weight:850;}}
.startdot{{width:36px;height:36px;border-radius:50%;background:#17142B;color:white;display:flex;align-items:center;justify-content:center;font-weight:950;margin:0 auto 5px;}}
.end{{position:absolute;right:36px;bottom:18px;z-index:4;text-align:center;font-size:11px;color:#312B57;font-weight:850;}}
.enddot{{width:24px;height:24px;border-radius:50%;background:#17142B;border:5px solid white;margin:0 auto 4px;box-shadow:0 5px 14px rgba(0,0,0,.18);}}
.missiongrid{{display:grid;grid-template-columns:repeat(4,1fr);gap:14px;margin-bottom:18px;}}
.mission{{background:white;border:1px solid #EDE7F8;border-radius:22px;padding:16px;min-height:185px;text-align:center;box-shadow:0 10px 24px rgba(51,34,101,.055);}}
.mico{{width:48px;height:48px;border-radius:17px;background:linear-gradient(135deg,#EFE7FF,#FFF0F7);margin:0 auto 13px;}}
.mtitle{{font-size:14px;font-weight:900;line-height:1.25;min-height:72px;}}
.mpoints{{font-size:14px;color:#C97900;font-weight:950;margin-top:10px;}}
.mstate{{display:inline-block;margin-top:8px;padding:6px 10px;border-radius:999px;background:#F0EAFF;color:#7B4DFF;font-size:12px;font-weight:900;}}
.rewardgrid{{display:grid;grid-template-columns:repeat(3,1fr);gap:14px;}}
.reward,.kpi,.logic{{background:#FAF7FF;border:1px solid #EDE7F8;border-radius:20px;padding:16px;margin-bottom:13px;}}
.rnum,.kval{{font-size:31px;font-weight:950;color:#2B244D;letter-spacing:-.8px;}}
.nav{{display:grid;grid-template-columns:repeat(5,1fr);border-top:1px solid #EDE7F8;padding-top:15px;text-align:center;font-size:13px;font-weight:900;color:#5F5875;}}
.nav div:first-child{{color:#7B4DFF;}}
.panel h3{{margin-top:0;font-size:25px;}}
.panel p,.logic p{{color:#817B97;line-height:1.5;font-size:14px;}}
@media(max-width:900px){{.wrap{{grid-template-columns:1fr;}}.prefgrid,.missiongrid,.rewardgrid{{grid-template-columns:1fr;}}.map{{height:auto;padding:70px 14px;}}.pin{{position:relative;left:auto!important;right:auto!important;top:auto!important;bottom:auto!important;margin:10px 0;width:auto;}}}}
</style>
</head>
<body>
<div class="wrap">
  <div class="shell">
    <div class="top"><div class="person"><div class="avatar"></div><div><div class="greet">Hi, Mia</div><div class="sub">Let's plan your perfect mall trip</div></div></div><div class="points">2,480 pts</div></div>
    <div class="sec"><b>Your preferences</b><span>Edit</span></div>
    <div class="prefgrid">
      <div class="pref"><div class="ico"></div><div class="lab">Budget</div><div class="val">¥{budget}</div></div>
      <div class="pref"><div class="ico"></div><div class="lab">Time</div><div class="val">{round(available_time/60,1)}h</div></div>
      <div class="pref"><div class="ico"></div><div class="lab">Style</div><div class="val" style="font-size:20px;">{esc(style.title())}</div></div>
    </div>
    <div class="sec"><b>Your AI Mall Journey</b><span>Est. {round(total_time/60,1)}h</span></div>
    <div class="map">
      <svg viewBox="0 0 900 360" preserveAspectRatio="none"><path d="M90 145 C170 60, 295 70, 385 125 S585 170, 680 118 S845 130, 808 225 S625 318, 480 278 S255 246, 166 300" fill="none" stroke="#7B4DFF" stroke-width="6" stroke-linecap="round" stroke-dasharray="14 13" opacity=".88"/></svg>
      <div class="start"><div class="startdot">S</div>Start<br>Main entrance</div>
      <div class="pin pin1"><div class="ptitle"><div class="num"><span>1</span></div>{names[0]}</div><div class="pmeta">{cats[0]} · {times[0]} min</div><div class="reason">{matches[0]}</div></div>
      <div class="pin pin2"><div class="ptitle"><div class="num"><span>2</span></div>{names[1]}</div><div class="pmeta">{cats[1]} · {times[1]} min</div><div class="reason">{matches[1]}</div></div>
      <div class="pin pin3"><div class="ptitle"><div class="num"><span>3</span></div>{names[2]}</div><div class="pmeta">{cats[2]} · {times[2]} min</div><div class="reason">{matches[2]}</div></div>
      <div class="pin pin4"><div class="ptitle"><div class="num"><span>4</span></div>{names[3]}</div><div class="pmeta">{cats[3]} · {times[3]} min</div><div class="reason">{matches[3]}</div></div>
      <div class="end"><div class="enddot"></div>End<br>South exit</div>
    </div>
    <div class="sec"><b>AI Shopping Missions</b><span>Ready to test</span></div>
    <div class="missiongrid">
      <div class="mission"><div class="mico"></div><div class="mtitle">{missions[0][:95]}</div><div class="mpoints">+200 pts</div><div class="mstate">Available</div></div>
      <div class="mission"><div class="mico"></div><div class="mtitle">{missions[1][:95]}</div><div class="mpoints">+100 pts</div><div class="mstate">Available</div></div>
      <div class="mission"><div class="mico"></div><div class="mtitle">{missions[2][:95]}</div><div class="mpoints">+80 pts</div><div class="mstate">Available</div></div>
      <div class="mission"><div class="mico"></div><div class="mtitle">{missions[3][:95]}</div><div class="mpoints">+120 pts</div><div class="mstate">Available</div></div>
    </div>
    <div class="sec"><b>Your Rewards</b><span>Prototype</span></div>
    <div class="rewardgrid"><div class="reward"><div class="rnum">2,480</div><div class="rlab">Points</div></div><div class="reward"><div class="rnum">3</div><div class="rlab">Coupons</div></div><div class="reward"><div class="rnum">5</div><div class="rlab">Check-ins</div></div></div>
    <br><div class="nav"><div>Home</div><div>Missions</div><div>Map</div><div>Rewards</div><div>Me</div></div>
  </div>
  <div class="panel">
    <h3>AI + merchant impact</h3>
    <p>This panel explains what the AI is doing and what Yintai could measure after deployment.</p>
    <div class="kpi"><div class="kval">+28%</div><div class="klab">Route-start uplift simulation</div></div>
    <div class="kpi"><div class="kval">18.7%</div><div class="klab">Coupon redemption simulation</div></div>
    <div class="kpi"><div class="kval">{len(stops)}</div><div class="klab">Recommended journey stops</div></div>
    <div class="kpi"><div class="kval">{total_time}</div><div class="klab">Estimated journey minutes</div></div>
    <div class="logic"><b>AI guardrails</b><p>For themed requests like Halloween, the route avoids irrelevant sports stores unless the user asks for shoes.</p></div>
  </div>
</div>
</body>
</html>
"""
components.html(app_html, height=1160, scrolling=False)

# Details
st.markdown('<div class="app-card">', unsafe_allow_html=True)
st.subheader("AI recommendation details")
cols = st.columns(4)
for i, s in enumerate(stops):
    with cols[i]:
        st.markdown(f"""
        <div class="detail-card">
            <div style="font-size:12px;color:#7B4DFF!important;font-weight:950;">STOP {i+1}</div>
            <div style="font-size:18px;font-weight:950;margin:6px 0;color:#17142B!important;">{esc(s.get("store_name", ""))}</div>
            <div class="detail-small">{esc(s.get("category", ""))} · {esc(s.get("zone", ""))} · {esc(s.get("floor", ""))}</div>
            <div class="detail-copy"><b>Why:</b> {esc(s.get("reason", ""))}</div>
            <div class="detail-copy" style="margin-top:8px;"><b>Reward:</b> {esc(s.get("reward", ""))}</div>
            <div style="font-size:12px;color:#7B4DFF!important;font-weight:850;margin-top:10px;">Match: {esc(s.get("match", "AI match"))}</div>
        </div>
        """, unsafe_allow_html=True)
st.markdown('</div>', unsafe_allow_html=True)

# Adaptation
st.markdown('<div class="app-card">', unsafe_allow_html=True)
st.subheader("Real-time AI adaptation")
change_text = st.text_input("Test a behavior change", value="I spent 25 minutes in KFC because I am hungry")
if st.button("Update journey based on behavior"):
    detected, logic, mission, reward, next_stops = instant_adaptation(change_text, stores)
    st.markdown(f"""
    <div class="adapt-box">
        <h3 style="color:#17142B!important;">MiaoGo detected: {esc(detected)}</h3>
        <p>{esc(logic)}</p>
        <p><b>New bonus mission:</b> {esc(mission)}</p>
        <p><b>New reward:</b> {esc(reward)}</p>
        <p style="color:#7B4DFF!important;font-weight:800;">Instant adaptation completed.</p>
    </div>
    """, unsafe_allow_html=True)
    scols = st.columns(3)
    for col, s in zip(scols, next_stops):
        with col:
            st.markdown(f"""
            <div class="detail-card" style="min-height:170px;">
                <div style="font-size:18px;font-weight:950;margin-bottom:4px;color:#17142B!important;">{esc(s.get("store_name", ""))}</div>
                <div class="detail-copy"><b>Reason:</b> {esc(s.get("reason", ""))}<br><br><b>Mission:</b> {esc(s.get("mission", ""))}</div>
            </div>
            """, unsafe_allow_html=True)
st.markdown('</div>', unsafe_allow_html=True)

st.subheader("Mission test")
st.write("Testers can mark which missions they would actually do.")
for i, s in enumerate(stops):
    st.checkbox(f"{s.get('store_name', '')}: {s.get('mission', '')}", key=f"mission_{i}")

st.subheader("Tester feedback")
with st.form("feedback_form"):
    f1, f2 = st.columns(2)
    with f1:
        rating = st.slider("Overall rating", 1, 5, 4)
        would_use = st.radio("Would you use this inside Miaojie?", ["Yes", "Maybe", "No"], horizontal=True)
    with f2:
        open_more = st.radio("Would this make you open Miaojie more often?", ["Yes", "Maybe", "No"], horizontal=True)
        useful_part = st.radio("Most useful part", ["AI route", "Missions", "Rewards", "Real-time adaptation", "Repurchase reminder"], horizontal=True)
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
            "free_text": free_text,
            "used_ai": used_ai,
            "rating": rating,
            "would_use": would_use,
            "open_more": open_more,
            "useful_part": useful_part,
            "improvement": improvement
        }])
        feedback.to_csv("feedback.csv", mode="a", header=not os.path.exists("feedback.csv"), index=False)
        st.success("Feedback saved. Thank you for testing MiaoGo.")

if os.path.exists("feedback.csv"):
    with open("feedback.csv", "rb") as f:
        st.download_button("Download feedback CSV", f, file_name="miaogo_feedback.csv", mime="text/csv")

with st.expander("Structured MVP dataset"):
    st.dataframe(stores, use_container_width=True)

with st.expander("Ranking table used by AI guardrails"):
    display_cols = [c for c in ["store_name", "category", "price_level", "estimated_time_min", "ai_score", "match_reasons"] if c in ranked.columns]
    st.dataframe(ranked[display_cols].head(25), use_container_width=True)
    
