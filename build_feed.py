#!/usr/bin/env python3
"""Bangun daftar prefix IP per ASN dari data publik RIPE NCC (tanpa library tambahan).

Sumber (tiga unduhan per jalan, bukan satu panggilan API per ASN):
  - Semua ASN dunia + nama + negara:  https://ftp.ripe.net/ripe/asnames/asn.txt
  - Tabel BGP gabungan RIPE RIS (prefix -> ASN asal, jumlah peer yang melihat):
    https://www.ris.ripe.net/dumps/riswhoisdump.IPv4.gz dan .IPv6.gz

Hasil (prefix: satu per baris, tanpa header, IPv4 lalu IPv6):
  - all_indonesia_ips.csv      semua prefix yang diumumkan ASN berkode negara ID
  - asn_indonesia.csv          daftar ASN Indonesia (asn,nama,jumlah_prefix)
  - asn_dunia.csv              daftar semua ASN dunia (asn,nama,negara,jumlah_prefix): tempat mencari
                               nomor ASN sebelum menambahkannya ke asn_tambahan.txt
  - AS<asn>_<Nama>.csv         satu file per ASN yang ditulis di asn_tambahan.txt (Indonesia atau dunia)
  - <nama>_versa.csv           pasangan setiap file prefix di atas dalam format address-object-file Versa:
                               '<nama><nomor>,ipv4-prefix|ipv6-prefix,<prefix>' (isi sama dengan file polosnya)

Pengaman: semua dihitung di memori dulu; bila sumber gagal/terlalu kecil, hasil terlalu sedikit,
atau prefix Indonesia susut > 10% dari hasil sebelumnya, TIDAK ada file yang ditulis dan skrip
keluar dengan kode 1 (GitHub Actions gagal -> email ke pemilik repo). File AS*.csv hanya dihapus
bila ASN-nya dihapus dari asn_tambahan.txt; ASN yang sedang tidak mengumumkan prefix tetap
memakai file lamanya.
"""
import argparse, gzip, ipaddress, os, re, sys, time, urllib.request
from pathlib import Path

ASNAMES_URL = "https://ftp.ripe.net/ripe/asnames/asn.txt"
RIS_URL = "https://www.ris.ripe.net/dumps/riswhoisdump.IPv{v}.gz"
USER_AGENT = "ip-indonesia-feed (+https://github.com/jamuanfc/ip-indonesia)"

COUNTRY = "ID"
MIN_PEERS = 2            # rute yang hanya dilihat 1 peer RIS = derau/bocoran (1.653 rute ASN ID, 2 Okt 2026);
                         # 2-9 peer = rute regional yang sah: untuk allowlist, IP yang terlewat memutus layanan
MAX_SHRINK = 0.10        # total prefix Indonesia boleh susut paling banyak 10% dari hasil sebelumnya
MIN_ASN_NAMES = 100_000  # jumlah ASN dunia di asn.txt (normal ~120 rb)
MIN_ROUTES = {4: 500_000, 6: 100_000}
MIN_ID_ASN = 1_000       # ASN berkode ID (normal ~2.500+)
MIN_ID_PREFIX = 5_000    # prefix Indonesia (normal ~27 rb)
WIDEST = {4: 8, 6: 16}   # prefix lebih lebar dari ini ditolak
VERSA_NAME_MAX = 50      # panjang dasar nama objek Versa (sebelum nomor urut)

BOGON = [ipaddress.ip_network(n) for n in (
    "0.0.0.0/8", "10.0.0.0/8", "100.64.0.0/10", "127.0.0.0/8", "169.254.0.0/16",
    "172.16.0.0/12", "192.0.0.0/24", "192.0.2.0/24", "192.168.0.0/16", "198.18.0.0/15",
    "198.51.100.0/24", "203.0.113.0/24", "224.0.0.0/4", "240.0.0.0/4",
    "2001:db8::/32", "fc00::/7", "fe80::/10", "ff00::/8")]
GLOBAL_V6 = ipaddress.ip_network("2000::/3")
ASN_FILE = re.compile(r"^AS\d+_.*\.csv$")


class FeedError(Exception):
    pass


