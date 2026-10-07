#!/usr/bin/env python3
"""Uji build_layanan.py dengan data sintetis (tanpa jaringan): python3 test_build_layanan.py"""
import json, re, sys, tempfile, unittest
from pathlib import Path

import build_layanan as bl
from build_feed import FeedError

DOCS = "https://learn.microsoft.com/en-us/microsoft-365/enterprise/urls-and-ip-address-ranges?view=o365-worldwide"
ZOOM = "https://support.zoom.com/hc/en/article?id=zm_kb&sysparm_article=KB0060548"
WEBEX = "https://help.webex.com/en-us/article/WBX000028782/Network-Requirements-for-Webex-Services"
GITHUB = "https://docs.github.com/en/authentication/keeping-your-account-and-data-secure/about-githubs-ip-addresses"
ATLASSIAN = "https://support.atlassian.com/organization-administration/docs/ip-addresses-and-domains-for-atlassian-cloud-products/"
ZSCALER = "https://config.zscaler.com/zscaler.net/cenr"


def m365(n_urls=30, n_ips=30, extra_urls=(), extra_ips=()):
    """JSON tiruan web service endpoints.office.com (bentuk entri sama dengan aslinya)."""
    return json.dumps([
        {"id": 1, "serviceArea": "Exchange", "serviceAreaDisplayName": "Exchange Online",
         "urls": ["outlook.office.com", "*.protection.outlook.com", "autodiscover.*.onmicrosoft.com"],
         "ips": ["13.107.6.152/31", "2603:1006::/40"], "tcpPorts": "80,443", "expressRoute": True,
         "category": "Optimize", "required": True},
        {"id": 2, "serviceArea": "Common", "urls": [f"svc{i}.microsoft.com" for i in range(n_urls)]
         + list(extra_urls), "tcpPorts": "443", "category": "Default", "required": False},
        {"id": 3, "serviceArea": "Skype", "ips": [f"52.112.{i}.0/24" for i in range(n_ips)]
         + list(extra_ips), "udpPorts": "3478", "category": "Optimize", "required": True,
         "notes": "IP saja"},
        {"id": 4, "serviceArea": "Common", "urls": ["OUTLOOK.office.com"], "category": "Allow",
         "required": True},                                       # duplikat beda huruf
    ]).encode()


def zoom_page(n_ips=60, article=True):
    """Halaman KB Zoom tiruan: isi artikel (HTML) di JSON-LD TechArticle.articleBody, seperti aslinya."""
    ips = "<br />".join(f"170.114.{i}.0/24" for i in range(n_ips))
    body = (
        "<p>Lihat tabel. Versi 5.0, mis. port 8801.</p><h3>Firewall rules for Zoom</h3><table><thead><tr>"
        "<th>Protocol</th><th>Ports</th><th>Source</th><th>Destination</th></tr></thead><tbody>"
        "<tr><td>TCP</td><td>80, 443</td><td>All Zoom Clients <br />User's web browser</td>"
        "<td>*.zoom.us <br />*.ZOOM.com<br />cdn.cookielaw.org<br />gstatic.com</td></tr></tbody></table>"
        "<h3>Meetings</h3><table><tbody><tr><td>UDP</td><td>3478, 3479, 8801 - 8810</td><td>All Zoom clients</td>"
        f"<td>IPv4: <br />{ips}<br />IPv6:<br />2620:123:2000::/40</td></tr>"
        "<tr><td>TCP</td><td>443</td><td>IPv4: <br />3.9.26.103<br /></td>"
        "<td>Specified endpoint from Network requests defined in Zoom Flow Script widget</td></tr>"
        + "".join(f"<tr><td>HTTP</td><td>80</td><td>Zoom client</td><td>crl{i}.digicert.com</td></tr>"
                  for i in range(10))
        + "</tbody></table>")
    ld = {"@context": "https://schema.org", "@type": "TechArticle" if article else "WebPage",
          "headline": "Zoom network firewall or proxy server settings", "articleBody": body}
    return (f'<html><head><script custom-tag="" type="application/ld+json">{json.dumps(ld)}</script>'
            '</head><body><div id="app"></div></body></html>').encode()


