import streamlit as st
from datetime import datetime, timedelta
from math import ceil
from dateutil.parser import parse
from notion_client import Client
import csv
import pandas as pd

# Notion credentials
notion_token = st.secrets["NOTION_API_TOKEN"]
database_id = st.secrets["NOTION_DATABASE_ID"]

notion = Client(auth=notion_token)

# Libur nasional
libur_nasional = [parse(t).date() for t in [
    "2025-01-01", "2025-01-27", "2025-01-29", "2025-03-29", "2025-03-31",
    "2025-04-01", "2025-04-18", "2025-04-20", "2025-05-01", "2025-05-12",
    "2025-05-29", "2025-06-01", "2025-06-06", "2025-06-27", "2025-08-17",
    "2025-09-05", "2025-12-25", "2025-01-28", "2025-03-28", "2025-04-02",
    "2025-04-03", "2025-04-04", "2025-04-07", "2025-05-13", "2025-05-30",
    "2025-06-09", "2025-12-26"
]]

# Template dan masalah
TEMPLATE = {
    "unpaid_vat": [
        {"week": 1, "actions": [
            "Analisis hasil pemeriksaan DJP",
            "Kumpulkan faktur pajak masukan & keluaran",
            "Hitung ulang total PPN terutang dan bandingkan dengan SPT yang sudah dilaporkan"
        ]},
        {"week": 2, "actions": [
            "Susun laporan klarifikasi ke DJP",
            "Ajukan permohonan pembayaran bertahap (jika diperlukan)"
        ]},
        {"week": 3, "actions": [
            "Lakukan pelunasan sesuai ketetapan",
            "Update sistem internal dan sampaikan dokumentasi ke manajemen"
        ]},
    ],

    "late_annual_filing": [
        {"week": 1, "actions": [
            "Kumpulkan laporan keuangan audit dan data SPT terkait",
            "Identifikasi penyebab keterlambatan"
        ]},
        {"week": 2, "actions": [
            "Susun SPT Tahunan Badan (form 1771)",
            "Lapor SPT melalui DJP Online",
            "Bayar denda keterlambatan"
        ]},
    ],

    "amend_pph21": [
        {"week": 1, "actions": [
            "Kumpulkan data pembayaran karyawan selama masa pajak terkait",
            "Identifikasi kesalahan pelaporan PPh 21",
            "Susun pembetulan SPT Masa PPh 21"
        ]},
        {"week": 2, "actions": [
            "Lapor SPT Pembetulan melalui e-Filing",
            "Bayar kekurangan jika ada",
            "Simpan dokumentasi pembetulan untuk audit selanjutnya"
        ]},
    ],

    "sp2dk_response": [
        {"week": 1, "actions": [
            "Baca dan pahami isi SP2DK",
            "Konsultasi dengan manajemen terkait poin yang dipermasalahkan",
            "Kumpulkan dokumen pendukung"
        ]},
        {"week": 2, "actions": [
            "Susun surat tanggapan dan lampiran",
            "Kirim ke KPP sebelum batas waktu",
            "Arsipkan seluruh komunikasi"
        ]}
    ],

    "tax_objection": [
        {"week": 1, "actions": [
            "Review SKPKB atau SKPKBT yang diterima",
            "Diskusi dengan manajemen terkait potensi keberatan",
            "Susun argumentasi & bukti pendukung"
        ]},
        {"week": 2, "actions": [
            "Ajukan permohonan keberatan resmi",
            "Pantau respon DJP dan siapkan pernyataan tambahan jika diminta"
        ]}
    ]
}

problem_options = {
    "PPN belum dibayar (Unpaid VAT)": "unpaid_vat",
    "SPT Tahunan belum dilaporkan": "late_annual_filing",
    "Pembetulan PPh 21": "amend_pph21",
    "Tanggapan SP2DK (Surat Permintaan Penjelasan)": "sp2dk_response",
    "Keberatan atas SKPKB/SKPKBT": "tax_objection",
    "Keterlambatan pelaporan PPh 23/26": "late_withholding_tax",
    "Permohonan pengangsuran SKP (Angsuran Pajak)": "installment_request",
    "Koreksi biaya tidak wajar (audit temuan biaya)": "expense_correction",
    "Ketidaksesuaian e-Faktur dan SPT Masa": "efaktur_discrepancy",
    "Restitusi PPN ditolak atau dikurangi": "vat_restitution_issue",
    "Tidak lapor laporan pemotongan PPh Final (4 ayat 2)": "final_tax_nonreporting"
}

