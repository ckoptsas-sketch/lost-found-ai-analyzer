import streamlit as st
import pandas as pd
from datetime import datetime
from google import genai
from google.genai import types
from PIL import Image, UnidentifiedImageError, ImageFile
import json
import time
import io

# =========================
# APP CONFIG
# =========================
st.set_page_config(
    page_title="ATH Lost & Found",
    page_icon="✈️",
    layout="wide",
    initial_sidebar_state="collapsed",
)

ImageFile.LOAD_TRUNCATED_IMAGES = True
MAX_SIZE = 15 * 1024 * 1024  # 15 MB

# =========================
# LOGIN
# =========================
def check_password():
    if "password_correct" not in st.session_state:
        st.markdown("## 🔒 ATH Lost & Found")
        st.markdown("### Είσοδος στο Σύστημα")

        st.text_input("Όνομα Χρήστη", key="username")
        st.text_input("Κωδικός Πρόσβασης", type="password", key="password")

        if st.button("Σύνδεση", use_container_width=True):
            if (
                st.session_state["username"] == st.secrets.get("USER_NAME", "")
                and st.session_state["password"] == st.secrets.get("USER_PASSWORD", "")
            ):
                st.session_state["password_correct"] = True
                st.session_state["logged_user"] = st.session_state["username"]
                st.rerun()
            else:
                st.session_state["password_correct"] = False
                st.error("❌ Λάθος στοιχεία πρόσβασης.")
        return False
    return st.session_state["password_correct"]

# =========================
# HELPERS
# =========================
def load_image_from_upload(uploaded_file):
    raw = uploaded_file.getvalue()
    try:
        img = Image.open(io.BytesIO(raw))
        img.load()
        return img.convert("RGB")
    except Exception as e:
        raise UnidentifiedImageError(
            f"Το αρχείο '{uploaded_file.name}' δεν αναγνωρίζεται ως εικόνα."
        ) from e

def buffer_key_exists(item_id):
    return item_id in [x["id"] for x in st.session_state.get("photo_buffer", [])]

def add_file_to_buffer(file_obj):
    if file_obj is None:
        return

    if file_obj.size > MAX_SIZE:
        st.error(f"⚠️ Το αρχείο '{file_obj.name}' είναι πολύ μεγάλο. Μέγιστο 15MB.")
        return

    try:
        img = load_image_from_upload(file_obj)
        item_id = f"{file_obj.name}_{file_obj.size}_{file_obj.type}"

        if not buffer_key_exists(item_id):
            st.session_state.photo_buffer.append(
                {
                    "id": item_id,
                    "name": file_obj.name,
                    "type": file_obj.type,
                    "size": file_obj.size,
                    "image": img,
                }
            )
            st.toast(f"Προστέθηκε: {file_obj.name}", icon="✅")
    except UnidentifiedImageError:
        st.error(f"⚠️ Το αρχείο '{file_obj.name}' δεν αναγνωρίζεται ως εικόνα.")
    except Exception as e:
        st.error(f"⚠️ Σφάλμα στο αρχείο '{file_obj.name}': {e}")

def show_buffer_preview(buffer_name, title):
    items = st.session_state.get(buffer_name, [])
    st.markdown(f"### {title}")

    if not items:
        st.info("Δεν υπάρχουν φωτογραφίες.")
        return

    n = len(items)
    if n == 1:
        st.image(items[0]["image"], caption=items[0]["name"], use_container_width=True)
        return

    cols = st.columns(2)
    for idx, item in enumerate(items):
        with cols[idx % 2]:
            st.image(item["image"], caption=item["name"], use_container_width=True)

def smart_json_parse(text):
    cleaned = text.replace("```json", "").replace("```", "").strip()
    return json.loads(cleaned)

