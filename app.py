
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

# -----------------------------
# Load data
# -----------------------------
@st.cache_data
def load_data():
    df = pd.read_csv("stores.csv")
    df.columns = [c.strip() for c in df.columns]
    return df

stores = load_data()

# -----------------------------
# Helpers
# -----------------------------
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

def first_nonempty(*values):
    for v in values:
        if v is not None and str(v).strip():
            return str(v)
    return ""

def detect_intents(style, goal, priority, free_text):
    text = f"{style} {goal} {priority} {free_text}".lower()
    return {
        "halloween": any(x in text for x in ["halloween", "scary", "creepy", "costume", "goth", "dark", "witch", "vampire"]),
        "fashion": any(x in text for x in ["outfit", "dress", "clothes", "fashion", "style", "cute", "casual", "chic", "fancy", "look"]),
        "shoes": any(x in text for x in ["shoe", "shoes", "sneaker", "sneakers", "nike", "boots"]),
        "beauty": any(x in text for x in ["beauty", "makeup", "skincare", "perfume", "lipstick", "sephora", "colorist"]),
        "gift": any(x in text for x in ["gift", "present", "friend", "family"]),
        "food": any(x in text for x in ["coffee", "food", "drink", "hungry", "tired", "break", "rest", "kfc"]),
        "budget": any(x in text for x in ["cheap", "budget", "affordable", "value", "student", "not expensive"]),
        "premium": any(x in text for x in ["premium", "luxury", "high-end", "high end", "fancy"]),
        "fast": any(x in text for x in ["fast", "quick", "short", "rush"]),
    }

def short_store_context(df, max_rows=45):
    cols = [
        "store_name","mall_name","zone","floor","category","sub_category","price_level",
        "budget_min_rmb","budget_max_rmb","best_for","style_tags","target_user",
        "estimated_time_min","mission","reward","coupon_type","repurchase_trigger",
        "ai_reason","keywords"
    ]
    existing = [c for c in cols if c in df.columns]
    return df[existing].head(max_rows).to_dict(orient="records")

def call_gemini_text(prompt, timeout=18):
    api_key = st.secrets.get("GEMINI_API_KEY", "")
    model = st.secrets.get("GEMINI_MODEL", "gemini-3-flash-preview")

    if not api_key:
        return None, "No GEMINI_API_KEY found in Streamlit Secrets."

    url = f"https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent?key={api_key}"
    payload = {
        "contents": [
            {
                "role": "user",
                "parts": [{"text": prompt}]
            }
        ],
        "generationConfig": {
            "temperature": 0.35,
            "topP": 0.9,
            "maxOutputTokens": 1800
        }
    }

    try:
        data = json.dumps(payload).encode("utf-8")
        req = urllib.request.Request(
            url,
            data=data,
            headers={"Content-Type": "application/json"},
            method="POST"
        )
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            raw = resp.read().decode("utf-8")
            obj = json.loads(raw)
            text = obj["candidates"][0]["content"]["parts"][0]["text"]
            return text, None

    except urllib.error.HTTPError as e:
        try:
            err = e.read().decode("utf-8")
        except Exception:
            err = str(e)
        return None, f"Gemini HTTP error: {err[:450]}"
    except Exception as e:
        return None, f"Gemini request failed: {e}"

def parse_json_loose(text):
    if not text:
        raise ValueError("empty Gemini response")
    t = text.strip()
    t = t.replace("```json", "").replace("```", "").strip()
    start = t.find("{")
    end = t.rfind("}")
    if start >= 0 and end > start:
        t = t[start:end + 1]
    return json.loads(t)

