#!/usr/bin/env python3
"""Bangun daftar URL + IP per layanan (aplikasi) dari sumber resmi vendornya (tanpa library tambahan).

Input: layanan_tambahan.txt, satu layanan per baris: '[Nama] <URL halaman vendor>', komentar setelah ' #'.
Tiap URL dikenali oleh sebuah *adapter* (lihat ADAPTERS) yang tahu dari mana data resmi vendor itu
diambil; URL yang belum punya adapter ditolak (run gagal), bukan ditebak dari HTML.

Hasil di folder layanan/, empat file per layanan (tanpa header):
  - <Nama>_url.csv         domain, satu per baris, wildcard apa adanya (*.teams.microsoft.com):
                           untuk FortiGate External Connector tipe Domain Name
  - <Nama>_ip.csv          prefix IPv4 lalu IPv6: untuk FortiGate External Connector tipe IP Address
  - <Nama>_url_versa.csv   file URL category Versa: 'string,<fqdn>,<reputasi>' untuk domain biasa,
                           'patterns,<regex>,<reputasi>' untuk domain dengan wildcard
  - <Nama>_ip_versa.csv    file address object Versa, format sama dengan feed ASN (build_feed.py)

Pengaman (sama dengan build_feed.py): semua dihitung di memori dulu; bila sumber gagal diunduh atau
tidak sesuai format, hasil di bawah minimum adapter, atau daftar URL/IP sebuah layanan susut > 10%
dari hasil sebelumnya, TIDAK ada file yang ditulis dan skrip keluar dengan kode 1. File sebuah
layanan hanya dihapus bila barisnya dihapus dari layanan_tambahan.txt.
"""
import argparse, ipaddress, json, os, re, sys
from html.parser import HTMLParser
from pathlib import Path
from urllib.parse import urlsplit

import build_feed as bf
from build_feed import FeedError

OUT_DIR = "layanan"
INPUT_FILE = "layanan_tambahan.txt"
MAX_SHRINK = 0.10              # daftar URL atau IP sebuah layanan boleh susut paling banyak 10%
URL_REPUTATION = "trustworthy"  # kolom ketiga file URL Versa
OUT_FILE = re.compile(r"^(?P<name>.+)_(?:url|ip|url_versa|ip_versa)\.csv$")
NAME = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_-]{0,39}$")
DOMAIN = re.compile(r"^(?=.*\.)[a-z0-9*]([a-z0-9*.-]*[a-z0-9])?$")


# ---------------------------------------------------------------- adapter per vendor

M365_URL = "https://endpoints.office.com/endpoints/worldwide?clientrequestid=7d0c5b39-8f0e-4b8a-9a77-2c1f0e4b6a51"


def microsoft365(get):
    """Web service resmi Microsoft 365 (sumber data halaman 'URLs and IP address ranges'):
    JSON berisi entri {id, serviceArea, category, urls[], ips[], ...}; semua entri diambil."""
    try:
        data = json.loads(get(M365_URL))
    except ValueError as e:
        raise FeedError(f"Microsoft 365: JSON tidak terbaca: {e}")
    if not isinstance(data, list) or not all(isinstance(e, dict) and "id" in e for e in data):
        raise FeedError("Microsoft 365: format JSON tidak dikenal (bukan daftar entri ber-id)")
    urls = [u for e in data for u in e.get("urls", [])]
    ips = [i for e in data for i in e.get("ips", [])]
    return urls, ips


ZOOM_URL = "https://support.zoom.com/hc/en/article?id=zm_kb&sysparm_article=KB0060548"
LD_JSON = re.compile(r'<script[^>]*type="application/ld\+json"[^>]*>(.*?)</script>', re.S)
DOMAIN_LIKE = re.compile(r"[*a-z0-9.-]+\.[a-z]{2,}")


class TableCells(HTMLParser):
    """Teks setiap sel <td> (baris baru dari <br> jadi spasi)."""
    def __init__(self):
        super().__init__()
        self.cells, self.cell = [], None

    def handle_starttag(self, tag, attrs):
        if tag == "td":
            self.cell = []
            self.cells.append(self.cell)
        elif tag == "br" and self.cell is not None:
            self.cell.append(" ")

    def handle_endtag(self, tag):
        if tag == "td":
            self.cell = None

    def handle_data(self, data):
        if self.cell is not None:
            self.cell.append(data)


