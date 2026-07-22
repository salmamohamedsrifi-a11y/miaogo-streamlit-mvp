
from datetime import datetime
import os, re, json, html
import pandas as pd
import streamlit as st
import streamlit.components.v1 as components
import google.generativeai as genai

st.set_page_config(page_title="MiaoGo MVP", page_icon="M", layout="wide", initial_sidebar_state="collapsed")

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

def intval(x, default=20):
    try:
        return int(float(x))
    except Exception:
        return default

def clean_json(text):
    text = text.strip().replace("```json", "").replace("```", "").strip()
    start, end = text.find("{"), text.rfind("}")
    if start != -1 and end != -1:
        return text[start:end+1]
    return text

def local_rank(df, budget, time_minutes, style, goal, priority, free_text):
    user_text = f"{style} {goal} {priority} {free_text}".lower()

    def score(row):
        db = " ".join([
            safe(row,"store_name"), safe(row,"category"), safe(row,"sub_category"),
            safe(row,"best_for"), safe(row,"style_tags"), safe(row,"target_user"),
            safe(row,"keywords"), safe(row,"ai_reason"), safe(row,"mission"),
            safe(row,"reward"), safe(row,"repurchase_trigger"), safe(row,"price_level")
        ]).lower()
        s = 0
        for w in re.findall(r"[a-zA-Z\u4e00-\u9fff]+", user_text):
            if len(w) > 2 and w in db: s += 3
        try:
            mn = float(row.get("budget_min_rmb",0)); mx = float(row.get("budget_max_rmb",999999))
            if mn <= budget <= mx: s += 8
            elif budget >= mn*.65 and budget <= mx*1.4: s += 4
        except Exception:
            pass
        if any(x in user_text for x in ["outfit","fashion","style","cute","casual","chic","clothes"]):
            if any(x in db for x in ["fashion","outfit","clothes","sportswear","style"]): s += 10
        if any(x in user_text for x in ["shoe","shoes","sneaker","nike"]):
            if any(x in db for x in ["shoe","sneaker","nike","sportswear"]): s += 12
        if any(x in user_text for x in ["beauty","makeup","skincare","perfume","lipstick","sephora"]):
            if any(x in db for x in ["beauty","makeup","skincare","perfume","lipstick","sephora"]): s += 12
        if any(x in user_text for x in ["gift","present"]):
            if any(x in db for x in ["gift","toy","lifestyle","entertainment"]): s += 10
        if any(x in user_text for x in ["coffee","break","tired","hungry","rest"]):
            if any(x in db for x in ["coffee","food","drink","break"]): s += 8
        if any(x in user_text for x in ["fast","quick"]) and intval(row.get("estimated_time_min",20)) <= 20:
            s += 6
        return s

    ranked = df.copy()
    ranked["ai_score"] = ranked.apply(score, axis=1)
    return ranked.sort_values("ai_score", ascending=False)

def fallback_journey(df, budget, time_minutes, style, goal, priority, free_text):
    ranked = local_rank(df, budget, time_minutes, style, goal, priority, free_text)
    stops = []
    used = set()
    for _, r in ranked.iterrows():
        name = safe(r, "store_name")
        if name in used: continue
        stops.append({
            "store_name": name,
            "category": safe(r, "category"),
            "zone": safe(r, "zone"),
            "floor": safe(r, "floor"),
            "estimated_time_min": intval(r.get("estimated_time_min", 20)),
            "reason": safe(r, "ai_reason", safe(r, "best_for")),
            "mission": safe(r, "mission"),
            "reward": safe(r, "reward"),
            "repurchase_reminder": safe(r, "repurchase_trigger"),
            "match": "local AI match"
        })
        used.add(name)
        if len(stops) == 4: break
    return {
        "summary": "MiaoGo generated a route using the local fallback engine: budget fit, time fit, store category, mission value, rewards, and repurchase triggers.",
        "route_name": "MiaoGo Journey",
        "estimated_total_time": sum(s["estimated_time_min"] for s in stops),
        "stops": stops,
        "overall_reward": "Journey points, coupons, and check-in rewards",
        "repurchase_strategy": "MiaoGo follows up with refill, replacement, or matching-product reminders.",
        "limits": "Prototype data only. Real deployment would connect to Miaojie APIs."
    }, ranked

