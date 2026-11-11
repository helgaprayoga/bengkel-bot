"""Mesin chatbot BengkelBot (berbasis aturan, tanpa LLM).

Alur kerja:
    pesan -> preprocess() -> similarity() ke setiap pola -> classify() -> reply()

Modul ini sengaja tidak mengimpor Flask atau pustaka web apa pun, sehingga
bisa dipakai di terminal sekarang dan di halaman web nanti tanpa diubah.
"""

import json
import random
import re
from datetime import datetime
from difflib import SequenceMatcher
from functools import lru_cache

# Skor minimum agar sebuah intent dianggap cocok (di bawahnya = fallback).
AMBANG_BAWAAN = 0.45

# Bobot tiga ukuran kemiripan; jumlahnya 1,0.
BOBOT_JACCARD = 0.4
BOBOT_FUZZY = 0.3
BOBOT_KEDALAMAN = 0.3

# Dua kata dianggap cocok bila rasio kemiripannya minimal sebesar ini.
AMBANG_TOKEN_MIRIP = 0.8

# Kamus normalisasi: kata tidak baku/singkatan -> bentuk baku.
# Nilai "" berarti kata dibuang. Pola di file tema juga melewati kamus ini,
# jadi pesan dan pola selalu dibandingkan dalam bentuk yang sama.
NORMALISASI = {
    "gmn": "bagaimana", "gimana": "bagaimana", "gmna": "bagaimana",
    "bgmn": "bagaimana",
    "gk": "tidak", "ga": "tidak", "gak": "tidak", "ngga": "tidak",
    "nggak": "tidak", "enggak": "tidak", "engga": "tidak", "tdk": "tidak",
    "udh": "sudah", "udah": "sudah", "sdh": "sudah", "blm": "belum",
    "krn": "karena", "karna": "karena", "tp": "tapi", "dgn": "dengan",
    "bgt": "banget", "kpn": "kapan", "brp": "berapa",
    "mtr": "motor", "motornya": "motor",
    "kalo": "kalau", "klo": "kalau",
    "cepet": "cepat", "abis": "habis", "ilang": "hilang",
    "item": "hitam", "tebel": "tebal", "dalem": "dalam",
    "thx": "terima kasih", "makasi": "makasih", "tengkyu": "makasih",
    # Kelistrikan
    "accu": "aki", "baterai": "aki", "batre": "aki",
    # Mesin dan saluran bahan bakar
    "karbu": "karburator", "carbu": "karburator",
    "knlapot": "knalpot", "knalpotnya": "knalpot", "exhaust": "knalpot",
    "nyalain": "nyala", "dinyalain": "nyala", "dinyalakan": "nyala",
    "menyalakan": "nyala", "menyala": "nyala",
    "hidupin": "hidup", "dihidupin": "hidup", "dihidupkan": "hidup",
    "menghidupkan": "hidup",
    "pelumas": "oli", "olinya": "oli",
    "bbm": "bensin", "bensinya": "bensin", "fuel": "bensin",
    "ngeden": "brebet", "ngebrebet": "brebet",
    # Rem, ban, dan kaki-kaki
    "brake": "rem", "tire": "ban", "bannya": "ban",
    "setang": "stang", "getaran": "getar", "bergetar": "getar",
    # Suhu dan servis
    "overheat": "panas", "kepanasan": "panas",
    "service": "servis", "serves": "servis",
    # Suara
    "suara": "bunyi", "berisik": "bunyi",
}

# Kata henti: kata umum yang tidak membedakan satu intent dari yang lain.
# "motor" ikut dibuang karena hampir semua pertanyaan di tema ini memuatnya.
STOPWORDS = {
    "yang", "di", "ke", "dari", "apa", "apakah", "mau", "itu", "ini", "dan",
    "atau", "saya", "aku", "gue", "gw", "kak", "kakak", "bang", "mas",
    "dong", "ya", "sih", "nih", "deh", "tuh", "tolong", "mohon", "kok",
    "kenapa", "ada", "jadi", "pas", "saat", "lagi", "banget", "doang",
    "saja", "aja", "untuk", "buat", "dengan", "motor", "kalau", "waktu",
    "kayak", "kaya",
}

# Kolom wajib pada file tema.
_KUNCI_TEMA = ("id", "bot_name", "fallback", "intents")