# =========================
# MAIN
# =========================
if check_password():
    api_key = st.secrets.get("GEMINI_API_KEY", "")
    if not api_key:
        st.error("⚠️ Λείπει το GEMINI_API_KEY από τα Secrets.")
        st.stop()

    client = genai.Client(api_key=api_key)

    if "final_dataframe" not in st.session_state:
        st.session_state.final_dataframe = pd.DataFrame(
            columns=[
                "Κύμα",
                "Agent",
                "Επιβάτης",
                "Tag Number",
                "Πτήση",
                "Διαδρομή",
                "Τύπος/Χρώμα",
                "File Reference / PIR",
                "STATUS",
            ]
        )

    if "photo_buffer" not in st.session_state:
        st.session_state.photo_buffer = []

    if "wt_buffer" not in st.session_state:
        st.session_state.wt_buffer = []

    st.title("✈️ ATH Lost & Found")
    st.caption(f"Συνδεδεμένος Χρήστης: {st.session_state.get('logged_user', 'Agent')}")

    # =========================
    # INBOUND
    # =========================
    st.markdown("## 📸 Βήμα 1: Νέο Κύμα")

    tab1, tab2 = st.tabs(["📂 Upload", "📷 Κάμερα"])

    with tab1:
        inbound_files = st.file_uploader(
            "Ανέβασε φωτογραφίες",
            type=["png", "jpg", "jpeg", "webp"],
            accept_multiple_files=True,
            key="inbound_uploader",
            label_visibility="visible",
        )
        if inbound_files:
            for f in inbound_files:
                add_file_to_buffer(f)

    with tab2:
        inbound_cam = st.camera_input(
            "Τράβηξε φωτογραφία",
            key="inbound_camera",
        )
        if inbound_cam is not None:
            add_file_to_buffer(inbound_cam)

    if st.session_state.photo_buffer:
        st.metric("Φωτογραφίες στο κύμα", len(st.session_state.photo_buffer))
        show_buffer_preview("photo_buffer", "Προεπισκόπηση Κύματος")

        c1, c2 = st.columns(2)
        with c1:
            if st.button("🚀 Ανάλυση Κύματος", use_container_width=True):
                with st.spinner("Ανάλυση φωτογραφιών..."):
                    wave_id = f"Wave_{datetime.now().strftime('%Y%m%d_%H%M%S')}"
                    current_agent = st.session_state.get("logged_user", "Agent")
                    new_rows = []

                    prompt_inbound = """
Ανάλυσε το tag της αποσκευής και επέστρεψε ΜΟΝΟ JSON:
{
  "Passenger": "ΕΠΩΝΥΜΟ/ΟΝΟΜΑ",
  "Tag_Number": "Αριθμός Tag χωρίς κενά",
  "Flight": "Πτήση",
  "Routing": "Διαδρομή",
  "WT_Code": "Τύπος/Χρώμα"
}
"""

                    for item in st.session_state.photo_buffer:
                        try:
                            response = client.models.generate_content(
                                model="gemini-2.5-flash",
                                contents=[item["image"], prompt_inbound],
                                config=types.GenerateContentConfig(
                                    response_mime_type="application/json"
                                ),
                            )
                            data = smart_json_parse(response.text)

                            new_rows.append(
                                {
                                    "Κύμα": wave_id,
                                    "Agent": current_agent,
                                    "Επιβάτης": data.get("Passenger", "N/A"),
                                    "Tag Number": str(data.get("Tag_Number", "N/A")).replace(" ", ""),
                                    "Πτήση": data.get("Flight", "N/A"),
                                    "Διαδρομή": data.get("Routing", "N/A"),
                                    "Τύπος/Χρώμα": data.get("WT_Code", "N/A"),
                                    "File Reference / PIR": "",
                                    "STATUS": "🔴 ΕΚΚΡΕΜΟΤΗΤΑ",
                                }
                            )
                        except Exception as e:
                            st.error(f"Σφάλμα OCR στο '{item['name']}': {e}")

                    if new_rows:
                        wave_df = pd.DataFrame(new_rows)
                        wave_df.drop_duplicates(subset=["Tag Number"], keep="first", inplace=True)
                        st.session_state.final_dataframe = pd.concat(
                            [st.session_state.final_dataframe, wave_df],
                            ignore_index=True,
                        )
                        st.session_state.final_dataframe.sort_values(by=["Επιβάτης"], inplace=True)
                        st.session_state.final_dataframe.reset_index(drop=True, inplace=True)

                    st.session_state.photo_buffer = []
                    st.success("Το κύμα καταχωρήθηκε.")
                    st.rerun()

        with c2:
            if st.button("🗑️ Καθαρισμός Κύματος", use_container_width=True):
                st.session_state.photo_buffer = []
                st.toast("Το κύμα καθάρισε.", icon="🧹")
                st.rerun()

    st.markdown("---")

    # =========================
    # WT
    # =========================
    st.markdown("## 🖥️ Βήμα 2: WorldTracer")

    pending_bags = st.session_state.final_dataframe[
        st.session_state.final_dataframe["STATUS"] != "🟢 ΟΛΟΚΛΗΡΩΣΗ"
    ]

    if pending_bags.empty:
        st.success("🎉 Όλες οι αποσκευές έχουν ολοκληρωθεί!")
    else:
        st.info(f"Εκκρεμούν {len(pending_bags)} αποσκευές.")

        tabw1, tabw2 = st.tabs(["📂 Upload Οθόνης", "📷 Κάμερα Οθόνης"])

        with tabw1:
            wt_file = st.file_uploader(
                "Ανέβασε φωτογραφία WorldTracer",
                type=["png", "jpg", "jpeg", "webp"],
                key="wt_uploader",
            )
            if wt_file is not None:
                try:
                    st.session_state.wt_buffer = [{
                        "id": f"{wt_file.name}_{wt_file.size}_{wt_file.type}",
                        "name": wt_file.name,
                        "type": wt_file.type,
                        "size": wt_file.size,
                        "image": load_image_from_upload(wt_file),
                    }]
                except Exception as e:
                    st.error(f"Σφάλμα φόρτωσης WT: {e}")

        with tabw2:
            wt_cam = st.camera_input(
                "Τράβηξε φωτογραφία WorldTracer",
                key="wt_camera",
            )
            if wt_cam is not None:
                try:
                    st.session_state.wt_buffer = [{
                        "id": f"{wt_cam.name}_{wt_cam.size}_{wt_cam.type}",
                        "name": wt_cam.name,
                        "type": wt_cam.type,
                        "size": wt_cam.size,
                        "image": load_image_from_upload(wt_cam),
                    }]
                except Exception as e:
                    st.error(f"Σφάλμα φόρτωσης WT: {e}")

        if st.session_state.wt_buffer:
            show_buffer_preview("wt_buffer", "Προεπισκόπηση WorldTracer")

            if st.button("💾 Επαλήθευση & Κλείσιμο", use_container_width=True):
                with st.spinner("Ανάγνωση οθόνης και σύγκριση..."):
                    try:
                        wt_item = st.session_state.wt_buffer[0]
                        response_wt = client.models.generate_content(
                            model="gemini-2.5-flash",
                            contents=[
                                wt_item["image"],
                                """
Ανάλυσε την οθόνη του WorldTracer και επέστρεψε ΜΟΝΟ JSON:
{
  "File_Reference": "Το File Reference Number",
  "Tags_On_Screen": ["Tag1", "Tag2"]
}
""",
                            ],
                            config=types.GenerateContentConfig(
                                response_mime_type="application/json"
                            ),
                        )

                        wt_data = smart_json_parse(response_wt.text)

                        pir_number = wt_data.get("File_Reference", "N/A")
                        tags_from_screen = [
                            str(tag).replace(" ", "")
                            for tag in wt_data.get("Tags_On_Screen", [])
                        ]

                        if pir_number != "N/A" and tags_from_screen:
                            matched_indices = []
                            for index, row in st.session_state.final_dataframe.iterrows():
                                if row["STATUS"] != "🟢 ΟΛΟΚΛΗΡΩΣΗ":
                                    current_tag = str(row["Tag Number"]).replace(" ", "")
                                    if current_tag in tags_from_screen:
                                        matched_indices.append(index)

                            if matched_indices:
                                for idx in matched_indices:
                                    st.session_state.final_dataframe.at[idx, "File Reference / PIR"] = pir_number
                                    st.session_state.final_dataframe.at[idx, "STATUS"] = "🟢 ΟΛΟΚΛΗΡΩΣΗ"

                                st.success(f"Κλείστηκαν {len(matched_indices)} αποσκευή(ες) με PIR: {pir_number}")
                                time.sleep(1.2)
                                st.rerun()
                            else:
                                st.error("Δεν βρέθηκε match με τα tags της οθόνης.")
                        else:
                            st.error("Δεν μπόρεσα να διαβάσω σωστά PIR ή Tags από τη φωτογραφία.")
                    except Exception as e:
                        st.error(f"Σφάλμα επαλήθευσης: {e}")

    st.markdown("---")

    # =========================
    # TABLE
    # =========================
    st.markdown("## 📊 Κεντρικός Πίνακας")

    if not st.session_state.final_dataframe.empty:
        edited_df = st.data_editor(
            st.session_state.final_dataframe,
            use_container_width=True,
            column_config={
                "STATUS": st.column_config.SelectboxColumn(
                    "STATUS",
                    options=[
                        "🔴 ΕΚΚΡΕΜΟΤΗΤΑ",
                        "🟡 ΔΗΜΙΟΥΡΓΙΑ/ΑΝΑΖΗΤΗΣΗ",
                        "🟢 ΟΛΟΚΛΗΡΩΣΗ",
                    ],
                    required=True,
                )
            },
            disabled=["Κύμα"],
        )
        st.session_state.final_dataframe = edited_df

        csv = st.session_state.final_dataframe.to_csv(index=False).encode("utf-8")
        st.download_button(
            "📥 Λήψη Shift Report (CSV)",
            data=csv,
            file_name=f"LF_Report_{datetime.now().strftime('%Y%m%d')}.csv",
            mime="text/csv",
            use_container_width=True,
        )
    else:
        st.info("Ο πίνακας είναι άδειος.")