def webex_page():
    """Halaman Webex tiruan: isi artikel (HTML) di __NEXT_DATA__ props.pageProps.UIData."""
    body = (
        "<h3>IP subnets for Webex media services</h3><table><tr><td>IPv4 Subnets for Media Services</td></tr>"
        + "".join(f"<tr><td>4.152.{i}.0/24*</td><td>66.163.{i}.0/24</td></tr>" for i in range(12))
        + "</table><h3>Domains and URLs that need to be accessed for Webex Services</h3><table>"
        "<tr><th>Domain / URL</th><th>Description</th><th>Used by</th></tr>"
        "<tr><td>*.webex.com<br/>*.wbx2.com</td><td>Microservices, see https://support.apple.com/en-us/HT1 "
        "and firebase.google.com</td><td>All</td></tr>"
        "<tr><td>*.webexcontent.com (1)</td><td>Replaced clouddrive.com in 2019</td><td>All</td></tr>"
        + "".join(f"<tr><td>svc{i}.webex.com</td><td>Service {i}</td><td>All</td></tr>" for i in range(20))
        + "</table><h3>Document Revision History - Network Requirements</h3><table>"
        "<tr><td>3/16/2026</td><td>Removed 163.129.0.0/16 and old.webex.com</td></tr></table>")
    data = {"props": {"pageProps": {"UIData": body}}}
    return (f'<html><body><script id="__NEXT_DATA__" type="application/json">{json.dumps(data)}</script>'
            '</body></html>').encode()


def github_meta():
    """JSON tiruan api.github.com/meta (kunci sesuai dokumentasi GitHub)."""
    return json.dumps({
        "verifiable_password_authentication": False,
        "ssh_key_fingerprints": {"SHA256_ED25519": "+DiY3wvvV6TuJJhbpZisF/zLDA0zPMSvHdkr4UvCOqU"},
        "ssh_keys": ["ssh-ed25519 AAAAC3NzaC1lZDI1NTE5AAAAIOMqqnkVzrm0SdG6UOoqKLsabgH5C9okWi0dh2l9GKJl"],
        "hooks": ["192.30.252.0/22"], "web": [f"140.82.{i}.0/24" for i in range(25)], "api": ["2a0a:a440::/29"],
        "git": ["140.82.0.0/24"], "packages": ["140.82.121.33/32"],
        "web_commit_signing": ["-----BEGIN PGP PUBLIC KEY BLOCK-----\n\nxsBNBFmUaEEBCACzXTDt6Zny\n-----END PGP"],
        "actions": [f"4.{i}.0.0/16" for i in range(200)], "actions_macos": ["13.105.117.0/31"],
        "domains": {"website": ["*.github.com", "*.github.dev", "*.githubusercontent.com"],
                    "codespaces": ["*.github.dev", "*.windows.net", "*.core.windows.net", "*.azureedge.net",
                                   "*.microsoft.com", "*.visualstudio.com", "*.vscode-webview.net"],
                    "copilot": ["*.githubcopilot.com"], "packages": ["ghcr.io", "*.pkg.github.com"],
                    "actions": ["*.actions.githubusercontent.com", "productionresultssa0.blob.core.windows.net"],
                    "actions_inbound": {"full_domains": ["github.com", "api.github.com", "codeload.github.com"],
                                        "wildcard_domains": ["*.ghcr.io"]},
                    "artifact_attestations": {"trust_domain": "", "services": ["*.actions.githubusercontent.com"]}},
    }).encode()


