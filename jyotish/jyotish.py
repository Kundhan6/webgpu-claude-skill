#!/usr/bin/env python3
"""Krish's Vedic chart: compute it, check it, and time it.

    python jyotish.py chart      -> chart.json     (Stage 1)

Sidereal zodiac, Lahiri ayanamsa, whole-sign houses.
Ephemeris: Swiss Ephemeris built-in Moshier (no .se1 files needed).
All times printed in IST (UTC+5:30) unless a field says UT.
"""
import argparse
import json
import os
from datetime import datetime, timedelta

import swisseph as swe

HERE = os.path.dirname(os.path.abspath(__file__))

BIRTH = {
    "name": "Krish",
    "sex": "male",
    "local": "2004-01-06 19:30",
    "tz_hours": 5.5,
    "place": "Kakinada, Andhra Pradesh, India",
    "lat": 16.9891,
    "lon": 82.2475,
    "told_nakshatra": "Ardra",
}

FLAGS = swe.FLG_MOSEPH | swe.FLG_SIDEREAL | swe.FLG_SPEED

SIGNS = ["Aries", "Taurus", "Gemini", "Cancer", "Leo", "Virgo",
         "Libra", "Scorpio", "Sagittarius", "Capricorn", "Aquarius", "Pisces"]
SIGNS_SKT = ["Mesha", "Vrishabha", "Mithuna", "Karka", "Simha", "Kanya",
             "Tula", "Vrischika", "Dhanu", "Makara", "Kumbha", "Meena"]
SIGN_LORD = ["Mars", "Venus", "Mercury", "Moon", "Sun", "Mercury",
             "Venus", "Mars", "Jupiter", "Saturn", "Saturn", "Jupiter"]

NAKSHATRAS = [
    ("Ashwini", "Ketu"), ("Bharani", "Venus"), ("Krittika", "Sun"),
    ("Rohini", "Moon"), ("Mrigashira", "Mars"), ("Ardra", "Rahu"),
    ("Punarvasu", "Jupiter"), ("Pushya", "Saturn"), ("Ashlesha", "Mercury"),
    ("Magha", "Ketu"), ("Purva Phalguni", "Venus"), ("Uttara Phalguni", "Sun"),
    ("Hasta", "Moon"), ("Chitra", "Mars"), ("Swati", "Rahu"),
    ("Vishakha", "Jupiter"), ("Anuradha", "Saturn"), ("Jyeshtha", "Mercury"),
    ("Mula", "Ketu"), ("Purva Ashadha", "Venus"), ("Uttara Ashadha", "Sun"),
    ("Shravana", "Moon"), ("Dhanishta", "Mars"), ("Shatabhisha", "Rahu"),
    ("Purva Bhadrapada", "Jupiter"), ("Uttara Bhadrapada", "Saturn"),
    ("Revati", "Mercury"),
]
NAK_SPAN = 360 / 27  # 13deg20'

GRAHAS = ["Sun", "Moon", "Mars", "Mercury", "Jupiter", "Venus", "Saturn", "Rahu", "Ketu"]
SWE_ID = {"Sun": swe.SUN, "Moon": swe.MOON, "Mars": swe.MARS, "Mercury": swe.MERCURY,
          "Jupiter": swe.JUPITER, "Venus": swe.VENUS, "Saturn": swe.SATURN}
BENEFICS = {"Mercury", "Jupiter", "Venus"}  # natural benefics (Moon handled separately)

# Exaltation sign index and deep-exaltation degree (BPHS ch. 3).
EXALT = {"Sun": (0, 10), "Moon": (1, 3), "Mars": (9, 28), "Mercury": (5, 15),
         "Jupiter": (3, 5), "Venus": (11, 27), "Saturn": (6, 20)}
OWN = {"Sun": [4], "Moon": [3], "Mars": [0, 7], "Mercury": [2, 5],
       "Jupiter": [8, 11], "Venus": [1, 6], "Saturn": [9, 10]}
