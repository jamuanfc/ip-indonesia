# ip-indonesia

Daftar prefix IP per ASN, diperbarui otomatis setiap hari pukul 05:00 WIB oleh GitHub Actions
(`.github/workflows/update.yml`). Dipakai sebagai *External Connector* (IP Address) di FortiGate
atau disalin langsung.

| File | Isi |
|---|---|
| `all_indonesia_ips.csv` | semua prefix (IPv4 lalu IPv6) yang diumumkan ASN Indonesia, satu per baris |
| `asn_indonesia.csv` | daftar ASN Indonesia: `asn,nama,jumlah_prefix` |
| `asn_dunia.csv` | daftar semua ASN dunia (~120 rb): `asn,nama,negara,jumlah_prefix`, untuk mencari nomor ASN |
| `AS<nomor>_<Nama>.csv` | prefix satu ASN, hanya untuk ASN yang ditulis di `asn_tambahan.txt` |
| `<nama>_versa.csv` | pasangan setiap file prefix di atas dalam format *address file* Versa, isinya sama |
| `asn_tambahan.txt` | daftar ASN tambahan (negara mana pun), diisi pemilik repo |

URL untuk FortiGate: `https://raw.githubusercontent.com/jamuanfc/ip-indonesia/master/all_indonesia_ips.csv`

## Format Versa

Setiap file prefix (`all_indonesia_ips.csv` dan `AS<nomor>_<Nama>.csv`) punya pasangan `..._versa.csv`
yang langsung bisa diunggah di Versa Director (*Objects & Connectors > Objects > Custom Objects > Address Files*):

```
AS8075_Microsoft_Corporation1,ipv4-prefix,1.186.0.0/16
AS8075_Microsoft_Corporation2,ipv4-prefix,2.58.103.0/24
AS8075_Microsoft_Corporation1333,ipv6-prefix,2a14:f180:130b::/48
```

Nama objek = nama file + nomor urut; IPv6 memakai `ipv6-prefix`. Menambah ASN di `asn_tambahan.txt`
otomatis membuat kedua file (polos + versa). Mengunggah file dengan nama yang sama di Director
menggantikan seluruh isi file lama.

## Sumber data (data publik RIPE NCC, 3 unduhan per jalan)

- ASN dunia + nama + negara: <https://ftp.ripe.net/ripe/asnames/asn.txt> (negara `ID` = ASN Indonesia)
- Tabel BGP gabungan RIPE RIS: `riswhoisdump.IPv4.gz` / `.IPv6.gz` (prefix -> ASN asal); rute yang
  hanya dilihat 1 peer RIS dibuang (derau), bogon dan prefix lebih lebar dari /8 (IPv4) atau /16 (IPv6) ditolak.

## Menambah ASN

1. Cari nomor ASN di `asn_dunia.csv`: buka file itu -> tombol *Raw* -> Ctrl+F nama organisasinya
   (mis. `Zoom`). File ini terlalu besar untuk tampilan tabel GitHub, jadi pakai *Raw*. Pilih baris dengan
   `jumlah_prefix` lebih dari 0; `0` = ASN itu sedang tidak mengumumkan prefix, file-nya belum dibuat.
   Satu organisasi bisa punya beberapa ASN (mis. per negara): tambahkan semua yang relevan.
2. Buka `asn_tambahan.txt` -> ikon pensil -> tulis nomor ASN satu per baris (mis. `8075`) -> *Commit changes*.
   Workflow langsung berjalan; sekitar dua menit kemudian `AS8075_Microsoft_Corporation.csv` tersedia.
   Menghapus baris = file ASN itu ikut dihapus pada jalan berikutnya.

## Layanan (URL + IP per aplikasi)

Selain per ASN, feed juga bisa dibuat per layanan dari daftar resmi vendornya. Workflow terpisah
(`.github/workflows/update_layanan.yml`, setiap hari 05:20 WIB, skrip `build_layanan.py`), jadi
feed ASN di atas tidak terpengaruh bila feed layanan gagal.

1. Buka `layanan_tambahan.txt` -> ikon pensil -> tulis `Nama URL` satu per baris, mis.
   `Microsoft365 https://learn.microsoft.com/en-us/microsoft-365/enterprise/urls-and-ip-address-ranges?view=o365-worldwide`
   -> *Commit changes*.
2. Sekitar satu menit kemudian folder `layanan/` berisi empat file (vendor yang hanya menerbitkan IP:
   dua file `_ip` saja):

