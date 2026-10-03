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
| `asn_tambahan.txt` | daftar ASN tambahan (negara mana pun), diisi pemilik repo |

URL untuk FortiGate: `https://raw.githubusercontent.com/jamuanfc/ip-indonesia/master/all_indonesia_ips.csv`

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

## Pengaman

Bila sumber gagal diunduh atau terlalu kecil, hasil terlalu sedikit, atau prefix Indonesia susut lebih
dari 10% dibanding hari sebelumnya, tidak ada file yang diubah: run ditandai gagal dan GitHub mengirim
email ke pemilik repo. Commit hanya dibuat bila isi berubah. Uji: `python3 test_build_feed.py`.
