import streamlit as st
import pandas as pd
import face_recognition
import cv2
import numpy as np
import os
from datetime import datetime
from geopy.distance import geodesic
from streamlit_geolocation import streamlit_geolocation
from streamlit_webrtc import webrtc_streamer, VideoTransformerBase
import av

# --- KONFIGURASI PROYEK ---
PAGE_TITLE = "AuraScan-Sense | Smart Attendance"
PAGE_ICON = "📍"
LOKASI_KANTOR = (-7.2575, 112.7521) # CONTOH: Surabaya (Ganti dengan koordinat Anda)
RADIUS_KM = 0.5 # Radius toleransi (misal 500 meter)
DIR_WAJAH = "data/wajah"
DIR_LOG = "data/absensi"
FILE_LOG = os.path.join(DIR_LOG, "log_absensi.csv")

# Pastikan folder tersedia
os.makedirs(DIR_WAJAH, exist_ok=True)
os.makedirs(DIR_LOG, exist_ok=True)

# --- SETUP HALAMAN ---
st.set_page_config(page_title=PAGE_TITLE, page_icon=PAGE_ICON, layout="wide")

# --- CSS CUSTOM UNTUK TAMPILAN ---
st.markdown("""
    <style>
    .main {background-color: #f5f7f9;}
    .stButton>button {width: 100%; border-radius: 5px;}
    .reportview-container .main .block-container{padding-top: 1rem;}
    </style>
    """, unsafe_allow_html=True)

# --- FUNGSI UTILITAS ---

@st.cache_resource
def load_known_faces():
    """Memuat dan mengenkode wajah dari folder data/wajah."""
    encodings = []
    names = []
    files = os.listdir(DIR_WAJAH)
    
    for filename in files:
        if filename.endswith(('.jpg', '.jpeg', '.png')):
            path = os.path.join(DIR_WAJAH, filename)
            try:
                img = face_recognition.load_image_file(path)
                img_enc = face_recognition.face_encodings(img)
                if img_enc:
                    encodings.append(img_enc[0])
                    # Nama file format: Nama_ID.jpg -> ambil Nama
                    name = os.path.splitext(filename)[0].split('_')[0]
                    names.append(name)
            except Exception as e:
                st.error(f"Error memuat {filename}: {e}")
                
    return encodings, names

def catat_log(nama, status, lokasi_user):
    """Mencatat hasil absensi ke CSV."""
    now = datetime.now()
    if not os.path.exists(FILE_LOG):
        df = pd.DataFrame(columns=["Waktu", "Nama", "Status", "Latitude", "Longitude"])
        df.to_csv(FILE_LOG, index=False)
        
    df = pd.read_csv(FILE_LOG)
    # Cek duplikasi absensi di hari yang sama (opsional)
    hari_ini = now.strftime("%Y-%m-%d")
    # Filter log hari ini untuk nama tersebut
    cek_absen = df[df['Nama'] == nama]
    sudah_absen = any(row['Waktu'].startswith(hari_ini) for index, row in cek_absen.iterrows())
    
    if not sudah_absen:
        new_data = {
            "Waktu": now.strftime("%Y-%m-%d %H:%M:%S"),
            "Nama": nama,
            "Status": status,
            "Latitude": lokasi_user[0],
            "Longitude": lokasi_user[1]
        }
        # Menggunakan pd.concat sebagai pengganti append (deprecated)
        df = pd.concat([df, pd.DataFrame([new_data])], ignore_index=True)
        df.to_csv(FILE_LOG, index=False)
        return True, "Absensi Berhasil!"
    else:
        return False, "Anda sudah absen hari ini."

def hitung_jarak_km(coords_1, coords_2):
    return geodesic(coords_1, coords_2).kilometers

# --- CALLBACK VIDEO STREAM ---
# Kita perlu kelas/fungsi callback untuk memproses frame video secara real-time
class VideoProcessor:
    def __init__(self):
        self.known_encodings, self.known_names = load_known_faces()
        self.found_name = None

    def recv(self, frame):
        img = frame.to_ndarray(format="bgr24")
        
        # Optimasi: Kecilkan ukuran frame untuk proses lebih cepat
        small_frame = cv2.resize(img, (0, 0), fx=0.25, fy=0.25)
        # Konversi BGR (OpenCV) ke RGB (face_recognition)
        rgb_small_frame = np.ascontiguousarray(small_frame[:, :, ::-1])

        face_locations = face_recognition.face_locations(rgb_small_frame)
        face_encodings = face_recognition.face_encodings(rgb_small_frame, face_locations)

        for face_encoding, face_location in zip(face_encodings, face_locations):
            matches = face_recognition.compare_faces(self.known_encodings, face_encoding, tolerance=0.5)
            name = "Unknown"
            
            face_distances = face_recognition.face_distance(self.known_encodings, face_encoding)
            if len(face_distances) > 0:
                best_match_index = np.argmin(face_distances)
                if matches[best_match_index]:
                    name = self.known_names[best_match_index]
                    self.found_name = name # Simpan nama yang ditemukan

            # Gambar kotak (Scale balik koordinat * 4)
            top, right, bottom, left = face_location
            top *= 4
            right *= 4
            bottom *= 4
            left *= 4

            color = (0, 255, 0) if name != "Unknown" else (0, 0, 255)
            cv2.rectangle(img, (left, top), (right, bottom), color, 2)
            cv2.rectangle(img, (left, bottom - 35), (right, bottom), color, cv2.FILLED)
            cv2.putText(img, name, (left + 6, bottom - 6), cv2.FONT_HERSHEY_DUPLEX, 0.8, (255, 255, 255), 1)

        return av.VideoFrame.from_ndarray(img, format="bgr24")

