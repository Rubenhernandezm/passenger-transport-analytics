#!/usr/bin/env python3
"""
Synthetic data generator for a fictional passenger transport company
("Autocares Demo S.L.").

Every record produced here is invented: customers, tax IDs, plates, routes,
amounts and fuel transactions come from random draws with a fixed seed, so the
output is reproducible. Typical data quality problems are planted on purpose
so that the SQL layer has something real to detect and flag.

Usage:
    python generator/generate_data.py             # writes ./data/*.csv
    python generator/generate_data.py --out tmp   # custom output folder

Standard library only (Python 3.10+).
"""
from __future__ import annotations

import argparse
import csv
import math
import random
from datetime import date, timedelta
from pathlib import Path

SEED = 42
START = date(2024, 1, 1)
END = date(2026, 9, 30)
TELEMATICS_START = date(2025, 1, 1)
SNAPSHOT_CUTOFF = date(2024, 7, 15)

MAIN_COMPANY = 1          # the operating company
TEST_COMPANIES = (2, 3)   # sandbox environments left inside the ERP
SNAPSHOT_COMPANY = 4      # frozen copy of company 1 taken before a year-end close

NIF_LETTERS = "TRWAGMYFPDXBNJZSQVHLCKE"
PLATE_LETTERS = "BCDFGHJKLMNPRSTVWXYZ"

TOWNS = ["Villaclara", "Montealto", "Fuentemayor", "Valdecielo", "Torrealba",
         "Peñarroja", "Navaluz", "Robledal", "Castrobravo", "Arroyoverde",
         "Sierramar", "Lomahermosa", "Riosol", "Valleseco", "Hontanar", "Prado Alto"]
PROVINCES = ["Madrid", "Toledo", "Zaragoza", "Valencia", "Burgos", "Navarra",
             "La Rioja", "Cáceres", "Valladolid", "Asturias"]
CITIES = ["Madrid", "Valencia", "Sevilla", "Bilbao", "Zaragoza", "Granada",
          "Santiago de Compostela", "Oviedo", "Málaga", "Toledo", "Segovia",
          "Cáceres", "Burgos", "Pamplona", "San Sebastián", "Córdoba", "Alicante", "Santander"]
ABROAD = ["Oporto", "Lisboa", "París", "Burdeos", "Roma", "Andorra la Vella",
          "Lourdes", "Fátima", "Ginebra", "Florencia"]
FIRST_NAMES = ["Lucía", "Hugo", "Martina", "Mateo", "Sofía", "Leo", "Julia", "Daniel",
               "Paula", "Pablo", "Carmen", "Javier", "Elena", "Álvaro", "Marta", "Diego",
               "Laura", "Sergio", "Irene", "Raúl", "Nerea", "Adrián", "Sara", "Iván"]
SURNAMES = ["García", "Martín", "López", "Sánchez", "Pérez", "Gómez", "Ruiz", "Díaz",
            "Moreno", "Muñoz", "Álvarez", "Romero", "Navarro", "Torres", "Domínguez",
            "Vázquez", "Ramos", "Gil", "Serrano", "Blanco", "Molina", "Ortega", "Delgado"]
SCHOOL_NAMES = ["Río Claro", "Los Pinares", "La Vega", "Miguel Hernández", "El Mirador",
                "Las Encinas", "San Isidro", "La Fuente", "Valle Verde", "El Castillo",
                "Los Olivos", "Santa Ana", "Antonio Machado", "La Ribera"]
AGENCY_A = ["Viajes", "Turismo", "Excursiones", "Eventos", "Congresos"]
AGENCY_B = ["Horizonte", "Alba", "Cumbre", "Brisa", "Faro", "Senda", "Rumbo",
            "Delta", "Aurora", "Mirador", "Estela", "Cierzo"]
STATIONS = [("EESS A-1 km 102", "Madrid"), ("EESS A-6 km 187", "Ávila"),
            ("EESS A-62 km 124", "Valladolid"), ("EESS N-630 km 340", "Cáceres"),
            ("EESS AP-6 km 61", "Segovia"), ("EESS A-66 km 255", "Zamora"),
            ("EESS Polígono Norte", "Madrid"), ("EESS Ronda Sur", "Valladolid")]
