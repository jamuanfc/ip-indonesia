#!/usr/bin/env python3
"""Bangun daftar URL + IP per layanan (aplikasi) dari sumber resmi vendornya (tanpa library tambahan).

Input: layanan_tambahan.txt, satu layanan per baris: '[Nama] <URL halaman vendor>', komentar setelah ' #'.
Tiap URL dikenali oleh sebuah *adapter* (lihat ADAPTERS) yang tahu dari mana data resmi vendor itu
diambil; URL yang belum punya adapter ditolak (run gagal), bukan ditebak dari HTML.

Hasil di folder layanan/, per layanan (tanpa header):
  - <Nama>_url.csv         domain, satu per baris, wildcard apa adanya (*.teams.microsoft.com):
                           untuk FortiGate External Connector tipe Domain Name
  - <Nama>_ip.csv          prefix IPv4 lalu IPv6: untuk FortiGate External Connector tipe IP Address
  - <Nama>_url_versa.csv   file URL category Versa: 'string,<fqdn>,<reputasi>' untuk domain biasa,
                           'patterns,<regex>,<reputasi>' untuk domain dengan wildcard
  - <Nama>_ip_versa.csv    file address object Versa, format sama dengan feed ASN (build_feed.py)
Vendor yang hanya menerbitkan IP (Google, Okta, Salesforce, Cloudflare, Zscaler) hanya punya dua file _ip.

Pengaman: semua dihitung di memori dulu. Bila sumber sebuah layanan gagal diunduh atau tidak sesuai
format, hasilnya di bawah minimum adapter, atau daftar URL/IP-nya susut > 10% dari hasil sebelumnya,
file layanan itu TIDAK diubah (layanan lain tetap diperbarui) dan skrip keluar dengan kode 1.
Kesalahan di layanan_tambahan.txt menghentikan semuanya sebelum ada file yang ditulis. File sebuah
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
KINDS = ("url", "url_versa", "ip", "ip_versa")
OUT_FILE = re.compile(r"^.+_(?:url|ip|url_versa|ip_versa)\.csv$")
NAME = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_-]{0,39}$")
DOMAIN = re.compile(r"^(?=.*\.)[a-z0-9*]([a-z0-9*.-]*[a-z0-9])?$")
DOMAIN_LIKE = re.compile(r"[*a-z0-9.-]+\.[a-z]{2,}")
LD_JSON = re.compile(r'<script[^>]*type="application/ld\+json"[^>]*>(.*?)</script>', re.S)
NEXT_DATA = re.compile(r'<script id="__NEXT_DATA__"[^>]*>(.*?)</script>', re.S)


# ---------------------------------------------------------------- alat bantu adapter

def load_json(get, url, vendor):
    try:
        return json.loads(get(url))
    except ValueError as e:
        raise FeedError(f"{vendor}: JSON tidak terbaca: {e}")


def require(ok, vendor, what):
    if not ok:
        raise FeedError(f"{vendor}: format sumber berubah ({what})")


class Tables(HTMLParser):
    """Semua tabel HTML: [(heading terakhir sebelum tabel, [[teks sel, ...], ...]), ...]."""
    def __init__(self):
        super().__init__()
        self.tables, self.heading, self.in_heading, self.row, self.cell = [], "", False, None, None

    def handle_starttag(self, tag, attrs):
        if tag in ("h1", "h2", "h3", "h4", "h5"):
            self.in_heading, self.heading = True, ""
        elif tag == "table":
            self.tables.append((self.heading.strip(), []))
        elif tag == "tr" and self.tables:
            self.row = []
            self.tables[-1][1].append(self.row)
        elif tag in ("td", "th") and self.row is not None:
            self.cell = []
            self.row.append(self.cell)
        elif tag in ("br", "p", "li", "div") and self.cell is not None:
            self.cell.append(" ")

    def handle_endtag(self, tag):
        if tag in ("h1", "h2", "h3", "h4", "h5"):
            self.in_heading = False
        elif tag in ("td", "th"):
            self.cell = None

    def handle_data(self, data):
        if self.in_heading:
            self.heading += data
        if self.cell is not None:
            self.cell.append(data)


def table_tokens(html, skip=None, domains_first_column=False):
    """Domain dan IP di sel tabel HTML; teks lain (protokol, port, keterangan) diabaikan.
    skip: regex heading tabel yang dilewati; domains_first_column: domain hanya dari kolom pertama
    (kolom lain berisi keterangan dengan tautan referensi), IP tetap dari semua kolom."""
    parser = Tables()
    parser.feed(html)
    urls, ips = [], []
    for heading, rows in parser.tables:
        if skip and re.search(skip, heading, re.I):
            continue
        for row in rows:
            for col, cell in enumerate(row):
                for token in re.split(r"[\s,;]+", "".join(cell)):
                    token = token.strip("()[]'\"").rstrip(".:;*").lower()
                    if "://" in token:                     # https://api.atlassian.com/... -> nama host
                        try:
                            token = urlsplit(token).hostname or ""
                        except ValueError:
                            continue
                    try:
                        ipaddress.ip_network(token)
                        ips.append(token)
                    except ValueError:
                        if DOMAIN_LIKE.fullmatch(token) and (col == 0 or not domains_first_column):
                            urls.append(token)
    return urls, ips


def strings_in(obj):
    if isinstance(obj, str):
        yield obj
    elif isinstance(obj, dict):
        for v in obj.values():
            yield from strings_in(v)
    elif isinstance(obj, list):
        for v in obj:
            yield from strings_in(v)


# ---------------------------------------------------------------- adapter per vendor
# Tiap adapter: fn(get, url) -> (daftar domain, daftar IP), mentah; dibersihkan oleh build().

M365_URL = "https://endpoints.office.com/endpoints/worldwide?clientrequestid=7d0c5b39-8f0e-4b8a-9a77-2c1f0e4b6a51"


def microsoft365(get, url):
    """Web service resmi Microsoft 365 (sumber data halaman 'URLs and IP address ranges'):
    JSON berisi entri {id, serviceArea, category, urls[], ips[], ...}; semua entri diambil."""
    data = load_json(get, M365_URL, "Microsoft 365")
    require(isinstance(data, list) and all(isinstance(e, dict) and "id" in e for e in data),
            "Microsoft 365", "bukan daftar entri ber-id")
    return [u for e in data for u in e.get("urls", [])], [i for e in data for i in e.get("ips", [])]


ZOOM_URL = "https://support.zoom.com/hc/en/article?id=zm_kb&sysparm_article=KB0060548"


def zoom(get, url):
    """Artikel KB 'Zoom network firewall or proxy server settings': isi artikel ada di blok JSON-LD
    (TechArticle.articleBody, HTML); semua domain dan IP di tabel firewall-nya diambil. File
    assets.zoom.us/docs/ipranges/*.txt tidak dipakai: isinya sama dengan tabel artikel kecuali
    ZoomApps.txt (~1.700 IP CloudFront yang dipakai bersama)."""
    page = get(ZOOM_URL).decode("utf-8", "replace")
    try:
        docs = [json.loads(b) for b in LD_JSON.findall(page)]
    except ValueError as e:
        raise FeedError(f"Zoom: JSON-LD tidak terbaca: {e}")
    bodies = [d.get("articleBody") for d in docs if isinstance(d, dict) and d.get("@type") == "TechArticle"]
    if not bodies or not isinstance(bodies[0], str):
        raise FeedError("Zoom: isi artikel (JSON-LD TechArticle.articleBody) tidak ditemukan")
    return table_tokens(bodies[0])


WEBEX_URL = "https://help.webex.com/en-us/article/WBX000028782/Network-Requirements-for-Webex-Services"


def webex(get, url):
    """Artikel 'Network Requirements for Webex Services': isi artikel (HTML) ada di data Next.js
    halaman (__NEXT_DATA__ props.pageProps.UIData). Domain (kolom pertama) + IP dari semua tabel kecuali
    riwayat revisi (berisi IP lama yang sudah dihapus)."""
    page = get(WEBEX_URL).decode("utf-8", "replace")
    found = NEXT_DATA.search(page)
    require(found, "Webex", "__NEXT_DATA__ tidak ditemukan")
    try:
        body = json.loads(found.group(1))["props"]["pageProps"]["UIData"]
    except (ValueError, KeyError, TypeError):
        body = None
    require(isinstance(body, str), "Webex", "isi artikel (props.pageProps.UIData) tidak ditemukan")
    return table_tokens(body, skip=r"revision history", domains_first_column=True)


GITHUB_URL = "https://api.github.com/meta"
GITHUB_SKIP = {"ssh_keys", "actions", "actions_macos"}   # actions*: ribuan IP Azure yang dipakai bersama
# Wildcard domain Azure/Microsoft di objek 'domains' (Codespaces, Copilot) yang mencakup layanan pelanggan
# siapa pun (mis. *.windows.net = semua Azure Storage); domain spesifik di bawahnya tetap diambil.
GITHUB_SHARED = ("windows.net", "azureedge.net", "msecnd.net", "visualstudio.com", "microsoft.com")


def shared_wildcard(domain):
    base = domain.lstrip("*.")
    return domain.startswith("*") and any(base == d or base.endswith("." + d) for d in GITHUB_SHARED)


def github(get, url):
    """API resmi GitHub /meta: daftar IP per layanan (web, api, git, hooks, ...) dan objek 'domains'.
    IP runner GitHub Actions dan wildcard Azure/Microsoft yang dipakai bersama (GITHUB_SHARED) tidak dipakai;
    teks lain di daftar /meta (mis. kunci PGP) bukan IP dan dilewati tanpa dilaporkan."""
    data = load_json(get, GITHUB_URL, "GitHub")
    require(isinstance(data, dict) and isinstance(data.get("web"), list) and isinstance(data.get("domains"), dict),
            "GitHub", "kunci 'web' / 'domains' tidak ada")
    ips = [ip for key, val in data.items() if key not in GITHUB_SKIP and isinstance(val, list)
           for ip in val if isinstance(ip, str) and not any(c.isspace() for c in ip)]
    urls = [s for s in strings_in(data["domains"]) if s and not shared_wildcard(s)]
    return urls, ips


ATLASSIAN_DOC = "https://support.atlassian.com/organization-administration/docs/ip-addresses-and-domains-for-atlassian-cloud-products/"
ATLASSIAN_IPS = "https://ip-ranges.atlassian.com/"


def atlassian(get, url):
    """Artikel 'IP addresses and domains for Atlassian cloud products': domain (kolom pertama) dan IP
    dari tabelnya, ditambah IP dari JSON resmi ip-ranges.atlassian.com. Atlassian Government Cloud
    (AS) tidak diambil."""
    page = get(ATLASSIAN_DOC).decode("utf-8", "replace")
    urls, ips = table_tokens(page, skip=r"government", domains_first_column=True)
    urls = [u for u in urls if "-us-gov-" not in u]          # juga muncul di tabel migrasi
    data = load_json(get, ATLASSIAN_IPS, "Atlassian")
    require(isinstance(data, dict) and isinstance(data.get("items"), list), "Atlassian", "kunci 'items' tidak ada")
    ips += [i.get("cidr") for i in data["items"] if isinstance(i, dict) and i.get("perimeter") == "commercial"]
    return urls, ips


GOOGLE_URL = "https://www.gstatic.com/ipranges/goog.json"
GOOGLE_CLOUD_URL = "https://www.gstatic.com/ipranges/cloud.json"


def google_prefixes(get, url):
    data = load_json(get, url, "Google")
    require(isinstance(data, dict) and isinstance(data.get("prefixes"), list), "Google", "kunci 'prefixes' tidak ada")
    nets = set()
    for p in data["prefixes"]:
        try:
            nets.add(ipaddress.ip_network(p.get("ipv4Prefix") or p.get("ipv6Prefix")))
        except (ValueError, TypeError, AttributeError):
            raise FeedError(f"Google: prefix tidak valid di {url}: {p}")
    return nets


def google(get, url):
    """IP layanan Google (Search, Workspace, YouTube, ...) sesuai cara yang dianjurkan Google:
    goog.json dikurangi cloud.json (IP pelanggan Google Cloud). Google tidak menerbitkan daftar domain."""
    cloud = google_prefixes(get, GOOGLE_CLOUD_URL)
    out = []
    for net in google_prefixes(get, GOOGLE_URL):
        parts = [net]
        for c in cloud:
            if c.version != net.version or not c.overlaps(net):
                continue
            rest = []
            for p in parts:
                if p.subnet_of(c):
                    continue
                rest.extend(p.address_exclude(c) if c.subnet_of(p) else [p])
            parts = rest
        out += parts
    return [], [str(n) for n in out]


OKTA_URL = "https://s3.amazonaws.com/okta-ip-ranges/ip_ranges.json"


def okta(get, url):
    """JSON resmi Okta: {<cell>: {ip_ranges: [...]}}; semua cell diambil (cell org Anda tidak diketahui)."""
    data = load_json(get, OKTA_URL, "Okta")
    require(isinstance(data, dict) and all(isinstance(v, dict) and "ip_ranges" in v for v in data.values()),
            "Okta", "bukan {cell: {ip_ranges}}")
    return [], [ip for v in data.values() for ip in v["ip_ranges"]]


SALESFORCE_URL = "https://ip-ranges.salesforce.com/ip-ranges.json"


def salesforce(get, url):
    """JSON resmi Salesforce: prefixes[].ip_prefix + ipv6_prefixes[].ipv6_prefix, semua region.
    Daftar domain Salesforce hanya ada di halaman help yang dirender JavaScript."""
    data = load_json(get, SALESFORCE_URL, "Salesforce")
    require(isinstance(data, dict) and isinstance(data.get("prefixes"), list), "Salesforce", "kunci 'prefixes' tidak ada")
    ips = [ip for p in data["prefixes"] for ip in p.get("ip_prefix", [])]
    ips += [ip for p in data.get("ipv6_prefixes", []) for ip in p.get("ipv6_prefix", [])]
    return [], ips


CLOUDFLARE_URL = "https://api.cloudflare.com/client/v4/ips"


def cloudflare(get, url):
    """API resmi Cloudflare: IP proxy Cloudflare. IP ini dipakai bersama jutaan situs: cocok untuk
    mengizinkan trafik MASUK dari Cloudflare ke server Anda, bukan sebagai allowlist keluar."""
    data = load_json(get, CLOUDFLARE_URL, "Cloudflare")
    result = data.get("result") if isinstance(data, dict) and data.get("success") else None
    require(isinstance(result, dict), "Cloudflare", "success/result tidak ada")
    return [], result.get("ipv4_cidrs", []) + result.get("ipv6_cidrs", [])


def zscaler_cloud(url):
    """Nama cloud Zscaler dari URL: config.zscaler.com/<cloud>/cenr atau /api/<cloud>/cenr/json."""
    found = re.fullmatch(r"(?:/api)?/([a-z0-9]+\.net)/cenr(?:/json)?", urlsplit(url).path.rstrip("/"))
    return found.group(1) if found else None


def zscaler(get, url):
    """API resmi config.zscaler.com untuk cloud di URL (mis. zscaler.net): Cloud Enforcement Node
    Ranges (semua kota) + svpnIPs + 'future' (range pusat data yang akan dipakai, dianjurkan Zscaler)."""
    cloud = zscaler_cloud(url)
    data = load_json(get, f"https://config.zscaler.com/api/{cloud}/cenr/json", "Zscaler")
    require(isinstance(data, dict) and isinstance(data.get(cloud), dict), "Zscaler", f"kunci '{cloud}' tidak ada")
    ips = [r.get("range") for cont in data[cloud].values() for city in cont.values() for r in city]
    ips += data.get("svpnIPs", [])
    future = load_json(get, f"https://config.zscaler.com/api/{cloud}/future/json", "Zscaler")
    require(isinstance(future, dict) and isinstance(future.get("prefixes"), list), "Zscaler", "future: 'prefixes' tidak ada")
    return [], ips + future["prefixes"]


def at(host, *paths):
    return lambda h, p, q: h == host and (not paths or p in paths)


# (nama bawaan, cocok(host, path, query), fungsi, minimal URL, minimal IP)
ADAPTERS = [
    ("Microsoft365",
     lambda h, p, q: (h == "learn.microsoft.com" and p.endswith("/microsoft-365/enterprise/urls-and-ip-address-ranges")
                      and q.get("view", "o365-worldwide") == "o365-worldwide")
     or at("endpoints.office.com", "/endpoints/worldwide")(h, p, q),
     microsoft365, 20, 20),
    ("Zoom", lambda h, p, q: h == "support.zoom.com" and q.get("sysparm_article") == "KB0060548", zoom, 10, 50),
    ("Webex", lambda h, p, q: h == "help.webex.com" and "/WBX000028782" in p, webex, 20, 20),
    ("GitHub",
     lambda h, p, q: at("api.github.com", "/meta")(h, p, q)
     or (h == "docs.github.com" and p.endswith("/about-githubs-ip-addresses")),
     github, 10, 20),
    ("Atlassian",
     lambda h, p, q: h == "support.atlassian.com" and p.endswith("/ip-addresses-and-domains-for-atlassian-cloud-products")
     or at("ip-ranges.atlassian.com", "")(h, p, q),
     atlassian, 10, 50),
    ("Google", at("www.gstatic.com", "/ipranges/goog.json"), google, 0, 50),
    ("Okta", at("s3.amazonaws.com", "/okta-ip-ranges/ip_ranges.json"), okta, 0, 100),
    ("Salesforce", at("ip-ranges.salesforce.com", "/ip-ranges.json"), salesforce, 0, 10),
    ("Cloudflare_InboundOnly",
     lambda h, p, q: at("www.cloudflare.com", "/ips", "/ips-v4", "/ips-v6")(h, p, q)
     or at("api.cloudflare.com", "/client/v4/ips")(h, p, q),
     cloudflare, 0, 10),
    ("Zscaler", lambda h, p, q: h == "config.zscaler.com" and zscaler_cloud("https://x" + p) is not None,
     zscaler, 0, 100),
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


def service_files(name, url, fn, min_urls, min_ips, get, out_dir):
    """File satu layanan + ringkasannya; FeedError bila sumber/hasilnya tidak lolos pengaman."""
    raw_urls, raw_ips = fn(get, url)
    urls, bad_urls = clean_urls(raw_urls)
    ips, bad_ips = clean_ips(raw_ips)
    if len(urls) < min_urls or len(ips) < min_ips:
        raise FeedError(f"hanya {len(urls)} URL dan {len(ips)} IP (minimal {min_urls} URL dan {min_ips} IP)")
    for kind, new in (("url", len(urls)), ("ip", len(ips))):
        old = count_lines(out_dir / f"{name}_{kind}.csv")
        if old and new < old * (1 - MAX_SHRINK):
            raise FeedError(f"daftar {kind.upper()} susut {old} -> {new} (> {MAX_SHRINK:.0%})")
    files = {f"{name}_ip.csv": bf.text(ips), f"{name}_ip_versa.csv": bf.versa_text(f"{name}_ip.csv", ips)}
    if urls:
        files.update({f"{name}_url.csv": "".join(f"{d}\n" for d in urls),
                      f"{name}_url_versa.csv": url_versa_text(urls)})
    skipped = bad_urls + bad_ips
    summary = (f"{len(urls)} URL ({sum('*' in d for d in urls)} wildcard), {len(ips)} IP"
               + (f"; dilewati {len(skipped)}: {', '.join(' '.join(s.split())[:60] for s in skipped[:10])}"
                  if skipped else ""))
    return files, summary


def build(root, get=bf.fetch):
    """-> (ringkasan per layanan, {layanan gagal: alasan}). File layanan yang gagal tidak diubah."""
    out_dir = root / OUT_DIR
    entries = read_input(root / INPUT_FILE)
    files, summary, failed = {}, {}, {}
    for name, url, fn, min_urls, min_ips in entries:
        try:
            service, summary[name] = service_files(name, url, fn, min_urls, min_ips, get, out_dir)
            files.update(service)
        except FeedError as e:
            failed[name] = summary[name] = f"GAGAL, file lama dipertahankan: {e}"

    old_files = {p.name for p in out_dir.iterdir() if OUT_FILE.match(p.name)} if out_dir.exists() else set()
    keep = {f"{name}_{kind}.csv" for name in failed for kind in KINDS}
    gone = old_files - files.keys() - keep

    out_dir.mkdir(exist_ok=True)
    for name, body in files.items():
        tmp = out_dir / f".{name}.tmp"
        tmp.write_text(body)
        os.replace(tmp, out_dir / name)
    for name in gone:
        (out_dir / name).unlink()
    summary["file"] = f"{len(files)} ditulis, {len(gone)} dihapus"
    return summary, failed


def main():
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--root", default=Path(__file__).resolve().parent, type=Path,
                    help="root repo, berisi layanan_tambahan.txt (bawaan: folder skrip)")
    args = ap.parse_args()
    try:
        summary, failed = build(args.root)
    except FeedError as e:
        print(f"GAGAL, tidak ada file yang diubah: {e}", file=sys.stderr)
        return 1
    lines = [f"- {k}: {v}" for k, v in summary.items()]
    print("\n".join(lines))
    if os.environ.get("GITHUB_STEP_SUMMARY"):
        with open(os.environ["GITHUB_STEP_SUMMARY"], "a") as f:
            f.write("### Feed layanan diperbarui\n" + "\n".join(lines) + "\n")
    if failed:
        print(f"GAGAL: {', '.join(failed)} (layanan lain tetap diperbarui)", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
