import streamlit as st
import pandas as pd
import face_recognition
import cv2
import numpy as np
import os
import hashlib
from datetime import datetime
from geopy.distance import geodesic
from streamlit_geolocation import streamlit_geolocation
from streamlit_webrtc import webrtc_streamer
import av
import time

# --- KONFIGURASI ---
PAGE_TITLE = "AuraScan Employee Portal"
PAGE_ICON = "🆔"
LOKASI_KANTOR = (-7.2575, 112.7521) # GANTI DENGAN KOORDINAT ANDA
RADIUS_KM = 0.5

DIR_DATA = "data"
DIR_WAJAH = os.path.join(DIR_DATA, "wajah")
FILE_LOG = os.path.join(DIR_DATA, "log_absensi.csv")
FILE_USERS = os.path.join(DIR_DATA, "users.csv")

os.makedirs(DIR_WAJAH, exist_ok=True)

# --- SETUP HALAMAN ---
st.set_page_config(page_title=PAGE_TITLE, page_icon=PAGE_ICON, layout="wide")

# --- CSS: PERBAIKAN TAMPILAN (KONTRAS TINGGI & CENTER) ---
st.markdown("""
    <style>
    /* 1. Latar Belakang & Font Global */
    .stApp {
        background-color: #f4f6f9 !important; /* Abu-abu sedikit lebih gelap agar elemen putih pop-up */
    }
    
    /* 2. Memaksa Container (Kotak Login) jadi Putih & Ada Bayangan */
    .stContainer, [data-testid="stExpander"] {
        background-color: #ffffff !important;
        border-radius: 15px !important;
        border: 1px solid #d1d5db !important;
        box-shadow: 0 10px 25px rgba(0,0,0,0.1) !important; /* Efek bayangan */
        padding: 20px !important;
    }

    /* 3. INPUT FIELD: Memperjelas Kotak Isian */
    input[type="text"], input[type="password"] {
        background-color: #ffffff !important;
        color: #000000 !important; /* Teks input hitam pekat */
        border: 1px solid #9ca3af !important; /* Border abu-abu tua */
        border-radius: 8px !important;
        padding: 10px !important;
    }
    
    /* 4. LABEL & TEKS: Masalah utama Anda (Kontras) */
    /* Memaksa semua label input dan teks paragraf jadi HITAM */
    label, p, .stMarkdown, [data-testid="stWidgetLabel"] {
        color: #111827 !important; /* Hitam hampir pekat */
        font-weight: 600 !important; /* Sedikit tebal agar terbaca */
        font-size: 14px !important;
    }
    
    /* Judul Besar */
    h1, h2, h3 {
        color: #111827 !important;
    }

    /* Tabs */
    button[data-baseweb="tab"] {
        color: #4b5563 !important; /* Warna tab tidak aktif */
        font-weight: bold;
    }
    button[data-baseweb="tab"][aria-selected="true"] {
        color: #000000 !important; /* Warna tab aktif hitam */
        background-color: white !important;
        border-bottom: 3px solid #ff4b4b !important;
    }

    /* Hilangkan Footer */
    #MainMenu {visibility: hidden;}
    footer {visibility: hidden;}
    </style>
    """, unsafe_allow_html=True)

# --- FUNGSI HELPER DATABASE USER ---
def init_user_db():
    if not os.path.exists(FILE_USERS):
        df = pd.DataFrame(columns=["nip", "nama", "password", "joined_at"])
        df.to_csv(FILE_USERS, index=False)

def hash_password(password):
    return hashlib.sha256(str.encode(password)).hexdigest()

def register_user(nip, nama, password, foto_buffer):
    init_user_db()
    df = pd.read_csv(FILE_USERS)
    if str(nip) in df['nip'].astype(str).values:
        return False, "NIP sudah terdaftar!"
    
    fname = f"{nama.replace(' ','-')}_{nip}.jpg"
    fpath = os.path.join(DIR_WAJAH, fname)
    with open(fpath, "wb") as f:
        f.write(foto_buffer.getbuffer())
        
    try:
        saved_img = face_recognition.load_image_file(fpath)
        if len(face_recognition.face_encodings(saved_img)) == 0:
            os.remove(fpath)
            return False, "Wajah tidak terdeteksi. Foto ulang tanpa masker."
    except:
        return False, "Gagal memproses gambar."

    new_user = pd.DataFrame([{
        "nip": str(nip),
        "nama": nama,
        "password": hash_password(password),
        "joined_at": datetime.now().strftime("%Y-%m-%d")
    }])
    df = pd.concat([df, new_user], ignore_index=True)
    df.to_csv(FILE_USERS, index=False)
    return True, "Registrasi Berhasil! Silakan Login."

