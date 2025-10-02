import streamlit as st
import pandas as pd
import plotly.express as px
import numpy as np
import os
import json
import random
from datetime import datetime, timedelta, date, time

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
    st.session_state.client_counter = data.get("client_counter", 1)
    st.session_state.not_found_counter = data.get("not_found_counter", 0)
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
    if d not in st.session_state.schedules[brygada]:
        st.session_state.schedules[brygada][d] = []
    st.session_state.schedules[b][d].append(slot)
    st.session_state.schedules[b][d].sort(key=lambda s: s["start"])
    save_state_to_json()

def schedule_client_immediately(client_name, slot_type_name, day, pref_start, pref_end):
    slot_type = next((s for s in st.session_state.slot_types if s["name"]==slot_type_name), None)
    if not slot_type:
        return False, None
    dur = timedelta(minutes=slot_type["minutes"])
    candidates=[]
    for b in st.session_state.brygady:
        existing=get_day_slots_for_brygada(b, day)
        start_wh,end_wh = st.session_state.working_hours[b]
        start_dt=datetime.combine(day, max(pref_start,start_wh))
        end_dt=datetime.combine(day, min(pref_end,end_wh))
        t=start_dt
        while t+dur<=end_dt:
            overlap=any(not(t+dur<=s["start"] or t>=s["end"]) for s in existing)
            if not overlap:
                candidates.append((b,t,t+dur))
            t+=timedelta(minutes=15)
    if not candidates:
        return False,None
    brygada,start,end=candidates[0]
    slot={"start":start,"end":end,"slot_type":slot_type_name,"duration_min":slot_type["minutes"],"client":client_name}
    add_slot_to_brygada(brygada, day, slot)
    return True, slot

# ===================== PREDEFINED SLOTS =====================

PREFERRED_SLOTS={
    "8:00-12:00": (time(8,0),time(12,0)),
    "12:00-16:00": (time(12,0),time(16,0)),
    "16:00-20:00": (time(16,0),time(20,0))
}

# ===================== UI =====================

st.title("📅 Harmonogram slotów")

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

    if st.button("🗑️ Wyczyść harmonogram"):
        st.session_state.schedules={b:{} for b in st.session_state.brygady}
        st.session_state.clients_added=[]
        st.session_state.client_counter=1
        st.session_state.not_found_counter=0
        save_state_to_json()
        st.success("Harmonogram wyczyszczony.")

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
    pref_start,pref_end=PREFERRED_SLOTS[pref_range_label]
    day=st.date_input("Dzień",value=date.today())
    submitted=st.form_submit_button("Dodaj")
    if submitted:
        ok,info=schedule_client_immediately(client_name,slot_type_name,day,pref_start,pref_end)
        if ok:
            for b in st.session_state.schedules:
                for d,slots in st.session_state.schedules[b].items():
                    for s in slots:
                        if s["client"]==client_name and s["start"]==info["start"]:
                            s["pref_range"]=pref_range_label
            st.session_state.clients_added.append({"client":client_name,"slot_type":slot_type_name,"pref_range":pref_range_label})
            st.success(f"✅ {client_name} dodany ({slot_type_name}, {pref_range_label})")
            st.session_state.client_counter+=1
        else:
            st.session_state.not_found_counter+=1
            st.error("❌ Brak miejsca w tym przedziale.")

# ===================== SCHEDULE TABLE =====================

all_slots=[]
for b in st.session_state.brygady:
    for d,slots in st.session_state.schedules.get(b,{}).items():
        for s in slots:
            all_slots.append({
                "Brygada":b,"Dzień":d,"Klient":s["client"],
                "Typ":s["slot_type"],"Preferencja":s.get("pref_range",""),
                "Start":s["start"],"Koniec":s["end"],"Czas [min]":s["duration_min"]
            })
df=pd.DataFrame(all_slots)
st.subheader("📋 Tabela harmonogramu")
st.dataframe(df)

# ===================== GANTT =====================

if not df.empty:
    st.subheader("📊 Wykres Gantta")
    fig=px.timeline(df,x_start="Start",x_end="Koniec",y="Brygada",color="Klient",hover_data=["Typ","Preferencja"])
    fig.update_yaxes(autorange="reversed")

    # przedziały czasowe
    colors=["rgba(200,200,200,0.15)"]*3
    for (label,(s,e)),col in zip(PREFERRED_SLOTS.items(),colors):
        fig.add_vrect(x0=datetime.combine(date.today(),s),x1=datetime.combine(date.today(),e),
                      fillcolor=col,opacity=0.2,layer="below",line_width=0)
        fig.add_vline(x=datetime.combine(date.today(),s),line_width=1,line_dash="dot",line_color="black")
        fig.add_vline(x=datetime.combine(date.today(),e),line_width=1,line_dash="dot",line_color="black")
    st.plotly_chart(fig,use_container_width=True)

# ===================== SUMMARY =====================

st.subheader("📌 Podsumowanie")
st.write(f"✅ Dodano klientów: {len(st.session_state.clients_added)}")
st.write(f"❌ Brak slotu dla: {st.session_state.not_found_counter}")

# ===================== UTILIZATION PER DAY =====================

st.subheader("📊 Wykorzystanie brygad w podziale na dni (%)")
all_days=set()
for b in st.session_state.brygady:
    all_days.update(st.session_state.schedules.get(b,{}).keys())
all_days=sorted(all_days)
util_data=[]
for b in st.session_state.brygady:
    row={"Brygada":b}
    wh_start,wh_end=st.session_state.working_hours[b]
    daily_minutes=(datetime.combine(date.today(),wh_end)-datetime.combine(date.today(),wh_start)).seconds//60
    for d in all_days:
        slots=st.session_state.schedules.get(b,{}).get(d,[])
        used=sum(s["duration_min"] for s in slots)
        row[d]=round(100*used/daily_minutes,1) if daily_minutes>0 else 0
    util_data.append(row)
st.dataframe(pd.DataFrame(util_data))

# ===================== TOTAL UTILIZATION =====================

st.subheader("📊 Wykorzystanie brygad (sumarycznie)")
rows=[]
for b in st.session_state.brygady:
    total=sum(s["duration_min"] for d in st.session_state.schedules.get(b,{}).values() for s in d)
    wh_start,wh_end=st.session_state.working_hours[b]
    daily_minutes=(datetime.combine(date.today(),wh_end)-datetime.combine(date.today(),wh_start)).seconds//60
    days_count=len(st.session_state.schedules.get(b,{}))
    available=daily_minutes*days_count if days_count>0 else 1
    utilization=round(100*total/available,1)
    rows.append({"Brygada":b,"Zajętość [min]":total,"Dostępne [min]":available,"Wykorzystanie [%]":utilization})
st.table(pd.DataFrame(rows))
