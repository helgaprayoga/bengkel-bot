"""Uji endpoint web BengkelBot dengan Flask test client.

Jalankan dengan: pytest -q
"""

import os
import sys

import pytest

# Tambahkan root project agar import app dan chatbot bekerja dari folder tests.
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

from app import create_app  # noqa: E402
from chatbot.database import ChatHistory  # noqa: E402


@pytest.fixture()
def app(tmp_path):
    """Buat aplikasi uji dengan database sementara agar tidak mengotori data asli."""
    return create_app({
        "TESTING": True,
        "SECRET_KEY": "kunci-uji",
        "DATABASE": str(tmp_path / "test_chat.db"),
        "ADMIN_KEY": "",
        "THRESHOLD": 0.45,
    })


@pytest.fixture()
def client(app):
    """Flask test client untuk memanggil route tanpa menjalankan server."""
    return app.test_client()


# ---------- halaman HTML ----------

def test_halaman_chat_tampil(client):
    # Halaman utama harus bisa dibuka dan memuat form chat.
    respons = client.get("/")
    assert respons.status_code == 200
    assert b"BengkelBot" in respons.data
    assert b"chat-form" in respons.data


def test_halaman_admin_tampil(client):
    # Dashboard admin harus menampilkan kartu ringkasan dan tabel intent.
    respons = client.get("/admin")
    assert respons.status_code == 200
    assert b"Dasbor Admin" in respons.data
    assert b"Jumlah pertanyaan" in respons.data


def test_halaman_tidak_ditemukan(client):
    # Route yang tidak ada harus memakai halaman error, bukan pesan bawaan Flask.
    respons = client.get("/halaman-tidak-ada")
    assert respons.status_code == 404
    assert b"Halaman tidak ditemukan" in respons.data


def test_health(client):
    # Endpoint health dipakai untuk cek cepat bahwa aplikasi hidup.
    respons = client.get("/health")
    assert respons.status_code == 200
    assert respons.get_json() == {"status": "ok"}


# ---------- API chat ----------

def test_api_chat_valid(client):
    # Pesan yang jelas harus dikenali sebagai intent rem.
    respons = client.post("/api/chat", json={"message": "rem blong"})
    assert respons.status_code == 200

    data = respons.get_json()
    assert data["intent"] == "rem"
    assert data["reply"]
    assert 0.0 <= data["score"] <= 1.0


def test_api_chat_body_bukan_objek(client):
    # Body JSON berupa list tetap harus ditolak karena bukan objek.
    respons = client.post("/api/chat", json=["rem blong"])
    assert respons.status_code == 400


def test_api_chat_json_tidak_valid(client):
    # Body yang bukan JSON valid harus menghasilkan galat 400.
    respons = client.post("/api/chat", data="bukan json",
                          content_type="application/json")
    assert respons.status_code == 400


def test_api_chat_pesan_kosong(client):
    # Pesan kosong tidak boleh masuk ke mesin chatbot.
    respons = client.post("/api/chat", json={"message": "   "})
    assert respons.status_code == 400
    assert "kosong" in respons.get_json()["error"]


def test_api_chat_pesan_terlalu_panjang(client):
    # Pesan melebihi 500 karakter harus ditolak sebelum diproses.
    respons = client.post("/api/chat", json={"message": "a" * 501})
    assert respons.status_code == 400
    assert "500" in respons.get_json()["error"]


def test_api_chat_fallback(client):
    # Pertanyaan di luar tema harus memakai fallback dengan intent None.
    respons = client.post("/api/chat", json={"message": "siapa presiden indonesia"})
    assert respons.status_code == 200

    data = respons.get_json()
    assert data["intent"] is None
    assert data["reply"]


# ---------- riwayat ----------

def test_api_history_menyimpan_user_dan_bot(client):
    # Satu percakapan menghasilkan dua baris: pesan user dan jawaban bot.
    client.post("/api/chat", json={"message": "rem blong"})

    respons = client.get("/api/history")
    assert respons.status_code == 200

    data = respons.get_json()
    assert len(data) == 2
    assert data[0]["sender"] == "user"
    assert data[0]["text"] == "rem blong"
    assert data[1]["sender"] == "bot"
    assert data[1]["intent"] == "rem"


def test_api_history_hapus_hanya_menyembunyikan(client):
    # Hapus riwayat tidak boleh menghilangkan angka statistik admin.
    client.post("/api/chat", json={"message": "rem blong"})
    hapus = client.delete("/api/history")
    assert hapus.status_code == 200

    riwayat = client.get("/api/history").get_json()
    assert riwayat == []

    statistik = client.get("/api/stats").get_json()
    assert statistik["total"] == 1


# ---------- statistik ----------

def test_api_stats_menghitung_intent(client):
    # Statistik harus menghitung pertanyaan user dan distribusi intent.
    client.post("/api/chat", json={"message": "rem blong"})

    respons = client.get("/api/stats")
    assert respons.status_code == 200

    data = respons.get_json()
    assert data["total"] == 1
    assert data["dikenali"] == 1
    assert data["persen_dikenali"] == 100.0
    assert data["sesi"] == 1
    assert data["per_intent"][0]["intent"] == "rem"


def test_api_stats_menghitung_tidak_dikenali(client):
    # Pertanyaan di luar tema masuk ke hitungan tidak dikenali.
    client.post("/api/chat", json={"message": "siapa presiden indonesia"})

    data = client.get("/api/stats").get_json()
    assert data["total"] == 1
    assert data["dikenali"] == 0
    assert data["tidak_dikenali_total"] == 1
    assert len(data["tidak_dikenali"]) == 1
    assert data["tidak_dikenali"][0]["text"] == "siapa presiden indonesia"


# ---------- proteksi admin ----------

def test_admin_key_melindungi_halaman_dan_api(tmp_path):
    # Saat ADMIN_KEY diisi, halaman dan API admin wajib memakai ?key=.
    aplikasi = create_app({
        "TESTING": True,
        "SECRET_KEY": "kunci-uji",
        "DATABASE": str(tmp_path / "admin_test.db"),
        "ADMIN_KEY": "rahasia",
    })
    klien = aplikasi.test_client()

    assert klien.get("/admin").status_code == 403
    assert klien.get("/admin?key=rahasia").status_code == 200
    assert klien.get("/api/stats").status_code == 403
    assert klien.get("/api/stats?key=rahasia").status_code == 200


# ---------- database langsung ----------

def test_database_riwayat_dan_statistik(tmp_path):
    # Uji lapisan database tanpa Flask agar perilaku penyimpanan terisolasi.
    riwayat = ChatHistory(str(tmp_path / "langsung.db"))
    riwayat.simpan_percakapan(
        "sesi-1",
        "rem blong",
        {"reply": "Segera ke bengkel.", "intent": "rem", "score": 0.95},
    )

    data = riwayat.riwayat("sesi-1")
    assert len(data) == 2
    assert data[0]["sender"] == "user"
    assert data[1]["sender"] == "bot"

    statistik = riwayat.statistik()
    assert statistik["total"] == 1
    assert statistik["dikenali"] == 1
    assert statistik["sesi"] == 1

    # Setelah disembunyikan, riwayat user kosong tetapi statistik tetap.
    riwayat.hapus("sesi-1")
    assert riwayat.riwayat("sesi-1") == []
    assert riwayat.statistik()["total"] == 1
