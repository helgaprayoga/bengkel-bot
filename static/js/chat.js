// ============================================================
// Chat BengkelBot: ambil elemen, kelola riwayat, dan kirim pesan.
// ============================================================
(function () {
  "use strict";

  // Elemen utama halaman chat.
  const messages = document.getElementById("messages");
  const form = document.getElementById("chat-form");
  const input = document.getElementById("chat-input");
  const btnSend = document.getElementById("btn-send");
  const btnClear = document.getElementById("btn-clear");
  const status = document.getElementById("chat-status");
  const modeBelajar = document.getElementById("mode-belajar");
  const suggestions = document.getElementById("suggestions");

  // Jika halaman bukan halaman chat, hentikan skrip dengan aman.
  if (!messages || !form || !input || !btnSend) {
    return;
  }

  const sapaan = messages.dataset.greeting || "Halo!";
  let sedangMengirim = false;

  // ------------------------------------------------------------
  // Utilitas tampilan
  // ------------------------------------------------------------

  function setStatus(teks, galat) {
    // Status dipakai untuk informasi "mengirim" dan galat jaringan.
    status.textContent = teks;
    status.classList.toggle("status-galat", Boolean(galat));
  }

  function gulirKeBawah() {
    // Tunggu render selesai agar posisi scroll selalu ke pesan terbaru.
    requestAnimationFrame(function () {
      messages.scrollTop = messages.scrollHeight;
    });
  }

  function buatMeta(intent, score) {
    // Metadata hanya tampil saat mode belajar aktif; CSS yang mengatur visibilitas.
    const meta = document.createElement("div");
    meta.className = "meta";

    const labelIntent = document.createElement("span");
    labelIntent.textContent = "Intent: " + (intent || "fallback");

    const labelSkor = document.createElement("span");
    const angka = typeof score === "number" ? score.toFixed(2) : "0.00";
    labelSkor.textContent = "Skor: " + angka;

    meta.append(labelIntent, labelSkor);
    return meta;
  }

  function buatPesan(pengirim, teks, intent, score, denganMeta) {
    // Struktur satu pesan: bubble teks dan metadata opsional.
    const artikel = document.createElement("article");
    artikel.className = "pesan pesan-" + pengirim;

    const bubble = document.createElement("div");
    bubble.className = "bubble";
    bubble.textContent = teks;
    artikel.append(bubble);

    if (denganMeta) {
      artikel.append(buatMeta(intent, score));
    }

    return artikel;
  }

  function tambahPesan(pengirim, teks, intent, score, denganMeta) {
    // Tambahkan pesan ke layar lalu gulir ke bawah.
    const artikel = buatPesan(
      pengirim,
      teks,
      intent,
      score,
      denganMeta !== false
    );
    messages.append(artikel);
    gulirKeBawah();
    return artikel;
  }

  function tampilkanSapaan() {
    // Sapaan hanya ditampilkan saat riwayat kosong atau setelah dihapus.
    messages.replaceChildren();
    tambahPesan("bot", sapaan, null, null, false);
  }

  function tampilkanMengetik() {
    // Indikator tiga titik saat menunggu respons server.
    const artikel = document.createElement("article");
    artikel.className = "pesan pesan-bot mengetik";

    const bubble = document.createElement("div");
    bubble.className = "bubble";
    for (let i = 0; i < 3; i += 1) {
      const titik = document.createElement("span");
      titik.className = "titik";
      bubble.append(titik);
    }

    artikel.append(bubble);
    messages.append(artikel);
    gulirKeBawah();
    return artikel;
  }

  // ------------------------------------------------------------
  // Komunikasi dengan API
  // ------------------------------------------------------------

  function pesanGalat(data, cadangan) {
    // Ambil pesan galat dari server bila ada, jika tidak pakai pesan cadangan.
    return data && typeof data.error === "string" ? data.error : cadangan;
  }

  async function muatRiwayat() {
    // Tampilkan sapaan lebih dulu agar halaman tidak kosong saat memuat.
    tampilkanSapaan();
    setStatus("Memuat riwayat...");

    try {
      const respons = await fetch("/api/history", {
        headers: { Accept: "application/json" }
      });
      const data = await respons.json().catch(function () {
        return [];
      });

      if (!respons.ok) {
        throw new Error(pesanGalat(data, "Gagal memuat riwayat."));
      }

      if (Array.isArray(data) && data.length > 0) {
        messages.replaceChildren();
        data.forEach(function (item) {
          tambahPesan(
            item.sender === "user" ? "user" : "bot",
            item.text,
            item.intent,
            item.score,
            item.sender !== "user"
          );
        });
      }

      setStatus("");
    } catch (galat) {
      // Kegagalan memuat riwayat tidak menghalangi pengguna untuk tetap chat.
      setStatus(galat.message, true);
    }
  }

  async function kirimPesan(teks) {
    // Cegah pengiriman ganda saat request masih berjalan.
    const pesan = String(teks || "").trim();
    if (!pesan || sedangMengirim) {
      return;
    }

    sedangMengirim = true;
    setStatus("Mengirim...");
    tambahPesan("user", pesan, null, null, false);
    input.value = "";
    input.disabled = true;
    btnSend.disabled = true;

    const indikator = tampilkanMengetik();

    try {
      const respons = await fetch("/api/chat", {
        method: "POST",
        headers: {
          "Content-Type": "application/json",
          Accept: "application/json"
        },
        body: JSON.stringify({ message: pesan })
      });
      const data = await respons.json().catch(function () {
        return {};
      });

      if (!respons.ok) {
        throw new Error(pesanGalat(data, "Gagal mengirim pesan."));
      }

      indikator.remove();
      tambahPesan("bot", data.reply, data.intent, data.score, true);
      setStatus("");
    } catch (galat) {
      // Hapus indikator dan beri tahu pengguna tanpa menambah bubble palsu.
      indikator.remove();
      setStatus(galat.message, true);
    } finally {
      sedangMengirim = false;
      input.disabled = false;
      btnSend.disabled = false;
      input.focus();
    }
  }

  async function hapusRiwayat() {
    // Konfirmasi mencegah penghapusan yang tidak disengaja.
    if (!window.confirm("Hapus riwayat chat di perangkat ini?")) {
      return;
    }

    btnClear.disabled = true;
    setStatus("Menghapus riwayat...");

    try {
      const respons = await fetch("/api/history", { method: "DELETE" });
      if (!respons.ok) {
        throw new Error("Gagal menghapus riwayat.");
      }
      tampilkanSapaan();
      setStatus("Riwayat dihapus.");
    } catch (galat) {
      setStatus(galat.message, true);
    } finally {
      btnClear.disabled = false;
    }
  }

  // ------------------------------------------------------------
  // Event handler
  // ------------------------------------------------------------

  form.addEventListener("submit", function (event) {
    // Enter atau tombol Kirim sama-sama memanggil jalur pengiriman yang sama.
    event.preventDefault();
    kirimPesan(input.value);
  });

  if (suggestions) {
    suggestions.addEventListener("click", function (event) {
      // Hanya tombol chip yang boleh mengisi input.
      const chip = event.target.closest(".chip");
      if (!chip) {
        return;
      }
      input.value = chip.textContent.trim();
      kirimPesan(input.value);
    });
  }

  if (btnClear) {
    btnClear.addEventListener("click", hapusRiwayat);
  }

  if (modeBelajar) {
    modeBelajar.addEventListener("change", function () {
      // CSS menampilkan atau menyembunyikan semua metadata sekaligus.
      messages.classList.toggle("mode-belajar", modeBelajar.checked);
    });
  }

  // ------------------------------------------------------------
  // Mulai aplikasi
  // ------------------------------------------------------------

  if (document.readyState === "loading") {
    document.addEventListener("DOMContentLoaded", muatRiwayat);
  } else {
    muatRiwayat();
  }
})();