def gemini_journey(df, budget, time_minutes, style, goal, priority, free_text):
    fallback, ranked = fallback_journey(df, budget, time_minutes, style, goal, priority, free_text)
    key = st.secrets.get("GEMINI_API_KEY", "")
    if not key:
        return fallback, ranked, False, "No Gemini key found."

    cols = [c for c in ["store_name","mall_name","zone","floor","category","sub_category","price_level",
                        "budget_min_rmb","budget_max_rmb","best_for","style_tags","target_user",
                        "estimated_time_min","mission","reward","coupon_type","repurchase_trigger",
                        "ai_reason","keywords","data_status","source_note"] if c in ranked.columns]
    context = ranked[cols].head(30).to_dict(orient="records")

    prompt = f"""
You are MiaoGo, an expert AI shopping journey planner for Yintai/Miaojie.
Use ONLY the provided store database. Do not invent stores. Do not claim private real Miaojie data.
Create a smart, realistic, testable mall journey.

Return ONLY valid JSON:
{{
 "summary":"smart paragraph explaining user intent and route logic",
 "route_name":"short name",
 "estimated_total_time":120,
 "stops":[
   {{"store_name":"database store name","category":"category","zone":"zone","floor":"floor","estimated_time_min":20,
     "reason":"why this store fits budget/style/goal","mission":"specific testable mission",
     "reward":"specific reward/coupon/points idea","repurchase_reminder":"after-visit reminder",
     "match":"2-4 word match label"}}
 ],
 "overall_reward":"overall journey reward",
 "repurchase_strategy":"how MiaoGo brings user back",
 "limits":"honest MVP limitation"
}}
Rules:
- Exactly 4 stops.
- Respect budget and time.
- Make missions specific and doable now.
- Include beauty/shoes/gift/coffee only when useful from the user's request.
- Be more useful than a normal chatbot: explain reasoning, connect route + mission + reward + repurchase.

USER:
budget_rmb={budget}
available_time_minutes={time_minutes}
style={style}
goal={goal}
priority={priority}
free_text={free_text}

STORE DATABASE:
{json.dumps(context, ensure_ascii=False)}
"""
    try:
        genai.configure(api_key=key)
        model_name = st.secrets.get("GEMINI_MODEL", "gemini-1.5-flash")
        model = genai.GenerativeModel(model_name)
        resp = model.generate_content(prompt, generation_config={
            "temperature": 0.35,
            "top_p": 0.9,
            "max_output_tokens": 1800,
            "response_mime_type": "application/json"
        })
        data = json.loads(clean_json(resp.text))
        if "stops" not in data or len(data["stops"]) < 4:
            raise ValueError("Missing 4 stops")
        data["stops"] = data["stops"][:4]
        return data, ranked, True, "Gemini AI active."
    except Exception as e:
        return fallback, ranked, False, f"Gemini fallback used: {e}"

