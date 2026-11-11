"""Ukur akurasi BengkelBot dengan kalimat uji berlabel.

Cara pakai:
    python evaluate.py                # akurasi pada ambang bawaan (0,45)
    python evaluate.py --sweep        # bandingkan beberapa ambang
    python evaluate.py --ambang 0.5   # coba satu ambang tertentu

Data uji ada di evaluasi/bengkel.csv (kolom: kalimat,intent). Baris dengan
intent "fallback" berarti bot seharusnya menolak (pertanyaan di luar tema).
Akurasi = kalimat yang ditebak benar / semua kalimat uji.
"""

import argparse
import csv
import os

from chatbot.engine import AMBANG_BAWAAN, ChatbotEngine, load_theme

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
TEMA = os.path.join(BASE_DIR, "themes", "bengkel.json")
DATA = os.path.join(BASE_DIR, "evaluasi", "bengkel.csv")
DAFTAR_AMBANG = [0.30, 0.35, 0.40, 0.45, 0.50, 0.55, 0.60, 0.70]


def baca_data(path):
    """Baca CSV uji menjadi daftar (kalimat, intent_benar)."""
    # DictReader membuat data uji terbaca sebagai pasangan kalimat dan label intent.
    with open(path, encoding="utf-8", newline="") as f:
        return [(baris["kalimat"], baris["intent"]) for baris in csv.DictReader(f)]


def evaluasi(bot, data):
    """Jalankan bot pada semua data uji; kembalikan (akurasi, daftar_salah)."""
    salah = []
    # Setiap kalimat diuji lewat jalur klasifikasi yang sama seperti saat chat.
    for kalimat, benar in data:
        tag, skor = bot.classify(kalimat)
        tebakan = tag or "fallback"
        if tebakan != benar:
            kandidat = bot.explain(kalimat, n=1)
            salah.append({"kalimat": kalimat, "benar": benar,
                          "tebakan": tebakan, "skor": skor,
                          "pola": kandidat[0]["pola"] if kandidat else "-"})
    # Akurasi adalah tebakan yang persis sama dengan label dibagi jumlah data uji.
    akurasi = (len(data) - len(salah)) / len(data)
    return akurasi, salah


def main():
    # Argumen memungkinkan evaluasi satu ambang atau perbandingan beberapa ambang.
    parser = argparse.ArgumentParser(description="Evaluasi akurasi BengkelBot")
    parser.add_argument("--ambang", type=float, default=AMBANG_BAWAAN)
    parser.add_argument("--sweep", action="store_true",
                        help="bandingkan akurasi di beberapa ambang")
    args = parser.parse_args()

    # Tema dan data uji dimuat sekali, lalu dipakai ulang untuk semua perhitungan.
    tema = load_theme(TEMA)
    data = baca_data(DATA)

    # Sweep membantu memilih ambang yang seimbang antara salah tolak dan salah terima.
    if args.sweep:
        print(f"Akurasi menurut ambang ({len(data)} kalimat uji):")
        for ambang in DAFTAR_AMBANG:
            akurasi, _ = evaluasi(ChatbotEngine(tema, ambang), data)
            print(f"  ambang {ambang:.2f}  ->  {akurasi:.1%}")
        return

    # Mode biasa menampilkan akurasi akhir dan kalimat yang masih salah untuk dianalisis.
    akurasi, salah = evaluasi(ChatbotEngine(tema, args.ambang), data)
    benar = len(data) - len(salah)
    print(f"Ambang {args.ambang}: {benar} benar dari {len(data)} "
          f"= {akurasi:.1%}")
    if salah:
        print("\nKalimat yang salah:")
        for s in salah:
            print(f"  - \"{s['kalimat']}\"")
            print(f"      seharusnya: {s['benar']} | ditebak: {s['tebakan']} "
                  f"(skor {s['skor']:.2f}, pola terdekat: \"{s['pola']}\")")


if __name__ == "__main__":
    main()
