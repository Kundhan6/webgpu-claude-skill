#!/usr/bin/env python3
"""Krish's Vedic chart: compute it, check it, and time it.

    python jyotish.py chart      -> chart.json     (Stage 1)
    python jyotish.py verify     -> adds "verification" to chart.json (Stage 2)
    python jyotish.py timeline   -> timeline.json  (Stage 3)

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


# ---------------------------------------------------------------- Stage 2: verify

def jd_meeus(y, m, d):
    """Julian Day from a Gregorian date, d may carry a day fraction (Meeus ch. 7)."""
    if m <= 2:
        y, m = y - 1, m + 12
    a = y // 100
    b = 2 - a + a // 4
    return int(365.25 * (y + 4716)) + int(30.6001 * (m + 1)) + d + b - 1524.5


def delta_t_seconds(year):
    """TT - UT for 2000-2005 (Espenak & Meeus polynomial)."""
    t = year - 2000
    return (63.86 + 0.3345 * t - 0.060374 * t ** 2 + 0.0017275 * t ** 3
            + 0.000651814 * t ** 4 + 0.00002373599 * t ** 5)


def lahiri_own(jde):
    """Lahiri ayanamsa from its definition, without Swiss Ephemeris.

    Indian Astronomical Ephemeris: 23°15'00.658" on 1956-03-21 0h; that value
    includes nutation, so subtract the nutation of that date (Meeus ch. 22) to
    get the mean value, then add IAU 2006 general precession in longitude.
    Returns (mean, true) in degrees; true = mean + nutation of the date.
    """
    from pymeeus.Coordinates import nutation_longitude
    from pymeeus.Epoch import Epoch

    def p_a(T):  # arcseconds, Capitaine et al. 2003 / IAU 2006
        return (5028.796195 * T + 1.1054348 * T ** 2 + 0.00007964 * T ** 3
                - 0.000023857 * T ** 4 - 0.0000000383 * T ** 5)
    jd0 = 2435553.5
    mean0 = 23.25018278 - float(nutation_longitude(Epoch(jd0)))
    T0, T = (jd0 - 2451545.0) / 36525, (jde - 2451545.0) / 36525
    mean = mean0 + (p_a(T) - p_a(T0)) / 3600
    return mean, mean + float(nutation_longitude(Epoch(jde)))


def lagna_own(jd_ut, jde, lat, lon):
    """Sidereal ascendant from Meeus sidereal time + obliquity, own ayanamsa."""
    import math
    from pymeeus.Coordinates import nutation_longitude, true_obliquity
    from pymeeus.Epoch import Epoch
    T = (jd_ut - 2451545.0) / 36525
    gmst = (280.46061837 + 360.98564736629 * (jd_ut - 2451545.0)
            + 0.000387933 * T ** 2 - T ** 3 / 38710000)          # Meeus 12.4
    eps = float(true_obliquity(Epoch(jde)))
    dpsi = float(nutation_longitude(Epoch(jde)))
    ramc = math.radians((gmst + dpsi * math.cos(math.radians(eps)) + lon) % 360)
    e, phi = math.radians(eps), math.radians(lat)
    asc = math.degrees(math.atan2(math.cos(ramc),
                                  -(math.sin(ramc) * math.cos(e) + math.tan(phi) * math.sin(e))))
    return (asc - lahiri_own(jde)[1]) % 360


def second_method(local):
    """Moon, Sun, ayanamsa, Lagna without Swiss Ephemeris: own JD, Delta-T and
    Lahiri; Moon and Sun from Meeus (pymeeus: ELP-2000/82 ch. 47, VSOP87)."""
    from pymeeus.Epoch import Epoch
    from pymeeus.Moon import Moon
    from pymeeus.Sun import Sun
    dt = datetime.strptime(local, "%Y-%m-%d %H:%M") - timedelta(hours=BIRTH["tz_hours"])
    jd_ut = jd_meeus(dt.year, dt.month, dt.day + (dt.hour + dt.minute / 60) / 24)
    jde = jd_ut + delta_t_seconds(dt.year + (dt.timetuple().tm_yday - 0.5) / 365.25) / 86400
    ay_mean, ay_true = lahiri_own(jde)
    moon_mean_eq = float(Moon.geocentric_ecliptical_pos(Epoch(jde))[0])   # mean equinox of date
    sun_app = float(Sun.apparent_geocentric_position(Epoch(jde))[0])      # true equinox, aberration
    return {"jd_ut": jd_ut, "jde": jde, "ayanamsa_mean": ay_mean, "ayanamsa_true": ay_true,
            "moon": (moon_mean_eq - ay_mean) % 360, "sun": (sun_app - ay_true) % 360,
            "lagna": lagna_own(jd_ut, jde, BIRTH["lat"], BIRTH["lon"])}


def third_method_moon(jd_ut, ay_mean):
    """PyEphem (libastro) Moon, mean equinox of date, minus own mean Lahiri."""
    import ephem
    d = ephem.Date(jd_ut - 2415020.0)  # ephem dates count from 1899-12-31 12:00 UT
    lon = float(ephem.Ecliptic(ephem.Moon(d), epoch=d).lon)
    import math
    return (math.degrees(lon) - ay_mean) % 360


def full_moon_jan_2004():
    """Full moon time by Swiss Ephemeris (bisection on Sun-Moon angle) and by
    Meeus ch. 49 (pymeeus), both in UT."""
    from pymeeus.Epoch import Epoch
    from pymeeus.Moon import Moon

    def elong(jd):
        m = swe.calc_ut(jd, swe.MOON, swe.FLG_MOSEPH)[0][0]
        s = swe.calc_ut(jd, swe.SUN, swe.FLG_MOSEPH)[0][0]
        return (m - s) % 360
    lo, hi = swe.julday(2004, 1, 6, 0), swe.julday(2004, 1, 9, 0)
    for _ in range(60):
        mid = (lo + hi) / 2
        lo, hi = (mid, hi) if elong(mid) < 180 else (lo, mid)
    swe_jd = lo
    # pymeeus rounds k = (year - 2000) * 12.3685 to the nearest new moon and adds
    # 0.5, so seed in mid-December 2003 to land on k = 49.5 (the January full moon).
    jde = float(Moon.moon_phase(Epoch(2003, 12, 20.0), target="full"))
    meeus_jd = jde - delta_t_seconds(2004.02) / 86400
    return swe_jd, meeus_jd


def angdiff(a, b):
    """Signed a-b in arcseconds, wrapped to +-180°."""
    return ((a - b + 180) % 360 - 180) * 3600


def window(fn, local=BIRTH["local"]):
    """IST window around birth over which fn(lagna longitude) stays the same."""
    jd = local_to_jd(local)
    v0 = fn(lagna_longitude(jd))
    out = {}
    for direction, key in ((-1, "from"), (1, "to")):
        a = jd
        while fn(lagna_longitude(a + direction / 1440)) == v0:
            a += direction / 1440
        out[key] = jd_to_ist(a).strftime("%H:%M")
    return v0, out


def verify():
    report = {}
    local = BIRTH["local"]
    c = build_chart(local)
    m1 = {"ayanamsa": c["settings"]["ayanamsa_value"], "moon": c["grahas"]["Moon"]["longitude"],
          "sun": c["grahas"]["Sun"]["longitude"], "lagna": c["lagna"]["longitude"]}
    m2 = second_method(local)
    m3_moon = third_method_moon(m2["jd_ut"], m2["ayanamsa_mean"])
    swe_jd = local_to_jd(local)

    print("== (a) second method: no Swiss Ephemeris ==")
    print(f"JD (UT): swe {swe_jd:.6f}  own Meeus {m2['jd_ut']:.6f}")
    rows = [("Lahiri ayanamsa (mean)", m1["ayanamsa"], m2["ayanamsa_mean"]),
            ("Moon sidereal", m1["moon"], m2["moon"]),
            ("Sun sidereal", m1["sun"], m2["sun"]),
            ("Lagna sidereal", m1["lagna"], m2["lagna"])]
    checks = []
    for name, a, b in rows:
        d = angdiff(a, b)
        print(f"{name:<24} swe {a:11.6f}  method-2 {b:11.6f}  diff {d:+7.1f}\"")
        checks.append({"item": name, "swisseph": round(a, 6), "method_2": round(b, 6),
                       "diff_arcsec": round(d, 1)})
    d3 = angdiff(m1["moon"], m3_moon)
    print(f"{'Moon (PyEphem, 3rd)':<24} swe {m1['moon']:11.6f}  pyephem  {m3_moon:11.6f}  diff {d3:+7.1f}\"")
    checks.append({"item": "Moon sidereal (PyEphem)", "swisseph": round(m1["moon"], 6),
                   "method_3": round(m3_moon, 6), "diff_arcsec": round(d3, 1)})
    naks = {nakshatra(x)["name"] + f" p{nakshatra(x)['pada']}" for x in (m1["moon"], m2["moon"], m3_moon)}
    print(f"Moon nakshatra by all methods: {naks}")
    report["second_method"] = checks
    report["moon_nakshatra_all_methods"] = sorted(naks)

    print("\n== (b) full moon of January 2004 ==")
    fm_swe, fm_meeus = full_moon_jan_2004()
    for name, jd in (("Swiss Ephemeris", fm_swe), ("Meeus ch.49", fm_meeus)):
        print(f"{name:<16} {jd_to_ist(jd) - timedelta(hours=5.5):%Y-%m-%d %H:%M} UT")
    hrs = (fm_swe - swe_jd) * 24
    angle = c["tithi"]["sun_moon_angle"]
    rate = c["grahas"]["Moon"]["speed_deg_per_day"] - c["grahas"]["Sun"]["speed_deg_per_day"]
    expect = 180 - rate * hrs / 24
    print(f"Birth is {hrs:.1f} h before full moon. Sun-Moon angle at birth {angle:.2f}°;"
          f" at today's relative speed {rate:.2f}°/day the expected angle is {expect:.2f}°.")
    report["full_moon"] = {
        "swisseph_ut": f"{jd_to_ist(fm_swe) - timedelta(hours=5.5):%Y-%m-%d %H:%M}",
        "meeus_ut": f"{jd_to_ist(fm_meeus) - timedelta(hours=5.5):%Y-%m-%d %H:%M}",
        "hours_birth_to_full_moon": round(hrs, 2), "sun_moon_angle_at_birth": angle,
        "expected_angle_from_speed": round(expect, 2)}

    print("\n== birth-time test ==")
    tt = []
    for t in ("19:15", "19:30", "19:45"):
        cc = build_chart(f"2004-01-06 {t}")
        L, M = cc["lagna"], cc["grahas"]["Moon"]
        row = {"time_ist": t, "lagna": f"{L['sign']} {L['degree']}", "lagna_nakshatra":
               f"{L['nakshatra']['name']} p{L['nakshatra']['pada']}", "d9_lagna": L["d9_sign"],
               "d10_lagna": L["d10_sign"], "moon": f"{M['sign']} {M['degree']}",
               "moon_nakshatra": f"{M['nakshatra']['name']} p{M['nakshatra']['pada']}",
               "moon_nak_fraction_elapsed": M["nakshatra"]["fraction_elapsed"]}
        tt.append(row)
        print(f"{t}  Lagna {row['lagna']:<20} {row['lagna_nakshatra']:<14} D9 {row['d9_lagna']:<12}"
              f" D10 {row['d10_lagna']:<8} Moon {row['moon']} {row['moon_nakshatra']}")
    s0, edges = window(lambda x: int(x // 30))
    wins = {
        "lagna_sign": (SIGNS[s0], edges),
        "lagna_nakshatra": (lambda v: (NAKSHATRAS[v[0]][0], v[1]))(window(lambda x: int(x // NAK_SPAN))),
        "d9_lagna": (lambda v: (SIGNS[v[0]], v[1]))(window(navamsa_sign)),
        "d10_lagna": (lambda v: (SIGNS[v[0]], v[1]))(window(dasamsa_sign)),
    }
    for k, (val, w) in wins.items():
        print(f"{k:<16} {val:<12} holds {w['from']} to {w['to']} IST")
    m2_15, m2_45 = second_method("2004-01-06 19:15")["lagna"], second_method("2004-01-06 19:45")["lagna"]
    print(f"Method-2 Lagna: 19:15 {SIGNS[int(m2_15 // 30)]} {dms(m2_15 % 30)}, "
          f"19:45 {SIGNS[int(m2_45 // 30)]} {dms(m2_45 % 30)}")
    stable = len({r["lagna"].split()[0] for r in tt}) == 1
    d9_stable = len({r["d9_lagna"] for r in tt}) == 1
    d10_stable = len({r["d10_lagna"] for r in tt}) == 1
    print(f"Lagna sign stable: {stable}. D9 Lagna stable: {d9_stable}. D10 Lagna stable: {d10_stable}.")
    # Dasha sensitivity: Moon motion over +-15 min, as days of the running Rahu-nakshatra dasha
    mo = [build_chart(f"2004-01-06 {t}")["grahas"]["Moon"]["longitude"] for t in ("19:15", "19:45")]
    shift = (mo[1] - mo[0]) / 2 / NAK_SPAN * 18 * 365.25
    print(f"Moon moves {(mo[1] - mo[0]) / 2 * 60:.1f}' per 15 min -> all dasha dates shift about"
          f" {shift:.0f} days per 15 min of birth-time error.")
    report["birth_time_test"] = {"rows": tt,
                                 "windows_ist": {k: {"value": v, **w} for k, (v, w) in wins.items()},
                                 "lagna_sign_stable": stable, "d9_lagna_stable": d9_stable,
                                 "d10_lagna_stable": d10_stable,
                                 "dasha_shift_days_per_15_min": round(shift)}
    return report


# ---------------------------------------------------------------- Stage 3: time periods

DASHA_ORDER = [("Ketu", 7), ("Venus", 20), ("Sun", 6), ("Moon", 10), ("Mars", 7),
               ("Rahu", 18), ("Jupiter", 16), ("Saturn", 19), ("Mercury", 17)]
YEAR_DAYS = 365.25  # Julian year; the commonest Vimshottari year (see NOTES.md)
WINDOW = ("2026-10-11", "2027-10-11")
ORD = {1: "1st", 2: "2nd", 3: "3rd", 4: "4th", 7: "7th", 8: "8th", 10: "10th", 12: "12th"}


def ist(jd, minutes=True):
    return jd_to_ist(jd).strftime("%Y-%m-%d %H:%M" if minutes else "%Y-%m-%d")


def date_jd(s):
    return local_to_jd(s + " 00:00")


def vimshottari(moon_lon, birth_jd, year_days=YEAR_DAYS):
    """Maha and antar dashas from the Moon's nakshatra; returns (balance, tree)."""
    nk = nakshatra(moon_lon)
    start_i = [l for l, _ in DASHA_ORDER].index(nk["lord"])
    first_years = DASHA_ORDER[start_i][1]
    t = birth_jd - nk["fraction_elapsed"] * first_years * year_days  # virtual MD start
    tree = []
    for k in range(9 + 1):
        lord, yrs = DASHA_ORDER[(start_i + k) % 9]
        md = {"lord": lord, "start_jd": t, "end_jd": t + yrs * year_days, "antar": []}
        a = t
        for j in range(9):
            al, ay = DASHA_ORDER[(start_i + k + j) % 9]
            dur = yrs * ay / 120 * year_days
            md["antar"].append({"lord": al, "start_jd": a, "end_jd": a + dur})
            a += dur
        tree.append(md)
        t = md["end_jd"]
    balance_years = (1 - nk["fraction_elapsed"]) * first_years
    return balance_years, tree


