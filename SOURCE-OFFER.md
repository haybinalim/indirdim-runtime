# Kaynak sunumu / Source offer (GPL-3.0)

**TR** · Bu deponun yayımladığı runtime AAR'ı, GNU GPL sürüm 3 (veya sonrası) ile lisanslı iki kütüphanenin
derlenmiş hâlini içerir: **GNU Readline 8.3 (yama 3)** ve **GNU gdbm 1.26** (`libgdbm.so`, `libgdbm_compat.so`).
Bu ikililer upstream AAR'dan (`io.github.deniscerri:ytdlnis_packages.python:3.14.6`) değiştirilmeden gelir;
Termux derleme sistemiyle derlenmiştir. Ayrıca GPL-2.0-or-later lisanslı **mutagen 1.48.1** saf Python'dır;
kaynağı runtime içindeki `.py` dosyalarının kendisidir.

GPL-3.0 §6(d) uyarınca karşılık gelen kaynak, ikili ile **aynı yerden, aynı biçimde** sunulur: her release'e
şu varlıklar eklenir (`SOURCES.md` her birinin SHA-256'sını listeler):

- `readline-8.3.tar.gz` ve resmî yamalar `readline83-001` … `readline83-003`
- `gdbm-1.26.tar.gz`
- `termux-recipes-<commit>.tar.gz`: termux-packages'ın `packages/readline`, `packages/gdbm` tarifleri, yamaları
  ve derlemeyi yöneten betikler (`build-package.sh`, `scripts/`), upstream derlemesinin zamanına karşılık gelen
  commit'ten (`2935d0eeff6eb9270227a72dc3d87bbce9c938de`; upstream commit'i kaydetmediği için derleme
  zamanından çıkarım)
- upstream'in runtime betiği `build_python.sh` (GPL-3.0)

Bu varlıklara erişilemezse, bu depoda bir issue açarak kaynağın tamamını isteyebilirsiniz; bu teklif ilgili
ikilinin son yayımlanmasından itibaren en az üç yıl geçerlidir ve kaynağı alan herkese açıktır.

**EN** · The runtime AAR published here contains compiled copies of two libraries licensed under the GNU GPL
version 3 (or later): **GNU Readline 8.3 (patch level 3)** and **GNU gdbm 1.26**. They come unmodified from the
upstream AAR and were built with the Termux build system. **mutagen 1.48.1** (GPL-2.0-or-later) is pure Python;
its source is the shipped `.py` files themselves.

Under GPL-3.0 §6(d) the Corresponding Source is offered **from the same place in the same way** as the binary:
every release carries the assets listed above, with SHA-256 sums in `SOURCES.md`. If those assets are ever
unavailable, open an issue in this repository to request the complete source; this offer is valid for at least
three years after the last release of the binary and is open to anyone who received it.
