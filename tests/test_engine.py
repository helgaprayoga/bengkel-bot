"""Uji otomatis mesin BengkelBot. Jalankan dengan: pytest -v"""

import os
import sys

import pytest

# Supaya `import chatbot` bekerja saat pytest dijalankan dari folder mana pun.
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

from chatbot.engine import (ChatbotEngine, load_theme, preprocess,  # noqa: E402
                            similarity, validate_theme)
from evaluate import baca_data, evaluasi  # noqa: E402

TEMA = os.path.join(ROOT, "themes", "bengkel.json")
DATA_UJI = os.path.join(ROOT, "evaluasi", "bengkel.csv")


@pytest.fixture(scope="module")
def tema():
    # Tema dimuat sekali untuk seluruh modul agar pengujian cepat.
    return load_theme(TEMA)


@pytest.fixture(scope="module")
def bot(tema):
    # Mesin yang sama dipakai ulang oleh semua test intent.
    return ChatbotEngine(tema)


# ---------- praproses ----------

def test_praproses_huruf_kecil_dan_tanda_baca():
    assert preprocess("REM BLONG!!!") == ["rem", "blong"]


def test_praproses_normalisasi_kata_tidak_baku():
    # "gk" -> "tidak", "udh" -> "sudah"
    assert preprocess("gk udh") == ["tidak", "sudah"]


def test_praproses_buang_kata_henti():
    # "motor", "saya", "kak" termasuk kata henti
    assert preprocess("motor saya brebet kak") == ["brebet"]


# ---------- skor kemiripan ----------

def test_skor_kalimat_sama_persis_bernilai_satu():
    assert similarity(["rem", "blong"], ["rem", "blong"]) == 1.0


def test_skor_kalimat_beda_total_rendah():
    assert similarity(["rem", "blong"], ["tekanan", "ban"]) < 0.3


def test_skor_kosong_bernilai_nol():
    assert similarity([], ["rem"]) == 0.0


def test_skor_kata_kunci_pendek():
    # Pesan satu kata yang seluruhnya dijelaskan pola tetap dianggap kuat.
    assert similarity(["oli"], ["kapan", "ganti", "oli"]) >= 0.45


def test_fuzzy_per_kata():
    # Salah ketik satu kata tetap dihitung cocok berkat pencocokan per token.
    assert similarity(["knlapot"], ["knalpot"]) > 0.5


# ---------- 10 uji tema baru: kalimat yang tidak ada di pola ----------

# Kalimat-kalimat ini sengaja tidak sama persis dengan pola di JSON.
KASUS_TEMA = [
    ("starter motor lemah banget", "susah_hidup"),
    ("motor saya tiba tiba mati sendiri", "mati_mendadak"),
    ("bensin motor boros banget", "boros_bensin"),
    ("rem belakang gak pakem", "rem"),
    ("mesin motor panas banget", "overheat"),
    ("knalpot saya berasap putih tebal", "asap_knalpot"),
    ("klakson motor lemah", "lampu_aki"),
    ("motor oleng kalau ngebut", "getaran"),
    ("kapan sebaiknya ganti oli motor", "ganti_oli"),
    ("tekanan angin ban motor berapa", "tekanan_ban"),
    ("terima kasih banyak", "terima_kasih"),
]


@pytest.mark.parametrize("kalimat,tag_benar", KASUS_TEMA)
def test_intent_tema_dikenali(bot, kalimat, tag_benar):
    tag, skor = bot.classify(kalimat)
    assert tag == tag_benar, f"skor {skor:.2f}"


# Kalimat alami hasil pengujian manual: gaya bicara sehari-hari dan istilah bengkel.
KASUS_ALAMI = [
    ("permisi mau tanya", "salam"),
    ("oke saya pamit dulu", "pamit"),
    ("motor saya gak mau nyala", "susah_hidup"),
    ("pagi pagi motor susah nyala", "susah_hidup"),
    ("busi basah", "susah_hidup"),
    ("mesin tiba tiba mati sendiri", "mati_mendadak"),
    ("matot di tengah jalan", "mati_mendadak"),
    ("motor brebet kalau digas", "brebet"),
    ("motor lemas pas nanjak", "brebet"),
    ("karburator kotor", "brebet"),
    ("motor saya nggak irit", "boros_bensin"),
    ("konsumsi bbm naik terus", "boros_bensin"),
    ("rem terasa kosong kalau diinjak", "rem"),
    ("motor overheat di jalan macet", "overheat"),
    ("indikator suhu naik", "overheat"),
    ("knalpot ngebul putih", "asap_knalpot"),
    ("asap hitam keluar dari knalpot", "asap_knalpot"),
    ("rantai kendor", "bunyi_kasar"),
    ("mesin berisik", "bunyi_kasar"),
    ("kelistrikan motor bermasalah", "lampu_aki"),
    ("lampu speedometer mati", "lampu_aki"),
    ("motor bergetar di kecepatan tinggi", "getaran"),
    ("interval ganti oli motor matic", "ganti_oli"),
    ("kapan ganti busi", "jadwal_servis"),
    ("isi angin ban berapa psi", "tekanan_ban"),
]