def rank_stores(df, budget, time_minutes, style, goal, priority, free_text):
    intents = detect_intents(style, goal, priority, free_text)
    user_text = f"{style} {goal} {priority} {free_text}".lower()

    def score(row):
        text = " ".join([
            safe(row, "store_name"), safe(row, "category"), safe(row, "sub_category"),
            safe(row, "best_for"), safe(row, "style_tags"), safe(row, "target_user"),
            safe(row, "keywords"), safe(row, "ai_reason"), safe(row, "mission"),
            safe(row, "reward"), safe(row, "repurchase_trigger")
        ]).lower()

        s = 0
        reasons = []

        for word in re.findall(r"[a-zA-Z\u4e00-\u9fff]+", user_text):
            if len(word) > 2 and word in text:
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

        if intents["halloween"]:
            if any(x in text for x in ["fashion", "dress", "clothes", "outfit", "beauty", "makeup", "accessory", "color", "sephora", "miniso"]):
                s += 18
                reasons.append("Halloween look fit")

        if intents["fashion"] and any(x in text for x in ["fashion", "dress", "outfit", "clothes", "style", "sportswear"]):
            s += 12
            reasons.append("outfit match")

        if intents["shoes"] and any(x in text for x in ["shoe", "sneaker", "nike", "sportswear"]):
            s += 14
            reasons.append("shoe match")

        if intents["beauty"] and any(x in text for x in ["beauty", "makeup", "skincare", "perfume", "lipstick", "sephora", "colorist"]):
            s += 14
            reasons.append("beauty match")

        if intents["gift"] and any(x in text for x in ["gift", "toy", "family", "lifestyle", "entertainment"]):
            s += 12
            reasons.append("gift match")

        if intents["food"] and any(x in text for x in ["coffee", "food", "drink", "break", "kfc"]):
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

def fallback_journey(df, budget, time_minutes, style, goal, priority, free_text):
    intents = detect_intents(style, goal, priority, free_text)
    ranked = rank_stores(df, budget, time_minutes, style, goal, priority, free_text)

    route = []
    used = set()

    def add_matching(filter_words):
        nonlocal route, used
        for _, row in ranked.iterrows():
            if len(route) >= 4:
                return
            name = safe(row, "store_name")
            text = str(row).lower()
            if name not in used and any(w in text for w in filter_words):
                route.append(row)
                used.add(name)
                return

    if intents["halloween"]:
        add_matching(["fashion", "dress", "outfit", "clothes"])
        add_matching(["beauty", "makeup", "sephora", "colorist", "perfume", "lipstick"])
        add_matching(["accessory", "miniso", "lifestyle", "gift"])
        add_matching(["shoe", "sneaker", "sportswear", "nike"])
    elif intents["fashion"]:
        add_matching(["fashion", "outfit", "clothes", "dress"])
    if intents["shoes"]:
        add_matching(["shoe", "sneaker", "nike", "sportswear"])
    if intents["beauty"]:
        add_matching(["beauty", "makeup", "skincare", "sephora", "colorist"])
    if intents["gift"]:
        add_matching(["gift", "toy", "lifestyle", "entertainment", "miniso"])
    if intents["food"]:
        add_matching(["coffee", "food", "drink", "break", "kfc"])

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
        base_reason = safe(row, "ai_reason", safe(row, "best_for"))
        base_mission = safe(row, "mission")
        base_reward = safe(row, "reward")

        if intents["halloween"]:
            if "beauty" in category.lower() or any(x in name.lower() for x in ["sephora", "colorist"]):
                mission = "Create one scary makeup or dark-color add-on that matches the Halloween outfit."
                reason = "Good for completing the Halloween look with makeup, color, or beauty detail."
            elif any(x in category.lower() for x in ["fashion", "sportswear"]) or any(x in name.lower() for x in ["ur", "only", "ledin", "uniqlo", "nike"]):
                mission = "Find one dark, dramatic, or costume-like piece that can work for a Halloween outfit."
                reason = "Useful for building the core Halloween outfit from available fashion stores."
            else:
                mission = "Pick one small accessory that makes the look more Halloween-ready."
                reason = "Adds a low-cost detail to make the outfit feel more themed."
        else:
            mission = base_mission or "Complete one store mission that fits your shopping goal."
            reason = base_reason or "Selected because it matches the user’s shopping goal and route constraints."

        stops.append({
            "store_name": name,
            "category": category,
            "zone": safe(row, "zone"),
            "floor": safe(row, "floor"),
            "estimated_time_min": to_int(row.get("estimated_time_min", 20), 20),
            "reason": reason,
            "mission": mission,
            "reward": base_reward or "Unlock journey points or a coupon.",
            "repurchase_reminder": safe(row, "repurchase_trigger", "Follow up with matching products later."),
            "match": safe(row, "match_reasons", "AI match")
        })

    total_time = sum(s["estimated_time_min"] for s in stops)

    if intents["halloween"]:
        summary = (
            "MiaoGo understood this as a Halloween/scary outfit request. Since the MVP database does not contain a dedicated costume store, "
            "it builds the closest realistic mall journey using fashion, beauty, accessory, and shoe stops from the structured Yintai dataset."
        )
    else:
        summary = (
            "MiaoGo generated a personalized route by matching the user’s budget, available time, style, shopping goal, store categories, missions, rewards, and repurchase triggers."
        )

    return {
        "summary": summary,
        "route_name": "Personalized MiaoGo Journey",
        "estimated_total_time": total_time,
        "stops": stops,
        "overall_reward": "Journey points, coupons, and check-in rewards.",
        "repurchase_strategy": "After the visit, MiaoGo can send refill, replacement, or matching-product reminders based on the selected items.",
        "limits": "This MVP uses structured prototype data. Real deployment would connect to Miaojie store, coupon, event, check-in, and transaction APIs."
    }, ranked