def pratyantars(md_lord, ad):
    start_i = [l for l, _ in DASHA_ORDER].index(ad["lord"])
    span = ad["end_jd"] - ad["start_jd"]
    out, p = [], ad["start_jd"]
    for j in range(9):
        pl, py = DASHA_ORDER[(start_i + j) % 9]
        dur = span * py / 120
        out.append({"lord": pl, "start_jd": p, "end_jd": p + dur})
        p += dur
    return out


def dasha_rows(tree, lo, hi, with_pd=True):
    rows = []
    for md in tree:
        for ad in md["antar"]:
            if ad["end_jd"] <= lo or ad["start_jd"] >= hi:
                continue
            row = {"maha": md["lord"], "antar": ad["lord"],
                   "start": ist(ad["start_jd"]), "end": ist(ad["end_jd"])}
            if with_pd:
                row["pratyantar"] = [
                    {"lord": pd["lord"], "start": ist(pd["start_jd"]), "end": ist(pd["end_jd"])}
                    for pd in pratyantars(md["lord"], ad)
                    if pd["end_jd"] > lo and pd["start_jd"] < hi]
            rows.append(row)
    return rows


def body_lon(jd, body, node="mean"):
    sidereal_setup()
    if body in SWE_ID:
        return swe.calc_ut(jd, SWE_ID[body], FLAGS)[0][0] % 360
    nid = swe.MEAN_NODE if node == "mean" else swe.TRUE_NODE
    lon = swe.calc_ut(jd, nid, FLAGS)[0][0] % 360
    return lon if body == "Rahu" else (lon + 180) % 360


