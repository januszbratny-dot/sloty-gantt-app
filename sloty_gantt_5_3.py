# sloty_gantt_5_3_modified.py
# Streamlit app — edycja slotów/brygad/typów + trwały zapis do JSON
# Kod w języku polskim (komentarze). Plik danych: dane.json

import streamlit as st
from datetime import datetime, date, time
import json
import os
import uuid
from typing import List, Dict, Any

# ---------- Konfiguracja pliku danych ----------
DATA_FILE = "dane.json"


# ---------- Pomocnicze funkcje do zapisu/odczytu ----------
def save_data():
    """
    Zapisuje aktualny stan istotnych elementów st.session_state do pliku JSON.
    """
    data = {
        "slot_types": st.session_state.get("slot_types", []),
        "brygady": st.session_state.get("brygady", []),
        "slots": st.session_state.get("slots", [])
    }
    try:
        with open(DATA_FILE, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=4, default=str)
        st.experimental_set_query_params(_saved=datetime.utcnow().isoformat())  # drobny sygnał
    except Exception as e:
        st.error(f"Błąd zapisu do pliku {DATA_FILE}: {e}")


def load_data():
    """
    Wczytuje dane z pliku JSON do st.session_state, jeśli plik istnieje.
    """
    if os.path.exists(DATA_FILE):
        try:
            with open(DATA_FILE, "r", encoding="utf-8") as f:
                data = json.load(f)
            # Ustaw domyślne struktury w session_state
            st.session_state["slot_types"] = data.get("slot_types", [])
            st.session_state["brygady"] = data.get("brygady", [])
            st.session_state["slots"] = data.get("slots", [])
        except Exception as e:
            st.error(f"Błąd odczytu pliku {DATA_FILE}: {e}")
            # safety: inicjalizuj puste struktury
            st.session_state.setdefault("slot_types", [])
            st.session_state.setdefault("brygady", [])
            st.session_state.setdefault("slots", [])
    else:
        # Plik nie istnieje — inicjalizuj puste struktury
        st.session_state.setdefault("slot_types", [])
        st.session_state.setdefault("brygady", [])
        st.session_state.setdefault("slots", [])


# ---------- Utility ----------
def ensure_session_state():
    """
    Zapewnia obecność wymaganych kluczy w st.session_state.
    """
    st.session_state.setdefault("slot_types", [])
    st.session_state.setdefault("brygady", [])
    st.session_state.setdefault("slots", [])


def gen_id(prefix="id"):
    """Generuje prosty unikalny identyfikator."""
    return f"{prefix}_{uuid.uuid4().hex[:8]}"


# ---------- Operacje na danych (wrappers które zapisują) ----------
def add_slot_type(name: str):
    name = name.strip()
    if not name:
        return
    # unikaj duplikatów (case-insensitive)
    existing = [s.lower() for s in st.session_state.slot_types]
    if name.lower() in existing:
        st.warning("Taki typ już istnieje.")
        return
    st.session_state.slot_types.append(name)
    save_data()
    st.success(f"Dodano typ: {name}")


def remove_slot_type(index: int):
    try:
        removed = st.session_state.slot_types.pop(index)
        # usuń referencje w slotach, jeśli potrzebne (ustaw na None)
        for s in st.session_state.slots:
            if s.get("type") == removed:
                s["type"] = None
        save_data()
        st.info(f"Usunięto typ: {removed}")
    except Exception as e:
        st.error(f"Błąd usuwania typu: {e}")


def add_brygada(name: str):
    name = name.strip()
    if not name:
        return
    existing = [b.get("name", "").lower() for b in st.session_state.brygady]
    if name.lower() in existing:
        st.warning("Taka brygada już istnieje.")
        return
    b = {"id": gen_id("bry"), "name": name}
    st.session_state.brygady.append(b)
    save_data()
    st.success(f"Dodano brygadę: {name}")


def remove_brygada(brygada_id: str):
    before = len(st.session_state.brygady)
    st.session_state.brygady = [b for b in st.session_state.brygady if b.get("id") != brygada_id]
    # usuń referencje w slotach
    for s in st.session_state.slots:
        if s.get("brygada_id") == brygada_id:
            s["brygada_id"] = None
    save_data()
    after = len(st.session_state.brygady)
    if before != after:
        st.info("Usunięto brygadę.")