def login_user(nip, password):
    init_user_db()
    df = pd.read_csv(FILE_USERS)
    user = df[df['nip'].astype(str) == str(nip)]
    if not user.empty:
        stored_pwd = user.iloc[0]['password']
        if stored_pwd == hash_password(password):
            return True, user.iloc[0]['nama']
    return False, None

# --- FUNGSI ABSENSI ---
@st.cache_resource
def load_known_faces():
    encodings, names = [], []
    if not os.path.exists(DIR_WAJAH): return [], []
    files = [f for f in os.listdir(DIR_WAJAH) if f.endswith(('.jpg','.jpeg','.png'))]
    for filename in files:
        path = os.path.join(DIR_WAJAH, filename)
        try:
            img = face_recognition.load_image_file(path)
            encs = face_recognition.face_encodings(img)
            if encs:
                encodings.append(encs[0])
                names.append(os.path.splitext(filename)[0].split('_')[0].replace('-', ' ').title())
        except: pass
    return encodings, names

def catat_log(nama, nip, status, lokasi):
    if not os.path.exists(FILE_LOG):
        pd.DataFrame(columns=["Tanggal","Waktu","NIP","Nama","Status","Lat","Lon"]).to_csv(FILE_LOG, index=False)
    df = pd.read_csv(FILE_LOG)
    now = datetime.now()
    hari = now.strftime("%Y-%m-%d")
    if not ((df['NIP'].astype(str) == str(nip)) & (df['Tanggal'] == hari)).any():
        new_row = pd.DataFrame([{
            "Tanggal": hari, "Waktu": now.strftime("%H:%M:%S"), "NIP": nip,
            "Nama": nama, "Status": status, "Lat": lokasi[0], "Lon": lokasi[1]
        }])
        df = pd.concat([df, new_row], ignore_index=True)
        df.to_csv(FILE_LOG, index=False)
        return True, "Absensi Berhasil!"
    return False, "Anda sudah absen hari ini."

# --- PROCESSOR VIDEO ---
class VideoProcessor:
    def __init__(self):
        self.known_encodings, self.known_names = load_known_faces()
        self.found_name, self.frame_count = None, 0
    def recv(self, frame):
        self.frame_count += 1
        if self.frame_count % 5 != 0: return av.VideoFrame.from_ndarray(frame.to_ndarray(format="bgr24"), format="bgr24")
        img = frame.to_ndarray(format="bgr24")
        small = cv2.resize(img, (0, 0), fx=0.25, fy=0.25)
        rgb = np.ascontiguousarray(small[:, :, ::-1])
        locs = face_recognition.face_locations(rgb)
        encs = face_recognition.face_encodings(rgb, locs)
        self.found_name = None
        for enc, loc in zip(encs, locs):
            matches = face_recognition.compare_faces(self.known_encodings, enc, tolerance=0.5)
            name = "Unknown"
            if True in matches:
                name = self.known_names[matches.index(True)]
                self.found_name = name
            top, right, bottom, left = [c * 4 for c in loc]
            color = (0, 255, 0) if name != "Unknown" else (0, 0, 255)
            cv2.rectangle(img, (left, top), (right, bottom), color, 2)
            cv2.putText(img, name, (left, bottom+20), cv2.FONT_HERSHEY_PLAIN, 1.5, color, 2)
        return av.VideoFrame.from_ndarray(img, format="bgr24")

# --- UI HALAMAN UTAMA ---
if 'user' not in st.session_state: st.session_state['user'] = None