def gemini_adapt(journey, change_text, df):
    key = st.secrets.get("GEMINI_API_KEY", "")
    if not key:
        return {
            "detected_signal":"behavior change",
            "updated_logic":"MiaoGo updates the journey using the new behavior signal.",
            "bonus_mission":"Complete one adaptive mission based on the new interest.",
            "new_reward":"Adaptive journey points.",
            "next_best_stops":[]
        }, False
    context = df.head(35).to_dict(orient="records")
    prompt = f"""
You are MiaoGo. Adapt the current mall route based on user behavior.
Use only database stores. Return ONLY JSON:
{{"detected_signal":"","updated_logic":"","bonus_mission":"","new_reward":"","next_best_stops":[{{"store_name":"","reason":"","mission":""}}]}}
CURRENT JOURNEY:
{json.dumps(journey, ensure_ascii=False)}
USER BEHAVIOR:
{change_text}
STORE DATABASE:
{json.dumps(context, ensure_ascii=False)}
"""
    try:
        genai.configure(api_key=key)
        model = genai.GenerativeModel(st.secrets.get("GEMINI_MODEL", "gemini-1.5-flash"))
        resp = model.generate_content(prompt, generation_config={
            "temperature":0.35, "top_p":0.9, "max_output_tokens":900, "response_mime_type":"application/json"
        })
        return json.loads(clean_json(resp.text)), True
    except Exception:
        return {
            "detected_signal":"behavior change",
            "updated_logic":"MiaoGo updates the journey using the new behavior signal.",
            "bonus_mission":"Complete one adaptive mission based on the current interest.",
            "new_reward":"Adaptive journey points.",
            "next_best_stops":[]
        }, False

st.markdown("""
<style>
@import url('https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600;700;800;900&display=swap');
html,body,[class*="css"]{font-family:Inter,-apple-system,BlinkMacSystemFont,"Segoe UI",sans-serif}
.stApp{background:radial-gradient(circle at 10% 0%,rgba(255,214,236,.72),transparent 28%),radial-gradient(circle at 90% 4%,rgba(221,210,255,.75),transparent 30%),linear-gradient(180deg,#fff 0%,#fbf8ff 54%,#fff 100%)}
.block-container{max-width:1240px;padding-top:1.2rem;padding-bottom:3rem}
#MainMenu,footer,header{visibility:hidden}[data-testid="collapsedControl"]{display:none}
h1,h2,h3,h4,h5,h6,p,div,span,label{font-family:Inter,-apple-system,BlinkMacSystemFont,"Segoe UI",sans-serif;color:#17142B}
.app-card{background:white;border:1px solid #EDE7F8;border-radius:30px;padding:24px;box-shadow:0 18px 45px rgba(51,34,101,.075);margin-bottom:22px}
.hero-card{background:rgba(255,255,255,.82);border:1px solid #EDE7F8;border-radius:32px;padding:30px;margin-bottom:22px;box-shadow:0 22px 55px rgba(51,34,101,.09)}
.hero-card h1{font-size:46px;line-height:1.07;letter-spacing:-1.8px;margin:0 0 12px 0;font-weight:950;max-width:850px}
.hero-card p{font-size:17px;color:#817B97;line-height:1.55;max-width:800px;margin:0}
.grad{background:linear-gradient(135deg,#7B4DFF,#FF7DBB);-webkit-background-clip:text;-webkit-text-fill-color:transparent}
.stButton>button{background:linear-gradient(135deg,#7B4DFF,#FF7DBB)!important;color:white!important;border:0!important;border-radius:999px!important;padding:.75rem 1.5rem!important;font-weight:900!important;box-shadow:0 13px 28px rgba(123,77,255,.23)!important}
input,textarea{color:#17142B!important;background:white!important}
div[role="radiogroup"] label{background:white!important;border:1px solid #EDE7F8!important;border-radius:999px!important;padding:8px 12px!important;margin-right:8px!important}
div[role="radiogroup"] label p{color:#17142B!important;font-weight:700!important}
[data-testid="stForm"]{background:white;border:1px solid #EDE7F8;border-radius:30px;padding:24px;box-shadow:0 18px 45px rgba(51,34,101,.075)}
.ai-box{background:linear-gradient(135deg,#F4EFFF,#FFF5FA);border:1px solid #E5DAFF;border-radius:22px;padding:18px;margin:10px 0 16px 0}.ai-box p{color:#5F5875;line-height:1.5;margin:.35rem 0}.badge{display:inline-block;background:#F0EAFF;color:#7B4DFF;border-radius:999px;padding:6px 10px;font-size:12px;font-weight:900;margin-bottom:8px}
</style>
""", unsafe_allow_html=True)