def preprocess(teks):
    """Ubah kalimat menjadi daftar token yang sudah diseragamkan.

    Langkah: huruf kecil -> buang tanda baca -> normalisasi kata tidak baku
    -> pecah per kata -> buang kata henti.
    """
    # Samakan bentuk teks lebih dulu agar kapitalisasi dan tanda baca tidak memengaruhi skor.
    teks = re.sub(r"[^a-z0-9\s]", " ", str(teks).lower())
    tokens = []
    # Normalisasi kata tidak baku lalu buang kata henti supaya hanya kata pembeda intent yang tersisa.
    for kata in teks.split():
        for k in NORMALISASI.get(kata, kata).split():
            if k and k not in STOPWORDS:
                tokens.append(k)
    return tokens


@lru_cache(maxsize=8192)
def _mirip(kata_a, kata_b):
    """True bila dua kata sama atau mirip, sehingga salah ketik tetap terhitung.

    Hasil di-cache karena pasangan kata yang sama dipakai berulang oleh banyak pola.
    """
    if kata_a == kata_b:
        return True
    # Rasio maksimum yang mungkin = 2*min(panjang) / jumlah panjang. Bila batas ini
    # sudah di bawah ambang, SequenceMatcher tidak perlu dijalankan sama sekali.
    panjang_a, panjang_b = len(kata_a), len(kata_b)
    if 2 * min(panjang_a, panjang_b) / (panjang_a + panjang_b) < AMBANG_TOKEN_MIRIP:
        return False
    return SequenceMatcher(None, kata_a, kata_b).ratio() >= AMBANG_TOKEN_MIRIP


def _jumlah_cocok(sumber, target):
    """Berapa token target yang punya pasangan di sumber (tiap token dipakai sekali)."""
    sisa = list(dict.fromkeys(sumber))
    cocok = 0
    for kata in dict.fromkeys(target):
        if kata in sisa:
            sisa.remove(kata)
            cocok += 1
            continue
        for i, lain in enumerate(sisa):
            if _mirip(kata, lain):
                sisa.pop(i)
                cocok += 1
                break
    return cocok


def similarity(tokens_pesan, tokens_pola):
    """Hitung skor kemiripan 0..1 antara pesan dan satu pola.

    skor = 0,4 x Jaccard + 0,3 x Fuzzy + 0,3 x Kedalaman
      - Jaccard   : kata sama / gabungan semua kata (kesamaan kosakata)
      - Fuzzy     : kemiripan huruf seluruh kalimat, tahan salah ketik
      - Kedalaman : max(cakupan, presisi). Cakupan = bagian pola yang muncul di
        pesan; presisi = bagian pesan yang dijelaskan pola. Dengan begitu pesan
        pendek seperti "oli" tetap yakin, sedangkan pesan panjang yang hanya
        menyinggung satu kata pola tidak ikut naik.
    Pencocokan kata memakai _mirip(), jadi salah ketik satu kata tetap dihitung.
    """
    if not tokens_pesan or not tokens_pola:
        return 0.0
    himpunan_pesan, himpunan_pola = set(tokens_pesan), set(tokens_pola)
    sama = himpunan_pesan & himpunan_pola

    # Jaccard menghukum kata yang tidak dipakai bersama, sehingga pesan nyasar tidak mudah cocok.
    jaccard = len(sama) / len(himpunan_pesan | himpunan_pola)
    # Fuzzy menjaga bot tetap peka saat pengguna salah ketik.
    fuzzy = SequenceMatcher(None, " ".join(tokens_pesan),
                            " ".join(tokens_pola)).ratio()
    # Cakupan mencegah pola panjang menang hanya karena kebetulan satu kata sama;
    # presisi membuat pesan pendek yang seluruhnya cocok tetap dianggap kuat.
    cakupan = _jumlah_cocok(himpunan_pesan, himpunan_pola) / len(himpunan_pola)
    presisi = _jumlah_cocok(himpunan_pola, himpunan_pesan) / len(himpunan_pesan)
    kedalaman = max(cakupan, presisi)

    # Gabungkan ketiga ukuran dengan bobot tetap agar skor selalu berada di rentang 0..1.
    skor = (BOBOT_JACCARD * jaccard + BOBOT_FUZZY * fuzzy
            + BOBOT_KEDALAMAN * kedalaman)
    return round(skor, 4)