def zoom(get):
    """Artikel KB 'Zoom network firewall or proxy server settings': isi artikel ada di blok JSON-LD
    (TechArticle.articleBody, HTML). Semua domain dan IP di sel tabel firewall-nya diambil; teks lain
    (protokol, port, keterangan) diabaikan. File assets.zoom.us/docs/ipranges/*.txt tidak dipakai:
    isinya sama dengan tabel artikel kecuali ZoomApps.txt (~1.700 IP CloudFront yang dipakai bersama)."""
    page = get(ZOOM_URL).decode("utf-8", "replace")
    try:
        docs = [json.loads(b) for b in LD_JSON.findall(page)]
    except ValueError as e:
        raise FeedError(f"Zoom: JSON-LD tidak terbaca: {e}")
    bodies = [d.get("articleBody") for d in docs if isinstance(d, dict) and d.get("@type") == "TechArticle"]
    if not bodies or not isinstance(bodies[0], str):
        raise FeedError("Zoom: isi artikel (JSON-LD TechArticle.articleBody) tidak ditemukan")
    parser = TableCells()
    parser.feed(bodies[0])
    urls, ips = [], []
    for cell in parser.cells:
        for token in re.split(r"[\s,]+", "".join(cell)):
            token = token.strip("()").rstrip(".:;").lower()
            try:
                ipaddress.ip_network(token)
                ips.append(token)
            except ValueError:
                if DOMAIN_LIKE.fullmatch(token):
                    urls.append(token)
    return urls, ips


# (nama bawaan, cocok(host, path, query), fungsi, minimal URL, minimal IP)
ADAPTERS = [
    ("Microsoft365",
     lambda host, path, query: (host == "learn.microsoft.com"
                                and path.endswith("/microsoft-365/enterprise/urls-and-ip-address-ranges")
                                and query.get("view", "o365-worldwide") == "o365-worldwide")
     or (host == "endpoints.office.com" and path == "/endpoints/worldwide"),
     microsoft365, 20, 20),
    ("Zoom",
     lambda host, path, query: host == "support.zoom.com" and query.get("sysparm_article") == "KB0060548",
     zoom, 10, 50),
]


def adapter_for(url):
    parts = urlsplit(url)
    query = dict(p.split("=", 1) for p in parts.query.split("&") if "=" in p)
    for default_name, match, fn, min_urls, min_ips in ADAPTERS:
        if match(parts.hostname or "", parts.path.rstrip("/"), query):
            return default_name, fn, min_urls, min_ips
    return None


# ---------------------------------------------------------------- olah hasil adapter

def read_input(path):
    """layanan_tambahan.txt: '[Nama] <URL>' per baris; baris diawali '#' dan teks setelah ' #' diabaikan."""
    if not path.exists():
        return []
    entries, seen = [], set()
    for n, line in enumerate(path.read_text().splitlines(), 1):
        tokens = re.split(r"\s#", " " + line.strip(), maxsplit=1)[0].split()
        if not tokens:
            continue
        if len(tokens) > 2 or not tokens[-1].startswith(("http://", "https://")):
            raise FeedError(f"{path.name} baris {n}: tulis '[Nama] <URL>', bukan '{line.strip()}'")
        found = adapter_for(tokens[-1])
        if not found:
            raise FeedError(f"{path.name} baris {n}: sumber belum didukung (belum ada adapter): {tokens[-1]}")
        name = tokens[0] if len(tokens) == 2 else found[0]
        if not NAME.match(name):
            raise FeedError(f"{path.name} baris {n}: nama '{name}' hanya boleh huruf, angka, _ dan - (maks 40)")
        if name.lower() in seen:
            raise FeedError(f"{path.name} baris {n}: nama '{name}' dipakai dua kali")
        seen.add(name.lower())
        entries.append((name, tokens[-1], *found[1:]))
    return entries


def clean_urls(raw):
    """Domain valid (huruf kecil, unik, urut); sisanya dikembalikan sebagai 'dilewati'."""
    good, bad = set(), []
    for u in raw:
        d = str(u).strip().lower().rstrip(".")
        (good.add(d) if DOMAIN.match(d) and ".." not in d else bad.append(str(u)))
    return sorted(good), bad