st.markdown("""
<div style="display:flex;align-items:center;justify-content:space-between;margin-bottom:18px;">
  <div style="display:flex;align-items:center;gap:13px;">
    <div style="width:48px;height:48px;border-radius:16px;background:linear-gradient(135deg,#7B4DFF,#FF7DBB);display:flex;align-items:center;justify-content:center;color:white;font-weight:900;font-size:23px;box-shadow:0 14px 30px rgba(123,77,255,.23);">M</div>
    <div><div style="font-size:27px;font-weight:900;letter-spacing:-.8px;line-height:1;">MiaoGo</div><div style="font-size:13px;color:#817B97;margin-top:3px;">AI shopping journey assistant for Miaojie</div></div>
  </div>
  <div style="background:white;border:1px solid #EDE7F8;border-radius:999px;padding:10px 15px;color:#5D38D6;font-weight:850;font-size:13px;box-shadow:0 10px 25px rgba(51,34,101,.08);">Gemini AI MVP</div>
</div>
<div class="hero-card"><h1>Plan mall journeys that feel personal, useful, and <span class="grad">worth opening the app for.</span></h1><p>MiaoGo uses a real AI model plus structured mall data to generate routes, missions, rewards, repurchase reminders, and real-time journey updates.</p></div>
""", unsafe_allow_html=True)

st.markdown('<div class="app-card">', unsafe_allow_html=True)
st.subheader("Create a test journey")
c1,c2=st.columns(2)
with c1: budget=st.number_input("Budget / RMB", min_value=50, max_value=5000, value=200, step=50)
with c2: available_time=st.slider("Available time / minutes",30,240,150,15)
style=st.text_input("Style", value="casual chic")
goal=st.text_input("Shopping goal", value="cute weekend outfit and shoes")
priority=st.radio("Main priority",["Trendy style","Best value","Beauty and skincare","Gift shopping","Fast route","High-end experience"],horizontal=True)
free_text=st.text_area("Tell MiaoGo what you want in normal language", value="I want a cute weekend outfit with shoes, not too expensive, and I might want one beauty add-on.", height=90)
generate=st.button("Generate AI mall journey", type="primary")
st.markdown('</div>', unsafe_allow_html=True)

if generate or "journey" not in st.session_state:
    with st.spinner("MiaoGo AI is reading the mall database and building your journey..."):
        journey, ranked, used_gemini, ai_status = gemini_journey(stores,budget,available_time,style,goal,priority,free_text)
    st.session_state["journey"]=journey; st.session_state["ranked"]=ranked; st.session_state["used_gemini"]=used_gemini; st.session_state["ai_status"]=ai_status
else:
    journey=st.session_state["journey"]; ranked=st.session_state["ranked"]; used_gemini=st.session_state["used_gemini"]; ai_status=st.session_state["ai_status"]

st.markdown(f'<div class="ai-box"><span class="badge">{"Gemini AI active" if used_gemini else "Fallback mode"}</span><p><b>AI journey summary:</b> {esc(journey.get("summary",""))}</p><p><b>Status:</b> {esc(ai_status)}</p></div>', unsafe_allow_html=True)

stops=journey.get("stops",[])[:4]
while len(stops)<4:
    stops.append({"store_name":"Store","category":"Category","zone":"","floor":"","estimated_time_min":20,"reason":"","mission":"Complete a store mission.","reward":"Journey points.","repurchase_reminder":"Follow-up reminder.","match":"AI match"})
total_time=journey.get("estimated_total_time",sum(intval(s.get("estimated_time_min",20)) for s in stops))
names=[esc(s.get("store_name","Store")) for s in stops]; cats=[esc(s.get("category","Store")) for s in stops]; times=[esc(s.get("estimated_time_min","20")) for s in stops]; missions=[esc(s.get("mission","Complete a mission.")) for s in stops]; matches=[esc(s.get("match","AI match")) for s in stops]

