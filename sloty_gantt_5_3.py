import streamlit as st
import pandas as pd
import plotly.express as px
import random
import os
import json
from datetime import datetime, timedelta, date, time
from statistics import pstdev

# ===================== PERSISTENCE =====================
def schedules_to_jsonable():
    data = {}
    for b, days in st.session_state.schedules.items():
        data[b] = {}
        for d, slots in days.items():
            data[b][d] = [
                {
                    "start": s["start"].isoformat(),
                    "end": s["end"].isoformat(),
                    "slot_type": s["slot_type"],
                    "duration_min": s["duration_min"],
                    "client": s["client"],
                    "pref_range": s.get("pref_range", "")
                }
                for s in slots
            ]
    return {
        "slot_types": st.session_state.slot_types,
        "brygady": st.session_state.brygady,
        "working_hours": {
            b: (wh[0].isoformat(), wh[1].isoformat())
            for b, wh in st.session_state.working_hours.items()
        },
        "schedules": data,
        "clients_added": st.session_state.clients_added,
        "balance_horizon": st.session_state.balance_horizon,
        "heur_weights": st.session_state.heur_weights,
        "client_counter": st.session_state.client_counter,
        "not_found_counter": st.session_state.not_found_counter,
    }

def save_state_to_json(filename="schedules.json"):
    with open(filename, "w", encoding="utf-8") as f:
        json.dump(schedules_to_jsonable(), f, ensure_ascii=False, indent=2)

def load_state_from_json(filename="schedules.json"):
    if not os.path.exists(filename):
        return False
    with open(filename, "r", encoding="utf-8") as f:
        data = json.load(f)
    st.session_state.slot_types = data.get("slot_types", [])
    st.session_state.brygady = data.get("brygady", [])

    def parse_time_str(t):
        try:
            return datetime.fromisoformat(t).time()
        except ValueError:
            return datetime.strptime(t, "%H:%M:%S").time() if ":" in t else datetime.strptime(t, "%H:%M").time()

    st.session_state.working_hours = {
        b: (parse_time_str(wh[0]), parse_time_str(wh[1]))
        for b, wh in data.get("working_hours", {}).items()
    }

    st.session_state.schedules = {}
    for b, days in data.get("schedules", {}).items():
        st.session_state.schedules[b] = {}
        for d, slots in days.items():
            st.session_state.schedules[b][d] = [
                {
                    "start": datetime.fromisoformat(s["start"]),
                    "end": datetime.fromisoformat(s["end"]),
                    "slot_type": s["slot_type"],
                    "duration_min": s["duration_min"],
                    "client": s["client"],
                    "pref_range": s.get("pref_range", "")
                }
                for s in slots
            ]
    st.session_state.clients_added = data.get("clients_added", [])
    st.session_state.balance_horizon = data.get("balance_horizon", "week")
    st.session_state.heur_weights = data.get("heur_weights", {"delay":0.34,"gap":0.33,"balance":0.33})
    st.session_state.client_counter = data.get("client_counter",1)
    st.session_state.not_found_counter = data.get("not_found_counter",0)
    return True

# ===================== INITIALIZATION =====================
if "slot_types" not in st.session_state:
    if not load_state_from_json():
        st.session_state.slot_types = [{"name": "Standard", "minutes": 60, "weight": 1}]
        st.session_state.brygady = ["Brygada 1", "Brygada 2"]
        st.session_state.working_hours = {}
        st.session_state.schedules = {}
        st.session_state.clients_added = []
        st.session_state.balance_horizon = "week"
        st.session_state.heur_weights = {"delay":0.34,"gap":0.33,"balance":0.33}
        st.session_state.client_counter = 1
        st.session_state.not_found_counter = 0

# ===================== HELPER FUNCTIONS =====================
def parse_slot_types(text):
    out = []
    for line in text.splitlines():
        parts = line.strip().split(",")
        if len(parts) >= 3:
            try:
                out.append({"name": parts[0].strip(),
                            "minutes": int(parts[1]),
                            "weight": float(parts[2])})
            except:
                pass
        elif len(parts) == 2:
            try:
                out.append({"name": parts[0].strip(),
                            "minutes": int(parts[1]),
                            "weight": 1})
            except:
                pass
    return out

