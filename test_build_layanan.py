#!/usr/bin/env python3
"""Uji build_layanan.py dengan data sintetis (tanpa jaringan): python3 test_build_layanan.py"""
import json, sys, tempfile, unittest
from pathlib import Path

import build_layanan as bl
from build_feed import FeedError

DOCS = "https://learn.microsoft.com/en-us/microsoft-365/enterprise/urls-and-ip-address-ranges?view=o365-worldwide"
ZOOM = "https://support.zoom.com/hc/en/article?id=zm_kb&sysparm_article=KB0060548"


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


class Layanan(unittest.TestCase):
    def setUp(self):
        self.root = Path(tempfile.mkdtemp())
        self.out = self.root / "layanan"
        self.body = m365()
        self.calls = []

    def get(self, url):
        self.calls.append(url)
        return self.body

    def build(self, lines=f"Microsoft365 {DOCS}\n"):
        (self.root / "layanan_tambahan.txt").write_text(lines)
        return bl.build(self.root, self.get)

    def read(self, name):
        return (self.out / name).read_text().splitlines()

    def test_empat_file_dari_url_dokumentasi(self):
        self.build("# komentar\nMicrosoft365   " + DOCS + "   # semua endpoint\n")
        self.assertEqual(self.calls, [bl.M365_URL])               # data dari JSON resmi, bukan HTML
        self.assertEqual(sorted(p.name for p in self.out.iterdir()),
                         ["Microsoft365_ip.csv", "Microsoft365_ip_versa.csv",
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
        import re
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
        self.body = m365(extra_urls=["bukan domain", "a..b.com"], extra_ips=["10.0.0.0/8", "xyz"])
        summary = self.build()
        self.assertIn("dilewati 4", summary["Microsoft365"])
        self.assertNotIn("10.0.0.0/8", self.read("Microsoft365_ip.csv"))

    def test_susut_lebih_dari_10_persen_tidak_menulis(self):
        self.build()
        before = {p.name: p.read_text() for p in self.out.iterdir()}
        self.body = m365(n_ips=20)                                 # 32 -> 22 IP
        with self.assertRaisesRegex(FeedError, "IP susut"):
            self.build()
        self.assertEqual({p.name: p.read_text() for p in self.out.iterdir()}, before)

    def test_sumber_rusak_atau_terlalu_kecil_tidak_menulis(self):
        for body, why in ((b"<html>bukan json</html>", "JSON"), (b'{"error": "x"}', "format"),
                          (m365(n_urls=0), "minimal")):
            self.body = body
            with self.assertRaisesRegex(FeedError, why):
                self.build()
            self.assertFalse(self.out.exists())

    def test_baris_dihapus_file_ikut_dihapus(self):
        self.build("Microsoft365 " + DOCS + "\nM365Lain " + DOCS + "\n")
        self.assertEqual(len(list(self.out.iterdir())), 8)
        self.build("Microsoft365 " + DOCS + "\n")
        self.assertEqual(len(list(self.out.iterdir())), 4)
        self.assertFalse((self.out / "M365Lain_url.csv").exists())
        self.build("# kosong\n")
        self.assertEqual(list(self.out.iterdir()), [])

    def test_zoom_dari_tabel_artikel_kb(self):
        self.body = zoom_page()
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
            self.body = body
            with self.assertRaisesRegex(FeedError, why):
                self.build(f"Zoom {ZOOM}\n")
            self.assertFalse(self.out.exists())

    def test_input_salah_ditolak(self):
        for line, why in (("Zoom https://support.zoom.com/hc/en/article?id=zm_kb&sysparm_article=KB0000001\n",
                           "belum didukung"),
                          ("https://learn.microsoft.com/en-us/microsoft-365/enterprise/"
                           "urls-and-ip-address-ranges?view=o365-21vianet\n", "belum didukung"),
                          ("Microsoft365\n", "Nama"), ("rm -rf / " + DOCS + "\n", "Nama"),
                          ("../etc " + DOCS + "\n", "nama"),
                          (f"A {DOCS}\na {DOCS}\n", "dua kali")):
            with self.assertRaisesRegex(FeedError, why):
                self.build(line)
            self.assertFalse(self.out.exists())
            self.assertEqual(self.calls, [])


if __name__ == "__main__":
    sys.exit(unittest.main())