app_html=f"""
<!DOCTYPE html><html><head><meta charset='UTF-8'><link href='https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600;700;800;900&display=swap' rel='stylesheet'><style>
*{{box-sizing:border-box}}body{{margin:0;font-family:Inter,-apple-system,BlinkMacSystemFont,"Segoe UI",sans-serif;background:transparent;color:#17142B}}.wrap{{display:grid;grid-template-columns:minmax(0,1.55fr) minmax(320px,.45fr);gap:28px;align-items:start}}.shell,.panel{{background:white;border:1px solid #EDE7F8;border-radius:30px;padding:24px;box-shadow:0 18px 45px rgba(51,34,101,.075)}}.top{{display:flex;align-items:center;justify-content:space-between;margin-bottom:20px}}.person{{display:flex;align-items:center;gap:12px}}.avatar{{width:50px;height:50px;border-radius:50%;background:linear-gradient(135deg,#F2E9FF,#FFE1EF);border:1px solid #EEE5FF;position:relative}}.avatar:before{{content:"";position:absolute;width:14px;height:14px;border-radius:50%;background:#FFD0E1;top:9px;left:18px}}.avatar:after{{content:"";position:absolute;width:30px;height:22px;border-radius:20px 20px 14px 14px;background:#7B4DFF;bottom:5px;left:10px}}.greet{{font-size:25px;font-weight:950;letter-spacing:-.5px}}.sub{{font-size:14px;color:#817B97;margin-top:2px}}.points{{background:#FFF8E7;border:1px solid #FFE6A9;border-radius:999px;padding:10px 16px;color:#AA6A00;font-size:17px;font-weight:950}}.sec{{display:flex;align-items:center;justify-content:space-between;margin:18px 0 12px}}.sec b{{font-size:22px;font-weight:950}}.sec span{{font-size:14px;font-weight:850;color:#7B4DFF}}.prefgrid{{display:grid;grid-template-columns:repeat(3,1fr);gap:14px}}.pref{{background:white;border:1px solid #EDE7F8;border-radius:22px;padding:18px;min-height:116px;box-shadow:0 10px 24px rgba(51,34,101,.055)}}.ico{{width:34px;height:34px;border-radius:12px;background:#DDF7E8;margin-bottom:14px}}.pref:nth-child(2) .ico{{background:#E6F0FF}}.pref:nth-child(3) .ico{{background:#F1E2FF}}.lab{{font-size:13px;color:#817B97;font-weight:850}}.val{{font-size:25px;font-weight:950;letter-spacing:-.8px;margin-top:2px}}.map{{height:360px;border:1px solid #EDE7F8;border-radius:28px;background:linear-gradient(rgba(255,255,255,.72),rgba(255,255,255,.72)),repeating-linear-gradient(90deg,transparent 0 92px,rgba(123,77,255,.08) 92px 100px),repeating-linear-gradient(0deg,transparent 0 82px,rgba(123,77,255,.08) 82px 90px),linear-gradient(135deg,#F5EFFF,#FFF6FA);position:relative;overflow:hidden;margin-bottom:18px;box-shadow:inset 0 0 0 1px rgba(255,255,255,.7)}}svg{{position:absolute;inset:0;z-index:1;pointer-events:none}}.pin{{position:absolute;z-index:3;background:white;border:1px solid #E5DBFF;border-radius:19px;padding:12px 13px;width:210px;box-shadow:0 18px 38px rgba(73,45,140,.15)}}.ptitle{{font-size:14px;font-weight:950;display:flex;align-items:center;gap:8px}}.num{{width:31px;height:31px;background:linear-gradient(135deg,#7B4DFF,#A879FF);border-radius:11px 11px 11px 3px;transform:rotate(45deg);display:inline-flex;align-items:center;justify-content:center;flex:none}}.num span{{transform:rotate(-45deg);color:white;font-weight:950}}.pmeta{{font-size:12px;color:#817B97;margin-top:6px;padding-left:40px}}.reason{{font-size:10.5px;color:#7B4DFF;padding-left:40px;margin-top:4px;font-weight:850}}.pin1{{left:250px;top:58px}}.pin2{{right:88px;top:126px}}.pin3{{left:90px;bottom:82px}}.pin4{{right:170px;bottom:42px}}.start{{position:absolute;left:48px;top:94px;z-index:4;text-align:center;font-size:12px;color:#312B57;font-weight:850}}.startdot{{width:36px;height:36px;border-radius:50%;background:#17142B;color:white;display:flex;align-items:center;justify-content:center;font-weight:950;margin:0 auto 5px}}.end{{position:absolute;right:36px;bottom:18px;z-index:4;text-align:center;font-size:11px;color:#312B57;font-weight:850}}.enddot{{width:24px;height:24px;border-radius:50%;background:#17142B;border:5px solid white;margin:0 auto 4px;box-shadow:0 5px 14px rgba(0,0,0,.18)}}.missiongrid{{display:grid;grid-template-columns:repeat(4,1fr);gap:14px;margin-bottom:18px}}.mission{{background:white;border:1px solid #EDE7F8;border-radius:22px;padding:16px;min-height:185px;text-align:center;box-shadow:0 10px 24px rgba(51,34,101,.055)}}.mico{{width:48px;height:48px;border-radius:17px;background:linear-gradient(135deg,#EFE7FF,#FFF0F7);margin:0 auto 13px}}.mtitle{{font-size:14px;font-weight:900;line-height:1.25;min-height:72px}}.mpoints{{font-size:14px;color:#C97900;font-weight:950;margin-top:10px}}.mstate{{display:inline-block;margin-top:8px;padding:6px 10px;border-radius:999px;background:#F0EAFF;color:#7B4DFF;font-size:12px;font-weight:900}}.rewardgrid{{display:grid;grid-template-columns:repeat(3,1fr);gap:14px}}.reward{{background:white;border:1px solid #EDE7F8;border-radius:22px;padding:18px;box-shadow:0 10px 24px rgba(51,34,101,.055)}}.rnum{{font-size:31px;font-weight:950;color:#2B244D;letter-spacing:-.8px}}.rlab{{font-size:14px;color:#817B97;font-weight:800}}.nav{{display:grid;grid-template-columns:repeat(5,1fr);border-top:1px solid #EDE7F8;padding-top:15px;text-align:center;font-size:13px;font-weight:900;color:#5F5875}}.nav div:first-child{{color:#7B4DFF}}.panel h3{{margin-top:0;font-size:25px}}.panel p{{color:#817B97;line-height:1.5;font-size:14px}}.kpi{{background:#FAF7FF;border:1px solid #EDE7F8;border-radius:20px;padding:16px;margin-bottom:13px}}.kval{{font-size:31px;font-weight:950;color:#2B244D}}.klab{{font-size:13px;color:#817B97;font-weight:750}}.logic{{background:linear-gradient(135deg,#F3EEFF,#FFF5FA);border:1px solid #E6DAFF;border-radius:20px;padding:16px;margin-top:14px}}.logic p{{font-size:13px;color:#5F5875;line-height:1.45;margin:8px 0 0 0}}
</style></head><body><div class='wrap'><div class='shell'><div class='top'><div class='person'><div class='avatar'></div><div><div class='greet'>Hi, Mia</div><div class='sub'>Let's plan your perfect mall trip</div></div></div><div class='points'>2,480 pts</div></div><div class='sec'><b>Your preferences</b><span>Edit</span></div><div class='prefgrid'><div class='pref'><div class='ico'></div><div class='lab'>Budget</div><div class='val'>¥{budget}</div></div><div class='pref'><div class='ico'></div><div class='lab'>Time</div><div class='val'>{round(available_time/60,1)}h</div></div><div class='pref'><div class='ico'></div><div class='lab'>Style</div><div class='val' style='font-size:20px'>{esc(style.title())}</div></div></div><div class='sec'><b>Your AI Mall Journey</b><span>Est. {round(float(total_time)/60,1)}h</span></div><div class='map'><svg viewBox='0 0 900 360' preserveAspectRatio='none'><path d='M90 145 C170 60, 295 70, 385 125 S585 170, 680 118 S845 130, 808 225 S625 318, 480 278 S255 246, 166 300' fill='none' stroke='#7B4DFF' stroke-width='6' stroke-linecap='round' stroke-dasharray='14 13' opacity='.88'/></svg><div class='start'><div class='startdot'>S</div>Start<br>Main entrance</div><div class='pin pin1'><div class='ptitle'><div class='num'><span>1</span></div>{names[0]}</div><div class='pmeta'>{cats[0]} · {times[0]} min</div><div class='reason'>{matches[0]}</div></div><div class='pin pin2'><div class='ptitle'><div class='num'><span>2</span></div>{names[1]}</div><div class='pmeta'>{cats[1]} · {times[1]} min</div><div class='reason'>{matches[1]}</div></div><div class='pin pin3'><div class='ptitle'><div class='num'><span>3</span></div>{names[2]}</div><div class='pmeta'>{cats[2]} · {times[2]} min</div><div class='reason'>{matches[2]}</div></div><div class='pin pin4'><div class='ptitle'><div class='num'><span>4</span></div>{names[3]}</div><div class='pmeta'>{cats[3]} · {times[3]} min</div><div class='reason'>{matches[3]}</div></div><div class='end'><div class='enddot'></div>End<br>South exit</div></div><div class='sec'><b>AI Shopping Missions</b><span>Ready to test</span></div><div class='missiongrid'><div class='mission'><div class='mico'></div><div class='mtitle'>{missions[0][:95]}</div><div class='mpoints'>+200 pts</div><div class='mstate'>Available</div></div><div class='mission'><div class='mico'></div><div class='mtitle'>{missions[1][:95]}</div><div class='mpoints'>+100 pts</div><div class='mstate'>Available</div></div><div class='mission'><div class='mico'></div><div class='mtitle'>{missions[2][:95]}</div><div class='mpoints'>+80 pts</div><div class='mstate'>Available</div></div><div class='mission'><div class='mico'></div><div class='mtitle'>{missions[3][:95]}</div><div class='mpoints'>+120 pts</div><div class='mstate'>Available</div></div></div><div class='sec'><b>Your Rewards</b><span>Prototype</span></div><div class='rewardgrid'><div class='reward'><div class='rnum'>2,480</div><div class='rlab'>Points</div></div><div class='reward'><div class='rnum'>3</div><div class='rlab'>Coupons</div></div><div class='reward'><div class='rnum'>5</div><div class='rlab'>Check-ins</div></div></div><br><div class='nav'><div>Home</div><div>Missions</div><div>Map</div><div>Rewards</div><div>Me</div></div></div><div class='panel'><h3>AI + merchant impact</h3><p>This panel explains what the AI is doing and what Yintai could measure after deployment.</p><div class='kpi'><div class='kval'>+28%</div><div class='klab'>Route-start uplift simulation</div></div><div class='kpi'><div class='kval'>18.7%</div><div class='klab'>Coupon redemption simulation</div></div><div class='kpi'><div class='kval'>{len(stops)}</div><div class='klab'>Recommended journey stops</div></div><div class='kpi'><div class='kval'>{total_time}</div><div class='klab'>Estimated journey minutes</div></div><div class='logic'><b>AI scoring logic</b><p>Gemini reads the user request and structured store data, then chooses route stops, missions, rewards, and repurchase logic.</p></div></div></div></body></html>
"""
components.html(app_html, height=1160, scrolling=False)