STATIONS_PT = [("Posto A25 Guarda", "Portugal"), ("Posto IP5 Viseu", "Portugal")]

# Raw product descriptions as a fuel-card provider might print them (deliberately messy).
DIESEL_DESC = [("DIESEL E+", "D01", 0.62), ("DIE E+", "D02", 0.24), ("DSL", "D03", 0.05),
               ("GASOLEO", "D04", 0.05), ("DIESEL E+1", "D05", 0.04)]
DIESEL_DESC_PT = [("GASOLEO AÇ", "D06"), ("DSL AÇO", "D07")]
ADBLUE_DESC = [("BLUE+GRANE", "A01", 0.62), ("ADB+GRN", "A02", 0.30), ("ADBLUE", "A03", 0.08)]
PETROL_DESC = [("EFI 95", "G01", 0.6), ("EFITEC 95", "G02", 0.4)]

NAT_SEASON = {1: .55, 2: .70, 3: .95, 4: 1.15, 5: 1.35, 6: 1.40,
              7: 1.05, 8: .80, 9: 1.00, 10: 1.15, 11: .90, 12: .75}
INT_SEASON = {1: .20, 2: .40, 3: 1.30, 4: 1.60, 5: 1.00, 6: 1.50,
              7: 1.90, 8: 1.60, 9: .90, 10: .60, 11: .30, 12: .40}
WEEKDAY = [0.80, 0.75, 0.80, 0.95, 1.35, 1.50, 0.85]          # Mon..Sun
GROWTH = {2024: 1.00, 2025: 1.08, 2026: 1.13}                   # volume growth
PRICE = {2024: 1.00, 2025: 1.03, 2026: 1.06}                    # price inflation


# --------------------------------------------------------------------------- helpers
def days(a: date, b: date):
    d = a
    while d <= b:
        yield d
        d += timedelta(days=1)


def months(a: date, b: date):
    y, m = a.year, a.month
    while (y, m) <= (b.year, b.month):
        yield y, m
        y, m = (y + 1, 1) if m == 12 else (y, m + 1)


def month_end(y: int, m: int) -> date:
    nxt = date(y + 1, 1, 1) if m == 12 else date(y, m + 1, 1)
    return nxt - timedelta(days=1)


def poisson(rng: random.Random, lam: float) -> int:
    limit, k, p = math.exp(-lam), 0, 1.0
    while True:
        p *= rng.random()
        if p <= limit:
            return k
        k += 1


def weighted(rng: random.Random, items):
    """Pick from tuples whose last element is the weight; returns the rest."""
    pick = rng.choices(items, weights=[i[-1] for i in items])[0]
    rest = pick[:-1]
    return rest if len(rest) > 1 else rest[0]


def money(x: float) -> str:
    return f"{x:.2f}"


def dt(d: date) -> str:
    return f"{d.isoformat()} 00:00:00"


def nif_person(rng):
    n = rng.randint(10_000_000, 99_999_999)
    return f"{n}{NIF_LETTERS[n % 23]}"


def nie(rng):
    prefix, n = rng.choice("XY"), rng.randint(1_000_000, 9_999_999)
    return f"{prefix}{n}{NIF_LETTERS[int(('0' if prefix == 'X' else '1') + str(n)) % 23]}"


def entity_id(rng, letter):
    return f"{letter}{rng.randint(1_000_000, 9_999_999)}{rng.choice('ABCDEFGHIJ0123456789')}"


def vin(rng):
    return "".join(rng.choice("ABCDEFGHJKLMNPRSTUVWXYZ0123456789") for _ in range(17))