# --- BAGIAN UI UTAMA ---
def main():
    # --- SCENARIO 1: SUDAH LOGIN (DASHBOARD) ---
    if st.session_state['user']:
        # ... (KODE BAGIAN INI TETAP SAMA SEPERTI SEBELUMNYA) ...
        user_data = st.session_state['user']
        with st.sidebar:
            st.title(f"Halo, {user_data['nama']}")
            st.info(f"NIP: {user_data['nip']}")
            if st.button("🚪 Logout", use_container_width=True):
                st.session_state['user'] = None
                st.rerun()
            st.divider()
            st.map(pd.DataFrame({'lat': [LOKASI_KANTOR[0]], 'lon': [LOKASI_KANTOR[1]]}), zoom=14)

        tab1, tab2 = st.tabs(["📸 Absensi", "📅 Riwayat"])
        with tab1:
            st.subheader("Kamera Absensi")
            col_loc, col_cam = st.columns([1, 2])
            with col_loc:
                with st.container(border=True):
                    loc = streamlit_geolocation()
                    valid_loc = False
                    user_coords = None
                    if loc and loc['latitude']:
                        user_coords = (loc['latitude'], loc['longitude'])
                        dist = geodesic(user_coords, LOKASI_KANTOR).kilometers
                        if dist <= RADIUS_KM:
                            st.success(f"Lokasi Valid ({dist:.2f} km)")
                            valid_loc = True
                        else: st.error(f"Jauh ({dist:.2f} km)")
                    else: st.info("Nyalakan GPS")
            with col_cam:
                if valid_loc:
                    ctx = webrtc_streamer(key="absen", video_processor_factory=VideoProcessor, 
                                          rtc_configuration={"iceServers": [{"urls": ["stun:stun.l.google.com:19302"]}]})
                    if ctx.video_processor and ctx.video_processor.found_name:
                        st.success(f"Wajah: {ctx.video_processor.found_name}")
                        if st.button("✅ KONFIRMASI HADIR"):
                            ok, msg = catat_log(ctx.video_processor.found_name, user_data['nip'], "Hadir", user_coords)
                            if ok: st.balloons(); st.success(msg)
                            else: st.warning(msg)
                else: st.warning("Buka kunci lokasi dahulu.")
        with tab2:
            st.subheader("Riwayat Anda")
            if os.path.exists(FILE_LOG):
                df = pd.read_csv(FILE_LOG)
                st.dataframe(df[df['NIP'].astype(str) == str(user_data['nip'])], use_container_width=True)
            else: st.info("Kosong.")

    # --- SCENARIO 2: BELUM LOGIN (LOGIN PAGE) ---
    else:
        st.markdown("<br>", unsafe_allow_html=True) 
        st.markdown("<h1 style='text-align: center;'>🆔 AuraScan Employee Portal</h1>", unsafe_allow_html=True)
        st.markdown("<p style='text-align: center;'>Silakan Login untuk absensi, atau Daftar jika pegawai baru.</p>", unsafe_allow_html=True)
        st.markdown("<br>", unsafe_allow_html=True)

        col_kiri, col_tengah, col_kanan = st.columns([1, 1.2, 1])

        with col_tengah:
            tab_login, tab_register = st.tabs(["🔐 Login Pegawai", "📝 Daftar Baru"])

            with tab_login:
                with st.container(): 
                    st.write("") 
                    nip_login = st.text_input("Masukkan NIP", key="l_nip", placeholder="Contoh: 12345")
                    pass_login = st.text_input("Kata Sandi", type="password", key="l_pass", placeholder="******")
                    
                    st.write("") 
                    if st.button("Masuk Sistem", type="primary", use_container_width=True):
                        if nip_login and pass_login:
                            success, nama = login_user(nip_login, pass_login)
                            if success:
                                st.session_state['user'] = {'nip': nip_login, 'nama': nama}
                                st.rerun()
                            else:
                                st.error("NIP atau Kata Sandi salah!")

            # --- PERBAIKAN DI BLOK INI ---
            with tab_register:
                with st.container():
                    st.info("⚠️ Wajib foto wajah tanpa masker.")

                    # 1. PERUBAHAN PENTING: Kamera DITARUH DI LUAR form
                    # Agar saat foto diambil, nilainya langsung tersimpan di memori
                    r_foto = st.camera_input("Ambil Foto Wajah")

                    # 2. Input teks tetap DITARUH DI DALAM form
                    # Agar tidak refresh saat mengetik
                    with st.form("register_form", clear_on_submit=False):
                        r_nama = st.text_input("Nama Lengkap")
                        r_nip = st.text_input("NIP (Untuk Login)")
                        r_pass = st.text_input("Buat Kata Sandi", type="password")

                        # Tombol Submit khusus untuk form
                        submitted = st.form_submit_button("Daftar Akun", type="primary", use_container_width=True)

                    # 3. Logika pengecekan SETELAH tombol submit ditekan
                    if submitted:
                        # Sekarang kita cek r_foto (yang di luar) dan inputan lain (yang di dalam)
                        if not r_nama:
                            st.warning("Nama Lengkap belum diisi.")
                        elif not r_nip:
                            st.warning("NIP belum diisi.")
                        elif not r_pass:
                            st.warning("Kata Sandi belum diisi.")
                        elif not r_foto: # Pengecekan ini sekarang akan berhasil!
                            st.warning("Foto Wajah belum diambil (Pastikan sudah klik 'Take Photo').")
                        else:
                            # Jika semua data lengkap
                            with st.spinner("Mendaftarkan..."):
                                ok, msg = register_user(r_nip, r_nama, r_pass, r_foto)
                                if ok:
                                    st.success(msg)
                                    time.sleep(1)
                                    st.cache_resource.clear()
                                    st.rerun()
                                else:
                                    st.error(msg)

if __name__ == "__main__":
    main()