def fetch(url, cache_dir=None):
    """Isi URL sebagai bytes; bila --sumber diberikan, baca file lokal dengan nama yang sama."""
    if cache_dir:
        return (Path(cache_dir) / url.rsplit("/", 1)[1]).read_bytes()
    for attempt in range(3):
        try:
            req = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
            with urllib.request.urlopen(req, timeout=180) as r:
                return r.read()
        except OSError as e:
            if attempt == 2:
                raise FeedError(f"unduh gagal {url}: {e}")
            time.sleep(10 * (attempt + 1))


def parse_asnames(raw):
    """asn.txt: '<asn> <HANDLE> - <Nama organisasi>, <CC>' -> {asn: (nama, cc)}."""
    out = {}
    for line in raw.decode("utf-8", "replace").splitlines():
        num, _, rest = line.partition(" ")
        if not num.isdigit():
            continue
        name, _, cc = rest.rpartition(", ")
        if not name or len(cc) != 2:
            name, cc = rest, ""
        out[int(num)] = (name.split(" - ", 1)[-1].strip() or name, cc.upper())
    if len(out) < MIN_ASN_NAMES:
        raise FeedError(f"asn.txt hanya {len(out)} ASN (minimal {MIN_ASN_NAMES})")
    return out


def usable(net):
    if net.prefixlen < WIDEST[net.version]:
        return False
    if net.version == 6 and not net.subnet_of(GLOBAL_V6):
        return False
    return not any(net.version == b.version and net.overlaps(b) for b in BOGON)


def parse_ris(raw, version):
    """riswhoisdump: '<asn asal>\\t<prefix>\\t<jumlah peer>' -> {asn: set(prefix)}."""
    routes, total = {}, 0
    for line in gzip.decompress(raw).decode("ascii", "replace").splitlines():
        if not line or line[0] == "%":
            continue
        parts = line.split("\t")
        if len(parts) != 3 or not parts[0].isdigit():
            continue  # AS-set {a,b} sebagai asal: tidak bisa diatribusikan ke satu ASN
        total += 1
        if int(parts[2]) < MIN_PEERS:
            continue
        try:
            net = ipaddress.ip_network(parts[1])
        except ValueError:
            continue
        if net.version == version:
            routes.setdefault(int(parts[0]), set()).add(net)   # bogon/lebar disaring saat dipakai (usable)
    if total < MIN_ROUTES[version]:
        raise FeedError(f"tabel RIS IPv{version} hanya {total} rute (minimal {MIN_ROUTES[version]})")
    return routes


def read_extra(path):
    """asn_tambahan.txt: satu ASN per baris ('8075' atau 'AS8075'), komentar setelah '#'."""
    if not path.exists():
        return []
    asns = []
    for n, line in enumerate(path.read_text().splitlines(), 1):
        token = line.split("#", 1)[0].strip().upper().removeprefix("AS")
        if not token:
            continue
        if not token.isdigit():
            raise FeedError(f"{path.name} baris {n}: '{line.strip()}' bukan nomor ASN")
        asns.append(int(token))
    return asns


def file_name(asn, name):
    slug = re.sub(r"[^A-Za-z0-9]+", "_", name).strip("_")[:80] or "unknown"
    return f"AS{asn}_{slug}.csv"


def quoted(name):
    return '"' + name.replace('"', "") + '"'


def ordered(nets):
    return sorted(nets, key=lambda n: (n.version, n.network_address, n.prefixlen))


def text(nets):
    return "".join(f"{n}\n" for n in ordered(nets))


def versa_name(file_name):
    return file_name.removesuffix(".csv") + "_versa.csv"


def versa_text(file_name, nets):
    """Format address-object-file Versa: '<nama><nomor>,ipv4-prefix,<prefix>' (ipv6-prefix untuk IPv6)."""
    base = file_name.removesuffix(".csv")[:VERSA_NAME_MAX]
    return "".join(f"{base}{i},ipv{n.version}-prefix,{n}\n" for i, n in enumerate(ordered(nets), 1))


def with_versa(file_name, nets):
    """File prefix polos + pasangan Versa-nya, dari himpunan prefix yang sama."""
    return {file_name: text(nets), versa_name(file_name): versa_text(file_name, nets)}