| File | Isi | Dipakai di |
|---|---|---|
| `<Nama>_url.csv` | domain, wildcard apa adanya (`*.teams.microsoft.com`) | FortiGate *External Connector* tipe *Domain Name* |
| `<Nama>_ip.csv` | prefix IPv4 lalu IPv6 | FortiGate *External Connector* tipe *IP Address* |
| `<Nama>_url_versa.csv` | `string,<fqdn>,trustworthy`; domain wildcard jadi `patterns,<regex>,trustworthy` | Versa *URL Category* (unggah file) |
| `<Nama>_ip_versa.csv` | `<Nama>_ip1,ipv4-prefix,<prefix>` | Versa *Address Files* |

Contoh regex Versa: `*.protection.outlook.com` ->
`patterns,([^/]*\\.)?protection\\.outlook\\.com(/.*)?$,trustworthy`: cocok dengan `protection.outlook.com` dan
semua subdomainnya (`\` ditulis `\\` sesuai aturan Versa).

Tiap URL harus dikenali oleh *adapter* di `build_layanan.py` yang mengambil data dari sumber resmi
yang bisa dibaca mesin, bukan dari HTML halaman. URL yang belum punya adapter membuat run gagal
dengan pesan "sumber belum didukung". Yang sudah didukung (URL lengkapnya ada di `layanan_tambahan.txt`):

- **Microsoft 365** (worldwide): halaman di atas -> web service resmi `endpoints.office.com`, semua endpoint
  (semua kategori dan service area).
- **Zoom**: `https://support.zoom.com/hc/en/article?id=zm_kb&sysparm_article=KB0060548` -> semua domain dan IP
  di tabel firewall artikel itu (termasuk domain pihak ketiga yang dicantumkan Zoom, mis. `gstatic.com` dan
  server CRL/OCSP sertifikat). File `assets.zoom.us/docs/ipranges/ZoomApps.txt` sengaja tidak dipakai: isinya
  ~1.700 IP CloudFront yang dipakai bersama banyak situs lain.
- **Webex**: artikel *Network Requirements for Webex Services* -> domain (kolom pertama) dan IP dari tabelnya,
  kecuali tabel riwayat revisi (berisi IP lama yang sudah dihapus).
- **GitHub**: API resmi `api.github.com/meta` -> IP semua layanan dan objek `domains`. IP runner GitHub Actions
  tidak dipakai (ribuan range Azure yang dipakai bersama).
- **Atlassian**: artikel *IP addresses and domains for Atlassian cloud products* (domain) + JSON resmi
  `ip-ranges.atlassian.com` (IP). Atlassian Government Cloud (AS) tidak diambil.

Hanya IP (vendor tidak menerbitkan daftar domain yang bisa dibaca mesin):

- **Google**: `goog.json` dikurangi `cloud.json`, sesuai anjuran Google: IP semua layanan Google (Search,
  Workspace, YouTube, ...) tanpa IP pelanggan Google Cloud. Tidak ada daftar khusus Workspace.
- **Okta**: JSON resmi, semua *cell* (cell org Anda tidak diketahui skrip).
- **Salesforce**: JSON resmi `ip-ranges.salesforce.com`, semua region.
- **Cloudflare_InboundOnly**: IP proxy Cloudflare. **Hanya untuk mengizinkan trafik MASUK** dari Cloudflare
  ke server Anda: IP ini dipakai bersama jutaan situs, jadi jangan dipakai sebagai allowlist keluar.
- **Zscaler**: `config.zscaler.com` untuk cloud di URL (`zscaler.net`, `zscalertwo.net`, ...): Cloud
  Enforcement Node Ranges semua kota + svpnIPs + range *future* yang dianjurkan Zscaler.

## Pengaman

Bila sumber gagal diunduh atau terlalu kecil, hasil terlalu sedikit, atau prefix Indonesia susut lebih
dari 10% dibanding hari sebelumnya, tidak ada file yang diubah: run ditandai gagal dan GitHub mengirim
email ke pemilik repo. Commit hanya dibuat bila isi berubah. Uji: `python3 test_build_feed.py`.
Feed layanan memakai pengaman yang sama (sumber gagal atau rusak, hasil terlalu sedikit, daftar URL atau IP
susut lebih dari 10%), per layanan: file layanan yang gagal tidak diubah, layanan lain tetap diperbarui,
dan run tetap ditandai gagal (email). Uji: `python3 test_build_layanan.py`.