def atlassian_sources():
    doc = (
        "<html><body><h2>Atlassian domains</h2><table><tr><th>Domain</th><th>Purpose</th></tr>"
        + "".join(f"<tr><td>*.svc{i}.atlassian.net</td><td>See https://aws.amazon.com/cloudfront/</td></tr>"
                  for i in range(10))
        + "</table><h2>Atlassian Government Cloud domains</h2><table><tr><td>*.atlassian-us-gov-mod.com</td>"
        "<td>Gov</td></tr></table><h2>For Jira Cloud Migration Assistant communication</h2><table>"
        "<tr><th>Atlassian Cloud</th><th>Atlassian Government Cloud</th><th>Isolated</th></tr>"
        "<tr><td>https://api.atlassian.com</td><td>https://api.atlassian-us-gov-mod.com</td>"
        "<td>https://media-api.[IC_BASE_DOMAIN]/</td></tr>"
        "<tr><td>https://api.atlassian-us-gov-mod.com/</td><td></td><td></td></tr></table>"
        "<h2>IPv4</h2><table><tr><td>13.200.41.128/25</td><td>13.200.41.224/28</td></tr></table></body></html>")
    items = [{"cidr": f"104.192.{i}.0/24", "perimeter": "commercial", "product": ["jira"],
              "direction": ["ingress"]} for i in range(60)]
    items.append({"cidr": "18.0.0.0/24", "perimeter": "fedramp-moderate", "product": ["jira"], "direction": ["egress"]})
    return {bl.ATLASSIAN_DOC: doc.encode(),
            bl.ATLASSIAN_IPS: json.dumps({"creationDate": "x", "syncToken": 1, "items": items}).encode()}


def google_sources():
    goog = [{"ipv4Prefix": f"142.250.{i}.0/24"} for i in range(60)] + [
        {"ipv4Prefix": "34.0.0.0/15"}, {"ipv4Prefix": "35.190.0.0/24"}, {"ipv6Prefix": "2001:4860::/32"}]
    cloud = [{"ipv4Prefix": "34.0.0.0/16", "service": "Google Cloud", "scope": "x"},
             {"ipv4Prefix": "35.190.0.0/24", "service": "Google Cloud", "scope": "y"}]
    return {bl.GOOGLE_URL: json.dumps({"syncToken": "1", "prefixes": goog}).encode(),
            bl.GOOGLE_CLOUD_URL: json.dumps({"syncToken": "1", "prefixes": cloud}).encode()}


def zscaler_sources(cloud="zscaler.net"):
    rows = [{"range": f"165.225.{i}.0/24", "vpn": "", "gre": "", "hostname": ""} for i in range(100)]
    cenr = {cloud: {"continent : APAC": {"city : Jakarta I": rows[:50], "city : Singapore IV": rows[50:]},
                    "continent : EMEA": {"city : Amsterdam II": [{"range": "2a03:eec0::/32"}]}},
            "svpnIPs": ["185.46.212.74", "2a03:eec0:1211::30"]}
    return {f"https://config.zscaler.com/api/{cloud}/cenr/json": json.dumps(cenr).encode(),
            f"https://config.zscaler.com/api/{cloud}/future/json":
                json.dumps({"cloudName": cloud, "prefixes": ["136.226.0.0/16"]}).encode()}


