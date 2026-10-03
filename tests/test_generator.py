"""
Tests for the synthetic data generator: the output is reproducible and every
planted data quality problem is actually present, so the SQL flags have
something to catch.

Run with:  python -m unittest discover tests
"""
import csv
import hashlib
import sys
import tempfile
import unittest
from contextlib import redirect_stdout
from io import StringIO
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "generator"))
import generate_data as gen  # noqa: E402


def read(folder: Path, name: str) -> list[dict]:
    with (folder / f"{name}.csv").open(encoding="utf-8", newline="") as f:
        return list(csv.DictReader(f))


def digest(folder: Path) -> str:
    h = hashlib.sha256()
    for path in sorted(folder.glob("*.csv")):
        h.update(path.read_bytes())
    return h.hexdigest()


class GeneratorTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.tmp = tempfile.TemporaryDirectory()
        cls.out = Path(cls.tmp.name) / "a"
        with redirect_stdout(StringIO()):
            gen.main(cls.out)
        cls.lines = read(cls.out, "sales_lines")
        cls.products = read(cls.out, "products")
        cls.fuel = read(cls.out, "fuel_card_transactions")
        cls.vehicles = read(cls.out, "vehicles")
        cls.telematics = read(cls.out, "telematics_monthly")

    @classmethod
    def tearDownClass(cls):
        cls.tmp.cleanup()

    def test_reproducible(self):
        other = Path(self.tmp.name) / "b"
        with redirect_stdout(StringIO()):
            gen.main(other)
        self.assertEqual(digest(self.out), digest(other))

    def test_all_files_written(self):
        for name in ("companies", "customers", "products", "delivery_notes", "sales_lines",
                     "vehicles", "fuel_card_transactions", "telematics_monthly"):
            self.assertTrue((self.out / f"{name}.csv").exists(), name)

    def test_snapshot_company_is_cut_at_cutoff(self):
        snapshot = [l for l in self.lines if l["company_id"] == str(gen.SNAPSHOT_COMPANY)]
        self.assertTrue(snapshot)
        self.assertTrue(all(l["posting_date"][:10] <= gen.SNAPSHOT_CUTOFF.isoformat() for l in snapshot))

    def test_planted_sales_problems(self):
        main = [l for l in self.lines if l["company_id"] == "1"]
        self.assertEqual(sum(l["service_date"].startswith("2052") for l in main), 1)
        self.assertEqual(sum(l["product_id"] == "3" for l in main), 3)
        self.assertTrue(any(float(l["amount"]) == 0 for l in main))
        self.assertTrue(any(l["service_date"] != l["posting_date"] for l in main))
        self.assertTrue(all(float(l["cost_amount"]) == 0 for l in main))

    def test_planted_catalogue_problems(self):
        regular = [p for p in self.products if p["company_id"] == "1" and int(p["product_id"]) >= 100]
        self.assertTrue(any(p["description"] == p["code"] for p in regular))
        self.assertEqual(sum(float(p["price"]) == 0 for p in regular), 1)

    def test_planted_fleet_problems(self):
        plates = {v["vehicle_id"] for v in self.vehicles}
        self.assertTrue(any(t["plate"] not in plates for t in self.fuel))
        self.assertTrue(any(t["operation_type"] == "R" and float(t["amount"]) < 0 for t in self.fuel))
        self.assertTrue(any(t["odometer_km"] == "0" for t in self.fuel))
        self.assertTrue(any(int(t["odometer_km"]) > 2_000_000 for t in self.fuel))
        retired = {v["vehicle_id"]: v["fleet_end_date"] for v in self.vehicles if v["fleet_end_date"]}
        self.assertTrue(any(t["plate"] in retired and str(t["operation_date"]) > retired[t["plate"]].replace("-", "")
                            for t in self.fuel))

    def test_planted_telematics_problems(self):
        self.assertEqual(sum(int(t["max_speed"]) > 130 for t in self.telematics), 1)
        last, drops = {}, 0
        for t in sorted(self.telematics, key=lambda r: (r["telematics_id"], r["month_end"])):
            if t["telematics_id"] in last and int(t["cumulative_km"]) < last[t["telematics_id"]]:
                drops += 1
            last[t["telematics_id"]] = int(t["cumulative_km"])
        self.assertEqual(drops, 1)


if __name__ == "__main__":
    unittest.main()
