# indirdim-runtime

**TR** · İndirdim Android uygulamasının gömülü Python runtime'ını (CPython 3.14 + yt-dlp + yardımcı paketler)
hash'e sabitlenmiş girdilerden, GitHub Actions'ta, tekrar üretilebilir biçimde yeniden paketleyen depo.
Çıktı, değişmez (immutable) bir GitHub Release varlığı olarak yayımlanan ve build attestation'ı taşıyan bir
Android AAR'ıdır. Uygulama bu AAR'ı SHA-256'sına sabitleyerek çeker; derleme sırasında hiçbir secret gerekmez.

**EN** · Rebuilds the embedded Python runtime (CPython 3.14 + yt-dlp + helper packages) of the İndirdim Android
app from hash-pinned inputs in GitHub Actions, reproducibly. The output is an Android AAR published as an
immutable GitHub Release asset with a build provenance attestation. The app pins the AAR by SHA-256; no secrets
are needed to build anything here.

## R0 (ilk teslimat / first release)

Girdi: upstream `io.github.deniscerri:ytdlnis_packages.python:3.14.6` AAR'ı (Maven Central). Yalnızca şunlar
değişir / Only these change:

| Bileşen / Component | Önce / Before | R0 |
|---|---|---|
| curl_cffi (yalnızca arm64-v8a) | 0.15.1b2 (beta, libcurl 8.15.0) | 0.17.0 (resmî PyPI wheel'i, PyPI attestation doğrulamalı; libcurl 8.23.0) |
| cffi (yalnızca arm64-v8a) | 2.0.0 | 2.1.1 (Termux tarifiyle derlenir) |
| brotli (Python) + libbrotli{common,dec,enc} | 1.2.0 | 1.2.1 (Termux tarifleriyle derlenir) |
| certifi + `usr/etc/tls/cert.pem` | 2026.6.17 | 2026.10.23 (aynı içerik / same content) |
| urllib3 | 2.7.0 | 2.8.0 |
| yt-dlp (`res/raw/ytdlp`) | 2026.08.19 | 2026.10.26 (`SHA2-256SUMS` + OpenPGP imzası) |

Geri kalan her şey (libpython, stdlib, OpenSSL, QuickJS `libqjs.so`, `libpython.so` başlatıcısı) upstream'den
bayt bayt aynen gelir. / Everything else is copied byte for byte from upstream.

## Yayım / Release

`release.yml` (elle, `workflow_dispatch`, yalnızca `main`): derleme hattını baştan koşar (native derlemeler,
iki runner'da yeniden paketleme ve SHA-256 eşitliği, içerik/ELF/16 KB kapıları, SBOM), GPL kaynaklarını ve
lisansları ekler, `actions/attest-build-provenance` ile AAR, SBOM ve `SHA256SUMS` için attestation üretir ve
release'i yayımlar. Varlıklar: AAR, `SHA256SUMS`, `diff-manifest.txt`, `sbom.cdx.json`, `SOURCES.md`, `NOTICE`,
`SOURCE-OFFER.md`, `licenses.tar.gz`, readline/gdbm kaynakları, termux tarifleri.

`release.yml` (manual, `main` only) re-runs the whole pipeline, adds GPL sources and licenses, attests the AAR,
SBOM and `SHA256SUMS`, and publishes the release.

## Doğrulama / Verification

```sh
sha256sum -c SHA256SUMS
gh attestation verify runtime-python-3.14.6-r0.aar --repo haybinalim/indirdim-runtime
```

## Lisans / License

Betikler GPL-3.0 (upstream `deniscerri/ytdlnis-packages` `scripts/build_python.sh`'nin atıflı türevi).
Dağıtılan ikililerdeki üçüncü taraf bileşenler ve lisansları: [`NOTICE`](NOTICE), metinler [`licenses/`](licenses).
GPL bileşenleri (readline, gdbm) için kaynak sunumu: [`SOURCE-OFFER.md`](SOURCE-OFFER.md).

Scripts are GPL-3.0 (an attributed derivative of upstream `scripts/build_python.sh`). Third-party components
and their licenses: [`NOTICE`](NOTICE), texts in [`licenses/`](licenses). Source offer for the GPL components:
[`SOURCE-OFFER.md`](SOURCE-OFFER.md).

Bu depo yalnızca açık kaynak betikler ve açık kaynak bileşenler içerir; secret ya da kişisel veri içermez.
This repository contains only open-source scripts and components; no secrets or personal data.