def build(out_dir, cache_dir=None):
    names = parse_asnames(fetch(ASNAMES_URL, cache_dir))
    raw_routes = {}
    for v in (4, 6):
        for asn, nets in parse_ris(fetch(RIS_URL.format(v=v), cache_dir), v).items():
            raw_routes.setdefault(asn, set()).update(nets)

    id_asns = sorted(a for a, (_, cc) in names.items() if cc == COUNTRY)
    if len(id_asns) < MIN_ID_ASN:
        raise FeedError(f"hanya {len(id_asns)} ASN berkode {COUNTRY} (minimal {MIN_ID_ASN})")
    extra = read_extra(out_dir / "asn_tambahan.txt")
    unknown = [a for a in extra if a not in names]
    if unknown:
        raise FeedError(f"ASN tidak terdaftar di asn.txt: {', '.join(map(str, unknown))}")
    routes = {a: {n for n in nets if usable(n)} for a, nets in raw_routes.items()}

    all_id = set()
    for asn in id_asns:
        all_id |= routes.get(asn, set())
    files = {**with_versa("all_indonesia_ips.csv", all_id),
             "asn_indonesia.csv": "asn,nama,jumlah_prefix\n" + "".join(
                 f'AS{a},{quoted(names[a][0])},{len(routes.get(a, ()))}\n' for a in id_asns),
             "asn_dunia.csv": "asn,nama,negara,jumlah_prefix\n" + "".join(
                 f'AS{a},{quoted(n)},{cc},{len(routes.get(a, ()))}\n' for a, (n, cc) in sorted(names.items()))}
    old_files = {p.name for p in out_dir.iterdir() if ASN_FILE.match(p.name)}
    keep = set()
    for asn in sorted(set(extra)):
        if routes.get(asn):
            files.update(with_versa(file_name(asn, names[asn][0]), routes[asn]))
        else:   # sedang tidak terlihat di BGP: file lamanya (bila ada) dibiarkan
            keep |= {n for n in old_files if n.startswith(f"AS{asn}_")}

    # Pengaman sebelum menulis apa pun
    if len(all_id) < MIN_ID_PREFIX:
        raise FeedError(f"hanya {len(all_id)} prefix Indonesia (minimal {MIN_ID_PREFIX})")
    old_all = out_dir / "all_indonesia_ips.csv"
    old_count = sum(1 for l in old_all.read_text().splitlines() if l.strip()) if old_all.exists() else 0
    if old_count and len(all_id) < old_count * (1 - MAX_SHRINK):
        raise FeedError(f"prefix Indonesia susut {old_count} -> {len(all_id)} (> {MAX_SHRINK:.0%})")
    gone = old_files - files.keys() - keep

    for name, body in files.items():
        tmp = out_dir / f".{name}.tmp"
        tmp.write_text(body)
        os.replace(tmp, out_dir / name)
    for name in gone:
        (out_dir / name).unlink()

    no_route = [a for a in extra if not routes.get(a)]
    return {
        "asn_dunia": f"{len(names)} ({sum(1 for a in names if routes.get(a))} beriklan)",
        "asn_indonesia": len(id_asns),
        "asn_indonesia_beriklan": sum(1 for a in id_asns if routes.get(a)),
        "prefix_indonesia": f"{old_count} -> {len(all_id)}",
        "file_asn_tambahan": f"{len(files) - 4} ditulis (polos + versa), {len(gone)} dihapus, {len(keep)} dipertahankan",
        "asn_tambahan": len(extra),
        "asn_tambahan_tanpa_prefix": ", ".join(f"AS{a}" for a in no_route) or "-",
    }


def main():
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--keluar", default=Path(__file__).resolve().parent, type=Path,
                    help="folder hasil (bawaan: folder skrip = root repo)")
    ap.add_argument("--sumber", help="folder berisi asn.txt + riswhoisdump.*.gz (uji tanpa unduh)")
    args = ap.parse_args()
    try:
        summary = build(args.keluar, args.sumber)
    except FeedError as e:
        print(f"GAGAL, tidak ada file yang diubah: {e}", file=sys.stderr)
        return 1
    lines = [f"- {k}: {v}" for k, v in summary.items()]
    print("\n".join(lines))
    if os.environ.get("GITHUB_STEP_SUMMARY"):
        with open(os.environ["GITHUB_STEP_SUMMARY"], "a") as f:
            f.write("### Feed IP diperbarui\n" + "\n".join(lines) + "\n")
    return 0


if __name__ == "__main__":
    sys.exit(main())