# --------------------------------------------------------------------------- master data
def build_customers(rng):
    customers, groups = [], {}

    def add(group, name, tax_id, city, country=""):
        cid = len(customers) + 1
        customers.append({"company_id": MAIN_COMPANY, "customer_id": cid, "code": f"C{cid:05d}",
                          "name": name, "legal_name": name.upper(), "tax_id": tax_id,
                          "city": city, "province": rng.choice(PROVINCES), "country_code": country})
        groups.setdefault(group, []).append(cid)

    for zone in ("Norte", "Sur", "Este"):
        add("education_dept", f"Dirección Territorial de Educación - Zona {zone}",
            entity_id(rng, "S"), rng.choice(TOWNS))
    for town in TOWNS[:14]:
        add("council", f"Ayuntamiento de {town}", entity_id(rng, "P"), town)
    schools = [(kind, name) for kind in ("IES", "CEIP") for name in SCHOOL_NAMES]
    for kind, name in rng.sample(schools, 18):
        town = rng.choice(TOWNS)
        add("public", f"{kind} {name} ({town})", entity_id(rng, "Q"), town)
    add("public", "Universidad Demo", entity_id(rng, "Q"), "Montealto")
    add("public", "Hospital Comarcal de Navaluz", entity_id(rng, "Q"), "Navaluz")
    for saint in ("Pedro", "Juan", "Andrés", "Miguel", "Esteban"):
        town = rng.choice(TOWNS)
        add("religious", f"Parroquia de San {saint} ({town})", entity_id(rng, "R"), town)
    for town in rng.sample(TOWNS, 8):
        add("association", f"Club Deportivo {town}", entity_id(rng, "G"), town)
    for town in rng.sample(TOWNS, 6):
        add("association", f"Asociación Cultural {town}", entity_id(rng, "G"), town)
    for a, b in rng.sample([(a, b) for a in AGENCY_A for b in AGENCY_B], 30):
        add("agency", f"{a} {b} S.L.", entity_id(rng, "B"), rng.choice(CITIES))
    for name in ("Bodegas Valleseco S.L.", "Congresos Meridiano S.L.", "Logística Riosol S.L.",
                 "Cafetería Estación Demo S.L.", "Hotel Prado Alto S.L.", "Colegio Concertado Alba S.L."):
        add("company", name, entity_id(rng, "B"), rng.choice(TOWNS))
    for name in ("Iberbus Motor S.A.", "Carrocerías Península S.A.", "Autobuses Meridiano S.A."):
        add("manufacturer", name, entity_id(rng, "A"), "Madrid")
    for _ in range(180):
        name = f"{rng.choice(FIRST_NAMES)} {rng.choice(SURNAMES)} {rng.choice(SURNAMES)}"
        add("individual", name, nie(rng) if rng.random() < 0.06 else nif_person(rng), rng.choice(TOWNS))
    for _ in range(12):                                   # walk-in customers, no tax ID captured
        add("individual", f"{rng.choice(FIRST_NAMES)} {rng.choice(SURNAMES)}", "", rng.choice(TOWNS))
    foreign = [("FR", lambda: f"FR{rng.randint(10**10, 10**11 - 1)}", "Voyages {} SARL", "Lyon"),
               ("DE", lambda: f"DE{rng.randint(10**8, 10**9 - 1)}", "{} Reisen GmbH", "Köln"),
               ("PT", lambda: f"PT{rng.randint(10**8, 10**9 - 1)}", "Viagens {} Lda", "Braga"),
               ("IT", lambda: f"IT{rng.randint(10**10, 10**11 - 1)}", "Viaggi {} Srl", "Torino"),
               ("CH", lambda: f"CHE{rng.randint(100, 999)}.{rng.randint(100, 999)}.{rng.randint(100, 999)}",
                "{} Tours AG", "Bern"),
               ("GB", lambda: f"GB{rng.randint(10**8, 10**9 - 1)}", "{} Travel Ltd", "Leeds")]
    for i in range(28):
        country, tax, pattern, city = foreign[i % len(foreign)]
        add("foreign", pattern.format(rng.choice(AGENCY_B)), tax(), city,
            country if rng.random() < 0.08 else "")      # the country field is almost never filled
    for cid in rng.sample(range(1, len(customers) + 1), 4):
        customers[cid - 1]["country_code"] = customers[cid - 1]["country_code"] or "ES"
    return customers, groups


