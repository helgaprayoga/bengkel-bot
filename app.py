"""Aplikasi web BengkelBot (Flask).

Dua tampilan:
    /       halaman chat (satu-satunya halaman untuk pengguna)
    /admin  dasbor admin: ringkasan angka, pertanyaan per intent,
            dan pertanyaan yang tidak dikenali bot

Menjalankan di komputer sendiri:
    python app.py

Variabel lingkungan (opsional): SECRET_KEY, ADMIN_KEY, THRESHOLD, DATABASE,
HOST, PORT, FLASK_DEBUG (1 = mode debug, hanya untuk komputer sendiri).
"""

import hmac
import os
import uuid

from flask import Flask, jsonify, render_template, request, session

from chatbot.database import ChatHistory
from chatbot.engine import AMBANG_BAWAAN, ChatbotEngine, load_theme

# Lokasi root project dipakai untuk mencari tema dan database bawaan.
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
MAKS_KARAKTER = 500  # Batas panjang satu pesan dari pengguna.


def create_app(config=None):
    """Bangun aplikasi Flask (application factory, memudahkan pengujian)."""
    app = Flask(__name__)

    # Konfigurasi bawaan; semuanya bisa ditimpa lewat environment atau config uji.
    app.config.update(
        # Ganti nilai ini lewat environment saat aplikasi dipasang di server.
        SECRET_KEY=os.environ.get("SECRET_KEY", "ganti-kunci-ini-di-produksi"),
        # Ambang skor intent; di bawah nilai ini bot memakai fallback.
        THRESHOLD=float(os.environ.get("THRESHOLD", AMBANG_BAWAAN)),
        # Lokasi file SQLite untuk riwayat chat.
        DATABASE=os.environ.get("DATABASE",
                                os.path.join(BASE_DIR, "chat_history.db")),
        # Kosong = dasbor admin terbuka (cukup untuk komputer sendiri).
        ADMIN_KEY=os.environ.get("ADMIN_KEY", ""),
        # File tema berisi intent, pola, respons, sapaan, dan fallback.
        THEME_PATH=os.path.join(BASE_DIR, "themes", "bengkel.json"),
        # Cookie sesi tidak bisa dibaca JavaScript dan tidak dikirim lintas situs.
        SESSION_COOKIE_SAMESITE="Lax",
        SESSION_COOKIE_HTTPONLY=True,
        # Tolak body request yang terlalu besar sejak awal.
        MAX_CONTENT_LENGTH=64 * 1024,
    )
    if config:
        app.config.update(config)

    # JSON dibiarkan UTF-8 agar teks Indonesia tidak berubah menjadi escape.
    app.json.ensure_ascii = False

    # Muat tema, mesin chatbot, dan penyimpanan riwayat satu kali saat aplikasi dibuat.
    theme = load_theme(app.config["THEME_PATH"])
    bot = ChatbotEngine(theme, threshold=app.config["THRESHOLD"])
    history = ChatHistory(app.config["DATABASE"])

    # ---------- fungsi bantu ----------

    def get_session_id():
        """Beri setiap pengunjung ID acak yang disimpan di cookie bertanda tangan."""
        if "sid" not in session:
            session["sid"] = uuid.uuid4().hex
        return session["sid"]

    def admin_diizinkan():
        """Cek kunci admin dari ?key=... (dibandingkan dengan waktu konstan)."""
        kunci = app.config["ADMIN_KEY"]
        # Tanpa ADMIN_KEY, dasbor terbuka untuk pemakaian lokal.
        if not kunci:
            return True
        dikirim = request.args.get("key", "")
        # compare_digest mencegah kebocoran informasi lewat perbedaan waktu.
        return hmac.compare_digest(dikirim.encode("utf-8"), kunci.encode("utf-8"))

    def galat(pesan, kode=400):
        """Respons galat JSON yang seragam untuk API."""
        return jsonify({"error": pesan}), kode

    def halaman_galat(kode, judul, pesan):
        """Respons halaman HTML untuk kesalahan yang dilihat pengguna."""
        return render_template("error.html", kode=kode, judul=judul,
                               pesan=pesan), kode

    # ---------- halaman HTML ----------

    @app.get("/")
    def index():
        """Halaman chat."""
        return render_template(
            "chat.html",
            bot_name=theme["bot_name"],
            greeting=bot.isi_teks(theme.get("greeting", "Halo!")),
            disclaimer=theme.get("disclaimer", ""),
            suggestions=theme.get("suggestions", []))

    @app.get("/admin")
    def admin():
        """Dasbor admin: apa yang sudah dan belum dipahami bot."""
        if not admin_diizinkan():
            return halaman_galat(403, "Akses ditolak",
                                 "Kunci admin salah. Buka /admin?key=KUNCI_ANDA")
        # Satu payload statistik dipakai untuk kartu ringkasan, tabel, dan daftar unknown.
        ringkasan = history.statistik()
        return render_template(
            "admin.html",
            theme=theme,
            bot_name=theme["bot_name"],
            summary=ringkasan,
            stats=ringkasan["per_intent"],
            unknown=ringkasan["tidak_dikenali"],
            ambang=app.config["THRESHOLD"])

    # ---------- REST API (JSON) ----------

    @app.post("/api/chat")
    def api_chat():
        """Terima pesan, kembalikan jawaban bot, dan simpan percakapan."""
        data = request.get_json(silent=True)
        # Tolak body yang bukan objek JSON agar akses data di bawah aman.
        if not isinstance(data, dict):
            return galat("Body harus berformat JSON")
        pesan = str(data.get("message", "")).strip()
        # Pesan kosong tidak perlu diproses oleh mesin chatbot.
        if not pesan:
            return galat("Pesan tidak boleh kosong")
        # Batasi panjang pesan agar request tetap wajar.
        if len(pesan) > MAKS_KARAKTER:
            return galat(f"Pesan maksimal {MAKS_KARAKTER} karakter")

        # Proses pesan, lalu simpan pasangan pertanyaan dan jawaban ke SQLite.
        hasil = bot.reply(pesan)
        history.simpan_percakapan(get_session_id(), pesan, hasil)
        return jsonify(hasil)

    @app.get("/api/history")
    def api_history():
        """Riwayat chat milik sesi ini."""
        return jsonify(history.riwayat(get_session_id()))

    @app.delete("/api/history")
    def api_history_hapus():
        """Hapus riwayat sesi ini dari tampilan (statistik admin tetap)."""
        history.hapus(get_session_id())
        return jsonify({"status": "ok"})

    @app.get("/api/stats")
    def api_stats():
        """Statistik untuk dasbor admin dalam bentuk JSON."""
        if not admin_diizinkan():
            return galat("Kunci admin salah", 403)
        return jsonify(history.statistik())

    @app.get("/health")
    def health():
        """Endpoint kecil untuk memastikan aplikasi hidup."""
        return jsonify({"status": "ok"})

    # ---------- penanganan galat ----------

    @app.errorhandler(404)
    def tidak_ditemukan(_):
        """Tampilkan halaman 404 yang ramah, bukan pesan bawaan Flask."""
        return halaman_galat(404, "Halaman tidak ditemukan",
                             "Alamat yang kamu buka tidak ada.")

    @app.errorhandler(413)
    def terlalu_besar(_):
        """Kembalikan JSON saat body request melewati MAX_CONTENT_LENGTH."""
        return galat("Permintaan terlalu besar", 413)

    @app.errorhandler(500)
    def kesalahan_server(_):
        """Bedakan respons API dan halaman saat terjadi kesalahan tak terduga."""
        if request.path.startswith("/api/"):
            return galat("Terjadi kesalahan pada server", 500)
        return halaman_galat(500, "Kesalahan server",
                             "Terjadi kesalahan. Coba muat ulang halaman.")

    return app


if __name__ == "__main__":
    aplikasi = create_app()
    # debug=True hanya untuk belajar di komputer sendiri, jangan di server.
    aplikasi.run(
        host=os.environ.get("HOST", "127.0.0.1"),
        port=int(os.environ.get("PORT", "5000")),
        debug=os.environ.get("FLASK_DEBUG") == "1")