def add_slot(name: str, start_date: str, end_date: str, slot_type: str = None, brygada_id: str = None):
    """
    Dodaje slot. Dates są zapisywane jako stringi ISO (YYYY-MM-DD) aby JSON był prosty.
    """
    if not name.strip():
        st.warning("Nazwa slotu jest wymagana.")
        return
    try:
        # prosta walidacja dat
        sd_obj = datetime.fromisoformat(start_date).date() if isinstance(start_date, str) else start_date
        ed_obj = datetime.fromisoformat(end_date).date() if isinstance(end_date, str) else end_date
        if sd_obj > ed_obj:
            st.warning("Data rozpoczęcia nie może być po dacie zakończenia.")
            return
    except Exception:
        st.warning("Błędny format daty. Użyj RRRR-MM-DD.")
        return

    slot = {
        "id": gen_id("slot"),
        "name": name.strip(),
        "start": start_date if isinstance(start_date, str) else sd_obj.isoformat(),
        "end": end_date if isinstance(end_date, str) else ed_obj.isoformat(),
        "type": slot_type,
        "brygada_id": brygada_id
    }
    st.session_state.slots.append(slot)
    save_data()
    st.success(f"Dodano slot: {name}")


def remove_slot(slot_id: str):
    before = len(st.session_state.slots)
    st.session_state.slots = [s for s in st.session_state.slots if s.get("id") != slot_id]
    save_data()
    after = len(st.session_state.slots)
    if before != after:
        st.info("Usunięto slot.")


def edit_slot(slot_id: str, **kwargs):
    for s in st.session_state.slots:
        if s.get("id") == slot_id:
            for k, v in kwargs.items():
                if k in s and v is not None:
                    s[k] = v
            save_data()
            st.success("Zaktualizowano slot.")
            return
    st.warning("Nie znaleziono slotu do edycji.")


# ---------- UI: formularze i widoki ----------
def sidebar_manage_types():
    st.sidebar.header("Typy slotów")
    with st.sidebar.form("form_add_type", clear_on_submit=True):
        new_type = st.text_input("Nazwa typu", key="input_new_type")
        submitted = st.form_submit_button("Dodaj typ")
        if submitted:
            add_slot_type(new_type)

    # Lista typów
    if st.session_state.slot_types:
        st.sidebar.markdown("**Istniejące typy:**")
        for i, t in enumerate(list(st.session_state.slot_types)):
            col1, col2 = st.sidebar.columns([3, 1])
            col1.write(t)
            if col2.button("Usuń", key=f"del_type_{i}"):
                remove_slot_type(i)


def sidebar_manage_brygady():
    st.sidebar.header("Brygady")
    with st.sidebar.form("form_add_brygada", clear_on_submit=True):
        new_bry = st.text_input("Nazwa brygady", key="input_new_bry")
        submitted = st.form_submit_button("Dodaj brygadę")
        if submitted:
            add_brygada(new_bry)

    if st.session_state.brygady:
        st.sidebar.markdown("**Lista brygad:**")
        for b in list(st.session_state.brygady):
            col1, col2 = st.sidebar.columns([3, 1])
            col1.write(b.get("name"))
            if col2.button("Usuń", key=f"del_bry_{b.get('id')}"):
                remove_brygada(b.get("id"))