def build_products(rng):
    products = [
        (1, "NAC", "TRAYECTO NACIONAL", 1, 0.0),
        (2, "INT", "TRAYECTO INTERNACIONAL", 4, 0.0),
        (3, "VEH", "VENTA VEHICULO", 1, 0.0),          # same accounting group as transport!
    ]
    routes = []
    pairs = rng.sample([(a, b) for a in TOWNS for b in TOWNS if a != b], 20)
    for i, (a, b) in enumerate(pairs):
        pid, code = 100 + i, f"RL{1100 + i}"
        name = f"{a.upper()} - {b.upper()}" if i < 4 else code     # most lines only carry the code
        price = 0.0 if i == 7 else round(rng.uniform(55, 190), 2)  # one line with no tariff in the catalogue
        products.append((pid, code, name, 1, price))
        routes.append({"product_id": pid, "code": code, "price": price})
    products += [(40, "COM", "COMISIONES", 5, 0.0),
                 (41, "SIVA", "SERVICIOS IVA INCLUIDO", 6, 0.0),
                 (42, "ALQ", "ALQUILER LOCAL", 7, 850.0)]
    rows = [{"company_id": MAIN_COMPANY, "product_id": p, "code": c, "description": d,
             "accounting_group": g, "price": money(pr)} for p, c, d, g, pr in products]
    return rows, routes


# --------------------------------------------------------------------------- sales
class Ledger:
    def __init__(self, customers):
        self.names = {c["customer_id"]: c["name"] for c in customers}
        self.notes, self.lines = [], []
        self.note_seq, self.line_seq = 20_000, 600_000

    def note(self, customer_id, note_date, items):
        """items: (product_id, description, service_date, quantity, unit_price, amount)"""
        note_date = min(note_date, END)
        self.note_seq += 1
        self.notes.append({"company_id": MAIN_COMPANY, "delivery_note_id": self.note_seq,
                           "note_date": note_date.isoformat(), "customer_id": customer_id,
                           "customer_name": self.names[customer_id]})
        for no, (pid, desc, sdate, qty, unit, amount) in enumerate(items, 1):
            self.line_seq += 1
            self.lines.append({"company_id": MAIN_COMPANY, "line_id": self.line_seq, "line_no": no,
                               "delivery_note_id": self.note_seq, "product_id": pid,
                               "description": desc, "service_date": dt(sdate),
                               "posting_date": dt(note_date),            # mirrors the header date
                               "quantity": money(qty), "unit_price": money(unit),
                               "amount": money(amount), "cost_amount": "0.00"})  # cost field never used


def dir3(rng, prefix):
    return f"{prefix}{rng.randint(10**6, 10**7 - 1)}"