st.markdown('<div class="app-card">', unsafe_allow_html=True)
st.subheader("AI recommendation details")
cols=st.columns(4)
for i,s in enumerate(stops):
    with cols[i]:
        st.markdown(f"""<div style="background:white;border:1px solid #EDE7F8;border-radius:22px;padding:17px;min-height:235px;box-shadow:0 10px 24px rgba(51,34,101,.055);"><div style="font-size:12px;color:#7B4DFF;font-weight:950;">STOP {i+1}</div><div style="font-size:18px;font-weight:950;margin:6px 0;">{esc(s.get("store_name",""))}</div><div style="font-size:12px;color:#817B97;margin-bottom:9px;">{esc(s.get("category",""))} · {esc(s.get("zone",""))} · {esc(s.get("floor",""))}</div><div style="font-size:13px;line-height:1.45;color:#423D5D;"><b>Why:</b> {esc(s.get("reason",""))}</div><div style="font-size:13px;line-height:1.45;color:#423D5D;margin-top:8px;"><b>Reward:</b> {esc(s.get("reward",""))}</div><div style="font-size:12px;color:#7B4DFF;font-weight:850;margin-top:10px;">Match: {esc(s.get("match","AI match"))}</div></div>""", unsafe_allow_html=True)
st.markdown('</div>', unsafe_allow_html=True)