def ingresses(body, lo, hi, step, node="mean"):
    """Sidereal sign changes between JDs lo and hi, refined to about a minute."""
    out = []
    a, sa = lo, int(body_lon(lo, body, node) // 30)
    while a < hi:
        b = min(a + step, hi)
        sb = int(body_lon(b, body, node) // 30)
        if sb != sa:
            x, y = a, b
            while y - x > 1 / 2880:
                m = (x + y) / 2
                if int(body_lon(m, body, node) // 30) == sa:
                    x = m
                else:
                    y = m
            out.append({"jd": y, "from": SIGNS[sa], "to": SIGNS[sb]})
        a, sa = b, sb
    return out


def stations(body, lo, hi):
    out = []
    a, sa = lo, speed(lo, body)
    while a < hi:
        b = a + 0.5
        sb = speed(b, body)
        if (sa < 0) != (sb < 0):
            x, y = a, b
            while y - x > 1 / 1440:
                m = (x + y) / 2
                if (speed(m, body) < 0) == (sa < 0):
                    x = m
                else:
                    y = m
            sid = body_lon(y, body)
            out.append({"body": body, "ist": ist(y), "turns": "direct" if sb > 0 else "retrograde",
                        "at": f"{SIGNS[int(sid // 30)]} {dms(sid % 30)}"})
        a, sa = b, sb
    return out


def eclipses(lo, hi):
    out = []
    t = lo
    while True:
        ret, tm = swe.sol_eclipse_when_glob(t, swe.FLG_MOSEPH, 0)
        if tm[0] > hi:
            break
        kind = ("total" if ret & swe.ECL_TOTAL else "annular" if ret & swe.ECL_ANNULAR
                else "hybrid" if ret & swe.ECL_ANNULAR_TOTAL else "partial")
        sid = body_lon(tm[0], "Sun")
        out.append({"type": f"solar ({kind})", "ist": ist(tm[0]),
                    "at": f"{SIGNS[int(sid // 30)]} {dms(sid % 30)}", "jd": tm[0]})
        t = tm[0] + 20
    t = lo
    while True:
        ret, tm = swe.lun_eclipse_when(t, swe.FLG_MOSEPH, 0)
        if tm[0] > hi:
            break
        kind = ("total" if ret & swe.ECL_TOTAL else "partial" if ret & swe.ECL_PARTIAL
                else "penumbral")
        sid = body_lon(tm[0], "Moon")
        out.append({"type": f"lunar ({kind})", "ist": ist(tm[0]),
                    "at": f"{SIGNS[int(sid // 30)]} {dms(sid % 30)}", "jd": tm[0]})
        t = tm[0] + 20
    return sorted(out, key=lambda e: e["jd"])


def saturn_phases(ing, lo_sign_jd, moon_s, lagna_s, hi):
    """Saturn periods by sign: Sade Sati, Ashtama, Kantaka (from Moon and Lagna)."""
    spans, start = [], lo_sign_jd
    sign = SIGNS.index(ing[0]["from"]) if ing else int(body_lon(lo_sign_jd, "Saturn") // 30)
    for e in ing:
        spans.append((start, e["jd"], sign))
        start, sign = e["jd"], SIGNS.index(e["to"])
    spans.append((start, hi, sign))
    out = []
    for a, b, s in spans:
        hm, hl = house_from(s, moon_s), house_from(s, lagna_s)
        tags = []
        if hm in (12, 1, 2):
            tags.append({12: "Sade Sati phase 1 (rising)", 1: "Sade Sati phase 2 (peak)",
                         2: "Sade Sati phase 3 (setting)"}[hm])
        if hm == 8:
            tags.append("Ashtama Shani (8th from Moon)")
        if hm in (4, 7, 10):
            tags.append(f"Kantaka Shani ({ORD[hm]} from Moon)")
        if hl == 8:
            tags.append("Ashtama Shani from Lagna (secondary view)")
        if hl in (1, 4, 7, 10):
            tags.append(f"Kantaka Shani from Lagna (secondary view, {ORD[hl]})")
        out.append({"from": ist(a, False), "to": ist(b, False), "saturn_in": SIGNS[s],
                    "house_from_moon": hm, "house_from_lagna": hl, "tags": tags or ["none"]})
    return out


def timeline():
    chart = json.load(open(os.path.join(HERE, "chart.json")))
    birth_jd = chart["birth"]["jd_ut"]
    moon = chart["grahas"]["Moon"]["longitude"]
    moon_s = SIGNS.index(chart["grahas"]["Moon"]["sign"])
    lagna_s = SIGNS.index(chart["lagna"]["sign"])
    lo, hi = date_jd(WINDOW[0]), date_jd(WINDOW[1])

    balance, tree = vimshottari(moon, birth_jd)
    md_list = [{"lord": m["lord"], "start": ist(m["start_jd"], False), "end": ist(m["end_jd"], False)}
               for m in tree]
    tl = {
        "window_ist": WINDOW,
        "settings": {"dasha": "Vimshottari", "year_days": YEAR_DAYS,
                     "moon_longitude": moon, "moon_nakshatra": chart["grahas"]["Moon"]["nakshatra"],
                     "node_for_transits": "mean (true-node dates also given)",
                     "timezone": "IST (UTC+5:30)"},
        "dasha_balance_at_birth": {"lord": tree[0]["lord"], "years": round(balance, 4),
                                   "ends": ist(tree[0]["end_jd"])},
        "maha_dashas": md_list,
        "antar_dashas_all": [{"maha": m["lord"], "antar": a["lord"], "start": ist(a["start_jd"], False),
                              "end": ist(a["end_jd"], False)} for m in tree for a in m["antar"]
                             if a["end_jd"] > birth_jd and a["start_jd"] < date_jd("2036-01-01")],
        "window_dashas": dasha_rows(tree, lo, hi),
        "acting_window_dashas_2027_2029": dasha_rows(tree, hi, date_jd("2030-01-01")),
    }

    # Sensitivity: the same dates under other conventions / birth times
    sens = {}
    for label, yd in (("year 365.2422 (tropical)", 365.2422), ("year 365.2564 (sidereal)", 365.2564),
                      ("year 360 (savana)", 360.0)):
        _, tr = vimshottari(moon, birth_jd, yd)
        r = dasha_rows(tr, lo, lo + 1, with_pd=False)
        sens[label] = f"{r[0]['maha']}-{r[0]['antar']} {r[0]['start']} to {r[0]['end']}" if r else "-"
    for t in ("19:15", "19:45"):
        c2 = build_chart(f"2004-01-06 {t}")
        _, tr = vimshottari(c2["grahas"]["Moon"]["longitude"], c2["birth"]["jd_ut"])
        r = dasha_rows(tr, lo, lo + 1, with_pd=False)
        sens[f"birth {t}"] = f"{r[0]['maha']}-{r[0]['antar']} {r[0]['start']} to {r[0]['end']}"
    for label, mode in (("Lahiri ICRC", swe.SIDM_LAHIRI_ICRC), ("Lahiri 1940", swe.SIDM_LAHIRI_1940),
                        ("Lahiri VP285", swe.SIDM_LAHIRI_VP285)):
        swe.set_sid_mode(mode, 0, 0)
        mlon = swe.calc_ut(birth_jd, swe.MOON, FLAGS)[0][0] % 360
        sidereal_setup()
        _, tr = vimshottari(mlon, birth_jd)
        r = dasha_rows(tr, lo, lo + 1, with_pd=False)
        sens[label] = (f"Moon {angdiff(mlon, moon):+.0f}\" vs Lahiri; "
                       f"{r[0]['maha']}-{r[0]['antar']} {r[0]['start']} to {r[0]['end']}")
    tl["dasha_sensitivity"] = sens

    # Transits
    t_lo, t_hi = date_jd("2025-01-01"), date_jd("2031-01-01")
    slow = {}
    for body in ("Saturn", "Jupiter", "Rahu", "Ketu"):
        rows = []
        for e in ingresses(body, t_lo, t_hi, 1.0):
            s = SIGNS.index(e["to"])
            row = {"ist": ist(e["jd"]), "from": e["from"], "enters": e["to"],
                   "house_from_lagna": house_from(s, lagna_s), "house_from_moon": house_from(s, moon_s),
                   "in_window": lo <= e["jd"] < hi}
            if body in ("Rahu", "Ketu"):
                tn = [x for x in ingresses(body, e["jd"] - 120, e["jd"] + 120, 1.0, node="true")
                      if x["to"] == e["to"]]
                row["true_node_ist"] = ", ".join(ist(x["jd"]) for x in tn) or "outside +-120 days"
            rows.append(row)
        slow[body] = rows
    tl["slow_transits"] = slow

    def where(jd):
        out = {}
        for b in ("Saturn", "Jupiter", "Rahu", "Ketu"):
            lon = body_lon(jd, b)
            s = int(lon // 30)
            out[b] = {"sign": SIGNS[s], "degree": dms(lon % 30),
                      "house_from_lagna": house_from(s, lagna_s), "house_from_moon": house_from(s, moon_s),
                      "retrograde": (speed(jd, b) < 0) if b in SWE_ID else True}
        return out
    tl["positions_at_window_start"] = where(lo)
    tl["positions_at_window_end"] = where(hi)

    sat_ing = [e for e in ingresses("Saturn", t_lo, date_jd("2036-01-01"), 1.0)]
    tl["saturn_phases"] = saturn_phases(sat_ing, t_lo, moon_s, lagna_s, date_jd("2036-01-01"))

    st = []
    for b in ("Mercury", "Venus", "Mars", "Jupiter", "Saturn"):
        st += stations(b, lo, hi)
    tl["stations_in_window"] = sorted(st, key=lambda r: r["ist"])

    fast = []
    for b, step in (("Sun", 1.0), ("Mars", 1.0), ("Venus", 0.5), ("Mercury", 0.5)):
        for e in ingresses(b, lo, hi, step):
            s = SIGNS.index(e["to"])
            fast.append({"body": b, "ist": ist(e["jd"]), "from": e["from"], "enters": e["to"],
                         "retrograde": speed(e["jd"], b) < 0,
                         "house_from_lagna": house_from(s, lagna_s), "house_from_moon": house_from(s, moon_s)})
    tl["fast_transits_in_window"] = sorted(fast, key=lambda r: r["ist"])
    tl["eclipses_in_window"] = [{k: v for k, v in e.items() if k != "jd"} | {
        "house_from_lagna": house_from(SIGNS.index(e["at"].split()[0]), lagna_s),
        "house_from_moon": house_from(SIGNS.index(e["at"].split()[0]), moon_s)}
        for e in eclipses(lo, hi)]
    return tl


def print_timeline(tl):
    b = tl["dasha_balance_at_birth"]
    print(f"Dasha balance at birth: {b['lord']} {b['years']} years, ends {b['ends']}")
    for m in tl["maha_dashas"][:4]:
        print(f"  MD {m['lord']:<8} {m['start']} -> {m['end']}")
    print("Window dashas:")
    for r in tl["window_dashas"]:
        print(f"  {r['maha']}-{r['antar']}  {r['start']} -> {r['end']}")
        for p in r["pratyantar"]:
            print(f"      PD {p['lord']:<8} {p['start']} -> {p['end']}")
    print("Sensitivity:", json.dumps(tl["dasha_sensitivity"], indent=1))
    for body, rows in tl["slow_transits"].items():
        for r in rows:
            mark = "*" if r["in_window"] else " "
            print(f" {mark} {body:<8} -> {r['enters']:<12} {r['ist']}  L{r['house_from_lagna']:<2} M{r['house_from_moon']:<2}"
                  f" {r.get('true_node_ist', '')}")
    for s in tl["saturn_phases"]:
        print(f"  Saturn {s['from']} -> {s['to']} {s['saturn_in']:<12} {s['tags']}")
    for s in tl["stations_in_window"]:
        print(f"  station {s['body']:<8} {s['turns']:<10} {s['ist']} at {s['at']}")
    for e in tl["eclipses_in_window"]:
        print(f"  eclipse {e['type']:<18} {e['ist']} at {e['at']} L{e['house_from_lagna']} M{e['house_from_moon']}")


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
    ap.add_argument("cmd", choices=["chart", "verify", "timeline"])
    args = ap.parse_args()
    if args.cmd == "chart":
        c = build_chart()
        c["node_check"] = {
            "true_node_rahu": build_chart(node="true")["grahas"]["Rahu"]["longitude"],
            "mean_node_rahu": c["grahas"]["Rahu"]["longitude"],
        }
        print_chart(c)
        write_json("chart.json", c)
    elif args.cmd == "verify":
        r = verify()
        c = json.load(open(os.path.join(HERE, "chart.json")))
        c["verification"] = r
        write_json("chart.json", c)
    elif args.cmd == "timeline":
        tl = timeline()
        print_timeline(tl)
        write_json("timeline.json", tl)


if __name__ == "__main__":
    main()