def build_sales(rng, customers, groups, routes):
    led = Ledger(customers)
    nat_pool = [("individual", .25), ("association", .18), ("agency", .25), ("public", .12),
                ("council", .08), ("religious", .04), ("company", .08)]
    int_pool = [("foreign", .55), ("agency", .35), ("public", .10)]
    seats = [(19, .6, .10), (35, .8, .20), (55, 1.0, .45), (60, 1.05, .15), (70, 1.25, .10)]
    public_groups = {"education_dept", "council", "public"}
    group_of = {cid: g for g, ids in groups.items() for cid in ids}

    def admin_lines(customer_id, pid, d, prob=1.0):
        """Public-sector paperwork: zero-amount reference lines on the same delivery note."""
        if group_of[customer_id] not in public_groups or rng.random() > prob:
            return []
        lines = [(pid, f"Órgano Gestor: {dir3(rng, 'A07')}", d, 0, 0, 0)]
        if rng.random() < 0.6:
            lines.append((pid, f"Unidad Tramitadora: {dir3(rng, 'GE0')}", d, 0, 0, 0))
        return lines

    for d in days(START, END):
        growth, price = GROWTH[d.year], PRICE[d.year]
        # national charters
        for _ in range(poisson(rng, 8.5 * NAT_SEASON[d.month] * WEEKDAY[d.weekday()] * growth)):
            cid = rng.choice(groups[weighted(rng, nat_pool)])
            n_seats, factor = weighted(rng, seats)
            lo, hi = weighted(rng, [((150, 600), .5), ((500, 1400), .35), ((1200, 3200), .15)])
            origin, dest = rng.sample(CITIES, 2)
            amount = round(rng.uniform(lo, hi) * factor * price, 2)
            items = [(1, f"{origin} - {dest} {n_seats} pl", d, 1, amount, amount)]
            if rng.random() < 0.15:                              # return leg on the same delivery note
                back = round(amount * rng.uniform(0.8, 1.0), 2)
                items.append((1, f"{dest} - {origin} {n_seats} pl",
                              d + timedelta(days=rng.randint(0, 3)), 1, back, back))
            items += admin_lines(cid, 1, d, prob=0.3)
            led.note(cid, d + timedelta(days=rng.choice([0, 0, 1, 3, 7, 12, 20])), items)
        # international charters
        for _ in range(poisson(rng, 0.35 * INT_SEASON[d.month] * growth)):
            cid = rng.choice(groups[weighted(rng, int_pool)])
            n_seats, _factor = weighted(rng, seats)
            ndays = rng.randint(2, 12)
            amount = round(rng.uniform(1800, 9000) * price, 2)
            items = [(2, f"{rng.choice(CITIES)} - {rng.choice(ABROAD)} ({ndays} días) {n_seats} pl",
                      d, 1, amount, amount)]
            items += admin_lines(cid, 2, d, prob=0.3)
            led.note(cid, d + timedelta(days=ndays + rng.randint(0, 15)), items)

    # regular lines: school routes billed monthly to education departments, plus council routes
    school, council_routes = routes[:14], routes[14:]
    owner = {r["product_id"]: rng.choice(groups["education_dept"]) for r in school}
    owner.update({r["product_id"]: rng.choice(groups["council"]) for r in council_routes})
    trip_price = {r["product_id"]: r["price"] or round(rng.uniform(80, 140), 2) for r in routes}
    for y, m in months(START, END):
        last = month_end(y, m)
        weekdays = sum(1 for d in days(date(y, m, 1), last) if d.weekday() < 5)
        by_customer = {}
        for r in routes:
            is_school = r in school
            if is_school and m in (7, 8):
                continue
            qty = weekdays - (rng.randint(4, 8) if is_school and m in (6, 9, 12) else rng.randint(0, 2))
            unit = round(trip_price[r["product_id"]] * PRICE[y], 2)
            by_customer.setdefault(owner[r["product_id"]], []).append(
                (r["product_id"], r["code"], last, qty, unit, round(qty * unit, 2)))
        for cid, items in by_customer.items():
            items += admin_lines(cid, items[0][0], last)
            led.note(cid, last + timedelta(days=rng.randint(0, 5)), items)
        # non-transport lines that live in the same table
        for _ in range(2):
            fee = round(rng.uniform(60, 450), 2)
            led.note(rng.choice(groups["agency"]), last, [(40, "Comisión agencia", last, 1, fee, fee)])
        led.note(groups["company"][3], last, [(42, "Alquiler local estación", last, 1, 850, 850)])
        for _ in range(4):
            fee = round(rng.uniform(20, 150), 2)
            led.note(rng.choice(groups["individual"]), last, [(41, "Servicio de guía", last, 1, fee, fee)])

    # used-coach sales recorded with a product that shares the transport accounting group
    for d, amount in ((date(2024, 3, 12), 62000.0), (date(2025, 2, 20), 118500.0), (date(2026, 5, 7), 167000.0)):
        led.note(rng.choice(groups["manufacturer"]), d,
                 [(3, f"Venta autocar usado bastidor {vin(rng)}", d, 1, amount, amount)])

    # one typo in a service date: 2025 typed as 2052
    candidates = [l for l in led.lines if l["product_id"] == 1 and l["service_date"].startswith("2025-05")]
    typo = rng.choice(candidates)
    typo["service_date"] = "2052" + typo["service_date"][4:]
    return led