st.markdown('<div class="app-card">', unsafe_allow_html=True)
st.subheader("Real-time AI adaptation")
change_text=st.text_input("Test a behavior change", value="I spent 25 minutes in Nike because I liked the shoes.")
if st.button("Update journey based on behavior"):
    with st.spinner("MiaoGo AI is adapting the journey..."):
        adapt, adapt_ai = gemini_adapt(journey, change_text, stores)
    st.markdown(f"""<div style="background:linear-gradient(135deg,#F3EEFF,#FFF5FA);border:1px solid #E6DAFF;border-radius:22px;padding:18px;margin-top:14px;"><h3>MiaoGo detected: {esc(adapt.get("detected_signal",""))}</h3><p style="color:#5F5875;">{esc(adapt.get("updated_logic",""))}</p><p><b>New bonus mission:</b> {esc(adapt.get("bonus_mission",""))}</p><p><b>New reward:</b> {esc(adapt.get("new_reward",""))}</p><p style="color:#7B4DFF;font-weight:800;">{'Gemini AI adapted this journey.' if adapt_ai else 'Fallback adaptation used.'}</p></div>""", unsafe_allow_html=True)
st.markdown('</div>', unsafe_allow_html=True)

st.subheader("Mission test")
st.write("Testers can mark which missions they would actually do.")
for i,s in enumerate(stops):
    st.checkbox(f"{s.get('store_name','')}: {s.get('mission','')}", key=f"mission_{i}")