class Layanan(unittest.TestCase):
    def setUp(self):
        self.root = Path(tempfile.mkdtemp())
        self.out = self.root / "layanan"
        self.sources = {bl.M365_URL: m365()}
        self.calls = []

    def get(self, url):
        self.calls.append(url)
        if url not in self.sources:
            raise FeedError(f"unduh gagal {url}: HTTP Error 404")
        return self.sources[url]

    def build(self, lines=f"Microsoft365 {DOCS}\n"):
        (self.root / "layanan_tambahan.txt").write_text(lines)
        return bl.build(self.root, self.get)

    def read(self, name):
        return (self.out / name).read_text().splitlines()

    def names(self):
        return sorted(p.name for p in self.out.iterdir()) if self.out.exists() else []

    def snapshot(self):
        return {p.name: p.read_text() for p in self.out.iterdir()}

    # ---- Microsoft 365 + perilaku umum

    def test_empat_file_dari_url_dokumentasi(self):
        self.build("# komentar\nMicrosoft365   " + DOCS + "   # semua endpoint\n")
        self.assertEqual(self.calls, [bl.M365_URL])               # data dari JSON resmi, bukan HTML
        self.assertEqual(self.names(), ["Microsoft365_ip.csv", "Microsoft365_ip_versa.csv",
                                        "Microsoft365_url.csv", "Microsoft365_url_versa.csv"])
        urls = self.read("Microsoft365_url.csv")
        self.assertEqual(len(urls), 33)                            # 30 + 3, duplikat beda huruf dibuang
        self.assertIn("*.protection.outlook.com", urls)            # wildcard apa adanya (FortiGate)
        self.assertEqual(urls.count("outlook.office.com"), 1)
        ips = self.read("Microsoft365_ip.csv")
        self.assertEqual(len(ips), 32)
        self.assertEqual(ips[-1], "2603:1006::/40")                # IPv4 dulu, lalu IPv6

    def test_url_versa(self):
        self.build()
        rows = self.read("Microsoft365_url_versa.csv")
        self.assertEqual(len(rows), len(self.read("Microsoft365_url.csv")))
        self.assertIn("string,outlook.office.com,trustworthy", rows)
        self.assertIn(r"patterns,([^/]*\\.)?protection\\.outlook\\.com(/.*)?$,trustworthy", rows)
        self.assertIn(r"patterns,autodiscover\\.[^/]*\\.onmicrosoft\\.com(/.*)?$,trustworthy", rows)
        self.assertTrue(all(len(r.split(",")) == 3 for r in rows))

    def test_regex_versa_cocok_dengan_url_yang_dimaksud(self):
        regex = bl.versa_pattern("*.protection.outlook.com").replace("\\\\", "\\")   # buang escape Versa
        for ok in ("x.protection.outlook.com", "a.b.protection.outlook.com/path?q=1", "protection.outlook.com"):
            self.assertTrue(re.fullmatch(regex, ok), ok)
        for bad in ("protection.outlook.com.evil.com", "evil.com/x.protection.outlook.com", "xprotection-outlook.com",
                    "evilprotection.outlook.com"):
            self.assertFalse(re.fullmatch(regex, bad), bad)

    def test_ip_versa_sama_dengan_file_polos(self):
        self.build()
        rows = [r.split(",") for r in self.read("Microsoft365_ip_versa.csv")]
        self.assertEqual([r[2] for r in rows], self.read("Microsoft365_ip.csv"))
        self.assertEqual(rows[0], ["Microsoft365_ip1", "ipv4-prefix", "13.107.6.152/31"])
        self.assertEqual(rows[-1][1], "ipv6-prefix")

    def test_nama_bawaan_bila_hanya_url(self):
        self.build(DOCS + "\n")
        self.assertTrue((self.out / "Microsoft365_url.csv").exists())

    def test_entri_rusak_dilewati(self):
        self.sources[bl.M365_URL] = m365(extra_urls=["bukan domain", "a..b.com"], extra_ips=["10.0.0.0/8", "xyz"])
        summary, failed = self.build()
        self.assertEqual(failed, {})
        self.assertIn("dilewati 4", summary["Microsoft365"])
        self.sources[bl.M365_URL] = m365(extra_ips=["BEGIN KEY\n" + "x" * 500])
        summary, _ = self.build()
        self.assertNotIn("\n", summary["Microsoft365"])           # entri berbaris banyak diringkas satu baris
        self.assertLess(len(summary["Microsoft365"]), 200)
        self.assertNotIn("10.0.0.0/8", self.read("Microsoft365_ip.csv"))

    def test_susut_lebih_dari_10_persen_tidak_menulis(self):
        self.build()
        before = self.snapshot()
        self.sources[bl.M365_URL] = m365(n_ips=20)                  # 32 -> 22 IP
        _, failed = self.build()
        self.assertRegex(failed["Microsoft365"], "IP susut")
        self.assertEqual(self.snapshot(), before)

    def test_sumber_rusak_atau_terlalu_kecil_tidak_menulis(self):
        for body, why in ((b"<html>bukan json</html>", "JSON"), (b'{"error": "x"}', "format"),
                          (m365(n_urls=0), "minimal")):
            self.sources[bl.M365_URL] = body
            _, failed = self.build()
            self.assertRegex(failed["Microsoft365"], why)
            self.assertEqual(self.names(), [])

    def test_satu_layanan_gagal_yang_lain_tetap_diperbarui(self):
        self.sources[bl.ZOOM_URL] = zoom_page()
        self.build(f"{DOCS}\n{ZOOM}\n")
        zoom_before = {n: t for n, t in self.snapshot().items() if n.startswith("Zoom_")}
        self.assertEqual(len(zoom_before), 4)
        del self.sources[bl.ZOOM_URL]                               # Zoom down
        self.sources[bl.M365_URL] = m365(n_urls=31)                 # Microsoft berubah
        summary, failed = self.build(f"{DOCS}\n{ZOOM}\n")
        self.assertEqual(list(failed), ["Zoom"])
        self.assertIn("unduh gagal", summary["Zoom"])
        self.assertEqual(len(self.read("Microsoft365_url.csv")), 34)  # tetap diperbarui
        self.assertEqual({n: t for n, t in self.snapshot().items() if n.startswith("Zoom_")}, zoom_before)

    def test_baris_dihapus_file_ikut_dihapus(self):
        self.build("Microsoft365 " + DOCS + "\nM365Lain " + DOCS + "\n")
        self.assertEqual(len(self.names()), 8)
        self.build("Microsoft365 " + DOCS + "\n")
        self.assertEqual(len(self.names()), 4)
        self.assertFalse((self.out / "M365Lain_url.csv").exists())
        self.build("# kosong\n")
        self.assertEqual(self.names(), [])

    def test_input_salah_ditolak(self):
        for line, why in (("Zoom https://support.zoom.com/hc/en/article?id=zm_kb&sysparm_article=KB0000001\n",
                           "belum didukung"),
                          ("https://learn.microsoft.com/en-us/microsoft-365/enterprise/"
                           "urls-and-ip-address-ranges?view=o365-21vianet\n", "belum didukung"),
                          ("https://ip-ranges.amazonaws.com/ip-ranges.json\n", "belum didukung"),
                          ("Microsoft365\n", "Nama"), ("rm -rf / " + DOCS + "\n", "Nama"),
                          ("../etc " + DOCS + "\n", "nama"),
                          (f"A {DOCS}\na {DOCS}\n", "dua kali")):
            with self.assertRaisesRegex(FeedError, why):
                self.build(line)
            self.assertFalse(self.out.exists())
            self.assertEqual(self.calls, [])

    def test_url_dokumentasi_tiap_vendor_dikenali(self):
        for url, name in ((DOCS, "Microsoft365"), (ZOOM, "Zoom"), (WEBEX, "Webex"), (GITHUB, "GitHub"),
                          ("https://api.github.com/meta", "GitHub"), (ATLASSIAN, "Atlassian"),
                          ("https://www.gstatic.com/ipranges/goog.json", "Google"),
                          ("https://s3.amazonaws.com/okta-ip-ranges/ip_ranges.json", "Okta"),
                          ("https://ip-ranges.salesforce.com/ip-ranges.json", "Salesforce"),
                          ("https://www.cloudflare.com/ips/", "Cloudflare_InboundOnly"),
                          ("https://api.cloudflare.com/client/v4/ips", "Cloudflare_InboundOnly"),
                          (ZSCALER, "Zscaler"), ("https://config.zscaler.com/api/zscalertwo.net/cenr/json", "Zscaler")):
            self.assertEqual(bl.adapter_for(url)[0], name, url)

    # ---- vendor dengan domain + IP

    def test_zoom_dari_tabel_artikel_kb(self):
        self.sources[bl.ZOOM_URL] = zoom_page()
        self.build(f"{ZOOM}\n")
        self.assertEqual(self.calls, [bl.ZOOM_URL])
        urls = self.read("Zoom_url.csv")
        self.assertEqual(urls[:4], ["*.zoom.com", "*.zoom.us", "cdn.cookielaw.org", "crl0.digicert.com"])
        self.assertEqual(len(urls), 14)                            # teks lain (port, "5.0", keterangan) diabaikan
        ips = self.read("Zoom_ip.csv")
        self.assertEqual(len(ips), 62)
        self.assertEqual(ips[0], "3.9.26.103/32")                  # IP tunggal dari kolom Source ikut
        self.assertEqual(ips[-1], "2620:123:2000::/40")
        self.assertIn(r"patterns,([^/]*\\.)?zoom\\.us(/.*)?$,trustworthy", self.read("Zoom_url_versa.csv"))

    def test_zoom_halaman_berubah_tidak_menulis(self):
        for body, why in ((b"<html><div id='app'></div></html>", "tidak ditemukan"),
                          (zoom_page(article=False), "tidak ditemukan"),
                          (b'<script type="application/ld+json">{rusak</script>', "JSON-LD"),
                          (zoom_page(n_ips=10), "minimal")):
            self.sources[bl.ZOOM_URL] = body
            _, failed = self.build(f"Zoom {ZOOM}\n")
            self.assertRegex(failed["Zoom"], why)
            self.assertEqual(self.names(), [])

    def test_webex(self):
        self.sources[bl.WEBEX_URL] = webex_page()
        self.build(f"{WEBEX}\n")
        urls = self.read("Webex_url.csv")
        self.assertEqual(len(urls), 23)
        self.assertIn("*.webexcontent.com", urls)                  # catatan kaki "(1)" diabaikan
        for ref in ("support.apple.com", "firebase.google.com", "clouddrive.com", "old.webex.com"):
            self.assertNotIn(ref, urls)                            # tautan di keterangan / riwayat revisi
        ips = self.read("Webex_ip.csv")
        self.assertEqual(len(ips), 24)                             # dua kolom IP, tanda '*' dibuang
        self.assertIn("4.152.0.0/24", ips)
        self.assertNotIn("163.129.0.0/16", ips)                    # IP lama di riwayat revisi
        self.sources[bl.WEBEX_URL] = b"<html>tanpa next data</html>"
        _, failed = self.build(f"{WEBEX}\n")
        self.assertRegex(failed["Webex"], "__NEXT_DATA__")

    def test_github(self):
        self.sources[bl.GITHUB_URL] = github_meta()
        summary, _ = self.build(f"{GITHUB}\n")
        self.assertNotIn("dilewati", summary["GitHub"])           # ssh_keys, kunci PGP, trust_domain "" tidak dilaporkan
        ips = self.read("GitHub_ip.csv")
        self.assertEqual(len(ips), 28)                             # git 140.82.0.0/24 sama dengan web
        self.assertNotIn("4.0.0.0/16", ips)                        # IP runner Actions (Azure) tidak ikut
        self.assertNotIn("13.105.117.0/31", ips)
        urls = self.read("GitHub_url.csv")
        self.assertEqual(len(urls), 13)                            # domains bersarang ikut, duplikat dibuang
        for shared in ("*.windows.net", "*.core.windows.net", "*.azureedge.net", "*.microsoft.com", "*.visualstudio.com"):
            self.assertNotIn(shared, urls)                         # wildcard Azure/Microsoft yang dipakai bersama
        self.assertIn("productionresultssa0.blob.core.windows.net", urls)   # domain spesifik tetap ikut
        self.assertIn("*.vscode-webview.net", urls)
        self.assertIn("ghcr.io", urls)
        self.assertIn("*.ghcr.io", urls)

    def test_atlassian(self):
        self.sources.update(atlassian_sources())
        self.build(f"{ATLASSIAN}\n")
        urls = self.read("Atlassian_url.csv")
        self.assertIn("api.atlassian.com", urls)                   # https://... -> nama host
        self.assertIn("*.svc0.atlassian.net", urls)
        self.assertEqual(len(urls), 11)
        self.assertFalse([u for u in urls if "gov" in u or "amazon" in u or "IC_BASE" in u])
        ips = self.read("Atlassian_ip.csv")
        self.assertEqual(len(ips), 62)                             # 60 JSON + 2 dari tabel
        self.assertNotIn("18.0.0.0/24", ips)                       # perimeter fedramp tidak ikut

    # ---- vendor yang hanya menerbitkan IP: dua file saja

    def test_google_goog_dikurangi_cloud(self):
        self.sources.update(google_sources())
        self.build("https://www.gstatic.com/ipranges/goog.json\n")
        self.assertEqual(self.names(), ["Google_ip.csv", "Google_ip_versa.csv"])
        ips = self.read("Google_ip.csv")
        self.assertIn("34.1.0.0/16", ips)                          # 34.0.0.0/15 minus 34.0.0.0/16
        self.assertNotIn("34.0.0.0/15", ips)
        self.assertNotIn("35.190.0.0/24", ips)                     # seluruhnya Google Cloud
        self.assertEqual(len(ips), 62)

    def test_okta_salesforce_cloudflare(self):
        okta = {"us_cell_1": {"ip_ranges": [f"3.97.{i}.0/26" for i in range(60)]},
                "apac_cell_1": {"ip_ranges": [f"3.98.{i}.0/26" for i in range(60)]}}
        sf = {"syncToken": "1", "prefixes": [{"region": "x", "provider": "aws",
                                              "ip_prefix": [f"141.163.{i}.0/24" for i in range(12)]}],
              "ipv6_prefixes": [{"region": "x", "provider": "aws", "ipv6_prefix": ["2a03:5d67:fe60::/45"]}]}
        cf = {"success": True, "errors": [], "result": {"ipv4_cidrs": [f"104.{i}.0.0/16" for i in range(16, 28)],
                                                         "ipv6_cidrs": ["2606:4700::/32"]}}
        self.sources.update({bl.OKTA_URL: json.dumps(okta).encode(), bl.SALESFORCE_URL: json.dumps(sf).encode(),
                             bl.CLOUDFLARE_URL: json.dumps(cf).encode()})
        _, failed = self.build("https://s3.amazonaws.com/okta-ip-ranges/ip_ranges.json\n"
                               "https://ip-ranges.salesforce.com/ip-ranges.json\nhttps://www.cloudflare.com/ips/\n")
        self.assertEqual(failed, {})
        self.assertEqual(self.names(), ["Cloudflare_InboundOnly_ip.csv", "Cloudflare_InboundOnly_ip_versa.csv",
                                        "Okta_ip.csv", "Okta_ip_versa.csv", "Salesforce_ip.csv",
                                        "Salesforce_ip_versa.csv"])
        self.assertEqual(len(self.read("Okta_ip.csv")), 120)
        self.assertEqual(self.read("Salesforce_ip.csv")[-1], "2a03:5d67:fe60::/45")
        self.assertEqual(self.read("Cloudflare_InboundOnly_ip_versa.csv")[0],
                         "Cloudflare_InboundOnly_ip1,ipv4-prefix,104.16.0.0/16")
        cf["success"] = False
        self.sources[bl.CLOUDFLARE_URL] = json.dumps(cf).encode()
        _, failed = self.build("https://www.cloudflare.com/ips/\n")
        self.assertRegex(failed["Cloudflare_InboundOnly"], "success")

    def test_zscaler_cloud_dari_url(self):
        self.sources.update(zscaler_sources("zscalertwo.net"))
        self.build("Zscaler2 https://config.zscaler.com/zscalertwo.net/cenr\n")
        ips = self.read("Zscaler2_ip.csv")
        self.assertEqual(len(ips), 104)                            # 100 + IPv6 kota + 2 svpn + 1 future
        self.assertIn("185.46.212.74/32", ips)
        self.assertIn("136.226.0.0/16", ips)
        self.assertTrue(all("zscalertwo.net" in u for u in self.calls))
        self.sources = zscaler_sources("zscaler.net")               # JSON untuk cloud lain: ditolak
        self.sources[f"https://config.zscaler.com/api/zscalertwo.net/cenr/json"] = \
            self.sources.pop("https://config.zscaler.com/api/zscaler.net/cenr/json")
        _, failed = self.build("Zscaler2 https://config.zscaler.com/zscalertwo.net/cenr\n")
        self.assertRegex(failed["Zscaler2"], "zscalertwo.net")


if __name__ == "__main__":
    sys.exit(unittest.main())