def build_other_companies(customers, products, led):
    companies = [
        {"company_id": 1, "name": "Autocares Demo S.L.", "tax_id": "B00000001"},
        {"company_id": 2, "name": "EMPRESA PRUEBA", "tax_id": ""},
        {"company_id": 3, "name": "Demo pruebas", "tax_id": ""},
        {"company_id": 4, "name": "COPIA AUTOCARES DEMO 2024 ANTES DE CIERRE", "tax_id": "B00000001"},
    ]
    rng = random.Random(SEED + 1)
    extra_c, extra_p, extra_n, extra_l = [], [], [], []
    for comp in TEST_COMPANIES:
        extra_c.append({**customers[0], "company_id": comp, "customer_id": 1, "code": "C00001",
                        "name": "CLIENTE PRUEBA", "legal_name": "CLIENTE PRUEBA", "tax_id": ""})
        extra_p += [{**p, "company_id": comp} for p in products if p["product_id"] in (1, 2, 3)]
        for i in range(25):
            d = START + timedelta(days=rng.randint(0, 600))
            amount = money(rng.uniform(1, 999))
            extra_n.append({"company_id": comp, "delivery_note_id": 1 + i, "note_date": d.isoformat(),
                            "customer_id": 1, "customer_name": "CLIENTE PRUEBA"})
            extra_l.append({"company_id": comp, "line_id": 1 + i, "line_no": 1, "delivery_note_id": 1 + i,
                            "product_id": rng.choice([1, 2]), "description": "PRUEBA", "service_date": dt(d),
                            "posting_date": dt(d), "quantity": "1.00", "unit_price": amount,
                            "amount": amount, "cost_amount": "0.00"})
    # frozen snapshot: an exact copy of company 1 up to the cut-off date
    cutoff = SNAPSHOT_CUTOFF.isoformat()
    extra_c += [{**c, "company_id": SNAPSHOT_COMPANY} for c in customers]
    extra_p += [{**p, "company_id": SNAPSHOT_COMPANY} for p in products]
    kept = {n["delivery_note_id"] for n in led.notes if n["note_date"] <= cutoff}
    extra_n += [{**n, "company_id": SNAPSHOT_COMPANY} for n in led.notes if n["delivery_note_id"] in kept]
    extra_l += [{**l, "company_id": SNAPSHOT_COMPANY} for l in led.lines if l["delivery_note_id"] in kept]
    return companies, extra_c, extra_p, extra_n, extra_l


# --------------------------------------------------------------------------- fleet
def build_fleet(rng):
    vehicles, params, used = [], {}, set()

    def new_plate():
        while True:
            p = f"{rng.randint(0, 9999):04d}{''.join(rng.choice(PLATE_LETTERS) for _ in range(3))}"
            if p not in used:
                used.add(p)
                return p

    coach_brands = [("IVECO", .25), ("Iveco", .05), ("MAN", .15), ("Man", .05), ("MAN / IRIZAR", .10),
                    ("MERCEDES", .10), ("MERCEDES BENZ", .08), ("SCANIA", .10), ("VOLVO", .07), ("IRIZAR", .05)]
    spec = ([("Coach", coach_brands)] * 32
            + [("Minibus", [("MERCEDES", .5), ("Mercedes Benz", .2), ("IVECO", .3)])] * 4
            + [("Car", [("SEAT", .4), ("TOYOTA", .35), ("Toyota", .1), ("SKODA", .15)])] * 7
            + [("Company car", [("VOLKSWAGEN", .6), ("SEAT", .4)])] * 3)
    retired = set(rng.sample(range(36), 9))
    for i, (kind, brands) in enumerate(spec):
        plate = new_plate()
        newcomer = rng.random() < 0.2
        start = (date(2024, 2, 1) + timedelta(days=rng.randint(0, 860))) if newcomer \
            else (date(2015, 1, 1) + timedelta(days=rng.randint(0, 3200)))
        first_reg = start if newcomer and rng.random() < 0.5 else start - timedelta(days=rng.randint(0, 6 * 365))
        end = None
        if i in retired and not newcomer:
            end = date(2024, 3, 1) + timedelta(days=rng.randint(0, 820))
        heavy = kind in ("Coach", "Minibus")
        vehicles.append({
            "vehicle_id": plate, "vehicle_type": kind, "brand": weighted(rng, brands), "chassis": vin(rng),
            "fuel_card_id": f"FC-{1000 + i}" if rng.random() < 0.96 else "",
            "toll_card_id": f"TC-{2000 + i}" if kind == "Coach" and rng.random() < 0.7 else "",
            "telematics_id": f"TLM-{3000 + i}" if heavy and rng.random() < 0.85 else "",
            "first_registration_date": first_reg.isoformat(), "fleet_start_date": start.isoformat(),
            "fleet_end_date": end.isoformat() if end else "", "status": "Retired" if end else "Active"})
        params[plate] = {
            "kind": kind, "start": start, "end": end,
            "base_km": rng.uniform(150, 320) if kind == "Coach"
            else rng.uniform(90, 180) if kind == "Minibus" else rng.uniform(35, 80),
            "l100": rng.uniform(28, 34) if kind == "Coach"
            else rng.uniform(14, 17) if kind == "Minibus" else rng.uniform(6, 8),
            "tank": (220, 420) if kind == "Coach" else (60, 90) if kind == "Minibus" else (35, 50),
            "odometer": rng.uniform(150_000, 900_000) if heavy and not newcomer else rng.uniform(2_000, 150_000),
            "petrol": kind in ("Car", "Company car") and rng.random() < 0.5,
        }
    return vehicles, params