def gemini_journey(df, budget, time_minutes, style, goal, priority, free_text):
    fallback, ranked = fallback_journey(df, budget, time_minutes, style, goal, priority, free_text)
    context = short_store_context(ranked, max_rows=35)

    prompt = f"""
You are MiaoGo, an expert AI shopping journey planner for Yintai/Miaojie.
Use ONLY the provided store database. Do not invent stores.
Understand messy user needs and create a practical route.

User:
- Budget RMB: {budget}
- Available time minutes: {time_minutes}
- Style: {style}
- Shopping goal: {goal}
- Priority: {priority}
- Free text: {free_text}

Store database:
{json.dumps(context, ensure_ascii=False)}

Return ONLY valid JSON, no markdown, no explanation outside JSON:
{{
  "summary": "smart paragraph explaining user intent and route logic",
  "route_name": "short route name",
  "estimated_total_time": 100,
  "stops": [
    {{
      "store_name": "exact database store name",
      "category": "category",
      "zone": "zone",
      "floor": "floor",
      "estimated_time_min": 25,
      "reason": "specific reason",
      "mission": "specific mission user can actually do",
      "reward": "specific reward/coupon/points idea",
      "repurchase_reminder": "later reminder",
      "match": "short match label"
    }}
  ],
  "overall_reward": "overall reward",
  "repurchase_strategy": "how MiaoGo brings user back",
  "limits": "honest MVP limitation"
}}

Rules:
- Exactly 4 stops.
- If the user asks for Halloween/scary/creepy/costume, build the closest Halloween look from fashion + beauty + accessories. Say in summary that dedicated costume stores are not in the MVP database if relevant.
- If the user asks for food/break/hungry, include a food/coffee stop only if available in database.
- Keep it budget-aware.
- Make every mission specific and testable.
"""

    text, err = call_gemini_text(prompt, timeout=16)
    if err:
        return fallback, ranked, False, err

    try:
        data = parse_json_loose(text)
        if "stops" not in data or len(data["stops"]) < 4:
            raise ValueError("Gemini returned fewer than 4 stops")
        data["stops"] = data["stops"][:4]
        return data, ranked, True, "Gemini AI active"
    except Exception as e:
        # Even if Gemini JSON fails, use strong personalized fallback rather than dumb generic fallback
        return fallback, ranked, False, f"Gemini replied but JSON parsing failed, using strong local personalization: {e}"