def validate_theme(theme):
    """Periksa struktur file tema; lempar ValueError bila ada yang kurang."""
    if not isinstance(theme, dict):
        raise ValueError("Isi tema harus berupa objek JSON.")
    # Validasi di awal mencegah error yang membingungkan saat bot sudah dipakai.
    for kunci in _KUNCI_TEMA:
        if kunci not in theme:
            raise ValueError(f"Tema tidak punya kolom '{kunci}'.")
    # Fallback wajib ada agar bot selalu punya jawaban cadangan.
    if not theme["fallback"]:
        raise ValueError("Kolom 'fallback' tidak boleh kosong.")
    # Minimal satu intent diperlukan agar mesin punya pola untuk dicocokkan.
    if not theme["intents"]:
        raise ValueError("Tema harus punya minimal satu intent.")
    # Setiap intent harus lengkap agar tidak error saat runtime.
    for intent in theme["intents"]:
        for kunci in ("tag", "patterns", "responses"):
            if not intent.get(kunci):
                raise ValueError(
                    f"Intent '{intent.get('tag', '?')}' kurang kolom '{kunci}'.")


def load_theme(path):
    """Baca file tema JSON, validasi, lalu kembalikan sebagai dict."""
    # Baca dengan UTF-8 agar teks Indonesia dan karakter khusus tetap utuh.
    with open(path, encoding="utf-8") as f:
        theme = json.load(f)
    # Validasi sebelum tema dipakai oleh mesin atau halaman web.
    validate_theme(theme)
    return theme


class ChatbotEngine:
    """Mesin chatbot untuk satu tema (satu file JSON)."""

    def __init__(self, theme, threshold=AMBANG_BAWAAN):
        validate_theme(theme)
        self.theme = theme
        self.threshold = threshold
        # Praproses semua pola sekali saja di awal supaya pencocokan cepat.
        self._pola = []  # daftar (tag, teks_pola, tokens_pola)
        # Simpan respons per tag supaya reply() tidak perlu memindai seluruh intent lagi.
        self._responses = {}
        for intent in theme["intents"]:
            self._responses[intent["tag"]] = intent["responses"]
            for pola in intent["patterns"]:
                tokens = preprocess(pola)
                if tokens:
                    self._pola.append((intent["tag"], pola, tokens))

    def explain(self, pesan, n=3):
        """Kembalikan n kandidat intent teratas beserta pola dan skornya.

        Tiap intent diwakili pola terbaiknya. Dipakai untuk mode debug.
        """
        tokens = preprocess(pesan)
        # Satu intent diwakili pola terbaiknya agar intent dengan banyak pola tidak otomatis menang.
        terbaik = {}  # tag -> (skor, pola)
        for tag, pola, tokens_pola in self._pola:
            skor = similarity(tokens, tokens_pola)
            if tag not in terbaik or skor > terbaik[tag][0]:
                terbaik[tag] = (skor, pola)
        # Urutkan kandidat dari skor tertinggi untuk classify dan mode debug.
        urut = sorted(terbaik.items(), key=lambda x: x[1][0], reverse=True)
        return [{"tag": tag, "pola": pola, "skor": skor}
                for tag, (skor, pola) in urut[:n]]

    def classify(self, pesan):
        """Pilih intent terbaik; (None, skor) bila di bawah ambang."""
        kandidat = self.explain(pesan, n=1)
        if not kandidat:
            return None, 0.0
        teratas = kandidat[0]
        # Ambang mencegah bot menjawab sesuatu yang sebenarnya di luar tema.
        if teratas["skor"] < self.threshold:
            return None, teratas["skor"]
        return teratas["tag"], teratas["skor"]

    def reply(self, pesan):
        """Hasilkan jawaban untuk satu pesan.

        Mengembalikan dict: {"reply": teks, "intent": tag atau None,
        "score": skor tertinggi}.
        """
        tag, skor = self.classify(pesan)
        # Fallback dipakai saat tidak ada intent yang cukup yakin, bukan jawaban asal.
        if tag is None:
            teks = random.choice(self.theme["fallback"])
        else:
            # Pilih respons acak agar jawaban bot tidak selalu sama.
            teks = random.choice(self._responses[tag])
        return {"reply": self._isi_placeholder(teks),
                "intent": tag, "score": skor}

    def _isi_placeholder(self, teks):
        """Ganti {waktu}, {tanggal}, dan {nama_bot} dengan nilai sebenarnya."""
        # Nilai waktu dihitung saat jawaban dibuat, bukan saat tema dimuat.
        sekarang = datetime.now()
        return (teks.replace("{waktu}", sekarang.strftime("%H:%M"))
                    .replace("{tanggal}", sekarang.strftime("%d-%m-%Y"))
                    .replace("{nama_bot}", self.theme["bot_name"]))

    def isi_teks(self, teks):
        """Versi publik _isi_placeholder untuk sapaan dan teks lain dari tema."""
        return self._isi_placeholder(teks)