def daily_km(rng, p, d):
    kind, wd = p["kind"], d.weekday()
    if kind in ("Coach", "Minibus"):
        idle = 0.12 if wd < 5 else 0.35
        season = 1.25 if d.month in (6, 7) else 0.9 if d.month in (1, 2, 11) else 1.0
    else:
        idle, season = (0.15 if wd < 5 else 0.6), 1.0
    if rng.random() < idle:
        return 0.0
    return p["base_km"] * season * rng.uniform(0.6, 1.4)


def fuel_price(rng, d, petrol=False):
    base = 1.46 + 0.07 * math.sin(2 * math.pi * d.timetuple().tm_yday / 365) + 0.03 * (d.year - 2024)
    return round(base + (0.14 if petrol else 0) + rng.gauss(0, 0.015), 3)


def simulate_fleet(rng, vehicles, params):
    tx, daily = [], {}

    def add(plate, card, d, odo, desc, code, litres, unit, amount, op="S", station=None):
        st, prov = station or rng.choice(STATIONS)
        if rng.random() < 0.03:
            reading = 0                                            # driver skipped the odometer
        elif rng.random() < 0.003:
            reading = int(odo) * 10 + rng.randint(0, 9)            # extra digit typed
        else:
            reading = int(odo)
        tx.append({"card_id": card, "plate": plate, "operation_date": int(d.strftime("%Y%m%d")),
                   "operation_time": f"{rng.randint(6, 22):02d}:{rng.randint(0, 59):02d}",
                   "station_name": st, "station_province": prov, "odometer_km": reading,
                   "product_code": code, "product_desc": desc, "litres": money(litres),
                   "unit_price": f"{unit:.3f}" if unit else "", "amount": money(amount), "operation_type": op})

    for v in vehicles:
        plate, card, p = v["vehicle_id"], v["fuel_card_id"], params[v["vehicle_id"]]
        first, last = max(START, p["start"]), min(END, p["end"] or END)
        odo, consumed, threshold = p["odometer"], 0.0, rng.uniform(*p["tank"])
        heavy = p["kind"] in ("Coach", "Minibus")
        daily[plate] = {}
        for d in days(first, last):
            km = daily_km(rng, p, d)
            odo += km
            daily[plate][d] = (km, odo)
            if not card:
                continue
            consumed += km * p["l100"] / 100
            if consumed >= threshold:
                litres = consumed
                abroad = heavy and rng.random() < 0.03
                if p["petrol"]:
                    desc, code = weighted(rng, PETROL_DESC)
                else:
                    desc, code = rng.choice(DIESEL_DESC_PT) if abroad else weighted(rng, DIESEL_DESC)
                unit = fuel_price(rng, d, p["petrol"])
                station = rng.choice(STATIONS_PT) if abroad else None
                add(plate, card, d, odo, desc, code, litres, unit, litres * unit, station=station)
                if rng.random() < 0.003:                           # refund of a wrong charge
                    add(plate, card, d, odo, desc, code, -litres, unit, -litres * unit, op="R", station=station)
                if p["kind"] == "Coach" and rng.random() < 0.30:
                    ad_l = litres * rng.uniform(0.03, 0.06)
                    ad_desc, ad_code = weighted(rng, ADBLUE_DESC)
                    ad_unit = round(rng.uniform(0.78, 0.95), 3)
                    add(plate, card, d, odo, ad_desc, ad_code, ad_l, ad_unit, ad_l * ad_unit, station=station)
                consumed, threshold = 0.0, rng.uniform(*p["tank"])
            if km and p["kind"] == "Coach" and rng.random() < 0.012:
                add(plate, card, d, odo, "AUTOPISTAS", "PJ", 0, 0, rng.uniform(6, 65))
            if km and rng.random() < 0.005:
                add(plate, card, d, odo, "LAVADOS", "LV", 0, 0, rng.uniform(15, 45))
            if heavy and rng.random() < 0.0025:
                add(plate, card, d, odo, rng.choice(["TALLER", "LUBRICANTE"]), "TL", 0, 0, rng.uniform(25, 180))

    # a card left active after its coach was retired
    gone = next(v for v in vehicles if v["status"] == "Retired" and v["fuel_card_id"] and v["vehicle_type"] == "Coach")
    end = date.fromisoformat(gone["fleet_end_date"])
    last_odo = daily[gone["vehicle_id"]][end][1]
    for extra in (12, 37):
        d = end + timedelta(days=extra)
        if d <= END:
            unit = fuel_price(rng, d)
            add(gone["vehicle_id"], gone["fuel_card_id"], d, last_odo, "DIESEL E+", "D01", 210, unit, 210 * unit)
    # a hired coach refuelled with a company card: plate not in the fleet register
    for d in (date(2025, 7, 3), date(2025, 7, 9), date(2025, 7, 15), date(2025, 7, 21), date(2025, 8, 2)):
        unit = fuel_price(rng, d)
        add("4821MZK", "FC-9001", d, 0, "DIESEL E+", "D01", 300, unit, 300 * unit)

    tx.sort(key=lambda t: (t["operation_date"], t["operation_time"], t["plate"]))
    for i, t in enumerate(tx, 1):
        t["transaction_id"] = i
    return tx, daily


