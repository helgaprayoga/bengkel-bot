# BengkelBot: Chatbot untuk Diagnosis Awal Kerusakan Sepeda Motor

Chatbot berbasis aturan (tanpa LLM) untuk diagnosis awal kerusakan sepeda motor.
Project ini punya dua antarmuka:

- **Web chat** satu halaman untuk pengguna.
- **Dashboard admin** untuk melihat statistik, intent terbanyak, dan pertanyaan
  yang belum dikenali bot.
- **CLI** tetap tersedia untuk pengujian cepat di terminal.

## Menjalankan web

```powershell
pip install -r requirements.txt
python app.py
```

Buka:

- Chat: <http://127.0.0.1:5000/>
- Admin: <http://127.0.0.1:5000/admin>

Jika `ADMIN_KEY` diisi, dashboard harus dibuka dengan query key:

```text
http://127.0.0.1:5000/admin?key=KUNCI_ANDA
```

## Menjalankan CLI

```powershell
python cli.py              # chat biasa
python cli.py --debug      # lihat 3 kandidat intent dan skornya
python evaluate.py         # akurasi pada 40 kalimat uji
python evaluate.py --sweep # bandingkan beberapa ambang
pytest -q                  # seluruh uji otomatis
```

## Variabel lingkungan

| Variabel | Bawaan | Fungsi |
|---|---|---|
| `SECRET_KEY` | kunci contoh | Kunci cookie sesi; wajib diganti di server. |
| `ADMIN_KEY` | kosong | Kunci dashboard admin; kosong berarti terbuka untuk lokal. |
| `THRESHOLD` | `0.45` | Ambang skor minimum agar intent dianggap cocok. |
| `DATABASE` | `chat_history.db` | Lokasi file SQLite riwayat chat. |
| `HOST` | `127.0.0.1` | Alamat bind server Flask. |
| `PORT` | `5000` | Port server Flask. |
| `FLASK_DEBUG` | kosong | Isi `1` untuk mode debug di komputer sendiri. |

Contoh di PowerShell:

```powershell
$env:SECRET_KEY = "kunci-acak-yang-panjang"
$env:ADMIN_KEY = "admin-rahasia"
$env:THRESHOLD = "0.45"
python app.py
```

## Struktur

```text
app.py                     aplikasi Flask (chat, API, admin)
cli.py                     antarmuka terminal
evaluate.py                ukur akurasi dari evaluasi/bengkel.csv
chatbot/engine.py          praproses, skor kemiripan, klasifikasi, jawaban
chatbot/database.py        riwayat chat dan statistik (SQLite)
templates/                 halaman HTML (chat, admin, error)
static/css/style.css       tampilan chat dan dashboard
static/js/chat.js          interaksi chat di browser
themes/bengkel.json        basis pengetahuan: 16 intent, pola, respons, fallback
evaluasi/bengkel.csv       40 kalimat uji berlabel
tests/test_engine.py       uji mesin chatbot
tests/test_web.py          uji endpoint web dan dashboard
```

## Cara kerja singkat

```text
pesan -> preprocess() -> similarity() ke setiap pola -> intent terbaik
      -> jawaban atau fallback -> disimpan ke SQLite
```

Skor = 0,4 x Jaccard + 0,3 x Fuzzy + 0,3 x Kedalaman. Kedalaman adalah
max(cakupan pola, presisi pesan), dan pencocokan kata tahan salah ketik. Di bawah
ambang 0,45 bot memakai fallback. Halaman admin membaca database yang sama, sehingga
pertanyaan yang tidak dikenali bisa dijadikan pola baru di `themes/bengkel.json`.

## Catatan data

- `chat_history.db` dibuat otomatis saat aplikasi pertama kali berjalan.
- Tombol **Hapus riwayat** hanya menyembunyikan riwayat dari pengguna.
  Statistik admin tetap menyimpan data tersebut.
- Untuk mereset seluruh data lokal, hentikan aplikasi lalu hapus
  `chat_history.db`.

Hasil hanya perkiraan awal dan bukan pengganti pemeriksaan montir.
