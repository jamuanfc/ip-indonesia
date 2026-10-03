#!/usr/bin/env python3
"""Uji pengaman build_feed.py dengan data sintetis (tanpa jaringan): python3 test_build_feed.py"""
import gzip, sys, tempfile, unittest
from pathlib import Path

import build_feed as bf


def source(dir_, ris4, ris6=(), names=None):
    """Tulis asn.txt + riswhoisdump.IPv4/6.gz sintetis di dir_."""
    names = names or {64500: ("PT Contoh Satu", "ID"), 64501: ("PT Contoh Dua", "ID"),
                      8075: ("Microsoft Corporation", "US")}
    (dir_ / "asn.txt").write_text("".join(f"{a} HANDLE-{a} - {n}, {cc}\n" for a, (n, cc) in names.items()))
    for v, rows in ((4, ris4), (6, ris6)):
        body = "% komentar\n" + "".join(f"{a}\t{p}\t{peers}\n" for a, p, peers in rows)
        (dir_ / f"riswhoisdump.IPv{v}.gz").write_bytes(gzip.compress(body.encode()))


class Pengaman(unittest.TestCase):
    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp())
        self.src, self.out = self.tmp / "src", self.tmp / "repo"
        self.src.mkdir(), self.out.mkdir()
        bf.MIN_ASN_NAMES, bf.MIN_ROUTES, bf.MIN_ID_ASN, bf.MIN_ID_PREFIX = 1, {4: 1, 6: 0}, 1, 1
        self.ris4 = [(64500, f"103.{i}.0.0/24", 50) for i in range(20)] + [
            (64501, "36.64.0.0/11", 300), (8075, "20.0.0.0/11", 300),
            (64500, "10.0.0.0/8", 50),          # bogon: dibuang
            (64500, "1.0.0.0/7", 50),           # lebih lebar dari /8: dibuang
            (64501, "203.0.114.0/24", 1),       # hanya 1 peer: derau
            (64501, "{64500,64501}", 50)]       # AS-set: dilewati
        self.ris6 = [(64500, "2001:448a::/32", 200), (64500, "2001:db8::/32", 200)]

    def build(self):
        return bf.build(self.out, self.src)

    def test_feed_indonesia_ipv4_ipv6(self):
        source(self.src, self.ris4, self.ris6)
        self.build()
        lines = (self.out / "all_indonesia_ips.csv").read_text().split()
        self.assertEqual(len(lines), 22)
        self.assertIn("36.64.0.0/11", lines)
        self.assertIn("2001:448a::/32", lines)
        for bad in ("10.0.0.0/8", "1.0.0.0/7", "203.0.114.0/24", "2001:db8::/32", "20.0.0.0/11"):
            self.assertNotIn(bad, lines)
        self.assertEqual(lines[-1], "2001:448a::/32")          # IPv4 dulu, lalu IPv6
        self.assertIn('AS64500,"PT Contoh Satu",21', (self.out / "asn_indonesia.csv").read_text())
        self.assertEqual(list(self.out.glob("AS*_*.csv")), [])  # tanpa asn_tambahan: tanpa file per ASN
        world = (self.out / "asn_dunia.csv").read_text().splitlines()
        self.assertEqual(world[0], "asn,nama,negara,jumlah_prefix")
        self.assertIn('AS8075,"Microsoft Corporation",US,1', world)  # ASN luar negeri ikut, tanpa file per ASN
        self.assertEqual(len(world), 4)

    def test_susut_lebih_dari_10_persen_tidak_menulis(self):
        source(self.src, self.ris4, self.ris6)
        self.build()
        before = (self.out / "all_indonesia_ips.csv").read_text()
        source(self.src, self.ris4[15:], self.ris6)              # 15 prefix hilang dari 22
        with self.assertRaisesRegex(bf.FeedError, "susut"):
            self.build()
        self.assertEqual((self.out / "all_indonesia_ips.csv").read_text(), before)

    def test_sumber_kosong_tidak_menulis(self):
        source(self.src, self.ris4, self.ris6)
        self.build()
        before = (self.out / "all_indonesia_ips.csv").read_text()
        bf.MIN_ROUTES = {4: 1000, 6: 0}
        with self.assertRaisesRegex(bf.FeedError, "rute"):
            self.build()
        self.assertEqual((self.out / "all_indonesia_ips.csv").read_text(), before)

    def test_asn_tambahan_dibuat_lalu_dihapus(self):
        source(self.src, self.ris4, self.ris6)
        (self.out / "asn_tambahan.txt").write_text("# komentar\nAS8075   # Microsoft\n")
        self.build()
        f = self.out / "AS8075_Microsoft_Corporation.csv"
        self.assertEqual(f.read_text(), "20.0.0.0/11\n")
        (self.out / "asn_tambahan.txt").write_text("# kosong\n")
        self.build()
        self.assertFalse(f.exists())

    def test_asn_tambahan_tanpa_rute_mempertahankan_file_lama(self):
        source(self.src, self.ris4, self.ris6)
        (self.out / "asn_tambahan.txt").write_text("8075\n")
        self.build()
        source(self.src, [r for r in self.ris4 if r[0] != 8075], self.ris6)
        self.build()
        self.assertTrue((self.out / "AS8075_Microsoft_Corporation.csv").exists())

    def test_isi_asn_tambahan_salah_ditolak(self):
        source(self.src, self.ris4, self.ris6)
        for bad, why in (("rm -rf /\n", "bukan nomor ASN"), ("4294967295\n", "tidak terdaftar")):
            (self.out / "asn_tambahan.txt").write_text(bad)
            with self.assertRaisesRegex(bf.FeedError, why):
                self.build()
            self.assertFalse((self.out / "all_indonesia_ips.csv").exists())


if __name__ == "__main__":
    sys.exit(unittest.main())