def clean_ips(raw):
    good, bad = set(), []
    for i in raw:
        try:
            net = ipaddress.ip_network(str(i).strip())
        except ValueError:
            bad.append(str(i))
            continue
        (good.add(net) if bf.usable(net) else bad.append(str(i)))
    return good, bad


def versa_pattern(domain):
    """'*.teams.microsoft.com' -> regex URL Versa: '*' = bagian nama host (tanpa '/'), path boleh apa saja;
    '*.' di depan juga mencakup domain induknya (teams.microsoft.com).
    Sesuai dokumentasi Versa, '\\' dan '{' di dalam regex ditulis '\\\\' dan '\\{'."""
    head, rest = (r"([^/]*\.)?", domain[2:]) if domain.startswith("*.") else ("", domain)
    regex = head + rest.replace(".", r"\.").replace("*", "[^/]*") + "(/.*)?$"
    return regex.replace("\\", "\\\\").replace("{", "\\{")


def url_versa_text(domains):
    return "".join(f"patterns,{versa_pattern(d)},{URL_REPUTATION}\n" if "*" in d
                   else f"string,{d},{URL_REPUTATION}\n" for d in domains)


def count_lines(path):
    return sum(1 for l in path.read_text().splitlines() if l.strip()) if path.exists() else 0


def build(root, get=bf.fetch):
    out_dir = root / OUT_DIR
    entries = read_input(root / INPUT_FILE)
    files, summary = {}, {}
    for name, _url, fn, min_urls, min_ips in entries:
        raw_urls, raw_ips = fn(get)
        urls, bad_urls = clean_urls(raw_urls)
        ips, bad_ips = clean_ips(raw_ips)
        if len(urls) < min_urls or len(ips) < min_ips:
            raise FeedError(f"{name}: hanya {len(urls)} URL dan {len(ips)} IP "
                            f"(minimal {min_urls} URL dan {min_ips} IP)")
        for kind, new in (("url", len(urls)), ("ip", len(ips))):
            old = count_lines(out_dir / f"{name}_{kind}.csv")
            if old and new < old * (1 - MAX_SHRINK):
                raise FeedError(f"{name}: daftar {kind.upper()} susut {old} -> {new} (> {MAX_SHRINK:.0%})")
        files[f"{name}_url.csv"] = "".join(f"{d}\n" for d in urls)
        files[f"{name}_url_versa.csv"] = url_versa_text(urls)
        files[f"{name}_ip.csv"] = bf.text(ips)
        files[f"{name}_ip_versa.csv"] = bf.versa_text(f"{name}_ip.csv", ips)
        skipped = bad_urls + bad_ips
        summary[name] = (f"{len(urls)} URL ({sum('*' in d for d in urls)} wildcard), {len(ips)} IP"
                         + (f"; dilewati {len(skipped)}: {', '.join(skipped[:10])}" if skipped else ""))

    old_files = {p.name for p in out_dir.iterdir() if OUT_FILE.match(p.name)} if out_dir.exists() else set()
    gone = old_files - files.keys()

    out_dir.mkdir(exist_ok=True)
    for name, body in files.items():
        tmp = out_dir / f".{name}.tmp"
        tmp.write_text(body)
        os.replace(tmp, out_dir / name)
    for name in gone:
        (out_dir / name).unlink()
    summary["file"] = f"{len(files)} ditulis, {len(gone)} dihapus"
    return summary


def main():
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--root", default=Path(__file__).resolve().parent, type=Path,
                    help="root repo, berisi layanan_tambahan.txt (bawaan: folder skrip)")
    args = ap.parse_args()
    try:
        summary = build(args.root)
    except FeedError as e:
        print(f"GAGAL, tidak ada file yang diubah: {e}", file=sys.stderr)
        return 1
    lines = [f"- {k}: {v}" for k, v in summary.items()]
    print("\n".join(lines))
    if os.environ.get("GITHUB_STEP_SUMMARY"):
        with open(os.environ["GITHUB_STEP_SUMMARY"], "a") as f:
            f.write("### Feed layanan diperbarui\n" + "\n".join(lines) + "\n")
    return 0


if __name__ == "__main__":
    sys.exit(main())