def instant_adaptation(change_text, journey, stores):
    text = change_text.lower()
    if any(x in text for x in ["kfc", "hungry", "food", "eat", "tired", "coffee", "break", "rest"]):
        detected = "food or rest need"
        logic = "MiaoGo pauses the shopping route and adds a nearby food or coffee break before continuing."
        mission = "Take a short break, check in, then decide whether to continue the original route or skip the lowest-priority stop."
        reward = "Coffee or food break points."
        words = ["food", "coffee", "drink", "break", "kfc"]
    elif any(x in text for x in ["nike", "shoe", "sneaker", "shoes", "boots"]):
        detected = "shoe interest"
        logic = "MiaoGo shifts the route toward shoe matching and outfit completion."
        mission = "Try two shoe styles and compare comfort, price, and outfit match."
        reward = "Shoe coupon or bonus journey points."
        words = ["shoe", "sneaker", "nike", "sportswear"]
    elif any(x in text for x in ["beauty", "makeup", "sephora", "lipstick", "perfume", "skincare"]):
        detected = "beauty interest"
        logic = "MiaoGo adds a beauty stop to complete the look."
        mission = "Choose one makeup or fragrance item that matches the outfit mood."
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

    ranked = stores.copy()
    if words:
        mask = ranked.apply(lambda r: any(w in str(r).lower() for w in words), axis=1)
        ranked = ranked[mask]
    if ranked.empty:
        ranked = stores.head(3)

    next_stops = []
    for _, row in ranked.head(3).iterrows():
        next_stops.append({
            "store_name": safe(row, "store_name"),
            "reason": safe(row, "ai_reason", safe(row, "best_for")),
            "mission": safe(row, "mission", mission)
        })

    return {
        "detected_signal": detected,
        "updated_logic": logic,
        "bonus_mission": mission,
        "new_reward": reward,
        "next_best_stops": next_stops
    }

# -----------------------------
# Header
# -----------------------------
st.markdown("""
<div style="display:flex;align-items:center;justify-content:space-between;margin-bottom:18px;">
  <div style="display:flex;align-items:center;gap:13px;">
    <div style="width:48px;height:48px;border-radius:16px;background:linear-gradient(135deg,#7B4DFF,#FF7DBB);display:flex;align-items:center;justify-content:center;color:white;font-weight:900;font-size:23px;box-shadow:0 14px 30px rgba(123,77,255,.23);">M</div>
    <div>
      <div style="font-size:27px;font-weight:900;letter-spacing:-.8px;line-height:1;">MiaoGo</div>
      <div style="font-size:13px;color:#817B97;margin-top:3px;">AI shopping journey assistant for Miaojie</div>
    </div>
  </div>
  <div style="background:white;border:1px solid #EDE7F8;border-radius:999px;padding:10px 15px;color:#5D38D6;font-weight:850;font-size:13px;box-shadow:0 10px 25px rgba(51,34,101,.08);">AI MVP Demo</div>
</div>

<div class="hero-card">
  <h1>Plan mall journeys that feel personal, useful, and <span class="grad">worth opening the app for.</span></h1>
  <p>MiaoGo combines Gemini with structured mall data. If Gemini is slow or returns invalid JSON, the app uses a stronger instant personalization engine so testing never gets stuck.</p>
</div>
""", unsafe_allow_html=True)

# -----------------------------
# Inputs
# -----------------------------
st.markdown('<div class="app-card">', unsafe_allow_html=True)
st.subheader("Create a test journey")
c1, c2 = st.columns(2)
with c1:
    budget = st.number_input("Budget / RMB", min_value=50, max_value=5000, value=200, step=50)
with c2:
    available_time = st.slider("Available time / minutes", 30, 240, 150, 15)

style = st.text_input("Style", value="casual chic")
goal = st.text_input("Shopping goal", value="cute weekend outfit and shoes")

priority = st.radio(
    "Main priority",
    ["Trendy style", "Best value", "Beauty and skincare", "Gift shopping", "Fast route", "High-end experience"],
    horizontal=True
)

free_text = st.text_area(
    "Tell MiaoGo what you want in normal language",
    value="I want a cute weekend outfit with shoes, not too expensive, and I might want one beauty add-on.",
    height=90
)

generate = st.button("Generate AI mall journey", type="primary")
st.markdown('</div>', unsafe_allow_html=True)

if generate or "journey" not in st.session_state:
    with st.spinner("MiaoGo is reading the mall database and building your route..."):
        journey, ranked, used_ai, ai_status = gemini_journey(
            stores, budget, available_time, style, goal, priority, free_text
        )
    st.session_state["journey"] = journey
    st.session_state["ranked"] = ranked
    st.session_state["used_ai"] = used_ai
    st.session_state["ai_status"] = ai_status
else:
    journey = st.session_state["journey"]
    ranked = st.session_state["ranked"]
    used_ai = st.session_state["used_ai"]
    ai_status = st.session_state["ai_status"]

