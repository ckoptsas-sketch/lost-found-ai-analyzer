import streamlit as st
import pandas as pd
from datetime import datetime
from google import genai
from google.genai import types
from PIL import Image, UnidentifiedImageError
import json
import time
import io

# ==========================================
# 1. ΑΣΦΑΛΕΙΑ: ΣΥΣΤΗΜΑ LOGIN (Secrets based)
# ==========================================
def check_password():
    if "password_correct" not in st.session_state:
        st.subheader("🔒 ATH Lost & Found - 🔑 Είσοδος στο Σύστημα")
        
        st.text_input("Όνομα Χρήστη", key="username")
        st.text_input("Κωδικός Πρόσβασης", type="password", key="password")
        
        if st.button("Σύνδεση"):
            if st.session_state["username"] == st.secrets.get("USER_NAME", "") and st.session_state["password"] == st.secrets.get("USER_PASSWORD", ""):
                st.session_state["password_correct"] = True
                st.session_state["logged_user"] = st.session_state["username"]
                st.rerun()
            else:
                st.session_state["password_correct"] = False
                st.error("❌ Λάθος στοιχεία πρόσβασης.")
        return False
    return st.session_state["password_correct"]

if check_password():
    # 2. ΡΥΘΜΙΣΗ GEMINI CLIENT
    api_key = st.secrets.get("GEMINI_API_KEY", "")
    if api_key:
        client = genai.Client(api_key=api_key)
    else:
        st.error("⚠️ Λείπει το GEMINI_API_KEY από τα Secrets.")
        st.stop()

    # 3. ΑΡΧΙΚΟΠΟΙΗΣΗ ΜΝΗΜΗΣ (Session State)
    if "final_dataframe" not in st.session_state:
        st.session_state.final_dataframe = pd.DataFrame(columns=[
            "Κύμα", "Agent", "Επιβάτης", "Tag Number", "Πτήση", "Διαδρομή", 
            "Τύπος/Χρώμα", "File Reference / PIR", "STATUS"
        ])
    if "photo_buffer" not in st.session_state:
        st.session_state.photo_buffer = []

    st.title("✈️ ATH Lost & Found - Smart Work Desk")
    st.caption(f"Συνδεδεμένος Χρήστης: {st.session_state.get('logged_user', 'Agent')}")

    # ==========================================
    # 4. ΡΟΗ Α: ΕΙΣΑΓΩΓΗ ΝΕΟΥ ΚΥΜΑΤΟΣ (INBOUND)
    # ==========================================
    st.subheader("📸 Βήμα 1: Καταγραφή Νέου Κύματος (Inbound)")

    uploaded_files = st.file_uploader(
        "Τράβηξε φωτογραφία ή επίλεξε αρχεία από τη συλλογή σου", 
        type=["png", "jpg", "jpeg"], 
        accept_multiple_files=True,
        key="inbound_uploader"
    )

    if uploaded_files:
        for file in uploaded_files:
            try:
                bytes_data = file.getvalue()
                pil_image = Image.open(io.BytesIO(bytes_data))
                pil_image = pil_image.convert("RGB")

                if file.name not in [x['id'] for x in st.session_state.photo_buffer]:
                    st.session_state.photo_buffer.append({"id": file.name, "image": pil_image})
                    st.success(f"Η φωτογραφία '{file.name}' προστέθηκε στο κύμα.")
            except UnidentifiedImageError:
                st.error(f"⚠️ Το αρχείο '{file.name}' δεν είναι έγκυρη εικόνα. Παρακαλώ επιλέξτε ξανά.")
            except Exception as e:
                st.error(f"⚠️ Σφάλμα στο αρχείο '{file.name}': {e}")

    st.metric(label="Φωτογραφίες έτοιμες για ανάλυση", value=len(st.session_state.photo_buffer))

    if st.button("🚀 ΟΛΟΚΛΗΡΩΣΗ ΚΥΜΑΤΟΣ & ΑΝΑΛΥΣΗ AI"):
        if len(st.session_state.photo_buffer) == 0:
            st.warning("Δεν υπάρχουν νέες φωτογραφίες.")
        else:
            with st.spinner("Το Gemini 2.5 Flash αναλύει τις αποσκευές..."):
                wave_id = f"Wave_{datetime.now().strftime('%H%M%S')}"
                current_agent = st.session_state.get('logged_user', 'Agent')
                new_rows = []

                prompt_inbound = """
                Ανάλυσε το tag της αποσκευής και επέστρεψε ΜΟΝΟ JSON (Χωρίς Markdown):
                {
                  "Passenger": "ΕΠΩΝΥΜΟ/ΟΝΟΜΑ",
                  "Tag_Number": "Αριθμός Tag (αφαίρεσε κενά)",
                  "Flight": "Πτήση",
                  "Routing": "Διαδρομή",
                  "WT_Code": "Τύπος/Χρώμα"
                }
                """
                for item in st.session_state.photo_buffer:
                    try:
                        response = client.models.generate_content(
                            model='gemini-2.5-flash',
                            contents=[item["image"], prompt_inbound],
                            config=types.GenerateContentConfig(response_mime_type="application/json")
                        )
                        clean_json_str = response.text.replace('```json', '').replace('```', '').strip()
                        res_data = json.loads(clean_json_str)
                        
                        new_rows.append({
                            "Κύμα": wave_id,
                            "Agent": current_agent,
                            "Επιβάτης": res_data.get("Passenger", "N/A"),
                            "Tag Number": str(res_data.get("Tag_Number", "N/A")).replace(' ', ''),
                            "Πτήση": res_data.get("Flight", "N/A"),
                            "Διαδρομή": res_data.get("Routing", "N/A"),
                            "Τύπος/Χρώμα": res_data.get("WT_Code", "N/A"),
                            "File Reference / PIR": "",
                            "STATUS": "🔴 ΕΚΚΡΕΜΟΤΗΤΑ"
                        })
                    except Exception as e:
                        st.error(f"Σφάλμα OCR: {e}")

                if new_rows:
                    wave_df = pd.DataFrame(new_rows)
                    wave_df.drop_duplicates(subset=["Tag Number"], keep="first", inplace=True)
                    st.session_state.final_dataframe = pd.concat([st.session_state.final_dataframe, wave_df], ignore_index=True)
                    st.session_state.final_dataframe.sort_values(by=["Επιβάτης"], inplace=True)
                    st.session_state.final_dataframe.reset_index(drop=True, inplace=True)
                
                st.session_state.photo_buffer = []
                st.success("Το κύμα καταχωρήθηκε επιτυχώς!")
                st.rerun()

    st.markdown("---")

    # ==========================================
    # 5. ΡΟΗ Β: ΑΥΤΟΜΑΤΟ MATCH ΜΕ ΦΩΤΟ ΟΘΟΝΗΣ
    # ==========================================
    st.subheader("🖥️ Βήμα 2: Αυτόματο Κλείσιμο (Φωτό Οθόνης WorldTracer)")
    
    pending_bags = st.session_state.final_dataframe[st.session_state.final_dataframe["STATUS"] != "🟢 ΟΛΟΚΛΗΡΩΣΗ"]
    
    if pending_bags.empty:
        st.success("🎉 Όλες οι αποσκευές έχουν ολοκληρωθεί!")
    else:
        st.info(f"Εκκρεμούν {len(pending_bags)} αποσκευές.")
        
        wt_screen_file = st.file_uploader(
            "Ανέβασε τη φωτογραφία της οθόνης WorldTracer (PIR & Tags)", 
            type=["png", "jpg", "jpeg"], 
            key="wt_uploader"
        )
        
        if wt_screen_file is not None:
            if st.button("💾 ΑΥΤΟΜΑΤΗ ΕΠΑΛΗΘΕΥΣΗ & ΚΛΕΙΣΙΜΟ"):
                with st.spinner("Ανάγνωση οθόνης συστήματος και σύγκριση..."):
                    try:
                        pil_wt = Image.open(io.BytesIO(wt_screen_file.getvalue())).convert("RGB")
                        prompt_wt = """
                        Ανάλυσε την οθόνη του WorldTracer και επέστρεψε ΜΟΝΟ JSON (Χωρίς Markdown):
                        {
                          "File_Reference": "Το File Reference Number (π.χ. ATHAF12345)",
                          "Tags_On_Screen": ["Tag1", "Tag2"] (αφαίρεσε κενά από τους αριθμούς)
                        }
                        """
                        response_wt = client.models.generate_content(
                            model='gemini-2.5-flash',
                            contents=[pil_wt, prompt_wt],
                            config=types.GenerateContentConfig(response_mime_type="application/json")
                        )
                        clean_json_wt = response_wt.text.replace('```json', '').replace('```', '').strip()
                        wt_data = json.loads(clean_json_wt)
                        
                        pir_number = wt_data.get("File_Reference", "N/A")
                        tags_from_screen = [str(tag).replace(' ', '') for tag in wt_data.get("Tags_On_Screen", [])]
                        
                        if pir_number != "N/A" and tags_from_screen:
                            matched_bags_indices = []
                            for index, row in st.session_state.final_dataframe.iterrows():
                                if row['STATUS'] != "🟢 ΟΛΟΚΛΗΡΩΣΗ":
                                    current_tag = str(row['Tag Number']).replace(' ', '')
                                    if current_tag in tags_from_screen:
                                        matched_bags_indices.append(index)
                            
                            if matched_bags_indices:
                                for idx in matched_bags_indices:
                                    st.session_state.final_dataframe.at[idx, "File Reference / PIR"] = pir_number
                                    st.session_state.final_dataframe.at[idx, "STATUS"] = "🟢 ΟΛΟΚΛΗΡΩΣΗ"
                                st.success(f"📌 {len(matched_bags_indices)} αποσκευή(ες) έκλεισαν αυτόματα με το PIR: {pir_number}")
                                time.sleep(1.5)
                                st.rerun()
                            else:
                                st.error("Δεν βρέθηκε match μεταξύ των tags της οθόνης και των εκκρεμοτήτων στον πίνακα.")
                        else:
                            st.error("Δεν μπόρεσα να διαβάσω File Reference ή Tags από τη φωτογραφία της οθόνης.")
                    except (UnidentifiedImageError, Exception) as e:
                        st.error(f"Σφάλμα ανάγνωσης αρχείου εικόνας: {e}")

    st.markdown("---")

    # ==========================================
    # 6. ΚΕΝΤΡΙΚΟΣ ΠΙΝΑΚΑΣ ΜΕ ΤΙΣ 3 ΚΑΤΗΓΟΡΙΕΣ
    # ==========================================
    st.subheader("📊 Κεντρικός Πίνακας Διαχείρισης Βάρδιας")
    
    if not st.session_state.final_dataframe.empty:
        edited_df = st.data_editor(
            st.session_state.final_dataframe,
            column_config={
                "STATUS": st.column_config.SelectboxColumn(
                    "STATUS",
                    options=["🔴 ΕΚΚΡΕΜΟΤΗΤΑ", "🟡 ΔΗΜΙΟΥΡΓΙΑ/ΑΝΑΖΗΤΗΣΗ", "🟢 ΟΛΟΚΛΗΡΩΣΗ"],
                    required=True
                )
            },
            disabled=["Κύμα"]
        )
        st.session_state.final_dataframe = edited_df
        
        csv = st.session_state.final_dataframe.to_csv(index=False).encode('utf-8')
        st.download_button("📥 Λήψη Shift Report (CSV)", data=csv, file_name=f"LF_Report_{datetime.now().strftime('%Y%m%d')}.csv", mime="text/csv")
    else:
        st.info("Ο πίνακας είναι άδειος. Ξεκίνα από το Βήμα 1.")