# Utility
def get_workdays(start_date, end_date, holidays):
    days = []
    current = start_date
    while current <= end_date:
        if current.weekday() < 5 and current.date() not in holidays:
            days.append(current)
        current += timedelta(days=1)
    return days

def generate_timeline(company, problems, start, end):
    workdays = get_workdays(start, end, libur_nasional)
    if not workdays:
        return "⛔ Tidak ada hari kerja tersedia.", []

    all_actions = []
    for p in problems:
        for step in TEMPLATE.get(p, []):
            all_actions.extend(step["actions"])

    chunk = ceil(len(all_actions) / len(workdays))
    output = f"📌 Timeline untuk {company}\n🗓️ {start.date()} - {end.date()}\n"
    csv_rows = []
    for i, (day, acts) in enumerate(zip(workdays, [all_actions[i:i+chunk] for i in range(0, len(all_actions), chunk)])):
        output += f"\n🟢 {day.date()}:\n"
        for act in acts:
            output += f"- {act}\n"
            csv_rows.append([day.date(), company, act])
    return output, csv_rows

def push_to_notion(token, db_id, rows, start_date):
    notion = Client(auth=token)
    for row in rows:
        tanggal, nama, aksi = row
        notion.pages.create(
            parent={"database_id": db_id},
            properties={
                "Nama Perusahaan": {"title": [{"text": {"content": nama}}]},
                "Tanggal Mulai": {"date": {"start": start_date.strftime("%Y-%m-%d")}},
                "Deadline": {"date": {"start": str(tanggal)}},
                "Tindakan": {"rich_text": [{"text": {"content": aksi}}]}
            }
        )

# === UI ===
st.title("📅 STA - Penjadwalan Tindakan")

nama = st.text_input("Nama Perusahaan")
selected_labels = st.multiselect("Masalah Pajak:", list(problem_options.keys()))
selected_codes = [problem_options[l] for l in selected_labels]

col1, col2 = st.columns(2)
with col1: mulai = st.date_input("Tanggal Mulai")
with col2: akhir = st.date_input("Deadline")

if st.button("Buat Timeline"):
    if not nama or not selected_codes or not mulai or not akhir:
        st.warning("❗ Lengkapi semua input.")
    else:
        text, rows = generate_timeline(nama, selected_codes, datetime.combine(mulai, datetime.min.time()), datetime.combine(akhir, datetime.min.time()))
        st.session_state["timeline_text"] = text
        st.session_state["timeline_rows"] = rows
        st.session_state["start"] = mulai
        st.session_state["timeline_ready"] = True
        st.session_state["already_sent"] = False

if st.session_state.get("timeline_ready"):
    st.text_area("📄 Timeline", st.session_state["timeline_text"], height=300)
    
    df = pd.DataFrame(st.session_state["timeline_rows"], columns=["Tanggal", "Perusahaan", "Aksi"])

    # CSV
    csv_file = "timeline_output.csv"
    df.to_csv(csv_file, index=False)
    with open(csv_file, "rb") as f:
        st.download_button("📥 Unduh CSV", f, file_name=csv_file, mime="text/csv")

    # Notion
    if not st.session_state.get("already_sent"):
        if st.button("🚀 Kirim ke Notion"):
            try:
                push_to_notion(notion_token, database_id, st.session_state["timeline_rows"], st.session_state["start"])
                st.success("✅ Sukses kirim ke Notion!")
                st.session_state["already_sent"] = True
            except Exception as e:
                st.error(f"❌ Gagal: {e}")
    
    st.markdown("🔗 [Lihat Notion](https://www.notion.so/1ff928154818805a94fdfe8fd6f4399f)")