@pytest.mark.parametrize("kalimat,tag_benar", KASUS_ALAMI)
def test_kalimat_alami_dikenali(bot, kalimat, tag_benar):
    tag, skor = bot.classify(kalimat)
    assert tag == tag_benar, f"skor {skor:.2f}"


@pytest.mark.parametrize("kalimat,tag_benar", [
    ("oli", "ganti_oli"),
    ("rem", "rem"),
    ("aki", "lampu_aki"),
    ("ban", "tekanan_ban"),
    ("brebet", "brebet"),
    ("servis", "jadwal_servis"),
])
def test_kata_kunci_pendek_dikenali(bot, kalimat, tag_benar):
    tag, skor = bot.classify(kalimat)
    assert tag == tag_benar, f"skor {skor:.2f}"


def test_salah_ketik_masih_dikenali(bot):
    tag, _ = bot.classify("jadwl servis motor")
    assert tag == "jadwal_servis"


# ---------- fallback dan input aneh ----------

@pytest.mark.parametrize("kalimat", ["siapa presiden indonesia",
                                     "cara masak rendang",
                                     "harga hp terbaru",
                                     "resep kue bolu",
                                     "cuaca hari ini bagaimana"])
def test_di_luar_tema_ditolak(bot, kalimat):
    tag, _ = bot.classify(kalimat)
    assert tag is None


@pytest.mark.parametrize("kalimat", ["", "   ", "!!!"])
def test_pesan_kosong_tidak_crash(bot, kalimat):
    hasil = bot.reply(kalimat)
    assert hasil["intent"] is None
    assert hasil["reply"]


def test_ambang_tinggi_membuat_bot_menolak(tema):
    # Kalimat ini mirip pola "starter lemah" tetapi tidak identik (skor < 0,99).
    kalimat = "starter motor saya agak lemah kalau pagi"
    longgar = ChatbotEngine(tema, threshold=0.30)
    ketat = ChatbotEngine(tema, threshold=0.99)
    assert longgar.classify(kalimat)[0] == "susah_hidup"
    assert ketat.classify(kalimat)[0] is None


# ---------- jawaban dan tema ----------

def test_placeholder_terisi(bot):
    for _ in range(10):  # respons dipilih acak, uji beberapa kali
        teks = bot.reply("halo")["reply"]
        assert "{" not in teks and "}" not in teks


def test_kandidat_debug_terurut(bot):
    kandidat = bot.explain("rem blong", n=3)
    assert len(kandidat) == 3
    assert kandidat[0]["tag"] == "rem"
    assert kandidat[0]["skor"] >= kandidat[1]["skor"] >= kandidat[2]["skor"]


def test_tema_tanpa_fallback_ditolak():
    with pytest.raises(ValueError):
        validate_theme({"id": "x", "bot_name": "X", "intents": []})


def test_intent_tanpa_respons_ditolak():
    tema_rusak = {"id": "x", "bot_name": "X", "fallback": ["maaf"],
                  "intents": [{"tag": "a", "patterns": ["a"], "responses": []}]}
    with pytest.raises(ValueError):
        validate_theme(tema_rusak)


def test_kualitas_basis_pengetahuan(tema):
    assert len(tema["intents"]) >= 10
    assert len(tema["suggestions"]) == 4
    for intent in tema["intents"]:
        assert len(intent["patterns"]) >= 5, intent["tag"]
        assert len(intent["responses"]) >= 2, intent["tag"]


def test_tidak_ada_pola_ganda(tema):
    # Pola yang sama di dua intent membuat hasil klasifikasi bergantung urutan data.
    pemilik = {}
    for intent in tema["intents"]:
        for pola in intent["patterns"]:
            kunci = " ".join(preprocess(pola))
            assert pemilik.get(kunci, intent["tag"]) == intent["tag"], pola
            pemilik[kunci] = intent["tag"]


# ---------- akurasi ----------

def test_akurasi_evaluasi_minimal_90_persen(bot):
    # Ambang 90% menjaga kualitas klasifikasi saat pola atau kamus diubah.
    akurasi, _ = evaluasi(bot, baca_data(DATA_UJI))
    assert akurasi >= 0.90