def weighted_choice(slot_types):
    names = [s["name"] for s in slot_types]
    weights = [s.get("weight",1) for s in slot_types]
    return random.choices(names, weights=weights, k=1)[0]

def ensure_brygady_in_state(brygady_list):
    for b in brygady_list:
        if b not in st.session_state.working_hours:
            st.session_state.working_hours[b] = (time(8,0), time(16,0))
        if b not in st.session_state.schedules:
            st.session_state.schedules[b] = {}

def get_day_slots_for_brygada(brygada, day):
    d = day.strftime("%Y-%m-%d")
    return sorted(st.session_state.schedules.get(brygada, {}).get(d, []), key=lambda s: s["start"])

def add_slot_to_brygada(brygada, day, slot):
    d = day.strftime("%Y-%m-%d")
    if brygada not in st.session_state.schedules:
        st.session_state.schedules[brygada] = {}
    if d not in st.session_state.schedules[brygada]:
        st.session_state.schedules[brygada][d] = []
    st.session_state.schedules[brygada][d].append(slot)
    st.session_state.schedules[brygada][d].sort(key=lambda s: s["start"])
    save_state_to_json()

def minutes_between(t1,t2):
    return int((t2-t1).total_seconds()/60)

def total_work_minutes_for_brygada(brygada):
    start,end=st.session_state.working_hours[brygada]
    return minutes_between(datetime.combine(date.today(),start),datetime.combine(date.today(),end))

def daily_used_minutes(brygada,day):
    return sum(s["duration_min"] for s in get_day_slots_for_brygada(brygada,day))

def week_days_containing(day):
    monday = day - timedelta(days=day.weekday())
    return [monday + timedelta(days=i) for i in range(7)]

def used_minutes_for_week(brygada,any_day_in_week):
    return sum(daily_used_minutes(brygada,d) for d in week_days_containing(any_day_in_week))

# ===================== PREDEFINED SLOTS =====================
PREFERRED_SLOTS={
    "8:00-12:00": (time(8,0),time(12,0)),
    "12:00-16:00": (time(12,0),time(16,0)),
    "16:00-20:00": (time(16,0),time(20,0))
}

# ===================== HEURISTIC SLOT SELECTION =====================
def find_best_slot(client_name, slot_type_name, day, pref_range_label):
    stype = next((s for s in st.session_state.slot_types if s["name"]==slot_type_name), None)
    if not stype:
        return None
    dur_min = stype["minutes"]
    pref_start, pref_end = PREFERRED_SLOTS[pref_range_label]
    pref_start_dt = datetime.combine(day,pref_start)
    pref_end_dt = datetime.combine(day,pref_end)
    window_len = max(1, minutes_between(pref_start_dt,pref_end_dt))

    base_minutes_day = {b: daily_used_minutes(b,day) for b in st.session_state.brygady}
    work_map_day = {b: total_work_minutes_for_brygada(b) for b in st.session_state.brygady}
    week_days = week_days_containing(day)
    base_minutes_week = {b: used_minutes_for_week(b,day) for b in st.session_state.brygady}
    work_map_week = {b: work_map_day[b]*len(week_days) for b in st.session_state.brygady}

    candidates=[]
    for b in st.session_state.brygady:
        day_start_dt = datetime.combine(day,st.session_state.working_hours[b][0])
        day_end_dt = datetime.combine(day,st.session_state.working_hours[b][1])
        if pref_end_dt<=day_start_dt or pref_start_dt>=day_end_dt:
            continue
        slots = get_day_slots_for_brygada(b,day)
        intervals=[]
        if not slots:
            intervals.append((day_start_dt,day_end_dt))
        else:
            intervals.append((day_start_dt,slots[0]["start"]))
            for i in range(len(slots)-1):
                intervals.append((slots[i]["end"],slots[i+1]["start"]))
            intervals.append((slots[-1]["end"],day_end_dt))
        for iv_start,iv_end in intervals:
            if minutes_between(iv_start,iv_end)<dur_min:
                continue
            candidate_start = max(iv_start,pref_start_dt,day_start_dt)
            latest_start = min(iv_end - timedelta(minutes=dur_min),pref_end_dt - timedelta(minutes=dur_min),day_end_dt - timedelta(minutes=dur_min))
            if candidate_start>latest_start:
                continue
            start_candidate=candidate_start
            end_candidate=start_candidate+timedelta(minutes=dur_min)
            delay_min = max(0, minutes_between(pref_start_dt,start_candidate))
            delay_norm = delay_min/window_len
            idle_before = minutes_between(iv_start,start_candidate)
            idle_after = minutes_between(end_candidate,iv_end)
            gap_total = idle_before+idle_after
            work_total_minutes_day = work_map_day[b]
            gap_norm = gap_total/work_total_minutes_day if work_total_minutes_day>0 else 0
            if st.session_state.balance_horizon=="day":
                mins_after={bb: base_minutes_day[bb] for bb in st.session_state.brygady}
                mins_after[b]+=dur_min
                util_list=[mins_after[bb]/work_map_day[bb] if work_map_day[bb]>0 else 0 for bb in st.session_state.brygady]
            else:
                mins_after={bb: base_minutes_week[bb] for bb in st.session_state.brygady}
                mins_after[b]+=dur_min
                util_list=[mins_after[bb]/work_map_week[bb] if work_map_week[bb]>0 else 0 for bb in st.session_state.brygady]
            fairness_std = pstdev(util_list) if len(util_list)>1 else 0
            W=st.session_state.heur_weights
            score = W["delay"]*delay_norm + W["gap"]*gap_norm + W["balance"]*fairness_std
            candidates.append((score,delay_min,start_candidate,end_candidate,b))
    if not candidates:
        return None
    candidates.sort(key=lambda x:(x[0],x[1],x[2]))
    best=candidates[0]
    return {"brygada":best[4],"start":best[2],"end":best[3],"score":best[0]}