def build_telematics(rng, vehicles, daily):
    rows = []
    tracked = [v for v in vehicles if v["telematics_id"]]
    # pick vehicles that are in service over the whole telematics period
    full = [v for v in tracked if TELEMATICS_START in daily[v["vehicle_id"]] and END in daily[v["vehicle_id"]]]
    replaced = full[0]["telematics_id"]                        # device swapped -> counter restarts
    glitch = (full[1]["telematics_id"], (2025, 11))            # GPS spike in max speed
    for v in tracked:
        series, offset = daily[v["vehicle_id"]], None
        for y, m in months(TELEMATICS_START, END):
            month_days = [d for d in series if d.year == y and d.month == m]
            if not month_days:
                continue
            km = sum(series[d][0] for d in month_days)
            cumulative = series[max(month_days)][1]
            if v["telematics_id"] == replaced and (y, m) >= (2025, 10):
                if offset is None:
                    offset = cumulative - km - rng.uniform(500, 2500)
                cumulative -= offset
            max_speed = rng.randint(99, 108) if v["vehicle_type"] == "Coach" else rng.randint(100, 112)
            if (v["telematics_id"], (y, m)) == glitch:
                max_speed = 197
            rows.append({"telematics_id": v["telematics_id"], "plate": v["vehicle_id"],
                         "month_end": month_end(y, m).isoformat(), "max_speed": max_speed,
                         "avg_speed": rng.randint(38, 66), "monthly_km": round(km),
                         "cumulative_km": round(cumulative)})
    return rows


# --------------------------------------------------------------------------- output
def write(out: Path, name: str, rows: list[dict]):
    with (out / f"{name}.csv").open("w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=list(rows[0].keys()))
        writer.writeheader()
        writer.writerows(rows)
    print(f"  {name + '.csv':<30} {len(rows):>7,} rows")


def main(out: Path, seed: int = SEED):
    rng = random.Random(seed)
    out.mkdir(parents=True, exist_ok=True)
    customers, groups = build_customers(rng)
    products, routes = build_products(rng)
    led = build_sales(rng, customers, groups, routes)
    companies, ec, ep, en, el = build_other_companies(customers, products, led)
    vehicles, params = build_fleet(rng)
    fuel, daily = simulate_fleet(rng, vehicles, params)
    telematics = build_telematics(rng, vehicles, daily)

    fuel_cols = ["transaction_id"] + [k for k in fuel[0] if k != "transaction_id"]
    print(f"Writing synthetic data to {out}/")
    write(out, "companies", companies)
    write(out, "customers", customers + ec)
    write(out, "products", products + ep)
    write(out, "delivery_notes", led.notes + en)
    write(out, "sales_lines", led.lines + el)
    write(out, "vehicles", vehicles)
    write(out, "fuel_card_transactions", [{k: t[k] for k in fuel_cols} for t in fuel])
    write(out, "telematics_monthly", telematics)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--out", type=Path, default=Path(__file__).resolve().parents[1] / "data")
    parser.add_argument("--seed", type=int, default=SEED)
    args = parser.parse_args()
    main(args.out, args.seed)