st.markdown(f"""
<div class="ai-box">
    <span class="badge">{'Gemini AI active' if used_ai else 'Smart fallback active'}</span>
    <p><b>AI journey summary:</b> {esc(journey.get("summary", ""))}</p>
    <p><b>Status:</b> {esc(ai_status)}</p>
</div>
""", unsafe_allow_html=True)

stops = journey.get("stops", [])[:4]
while len(stops) < 4:
    stops.append({
        "store_name": "Store",
        "category": "Category",
        "zone": "",
        "floor": "",
        "estimated_time_min": 20,
        "reason": "",
        "mission": "Complete a store mission.",
        "reward": "Journey points.",
        "repurchase_reminder": "Follow-up reminder.",
        "match": "AI match"
    })

names = [esc(s.get("store_name", f"Store {i+1}")) for i, s in enumerate(stops)]
cats = [esc(s.get("category", "Store")) for s in stops]
times = [esc(s.get("estimated_time_min", "20")) for s in stops]
missions = [esc(s.get("mission", "Complete a mission.")) for s in stops]
matches = [esc(s.get("match", "AI match")) for s in stops]
total_time = to_int(journey.get("estimated_total_time", sum(to_int(s.get("estimated_time_min", 20), 20) for s in stops)), 90)

# -----------------------------
# Visual app component
# -----------------------------
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
.shell{{background:white;border:1px solid #EDE7F8;border-radius:30px;padding:24px;box-shadow:0 18px 45px rgba(51,34,101,.075);}}
.top{{display:flex;align-items:center;justify-content:space-between;margin-bottom:20px;}}
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
.pmeta{{font-size:12px;color:#817B97;margin-top:6px;padding-left:40px;}}
.reason{{font-size:10.5px;color:#7B4DFF;padding-left:40px;margin-top:4px;font-weight:850;}}
.pin1{{left:250px;top:58px;}}
.pin2{{right:88px;top:126px;}}
.pin3{{left:90px;bottom:82px;}}
.pin4{{right:170px;bottom:42px;}}
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
.logic{{background:linear-gradient(135deg,#F3EEFF,#FFF5FA);border:1px solid #E6DAFF;border-radius:20px;padding:16px;margin-top:14px;}}
.logic b{{font-size:14px;}}
.logic p{{font-size:13px;color:#5F5875;line-height:1.45;margin:8px 0 0 0;}}
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
    <div class="rewardgrid">
      <div class="reward"><div class="rnum">2,480</div><div class="rlab">Points</div></div>
      <div class="reward"><div class="rnum">3</div><div class="rlab">Coupons</div></div>
      <div class="reward"><div class="rnum">5</div><div class="rlab">Check-ins</div></div>
    </div>
    <br>
    <div class="nav"><div>Home</div><div>Missions</div><div>Map</div><div>Rewards</div><div>Me</div></div>
  </div>

  <div class="panel">
    <h3>AI + merchant impact</h3>
    <p>This panel explains what the AI is doing and what Yintai could measure after deployment.</p>
    <div class="kpi"><div class="kval">+28%</div><div class="klab">Route-start uplift simulation</div></div>
    <div class="kpi"><div class="kval">18.7%</div><div class="klab">Coupon redemption simulation</div></div>
    <div class="kpi"><div class="kval">{len(stops)}</div><div class="klab">Recommended journey stops</div></div>
    <div class="kpi"><div class="kval">{total_time}</div><div class="klab">Estimated journey minutes</div></div>
    <div class="logic">
      <b>AI logic</b>
      <p>Gemini or the instant personalization engine reads the user request and structured store data, then chooses route stops, missions, rewards, and repurchase logic.</p>
    </div>
  </div>
</div>
</body>
</html>
"""

components.html(app_html, height=1160, scrolling=False)

# -----------------------------
# Details
# -----------------------------
st.markdown('<div class="app-card">', unsafe_allow_html=True)
st.subheader("AI recommendation details")
cols = st.columns(4)
for i, s in enumerate(stops):
    with cols[i]:
        st.markdown(
            f"""
            <div style="background:white;border:1px solid #EDE7F8;border-radius:22px;padding:17px;min-height:235px;box-shadow:0 10px 24px rgba(51,34,101,.055);">
                <div style="font-size:12px;color:#7B4DFF;font-weight:950;">STOP {i+1}</div>
                <div style="font-size:18px;font-weight:950;margin:6px 0;">{esc(s.get("store_name", ""))}</div>
                <div style="font-size:12px;color:#817B97;margin-bottom:9px;">{esc(s.get("category", ""))} · {esc(s.get("zone", ""))} · {esc(s.get("floor", ""))}</div>
                <div style="font-size:13px;line-height:1.45;color:#423D5D;"><b>Why:</b> {esc(s.get("reason", ""))}</div>
                <div style="font-size:13px;line-height:1.45;color:#423D5D;margin-top:8px;"><b>Reward:</b> {esc(s.get("reward", ""))}</div>
                <div style="font-size:12px;color:#7B4DFF;font-weight:850;margin-top:10px;">Match: {esc(s.get("match", "AI match"))}</div>
            </div>
            """,
            unsafe_allow_html=True,
        )
st.markdown('</div>', unsafe_allow_html=True)

# -----------------------------
# Real-time adaptation - instant, no freezing
# -----------------------------
st.markdown('<div class="app-card">', unsafe_allow_html=True)
st.subheader("Real-time AI adaptation")
change_text = st.text_input("Test a behavior change", value="I spent 25 minutes in Nike because I liked the shoes.")

if st.button("Update journey based on behavior"):
    adapt = instant_adaptation(change_text, journey, stores)
    st.markdown(
        f"""
        <div style="background:linear-gradient(135deg,#F3EEFF,#FFF5FA);border:1px solid #E6DAFF;border-radius:22px;padding:18px;margin-top:14px;">
            <h3>MiaoGo detected: {esc(adapt.get("detected_signal", ""))}</h3>
            <p style="color:#5F5875;">{esc(adapt.get("updated_logic", ""))}</p>
            <p><b>New bonus mission:</b> {esc(adapt.get("bonus_mission", ""))}</p>
            <p><b>New reward:</b> {esc(adapt.get("new_reward", ""))}</p>
            <p style="color:#7B4DFF;font-weight:800;">Instant adaptation completed.</p>
        </div>
        """,
        unsafe_allow_html=True,
    )

    next_stops = adapt.get("next_best_stops", [])[:3]
    if next_stops:
        scols = st.columns(3)
        for col, s in zip(scols, next_stops):
            with col:
                st.markdown(
                    f"""
                    <div style="background:white;border:1px solid #EDE7F8;border-radius:22px;padding:17px;min-height:170px;box-shadow:0 10px 24px rgba(51,34,101,.055);">
                        <div style="font-size:18px;font-weight:950;margin-bottom:4px;">{esc(s.get("store_name", ""))}</div>
                        <div style="font-size:13px;line-height:1.45;color:#423D5D;"><b>Reason:</b> {esc(s.get("reason", ""))}<br><br><b>Mission:</b> {esc(s.get("mission", ""))}</div>
                    </div>
                    """,
                    unsafe_allow_html=True,
                )
st.markdown('</div>', unsafe_allow_html=True)

# -----------------------------
# Mission test
# -----------------------------
st.subheader("Mission test")
st.write("Testers can mark which missions they would actually do.")
for i, s in enumerate(stops):
    st.checkbox(f"{s.get('store_name', '')}: {s.get('mission', '')}", key=f"mission_{i}")

# -----------------------------
# Feedback
# -----------------------------
st.subheader("Tester feedback")
with st.form("feedback_form"):
    f1, f2 = st.columns(2)
    with f1:
        rating = st.slider("Overall rating", 1, 5, 4)
        would_use = st.radio("Would you use this inside Miaojie?", ["Yes", "Maybe", "No"], horizontal=True)
    with f2:
        open_more = st.radio("Would this make you open Miaojie more often?", ["Yes", "Maybe", "No"], horizontal=True)
        useful_part = st.radio(
            "Most useful part",
            ["AI route", "Missions", "Rewards", "Real-time adaptation", "Repurchase reminder"],
            horizontal=True
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
            "free_text": free_text,
            "used_ai": used_ai,
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

with st.expander("Ranking table used by instant personalization"):
    display_cols = [c for c in ["store_name", "category", "price_level", "estimated_time_min", "ai_score", "match_reasons"] if c in ranked.columns]
    st.dataframe(ranked[display_cols].head(25), use_container_width=True)