def main():
    st.set_page_config(page_title="Sloty Gantt - z zapisem JSON", layout="wide")
    st.title("Sloty / Gantt — z zapisem do JSON")
    st.write("Aplikacja zapamiętuje dane w pliku `dane.json`. Dodawaj typy, brygady i sloty. Po każdej zmianie następuje zapis.")

    # Inicjalizacja i wczytanie danych
    ensure_session_state()
    # Jeżeli jeszcze nie wczytano danych (np. pierwszy run w tej sesji), załaduj
    if "loaded_from_file" not in st.session_state:
        load_data()
        st.session_state["loaded_from_file"] = True

    # Pasek boczny: zarządzanie typami i brygadami
    sidebar_manage_types()
    sidebar_manage_brygady()

    # Główna kolumna: lista slotów + formularz dodawania
    col1, col2 = st.columns([2, 3])

    with col1:
        st.header("Dodaj nowy slot")
        with st.form("form_add_slot", clear_on_submit=True):
            name = st.text_input("Nazwa slotu", key="slot_name")
            # daty
            today = date.today()
            start_date = st.date_input("Data rozpoczęcia", value=today, key="start_date")
            end_date = st.date_input("Data zakończenia", value=today, key="end_date")
            # wybór typu
            slot_type = None
            if st.session_state.slot_types:
                slot_type = st.selectbox("Typ slotu", options=[""] + st.session_state.slot_types, index=0, key="slot_type")
                if slot_type == "":
                    slot_type = None
            else:
                st.info("Brak zdefiniowanych typów. Dodaj w pasku bocznym.")

            # wybór brygady
            bry_options = [""] + [b.get("name") for b in st.session_state.brygady]
            bry_selected = None
            if st.session_state.brygady:
                bry_selected_name = st.selectbox("Przypisz brygadę", options=bry_options, index=0, key="slot_brygada")
                if bry_selected_name:
                    # znajdź id
                    bry_selected = next((b.get("id") for b in st.session_state.brygady if b.get("name") == bry_selected_name), None)
            else:
                st.info("Brak brygad. Dodaj w pasku bocznym.")

            submitted = st.form_submit_button("Dodaj slot")
            if submitted:
                # konwertuj daty na isoformat string przed zapisem
                add_slot(
                    name=name,
                    start_date=start_date.isoformat() if isinstance(start_date, date) else str(start_date),
                    end_date=end_date.isoformat() if isinstance(end_date, date) else str(end_date),
                    slot_type=slot_type,
                    brygada_id=bry_selected
                )

        st.markdown("---")
        st.header("Eksport / import danych")
        if st.button("Zapisz teraz (ręcznie)"):
            save_data()
            st.success("Dane zapisane do pliku.")

        if st.button("Wczytaj z pliku (nadpisz sesję)"):
            load_data()
            st.success("Wczytano dane z pliku.")

        st.download_button(
            label="Pobierz dane JSON",
            data=json.dumps({
                "slot_types": st.session_state.slot_types,
                "brygady": st.session_state.brygady,
                "slots": st.session_state.slots
            }, ensure_ascii=False, indent=4),
            file_name="dane.json",
            mime="application/json"
        )

    with col2:
        st.header("Lista slotów")
        if not st.session_state.slots:
            st.info("Brak slotów. Dodaj nowy slot w formularzu po lewej.")
        else:
            # Tabela prostego widoku slotów z operacjami
            for s in list(st.session_state.slots):
                box = st.expander(f"{s.get('name')} ({s.get('start')} → {s.get('end')})", expanded=False)
                with box:
                    c1, c2, c3 = st.columns([3, 2, 1])
                    c1.markdown(f"**Nazwa:** {s.get('name')}")
                    c1.markdown(f"**Typ:** {s.get('type') or '-'}")
                    bry_name = "-"
                    if s.get("brygada_id"):
                        bry = next((b for b in st.session_state.brygady if b.get("id") == s.get("brygada_id")), None)
                        if bry:
                            bry_name = bry.get("name")
                    c1.markdown(f"**Brygada:** {bry_name}")
                    c1.markdown(f"**Start:** {s.get('start')}")
                    c1.markdown(f"**Koniec:** {s.get('end')}")

                    # Opcje: edycja prostego formularza
                    with c2.form(f"edit_slot_form_{s.get('id')}"):
                        new_name = st.text_input("Nazwa", value=s.get("name"), key=f"ename_{s.get('id')}")
                        try:
                            new_start = st.date_input("Start", value=datetime.fromisoformat(s.get("start")).date(), key=f"estart_{s.get('id')}")
                            new_end = st.date_input("End", value=datetime.fromisoformat(s.get("end")).date(), key=f"eend_{s.get('id')}")
                        except Exception:
                            # w razie błędnego formatu dat w danych (defensywnie)
                            new_start = st.date_input("Start", value=date.today(), key=f"estart_{s.get('id')}")
                            new_end = st.date_input("End", value=date.today(), key=f"eend_{s.get('id')}")
                        # typ
                        type_options = [""] + st.session_state.slot_types if st.session_state.slot_types else [""]
                        current_type = s.get("type") or ""
                        new_type = st.selectbox("Typ", options=type_options, index=type_options.index(current_type) if current_type in type_options else 0, key=f"etype_{s.get('id')}")
                        if new_type == "":
                            new_type = None
                        # brygada
                        bry_options = [""] + [b.get("name") for b in st.session_state.brygady] if st.session_state.brygady else [""]
                        current_bry_name = bry_name if bry_name != "-" else ""
                        new_bry_name = st.selectbox("Brygada", options=bry_options, index=bry_options.index(current_bry_name) if current_bry_name in bry_options else 0, key=f"ebry_{s.get('id')}")
                        new_bry_id = None
                        if new_bry_name:
                            new_bry_id = next((b.get("id") for b in st.session_state.brygady if b.get("name") == new_bry_name), None)

                        btn_update = st.form_submit_button("Zapisz")
                        if btn_update:
                            edit_slot(
                                s.get("id"),
                                name=new_name.strip(),
                                start=new_start.isoformat(),
                                end=new_end.isoformat(),
                                type=new_type,
                                brygada_id=new_bry_id
                            )

                    # Usuń slot
                    if c3.button("Usuń", key=f"del_slot_{s.get('id')}"):
                        remove_slot(s.get("id"))

    st.markdown("---")
    st.write("Informacje techniczne:")
    st.write(f"Ilość typów: **{len(st.session_state.slot_types)}**, brygad: **{len(st.session_state.brygady)}**, slotów: **{len(st.session_state.slots)}**")
    st.caption(f"Plik danych: `{DATA_FILE}` (zapisane w katalogu, z którego uruchomiono aplikację)")

    # Opcjonalnie: szybkie podglądy JSON
    if st.checkbox("Pokaż surowe dane (JSON)", key="show_raw"):
        st.json({
            "slot_types": st.session_state.slot_types,
            "brygady": st.session_state.brygady,
            "slots": st.session_state.slots
        })


if __name__ == "__main__":
    main()
