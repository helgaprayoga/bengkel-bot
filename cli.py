"""Chat dengan BengkelBot lewat terminal.

Cara pakai:
    python cli.py                 # mode biasa
    python cli.py --debug         # tampilkan 3 kandidat intent beserta skornya
    python cli.py --ambang 0.5    # ubah ambang skor (bawaan 0,45)

Ketik "keluar" untuk berhenti.
"""

import argparse
import os
import sys

from chatbot.engine import AMBANG_BAWAAN, ChatbotEngine, load_theme

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
TEMA_BAWAAN = os.path.join(BASE_DIR, "themes", "bengkel.json")
MAKS_KARAKTER = 500  # Batas panjang pesan, sama seperti versi web.
KATA_KELUAR = {"keluar", "exit", "quit"}  # Kata yang menghentikan sesi CLI.


def baca_argumen():
    """Baca opsi dari baris perintah."""
    parser = argparse.ArgumentParser(description="BengkelBot di terminal")
    parser.add_argument("--tema", default=TEMA_BAWAAN, help="path file tema JSON")
    parser.add_argument("--ambang", type=float, default=AMBANG_BAWAAN,
                        help="skor minimum agar intent dianggap cocok")
    parser.add_argument("--debug", action="store_true",
                        help="tampilkan kandidat intent dan skor")
    return parser.parse_args()


def tampilkan_debug(bot, pesan, hasil):
    """Cetak intent terpilih dan tiga kandidat teratas (mode belajar)."""
    intent = hasil["intent"] or "(fallback)"
    print(f"   [debug] intent={intent}  skor={hasil['score']:.2f}  "
          f"ambang={bot.threshold}")
    for k in bot.explain(pesan, n=3):
        print(f"   [debug]   {k['tag']:<14} {k['skor']:.2f}  pola: {k['pola']}")


def main():
    args = baca_argumen()

    # Validasi tema di awal supaya kesalahan JSON tidak baru terlihat saat chat berjalan.
    try:
        tema = load_theme(args.tema)
    except (OSError, ValueError) as galat:
        print(f"Gagal memuat tema: {galat}")
        sys.exit(1)

    # Satu mesin dipakai sepanjang sesi agar pola tidak diproses ulang tiap pesan.
    bot = ChatbotEngine(tema, threshold=args.ambang)
    nama = tema["bot_name"]

    # Sapaan pembuka: sebut topik yang dikuasai dan beri contoh pertanyaan.
    print("=" * 60)
    print(f"{nama}: {bot.isi_teks(tema.get('greeting', 'Halo!'))}")
    if tema.get("disclaimer"):
        print(f"(Catatan: {tema['disclaimer']})")
    if tema.get("suggestions"):
        print("Contoh pertanyaan: " + " | ".join(tema["suggestions"]))
    print('Ketik "keluar" untuk berhenti.')
    print("=" * 60)

    # Satu loop menangani seluruh sesi chat sampai pengguna keluar.
    while True:
        try:
            pesan = input("\nAnda   : ").strip()
        except (EOFError, KeyboardInterrupt):  # Ctrl+D / Ctrl+C
            print(f"\n{nama}: Sampai jumpa!")
            break

        # Lewati pesan kosong agar tidak memicu pencocokan tanpa kata.
        if not pesan:
            continue
        if pesan.lower() in KATA_KELUAR:
            print(f"{nama}: Sampai jumpa! Hati-hati di jalan.")
            break
        # Tolak pesan yang terlalu panjang sebelum masuk ke mesin klasifikasi.
        if len(pesan) > MAKS_KARAKTER:
            print(f"{nama}: Pesan terlalu panjang (maksimal {MAKS_KARAKTER} karakter).")
            continue

        # Mesin mengembalikan jawaban beserta intent dan skor untuk ditampilkan saat debug.
        hasil = bot.reply(pesan)
        print(f"{nama}: {hasil['reply']}")
        if args.debug:
            tampilkan_debug(bot, pesan, hasil)


if __name__ == "__main__":
    main()