# Moolatrikona: sign index, from-degree, to-degree (BPHS ch. 3).
MOOLA = {"Sun": (4, 0, 20), "Moon": (1, 4, 30), "Mars": (0, 0, 12), "Mercury": (5, 16, 20),
         "Jupiter": (8, 0, 10), "Venus": (6, 0, 15), "Saturn": (10, 0, 20)}
# Nodes: the most common view; the alternative view is recorded in the output.
NODE_EXALT = {"Rahu": 1, "Ketu": 7}  # Taurus / Scorpio (alt: Gemini / Sagittarius)

# Natural friendships (BPHS ch. 3): friends, neutrals; the rest are enemies.
NATURAL = {
    "Sun": ({"Moon", "Mars", "Jupiter"}, {"Mercury"}),
    "Moon": ({"Sun", "Mercury"}, {"Mars", "Jupiter", "Venus", "Saturn"}),
    "Mars": ({"Sun", "Moon", "Jupiter"}, {"Venus", "Saturn"}),
    "Mercury": ({"Sun", "Venus"}, {"Mars", "Jupiter", "Saturn"}),
    "Jupiter": ({"Sun", "Moon", "Mars"}, {"Saturn"}),
    "Venus": ({"Mercury", "Saturn"}, {"Mars", "Jupiter"}),
    "Saturn": ({"Mercury", "Venus"}, {"Jupiter"}),
}

# Combustion orbs in degrees from the Sun (Surya Siddhanta values, used by
# most Parashari software). Mercury and Venus use smaller orbs when retrograde.
COMBUST_ORB = {"Moon": 12, "Mars": 17, "Mercury": 14, "Jupiter": 11, "Venus": 10, "Saturn": 15}
COMBUST_ORB_RETRO = {"Mercury": 12, "Venus": 8}

# Whole-sign special aspects (counted inclusively: 7 = the 7th sign from).
SPECIAL_ASPECTS = {"Mars": [4, 7, 8], "Jupiter": [5, 7, 9], "Saturn": [3, 7, 10],
                   "Rahu": [5, 7, 9], "Ketu": [5, 7, 9]}


# ---------------------------------------------------------------- basics

def local_to_jd(local, tz=BIRTH["tz_hours"]):
    dt = datetime.strptime(local, "%Y-%m-%d %H:%M") - timedelta(hours=tz)
    return swe.julday(dt.year, dt.month, dt.day, dt.hour + dt.minute / 60)


def jd_to_ist(jd):
    y, m, d, h = swe.revjul(jd + 5.5 / 24)
    return datetime(y, m, d) + timedelta(seconds=round(h * 3600))


def dms(x):
    """Degrees within a sign -> 12°34'56\"."""
    total = round(x * 3600)
    d, rem = divmod(total, 3600)
    m, s = divmod(rem, 60)
    return f"{d}°{m:02d}'{s:02d}\""


def sidereal_setup():
    swe.set_sid_mode(swe.SIDM_LAHIRI, 0, 0)


def graha_longitudes(jd, node="mean"):
    """Sidereal longitude and daily speed of the 9 grahas."""
    sidereal_setup()
    out = {}
    for name, pid in SWE_ID.items():
        xx, ret = swe.calc_ut(jd, pid, FLAGS)
        if not ret & swe.FLG_MOSEPH:
            raise RuntimeError(f"{name}: Moshier ephemeris was not used (flag {ret})")
        out[name] = (xx[0] % 360, xx[3])
    nid = swe.MEAN_NODE if node == "mean" else swe.TRUE_NODE
    xx, _ = swe.calc_ut(jd, nid, FLAGS)
    out["Rahu"] = (xx[0] % 360, xx[3])
    out["Ketu"] = ((xx[0] + 180) % 360, xx[3])
    return out