st.subheader("Tester feedback")
with st.form("feedback_form"):
    f1,f2=st.columns(2)
    with f1:
        rating=st.slider("Overall rating",1,5,4)
        would_use=st.radio("Would you use this inside Miaojie?",["Yes","Maybe","No"],horizontal=True)
    with f2:
        open_more=st.radio("Would this make you open Miaojie more often?",["Yes","Maybe","No"],horizontal=True)
        useful_part=st.radio("Most useful part",["AI route","Missions","Rewards","Real-time adaptation","Repurchase reminder"],horizontal=True)
    improvement=st.text_area("What should be improved?")
    submitted=st.form_submit_button("Submit feedback")
    if submitted:
        feedback=pd.DataFrame([{"timestamp":datetime.now().strftime("%Y-%m-%d %H:%M:%S"),"budget":budget,"time":available_time,"style":style,"goal":goal,"priority":priority,"free_text":free_text,"used_gemini":used_gemini,"rating":rating,"would_use":would_use,"open_more":open_more,"useful_part":useful_part,"improvement":improvement}])
        exists=os.path.exists("feedback.csv")
        feedback.to_csv("feedback.csv", mode="a", header=not exists, index=False)
        st.success("Feedback saved. Thank you for testing MiaoGo.")

if os.path.exists("feedback.csv"):
    with open("feedback.csv","rb") as f:
        st.download_button("Download feedback CSV", f, file_name="miaogo_feedback.csv", mime="text/csv")

with st.expander("Structured MVP dataset"):
    st.dataframe(stores, use_container_width=True)
with st.expander("Local ranking table used before Gemini prompt"):
    cols=[c for c in ["store_name","category","price_level","estimated_time_min","ai_score"] if c in ranked.columns]
    st.dataframe(ranked[cols].head(25), use_container_width=True)
