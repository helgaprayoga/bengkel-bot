"""Penyimpanan riwayat chat dan statistik untuk dasbor admin (SQLite).

Semua nilai dari pengguna dikirim lewat parameter "?" sehingga aman dari
SQL injection. Modul ini tidak mengimpor Flask.
"""

import os
import sqlite3
from contextlib import closing

# Skema dasar: satu baris untuk setiap pesan user atau bot.
SKEMA = """
CREATE TABLE IF NOT EXISTS messages (
    id            INTEGER PRIMARY KEY AUTOINCREMENT,
    session_id    TEXT    NOT NULL,           -- ID pengunjung dari cookie
    sender        TEXT    NOT NULL,           -- 'user' atau 'bot'
    text          TEXT    NOT NULL,           -- isi pesan
    intent        TEXT,                       -- intent dikenali (NULL = tidak dikenali)
    score         REAL,                       -- skor tertinggi
    hidden        INTEGER NOT NULL DEFAULT 0, -- 1 = disembunyikan dari tampilan pengguna
    created_at    TIMESTAMP DEFAULT (datetime('now', 'localtime'))
);
"""

# Index mempercepat query riwayat per sesi dan agregasi statistik per intent.
INDEKS = """
CREATE INDEX IF NOT EXISTS idx_messages_session ON messages(session_id);
CREATE INDEX IF NOT EXISTS idx_messages_intent ON messages(intent);
"""


class ChatHistory:
    """Akses tabel riwayat chat."""

    def __init__(self, path):
        """Buat database dan tabel bila belum ada, lalu siapkan index."""
        self.path = path
        # Pastikan folder database ada agar SQLite tidak gagal membuka file.
        if path != ":memory:":
            folder = os.path.dirname(os.path.abspath(path))
            if folder:
                os.makedirs(folder, exist_ok=True)
        with closing(self._koneksi()) as conn, conn:
            conn.executescript(SKEMA + INDEKS)

    def _koneksi(self):
        """Buka koneksi baru; baris hasil query bisa diakses lewat nama kolom."""
        conn = sqlite3.connect(self.path)
        conn.row_factory = sqlite3.Row
        return conn

    def simpan_percakapan(self, session_id, pesan, hasil):
        """Simpan satu pertanyaan pengguna dan jawaban bot sekaligus.

        `hasil` adalah dict dari ChatbotEngine.reply(). Keduanya disimpan
        dalam satu transaksi (with conn: commit bila berhasil, rollback bila galat).
        """
        # Satu transaksi menjaga agar pesan user dan bot tidak pernah terpisah.
        with closing(self._koneksi()) as conn, conn:
            sql = ("INSERT INTO messages (session_id, sender, text, intent, score) "
                   "VALUES (?, ?, ?, ?, ?)")
            conn.execute(sql, (session_id, "user", pesan,
                               hasil["intent"], hasil["score"]))
            conn.execute(sql, (session_id, "bot", hasil["reply"],
                               hasil["intent"], hasil["score"]))

    def riwayat(self, session_id, batas=100):
        """Ambil riwayat satu sesi (yang tidak disembunyikan), urut dari lama."""
        with closing(self._koneksi()) as conn:
            baris = conn.execute(
                "SELECT sender, text, intent, score FROM messages "
                "WHERE session_id = ? AND hidden = 0 ORDER BY id DESC LIMIT ?",
                (session_id, batas)).fetchall()
        # Query mengambil dari yang terbaru; balikkan agar tampil kronologis.
        return [dict(b) for b in reversed(baris)]

    def hapus(self, session_id):
        """Sembunyikan riwayat satu sesi dari pengguna.

        Barisnya tidak dihapus supaya statistik di dasbor admin tetap utuh.
        """
        with closing(self._koneksi()) as conn, conn:
            conn.execute("UPDATE messages SET hidden = 1 WHERE session_id = ?",
                         (session_id,))

    def statistik(self, batas_tidak_dikenali=50):
        """Hitung angka ringkasan untuk dasbor admin."""
        with closing(self._koneksi()) as conn:
            # Total pertanyaan dihitung dari pesan user saja.
            total = conn.execute(
                "SELECT COUNT(*) FROM messages WHERE sender = 'user'").fetchone()[0]
            # Pertanyaan dikenali adalah pesan user yang punya intent.
            dikenali = conn.execute(
                "SELECT COUNT(*) FROM messages "
                "WHERE sender = 'user' AND intent IS NOT NULL").fetchone()[0]
            # Jumlah sesi unik yang pernah mengirim pesan.
            sesi = conn.execute(
                "SELECT COUNT(DISTINCT session_id) FROM messages").fetchone()[0]
            # Distribusi pertanyaan per intent, termasuk kelompok tidak dikenali.
            per_intent = conn.execute(
                "SELECT COALESCE(intent, '(tidak dikenali)') AS intent, "
                "COUNT(*) AS jumlah FROM messages WHERE sender = 'user' "
                "GROUP BY intent ORDER BY jumlah DESC, intent").fetchall()
            # Hitung seluruh pertanyaan tak dikenali, bukan hanya yang ditampilkan.
            tidak_dikenali_total = conn.execute(
                "SELECT COUNT(*) FROM messages "
                "WHERE sender = 'user' AND intent IS NULL").fetchone()[0]
            # Ambil contoh pertanyaan tak dikenali terbaru untuk bahan perbaikan pola.
            tidak_dikenali = conn.execute(
                "SELECT text, score, created_at FROM messages "
                "WHERE sender = 'user' AND intent IS NULL "
                "ORDER BY id DESC LIMIT ?", (batas_tidak_dikenali,)).fetchall()

        # Panjang batang grafik dibuat relatif terhadap intent terbanyak (0-100).
        terbanyak = max((b["jumlah"] for b in per_intent), default=1)
        return {
            "total": total,
            "dikenali": dikenali,
            "persen_dikenali": round(100 * dikenali / total, 1) if total else 0,
            "sesi": sesi,
            "tidak_dikenali_total": tidak_dikenali_total,
            "per_intent": [
                {
                    "intent": b["intent"],
                    "jumlah": b["jumlah"],
                    # Proporsi terhadap seluruh pertanyaan user.
                    "persen_total": round(100 * b["jumlah"] / total, 1) if total else 0,
                    # Proporsi terhadap intent terbanyak untuk lebar batang.
                    "persen_bar": round(100 * b["jumlah"] / terbanyak),
                }
                for b in per_intent
            ],
            "tidak_dikenali": [dict(b) for b in tidak_dikenali],
        }