def lagna_longitude(jd, lat=BIRTH["lat"], lon=BIRTH["lon"]):
    sidereal_setup()
    _, ascmc = swe.houses_ex(jd, lat, lon, b"W", swe.FLG_SIDEREAL)
    return ascmc[0] % 360


def nakshatra(lon):
    i = int(lon // NAK_SPAN)
    within = lon - i * NAK_SPAN
    name, lord = NAKSHATRAS[i]
    return {"index": i + 1, "name": name, "lord": lord,
            "pada": int(within // (NAK_SPAN / 4)) + 1,
            "fraction_elapsed": round(within / NAK_SPAN, 6)}


def navamsa_sign(lon):
    # Movable signs start from themselves, fixed from the 9th, dual from the 5th;
    # that rule collapses to counting 3°20' parts straight from 0° Aries.
    return int(lon // (30 / 9)) % 12


def dasamsa_sign(lon):
    # Odd signs start from themselves, even signs from the 9th (BPHS ch. 6).
    s = int(lon // 30)
    part = int((lon % 30) // 3)
    return (s + part) % 12 if s % 2 == 0 else (s + 8 + part) % 12


def house_from(sign, ref_sign):
    return (sign - ref_sign) % 12 + 1


def relationship(p, other, signs):
    """Compound (panchadha) relationship of p towards other: natural + temporal."""
    friends, neutrals = NATURAL[p]
    nat = 1 if other in friends else (0 if other in neutrals else -1)
    temporal = 1 if house_from(signs[other], signs[p]) in (2, 3, 4, 10, 11, 12) else -1
    return {2: "great friend", 1: "friend", 0: "neutral",
            -1: "enemy", -2: "great enemy"}[nat + temporal]


def dignity(p, lon, signs):
    s, deg = int(lon // 30), lon % 30
    if p in ("Rahu", "Ketu"):
        if s == NODE_EXALT[p]:
            return "exalted (common view)"
        if s == (NODE_EXALT[p] + 6) % 12:
            return "debilitated (common view)"
        return f"in {SIGN_LORD[s]}'s sign (nodes have no fixed dignity)"
    if s == EXALT[p][0]:
        return "exalted"
    if s == (EXALT[p][0] + 6) % 12:
        return "debilitated"
    m = MOOLA[p]
    if s == m[0] and m[1] <= deg < m[2]:
        return "moolatrikona"
    if s in OWN[p]:
        return "own sign"
    lord = SIGN_LORD[s]
    friends, neutrals = NATURAL[p]
    nat = "friend" if lord in friends else ("neutral" if lord in neutrals else "enemy")
    return f"{lord}'s sign: natural {nat}, compound {relationship(p, lord, signs)}"


def speed(jd, p):
    sidereal_setup()
    return swe.calc_ut(jd, SWE_ID[p], FLAGS)[0][3]


def nearest_station(jd, p, window=20):
    """Closest time (within +-window days) the planet's speed changes sign."""
    best = None
    for direction in (-1, 1):
        a, sa = jd, speed(jd, p)
        for _ in range(window * 4):
            b = a + direction * 0.25
            sb = speed(b, p)
            if (sa < 0) != (sb < 0):
                lo, hi = (a, b) if a < b else (b, a)
                for _ in range(40):
                    mid = (lo + hi) / 2
                    if (speed(lo, p) < 0) == (speed(mid, p) < 0):
                        lo = mid
                    else:
                        hi = mid
                if best is None or abs(lo - jd) < abs(best - jd):
                    best = lo
                break
            a, sa = b, sb
    if best is None:
        return None
    turns = "direct" if speed(best + 0.01, p) > 0 else "retrograde"
    return {"turns": turns, "ist": jd_to_ist(best).isoformat(sep=" ", timespec="minutes"),
            "hours_from_birth": round((best - jd) * 24, 1)}


def aspects_cast(p, sign):
    """Signs a graha aspects (whole-sign graha drishti)."""
    return [(sign + n - 1) % 12 for n in SPECIAL_ASPECTS.get(p, [7])]


# ---------------------------------------------------------------- chart

def build_chart(local=BIRTH["local"], node="mean"):
    jd = local_to_jd(local)
    pos = graha_longitudes(jd, node)
    asc = lagna_longitude(jd)
    lsign = int(asc // 30)
    signs = {p: int(pos[p][0] // 30) for p in GRAHAS}
    sun = pos["Sun"][0]

    grahas = {}
    for p in GRAHAS:
        lon, spd = pos[p]
        s = signs[p]
        retro = spd < 0 if p not in ("Rahu", "Ketu") else True
        comb = None
        if p in COMBUST_ORB:
            sep = abs((lon - sun + 180) % 360 - 180)
            orb = COMBUST_ORB_RETRO.get(p, COMBUST_ORB[p]) if retro else COMBUST_ORB[p]
            comb = {"combust": sep < orb, "distance_from_sun": round(sep, 2), "orb_used": orb}
        grahas[p] = {
            "longitude": round(lon, 6),
            "sign": SIGNS[s], "sign_sanskrit": SIGNS_SKT[s],
            "degree": dms(lon % 30),
            "nakshatra": nakshatra(lon),
            "house": house_from(s, lsign),
            "retrograde": retro,
            "speed_deg_per_day": round(spd, 4),
            "combustion": comb,
            "dignity": dignity(p, lon, signs),
            "d9_sign": SIGNS[navamsa_sign(lon)],
            "d10_sign": SIGNS[dasamsa_sign(lon)],
            "vargottama": navamsa_sign(lon) == s,
            "aspects_houses": [house_from(a, lsign) for a in aspects_cast(p, s)],
        }
        if p in ("Mars", "Mercury", "Jupiter", "Venus", "Saturn"):
            grahas[p]["nearest_station_within_20_days"] = nearest_station(jd, p)

    houses = []
    for h in range(1, 13):
        sign = (lsign + h - 1) % 12
        lord = SIGN_LORD[sign]
        houses.append({
            "house": h, "sign": SIGNS[sign], "lord": lord,
            "lord_in_house": grahas[lord]["house"],
            "occupants": [p for p in GRAHAS if signs[p] == sign],
            "aspected_by": [p for p in GRAHAS if sign in aspects_cast(p, signs[p])],
        })

    d9_lagna, d10_lagna = navamsa_sign(asc), dasamsa_sign(asc)
    chart = {
        "birth": BIRTH | {"local_used": local, "jd_ut": round(jd, 6),
                          "utc": (datetime.strptime(local, "%Y-%m-%d %H:%M")
                                  - timedelta(hours=BIRTH["tz_hours"])).isoformat()},
        "settings": {
            "zodiac": "sidereal", "ayanamsa": "Lahiri (swe.SIDM_LAHIRI)",
            "ayanamsa_value": round(swe.get_ayanamsa_ut(jd), 6),
            "ayanamsa_dms": dms(swe.get_ayanamsa_ut(jd)),
            "houses": "whole sign", "ephemeris": "Swiss Ephemeris Moshier (built-in)",
            "swisseph_version": swe.version, "node": f"{node} node",
            "combust_orbs": COMBUST_ORB, "combust_orbs_retrograde": COMBUST_ORB_RETRO,
        },
        "lagna": {
            "longitude": round(asc, 6), "sign": SIGNS[lsign], "sign_sanskrit": SIGNS_SKT[lsign],
            "degree": dms(asc % 30), "nakshatra": nakshatra(asc), "lord": SIGN_LORD[lsign],
            "d9_sign": SIGNS[d9_lagna], "d10_sign": SIGNS[d10_lagna],
        },
        "grahas": grahas,
        "houses": houses,
        "d9": varga_table(asc, pos, navamsa_sign),
        "d10": varga_table(asc, pos, dasamsa_sign),
        "tithi": tithi(pos["Moon"][0], sun),
    }
    chart["yogas"] = find_yogas(chart, signs, lsign, pos)
    return chart


def varga_table(asc, pos, fn):
    lsign = fn(asc)
    rows = {"Lagna": {"sign": SIGNS[lsign], "house": 1}}
    for p in GRAHAS:
        s = fn(pos[p][0])
        rows[p] = {"sign": SIGNS[s], "house": house_from(s, lsign)}
    return rows


def tithi(moon, sun):
    elong = (moon - sun) % 360
    n = int(elong // 12) + 1
    paksha = "Shukla (waxing)" if n <= 15 else "Krishna (waning)"
    return {"sun_moon_angle": round(elong, 4), "number": n, "paksha": paksha,
            "in_paksha": n if n <= 15 else n - 15}


# ---------------------------------------------------------------- yogas

def find_yogas(chart, signs, lsign, pos):
    """Main yogas. Each entry records the rule used, so it can be checked."""
    G = chart["grahas"]
    house = {p: G[p]["house"] for p in GRAHAS}
    lord_of = {h["house"]: h["lord"] for h in chart["houses"]}
    moon_s, sun_s = signs["Moon"], signs["Sun"]
    seven = ["Sun", "Moon", "Mars", "Mercury", "Jupiter", "Venus", "Saturn"]

    def aspects(a, b):
        return signs[b] in aspects_cast(a, signs[a])

    def linked(a, b):
        """Parashari sambandha: conjunction, mutual aspect, exchange, or one in the
        other's sign and aspected by it."""
        if a == b:
            return None
        if signs[a] == signs[b]:
            return "conjunct"
        if aspects(a, b) and aspects(b, a):
            return "mutual aspect"
        if SIGN_LORD[signs[a]] == b and SIGN_LORD[signs[b]] == a:
            return "sign exchange"
        for x, y in ((a, b), (b, a)):
            if SIGN_LORD[signs[x]] == y and aspects(y, x):
                return f"{x} in {y}'s sign, aspected by {y}"
        return None

    def taint(*ps):
        bad = [p for p in ps if set(owned(p, lord_of).split("/")) & {"6", "8", "12"}]
        return f"mixed: {', '.join(bad)} also rules 6/8/12" if bad else ""

    yogas = []

    def add(name, present, rule, detail, note=""):
        yogas.append({"name": name, "present": present, "rule": rule,
                      "detail": detail, "note": note})

    # Gaja Kesari
    hj = house_from(signs["Jupiter"], moon_s)
    add("Gaja Kesari", hj in (1, 4, 7, 10), "Jupiter in a kendra (1/4/7/10) from the Moon",
        f"Jupiter is house {hj} from the Moon")

    # Budha-Aditya
    add("Budha-Aditya", signs["Sun"] == signs["Mercury"], "Sun and Mercury in one sign",
        f"Sun {SIGNS[signs['Sun']]}, Mercury {SIGNS[signs['Mercury']]}",
        "Weak if Mercury is combust: " + str(G["Mercury"]["combustion"]["combust"]))

    # Chandra-Mangala
    add("Chandra-Mangala", signs["Moon"] == signs["Mars"], "Moon and Mars in one sign",
        f"Moon {SIGNS[moon_s]}, Mars {SIGNS[signs['Mars']]}")

    # Pancha Mahapurusha
    for p, yname in [("Mars", "Ruchaka"), ("Mercury", "Bhadra"), ("Jupiter", "Hamsa"),
                     ("Venus", "Malavya"), ("Saturn", "Sasa")]:
        strong = signs[p] in OWN[p] or signs[p] == EXALT[p][0]
        add(f"{yname} (Mahapurusha)", strong and house[p] in (1, 4, 7, 10),
            f"{p} in own/exaltation sign AND in a kendra from Lagna",
            f"{p}: house {house[p]}, {G[p]['dignity']}")

    # Raja yogas: kendra lord linked with trikona lord
    kendra_l = {lord_of[h] for h in (1, 4, 7, 10)}
    trikona_l = {lord_of[h] for h in (1, 5, 9)}
    found = []
    for k in sorted(kendra_l):
        for t in sorted(trikona_l):
            how = linked(k, t)
            if how:
                q = taint(k, t)
                found.append(f"{k} (lord of {owned(k, lord_of)}, in {house[k]}) + {t} (lord of "
                             f"{owned(t, lord_of)}, in {house[t]}): {how}" + (f" [{q}]" if q else ""))
    yk = [p for p in seven if p in kendra_l and p in trikona_l and p != lord_of[1]]
    add("Raja yoga (kendra-trikona link)", bool(found),
        "Lord of 1/4/7/10 joined to lord of 1/5/9 (4-fold sambandha)",
        "; ".join(found) or "no such link")
    add("Yogakaraka", bool(yk), "One planet rules both a kendra and a trikona (not the Lagna lord)",
        ", ".join(f"{p} rules houses {owned(p, lord_of)}, sits in house {house[p]}, {G[p]['dignity']}"
                  for p in yk) or "none")

    # Dhana yogas: links among lords of 1, 2, 5, 9, 11
    dl = sorted({lord_of[h] for h in (1, 2, 5, 9, 11)})
    found = []
    for i, a in enumerate(dl):
        for b in dl[i + 1:]:
            how = linked(a, b)
            if how:
                q = taint(a, b)
                found.append(f"{a} (lord of {owned(a, lord_of)}, in {house[a]}) + {b} (lord of "
                             f"{owned(b, lord_of)}, in {house[b]}): {how}" + (f" [{q}]" if q else ""))
    add("Dhana yoga (wealth-lord link)", bool(found),
        "Lords of 1/2/5/9/11 joined (4-fold sambandha)",
        "; ".join(found) or "no such link")

    # Viparita Raja yogas
    for h, yname in [(6, "Harsha"), (8, "Sarala"), (12, "Vimala")]:
        lord = lord_of[h]
        add(f"{yname} (Viparita Raja)", house[lord] in (6, 8, 12),
            f"Lord of house {h} placed in house 6, 8 or 12",
            f"{lord} (lord of {h}) is in house {house[lord]}")

    # Parivartana (exchanges)
    ex = []
    for i, a in enumerate(seven):
        for b in seven[i + 1:]:
            if SIGN_LORD[signs[a]] == b and SIGN_LORD[signs[b]] == a:
                hs = {house[a], house[b]}
                kind = ("Dainya (a 6/8/12 house is involved)" if hs & {6, 8, 12} else
                        "Khala (the 3rd house is involved)" if 3 in hs else "Maha")
                ex.append(f"{a} in {SIGNS[signs[a]]} (house {house[a]}) <-> {b} in "
                          f"{SIGNS[signs[b]]} (house {house[b]}): {kind}")
    add("Parivartana (sign exchange)", bool(ex),
        "Two planets in each other's signs; type set by the two HOUSES exchanged (Phaladeepika ch. 6)",
        "; ".join(ex) or "none")

    # Moon-based yogas (Sun and nodes excluded)
    moon_2 = [p for p in seven if p not in ("Sun", "Moon") and house_from(signs[p], moon_s) == 2]
    moon_12 = [p for p in seven if p not in ("Sun", "Moon") and house_from(signs[p], moon_s) == 12]
    with_moon = [p for p in seven if p not in ("Sun", "Moon") and signs[p] == moon_s]
    add("Sunapha", bool(moon_2) and not moon_12, "Planet(s) other than Sun in 2nd from Moon only",
        f"2nd from Moon: {moon_2 or 'none'}")
    add("Anapha", bool(moon_12) and not moon_2, "Planet(s) other than Sun in 12th from Moon only",
        f"12th from Moon: {moon_12 or 'none'}")
    add("Durudhara", bool(moon_2) and bool(moon_12), "Planets in both 2nd and 12th from Moon",
        f"2nd: {moon_2 or 'none'}; 12th: {moon_12 or 'none'}")
    kendra_from_lagna = [p for p in seven if p != "Moon" and house[p] in (1, 4, 7, 10)]
    kendra_from_moon = [p for p in seven if p != "Moon" and house_from(signs[p], moon_s) in (1, 4, 7, 10)]
    kema = not moon_2 and not moon_12
    add("Kemadruma", kema, "No planet (except Sun/nodes) in 2nd or 12th from Moon",
        f"2nd: {moon_2 or 'none'}; 12th: {moon_12 or 'none'}; with Moon: {with_moon or 'none'}",
        (("CANCELLED by the kendra rule. " if (kendra_from_lagna or kendra_from_moon) else "")
         + "Planets in kendra from Lagna "
         f"{kendra_from_lagna or 'none'}; from Moon {kendra_from_moon or 'none'}") if kema else "")

    # Sun-based yogas (Moon and nodes excluded)
    sun_2 = [p for p in seven if p not in ("Sun", "Moon") and house_from(signs[p], sun_s) == 2]
    sun_12 = [p for p in seven if p not in ("Sun", "Moon") and house_from(signs[p], sun_s) == 12]
    add("Vesi", bool(sun_2) and not sun_12, "Planet (not Moon) in 2nd from Sun only",
        f"2nd from Sun: {sun_2 or 'none'}")
    add("Vasi", bool(sun_12) and not sun_2, "Planet (not Moon) in 12th from Sun only",
        f"12th from Sun: {sun_12 or 'none'}")
    add("Ubhayachari", bool(sun_2) and bool(sun_12), "Planets in both 2nd and 12th from Sun",
        f"2nd: {sun_2 or 'none'}; 12th: {sun_12 or 'none'}")

    # Adhi yoga
    adhi = [p for p in BENEFICS if house_from(signs[p], moon_s) in (6, 7, 8)]
    add("Adhi", len(adhi) >= 1, "Natural benefics in 6th/7th/8th from Moon (full yoga: all three)",
        f"benefics there: {sorted(adhi) or 'none'}",
        "full" if len(adhi) == 3 else ("partial" if adhi else ""))

    # Amala
    am_l = [p for p in BENEFICS if house[p] == 10]
    am_m = [p for p in BENEFICS if house_from(signs[p], moon_s) == 10]
    add("Amala", bool(am_l or am_m), "Natural benefic in 10th from Lagna or Moon",
        f"10th from Lagna: {am_l or 'none'}; 10th from Moon: {am_m or 'none'}")

    # Shakata
    hm = house_from(moon_s, signs["Jupiter"])
    add("Shakata", hm in (6, 8, 12), "Moon in 6th/8th/12th from Jupiter",
        f"Moon is house {hm} from Jupiter",
        "Cancelled by many if Moon is in a kendra from Lagna" if hm in (6, 8, 12) else "")

    # Moon-Saturn in one sign: "Punarphoo" / "Vish" are modern names, not BPHS yogas
    add("Moon-Saturn conjunction (Punarphoo/Vish, modern)", signs["Moon"] == signs["Saturn"],
        "Moon and Saturn in one sign", f"Moon {SIGNS[moon_s]}, Saturn {SIGNS[signs['Saturn']]}, "
        f"{abs(pos['Moon'][0] - pos['Saturn'][0]):.2f}° apart", "Modern label; treat as a combination, not a classical yoga.")

    # Guru-Chandala
    add("Guru-Chandala", signs["Jupiter"] in (signs["Rahu"], signs["Ketu"]),
        "Jupiter with Rahu (some include Ketu)",
        f"Jupiter {SIGNS[signs['Jupiter']]}, Rahu {SIGNS[signs['Rahu']]}, Ketu {SIGNS[signs['Ketu']]}")

    # Kala Sarpa: all seven on one side of the Rahu-Ketu axis
    rahu = pos["Rahu"][0]
    side = [((pos[p][0] - rahu) % 360) < 180 for p in seven]
    add("Kala Sarpa", all(side) or not any(side), "All 7 planets on one side of the Rahu-Ketu axis",
        f"{sum(side)} of 7 on the Rahu->Ketu side")

    # Neecha Bhanga for each debilitated planet
    for p in seven:
        if "debilitated" not in G[p]["dignity"]:
            continue
        s = signs[p]
        dl_ = SIGN_LORD[s]
        ex_in = [q for q in EXALT if EXALT[q][0] == s]
        ex_lord = SIGN_LORD[EXALT[p][0]]
        reasons = []
        for q, why in [(dl_, "lord of debilitation sign"), (ex_lord, "lord of its exaltation sign")] + \
                [(q, "planet exalted in that sign") for q in ex_in]:
            if house[q] in (1, 4, 7, 10):
                reasons.append(f"{q} ({why}) in kendra from Lagna")
            if house_from(signs[q], moon_s) in (1, 4, 7, 10):
                reasons.append(f"{q} ({why}) in kendra from Moon")
        if aspects(dl_, p) or signs[dl_] == s:
            reasons.append(f"{dl_} (lord of debilitation sign) joins or aspects it")
        add(f"Neecha Bhanga for {p}", bool(reasons), "Cancellation of debilitation (BPHS/Phaladeepika rules)",
            "; ".join(reasons) or "no cancellation rule met")

    # Mangal (Kuja) dosha: popular/marriage tradition, not core BPHS
    mh = {"Lagna": house["Mars"], "Moon": house_from(signs["Mars"], moon_s),
          "Venus": house_from(signs["Mars"], signs["Venus"])}
    hits = [k for k, v in mh.items() if v in (1, 2, 4, 7, 8, 12)]
    add("Mangal dosha", bool(hits), "Mars in 1/2/4/7/8/12 from Lagna, Moon or Venus",
        f"Mars house from Lagna {mh['Lagna']}, from Moon {mh['Moon']}, from Venus {mh['Venus']}",
        "Folk/marriage-matching rule; many exceptions are taught.")
    return yogas


def owned(p, lord_of):
    return "/".join(str(h) for h in sorted(h for h, l in lord_of.items() if l == p))


# ---------------------------------------------------------------- main

def write_json(name, data):
    path = os.path.join(HERE, name)
    with open(path, "w") as f:
        json.dump(data, f, indent=2, ensure_ascii=False)
    print(f"wrote {path}")


def print_chart(c):
    L = c["lagna"]
    print(f"Ayanamsa (Lahiri): {c['settings']['ayanamsa_dms']}")
    print(f"Lagna  {L['sign']:<12}{L['degree']:>12}  {L['nakshatra']['name']} p{L['nakshatra']['pada']}"
          f"  D9 {L['d9_sign']}  D10 {L['d10_sign']}")
    for p, g in c["grahas"].items():
        cb = g["combustion"]
        print(f"{p:<7}{g['sign']:<12}{g['degree']:>12}  {g['nakshatra']['name']:<17}p{g['nakshatra']['pada']}"
              f"  H{g['house']:<3}{'R' if g['retrograde'] else ' '} {'C' if cb and cb['combust'] else ' '}"
              f"  {g['dignity']:<34} D9 {g['d9_sign']:<12} D10 {g['d10_sign']}")
    print("Yogas present:")
    for y in c["yogas"]:
        if y["present"]:
            print(f"  - {y['name']}: {y['detail']}")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("cmd", choices=["chart"])
    args = ap.parse_args()
    if args.cmd == "chart":
        c = build_chart()
        c["node_check"] = {
            "true_node_rahu": build_chart(node="true")["grahas"]["Rahu"]["longitude"],
            "mean_node_rahu": c["grahas"]["Rahu"]["longitude"],
        }
        print_chart(c)
        write_json("chart.json", c)


if __name__ == "__main__":
    main()