def schedule_client(client_name, slot_type_name, day, pref_range_label):
    res = find_best_slot(client_name, slot_type_name, day, pref_range_label)
    if not res:
        return False,None
    slot={"start":res["start"],"end":res["end"],"slot_type":slot_type_name,"duration_min":(res["end"]-res["start"]).seconds//60,"client":client_name,"pref_range":pref_range_label}
    add_slot_to_brygada(res["brygada"],day,slot)
    return True,res

# ===================== UI =====================
st.title("📅 Harmonogram slotów - Tydzień")

with st.sidebar:
    st.subheader("⚙️ Konfiguracja")
    txt = st.text_area("Typy slotów (format: Nazwa, minuty, waga)",
                       value="\n".join(f"{s['name']},{s['minutes']},{s.get('weight',1)}" for s in st.session_state.slot_types))
    st.session_state.slot_types=parse_slot_types(txt)

    txt_b = st.text_area("Lista brygad",value="\n".join(st.session_state.brygady))
    st.session_state.brygady=[line.strip() for line in txt_b.splitlines() if line.strip()]
    ensure_brygady_in_state(st.session_state.brygady)

    for b in st.session_state.brygady:
        st.write(f"Godziny pracy {b}:")
        start_t=st.time_input(f"Start {b}",value=st.session_state.working_hours[b][0],key=f"{b}_start")
        end_t=st.time_input(f"Koniec {b}",value=st.session_state.working_hours[b][1],key=f"{b}_end")
        st.session_state.working_hours[b]=(start_t,end_t)

    st.subheader("Heurystyka")
    d = st.slider("Delay",0.0,1.0,st.session_state.heur_weights["delay"])
    g = st.slider("Gap",0.0,1.0,st.session_state.heur_weights["gap"])
    bal = st.slider("Balance",0.0,1.0,st.session_state.heur_weights["balance"])
    s=d+g+bal
    if s==0:
        st.session_state.heur_weights={"delay":0.34,"gap":0.33,"balance":0.33}
    else:
        st.session_state.heur_weights={"delay":d/s,"gap":g/s,"balance":bal/s}

    if st.button("🗑️ Wyczyść harmonogram"):
        st.session_state.schedules={b:{} for b in st.session_state.brygady}
        st.session_state.clients_added=[]
        st.session_state.client_counter=1
        st.session_state.not_found_counter=0
        save_state_to_json()
        st.success("Harmonogram wyczyszczony.")

# ===================== WEEK NAVIGATION =====================
if "week_offset" not in st.session_state:
    st.session_state.week_offset = 0

st.sidebar.subheader("⬅️ Wybór tygodnia")
col1,col2 = st.sidebar.columns(2)
if col1.button("‹ Poprzedni tydzień"):
    st.session_state.week_offset-=1
if col2.button("Następny tydzień ›"):
    st.session_state.week_offset+=1

week_ref = date.today() + timedelta(weeks=st.session_state.week_offset)
week_days = get_week_days(week_ref)
st.sidebar.write(f"Tydzień: {week_days[0].strftime('%d-%m-%Y')} – {week_days[-1].strftime('%d-%m-%Y')}")

# ===================== ADD CLIENT =====================
st.subheader("➕ Dodaj klienta")
with st.form("add_client_form"):
    default_client=f"Klient {st.session_state.client_counter}"
    client_name=st.text_input("Nazwa klienta",value=default_client)
    auto_type=weighted_choice(st.session_state.slot_types) if st.session_state.slot_types else "Standard"
    auto_pref=random.choice(list(PREFERRED_SLOTS.keys()))
    st.info(f"Automatycznie wybrano: **{auto_type}**, preferencja: **{auto_pref}**")
    slot_type_name=st.selectbox("Typ slotu",[s["name"] for s in st.session_state.slot_types],
                                index=[s["name"] for s in st.session_state.slot_types].index(auto_type))
    pref_range_label=st.radio("Preferowany przedział czasowy",list(PREFERRED_SLOTS.keys()),
                              index=list(PREFERRED_SLOTS.keys()).index(auto_pref))
    day=st.date_input("Dzień",value=date.today())
    submitted=st.form_submit_button("Dodaj")
    if submitted:
        ok,res=schedule_client(client_name,slot_type_name,day,pref_range_label)
        if ok:
            st.session_state.clients_added.append({"client":client_name,"slot_type":slot_type_name,"pref_range":pref_range_label})
            st.success(f"✅ {client_name} dodany ({slot_type_name}, {pref_range_label})")
            st.session_state.client_counter+=1
        else:
            st.session_state.not_found_counter+=1
            st.error("❌ Brak miejsca w tym przedziale.")

# ===================== TABLE =====================
all_slots=[]
for b in st.session_state.brygady:
    for d in week_days:
        d_str=d.strftime("%Y-%m-%d")
        slots=st.session_state.schedules.get(b,{}).get(d_str,[])
        for s in slots:
            all_slots.append({"Brygada":b,"Dzień":d_str,"Klient":s["client"],
                              "Typ":s["slot_type"],"Preferencja":s.get("pref_range",""),
                              "Start":s["start"],"Koniec":s["end"],"Czas [min]":s["duration_min"]})

df=pd.DataFrame(all_slots)
st.subheader("📋 Tabela harmonogramu")
st.dataframe(df)

# ===================== UTILIZATION =====================
st.subheader("📊 Wykorzystanie brygad (%)")
util_data=[]
for b in st.session_state.brygady:
    row=[]
    for d in week_days:
        row.append(round(compute_utilization_for_day(b,d)*100,1))
    util_data.append(row)
util_df=pd.DataFrame(util_data,index=st.session_state.brygady,columns=[d.strftime("%a %d-%m") for d in week_days])
st.dataframe(util_df)

st.write(f"Nie znaleziono slotów: {st.session_state.not_found_counter}")

# ===================== GANTT =====================
if not df.empty:
    st.subheader("📈 Wykres Gantta")
    fig=px.timeline(df,x_start="Start",x_end="Koniec",y="Brygada",color="Klient",
                    hover_data=["Typ","Preferencja"])
    fig.update_yaxes(autorange="reversed")
    # Linie podziału slotów
    for s_label,(s_start,s_end) in PREFERRED_SLOTS.items():
        for d in week_days:
            fig.add_vline(x=datetime.combine(d,s_start),line=dict(color="gray",dash="dot"),annotation_text=s_label.split("-")[0])
            fig.add_vline(x=datetime.combine(d,s_end),line=dict(color="gray",dash="dot"),annotation_text=s_label.split("-")[1])
    st.plotly_chart(fig,use_container_width=True)