# --- MAIN APP LAYOUT ---

st.title(f"{PAGE_ICON} AuraScan-Sense")
st.write("Sistem Absensi Cerdas Berbasis Wajah & Lokasi")

# Sidebar untuk Info Kantor
with st.sidebar:
    st.header("🏢 Info Kantor")
    st.map(pd.DataFrame({'lat': [LOKASI_KANTOR[0]], 'lon': [LOKASI_KANTOR[1]]}), zoom=14)
    st.caption(f"Koordinat Pusat: {LOKASI_KANTOR}")
    st.caption(f"Radius Izin: {RADIUS_KM} km")
    if st.button("🔄 Refresh Data Wajah"):
        st.cache_resource.clear()
        st.success("Cache wajah diperbarui!")

# Tabs Navigasi
tab1, tab2, tab3 = st.tabs(["📸 Absensi", "📝 Riwayat", "➕ Registrasi (Admin)"])

# --- TAB 1: ABSENSI ---
with tab1:
    col1, col2 = st.columns([1, 2])
    
    with col1:
        st.info("Langkah 1: Dapatkan Lokasi")
        location = streamlit_geolocation()
        
        lokasi_valid = False
        user_coords = None

        if location and location['latitude'] is not None:
            user_coords = (location['latitude'], location['longitude'])
            jarak = hitung_jarak_km(user_coords, LOKASI_KANTOR)
            
            st.metric("Jarak ke Kantor", f"{jarak:.2f} km")
            
            if jarak <= RADIUS_KM:
                st.success("✅ Lokasi Valid")
                lokasi_valid = True
            else:
                st.error("❌ Di Luar Jangkauan")
        else:
            st.warning("Menunggu akses lokasi...")

    with col2:
        st.info("Langkah 2: Scan Wajah")
        if lokasi_valid:
            # Panggil class processor di luar loop agar persist
            ctx = webrtc_streamer(
                key="absensi-stream",
                video_processor_factory=VideoProcessor,
                rtc_configuration={"iceServers": [{"urls": ["stun:stun.l.google.com:19302"]}]},
            )
            
            # Logika tombol manual untuk trigger simpan database
            if ctx.video_processor:
                detected_name = ctx.video_processor.found_name
                if detected_name and detected_name != "Unknown":
                    st.success(f"Wajah dikenali: **{detected_name}**")
                    if st.button(f"📅 Catat Hadir: {detected_name}"):
                        status_ok, msg = catat_log(detected_name, "Hadir", user_coords)
                        if status_ok:
                            st.balloons()
                            st.success(msg)
                        else:
                            st.warning(msg)
        else:
            st.image("https://via.placeholder.com/640x360.png?text=Buka+Kunci+Lokasi+Dahulu", use_column_width=True)

# --- TAB 2: RIWAYAT ---
with tab2:
    st.header("Log Kehadiran")
    if os.path.exists(FILE_LOG):
        df = pd.read_csv(FILE_LOG)
        df['Waktu'] = pd.to_datetime(df['Waktu'])
        df = df.sort_values(by='Waktu', ascending=False)
        st.dataframe(df, use_container_width=True)
        
        # Download button
        csv = df.to_csv(index=False).encode('utf-8')
        st.download_button("Unduh CSV", csv, "laporan_absensi.csv", "text/csv")
    else:
        st.info("Belum ada data absensi.")

# --- TAB 3: REGISTRASI (ADMIN) ---
with tab3:
    st.header("Pendaftaran Pegawai Baru")
    st.write("Tambahkan wajah pegawai baru ke database tanpa coding.")
    
    with st.form("registrasi_form"):
        nama_pegawai = st.text_input("Nama Pegawai (Tanpa Spasi disarankan)", placeholder="Budi_Santoso")
        id_pegawai = st.text_input("ID Pegawai", placeholder="1001")
        img_file = st.camera_input("Ambil Foto Wajah")
        
        submit = st.form_submit_button("Simpan Data")
        
        if submit:
            if nama_pegawai and id_pegawai and img_file:
                # Format nama file: Nama_ID.jpg
                filename = f"{nama_pegawai}_{id_pegawai}.jpg"
                filepath = os.path.join(DIR_WAJAH, filename)
                
                with open(filepath, "wb") as f:
                    f.write(img_file.getbuffer())
                
                st.success(f"✅ Pegawai {nama_pegawai} berhasil didaftarkan! Silakan refresh data di Sidebar.")
                # Opsional: auto clear cache
                st.cache_resource.clear()
            else:
                st.error("Mohon lengkapi Nama, ID, dan Foto.")