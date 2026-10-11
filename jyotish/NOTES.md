# NOTES — Krish's reading, 11 Oct 2026 to 11 Oct 2027

Working log. Done / next / open questions.
Math lives in `chart.json` and `timeline.json`.
Meaning lives in `LIFE-READING.md`.

## How to run

pyswisseph won't install into the system Python here
(Debian setuptools `install_layout` bug), so use a venv:

    python3 -m venv /tmp/jvenv
    /tmp/jvenv/bin/pip install pyswisseph pymeeus ephem
    /tmp/jvenv/bin/python jyotish.py chart

Moshier ephemeris only (built into Swiss Ephemeris).
No .se1 files. The script checks the Moshier flag on
every planet call and stops if it wasn't used.

## Done

### Stage 1 — chart (code)
- `jyotish.py chart` -> `chart.json`.
- Sidereal, Lahiri (swe.SIDM_LAHIRI), whole-sign houses.
- Birth 2004-01-06 19:30 IST = 14:00 UT, JD 2453011.083333.
- Lahiri ayanamsa at birth: 23°54'47".
- Lagna: Cancer 16°55' (Ashlesha pada 1).
- Moon: Gemini 9°46'42", Ardra pada 1. Matches the told nakshatra
  (still to be checked in Stage 2).
- Mercury turned direct at 19:14 IST, 16 min before birth,
  so it was stationary. Jupiter turned retrograde 62 h before birth.
- Nodes: mean node used. True node is Aries 25°08' vs mean 23°30'.
  Same sign, nakshatra (Bharani), pada (4) and D9 either way,
  so the choice doesn't change the natal chart.
- D9 Lagna Sagittarius. D10 Lagna Leo.
- Yogas found (rules recorded in chart.json):
  - Budha-Aditya (Sun + Mercury in Sag; Mercury not combust).
  - Mars is yogakaraka (rules 5 and 10), placed in the 9th.
  - Raja-yoga links: Saturn (7/8) and Mars (5/10) aspect each other.
    Saturn and Moon (1) are conjunct. Both are mixed, since Saturn also rules the 8th.
  - Sun and Jupiter exchange signs (2nd and 6th houses): a Dainya
    parivartana by house. It also counts as a dhana link (2nd lord and 9th lord).
  - Sarala (8th lord in 12th) and Vimala (12th lord in 6th): Viparita Raja.
  - Kemadruma is formally present (nothing in the 2nd or 12th from the Moon)
    but cancelled by the kendra rule.
  - Vesi (Venus 2nd from Sun). Adhi is partial (Mercury, Venus in 7/8 from Moon).
  - Moon and Saturn are conjunct in the 12th. "Punarphoo" and "Vish" are modern names for this.

### Stage 2 — verify (DONE: all checks agree)
`jyotish.py verify` writes `verification` into chart.json.
- (a) Second method, no Swiss Ephemeris: own Julian Day (Meeus ch.7),
  own Delta-T (Espenak-Meeus), own Lahiri (23°15'00.658" on 1956-03-21
  minus that day's nutation, then IAU 2006 precession), Moon by Meeus
  ch.47 (pymeeus), Sun by VSOP87 (pymeeus), Lagna by Meeus sidereal time.
  Results vs Swiss Ephemeris:
  - Lahiri ayanamsa: 23.913163 vs 23.913127, diff 0.1".
  - Moon: diff 1.2". Sun: diff 0.1". Lagna: diff 0.1".
  - Third method, PyEphem Moon: diff 1.2".
  - Moon nakshatra by all three: Ardra pada 1. **The told nakshatra (Ardra) is confirmed.**
- (b) Full moon, Jan 2004: Swiss Ephemeris and Meeus ch.49 both give
  7 Jan 2004 15:40 UT. Birth is 25.7 h before that. Sun-Moon angle at
  birth is 168.11°, against 168.20° expected from the relative speed
  (11.03°/day). That fits.
  Web: NASA (Espenak) and USNO, two independent sources, both say 7 Jan
  2004 15:40 UT. lunaf.com agrees.
- (c) Published ephemeris (findyourfate.com 0h GMT, matched by signsbystars):
  every body is within 0.9' on 6 and 7 Jan 2004. Values are rounded to 1'.
  Its "Node" is the mean node (0.2' off); the true node is 1.7° off.
- (d) Published Lahiri: 23°54'34" true on 1 Jan 2004 (jagannathhora table).
  Ours is 23°54'35" true on 6 Jan. The ~1" gap is 5 days of precession.
  IAE J2000 mean 23°51'25.53" = Swiss Ephemeris.
- (e) Blind recompute by a separate agent. It never saw our files, used
  PyEphem plus its own Meeus formulas, and derived Lahiri itself:
  - Lagna 106.91679 (ours 106.91680). Moon 69.778716 (ours 69.778425, 1.0").
  - All planets within 1.3". Ardra pada 1. Jupiter and Saturn retrograde.
  - It found the same Mercury station time (13:44 UT = 19:14 IST).
  - It found the Moon reaches Ardra pada 2 only at ~19:56 IST.
- Web station times: Mercury direct 6 Jan 19:14 (aaps.space, JPL
  Horizons). Jupiter retrograde ~4 Jan 05:15 IST (aaps.space, vedicmarga).
  Both match chart.json.
- (f) Rule audit by a separate agent against BPHS/Phaladeepika. It confirmed:
  nakshatras, dasha order, D9 and D10 rules, exaltation, friendships,
  combust orbs, sambandha and parivartana typing. Fixes made:
  - Mercury joined by the Sun counts as a malefic (BPHS 3.11). The bright
    Moon (168° from Sun) counts as a benefic.
  - Adhi needs benefics IN the 6th, 7th and 8th from the Moon (BPHS 37.5).
    Here only Venus (8th) qualifies, so it is partial, a commentary view only.
  - Amala needs ONLY benefics in the 10th (BPHS 36.5). Absent here anyway.
  - Gaja Kesari: from the Lagna OR the Moon (BPHS 36.3). Absent either way.
  - Kemadruma: now reported as "formed but cancelled". The BPHS 37.11
    kendra-from-Lagna clause is met (Venus). The kendra-from-Moon clause is from later texts.
  - Viparita (Sarala, Vimala): the modern form holds. The strict Uttara
    Kalamrita 4.22 form fails: Saturn and Mercury are linked with other lords.
  - Node aspects are now listed apart, marked disputed.
  - Kala Sarpa is labelled modern. Moolatrikona is checked before exaltation
    for the Moon and Mercury. Float-safe boundaries. Neecha Bhanga rules
    widened (no planet is debilitated here, so no effect).
  - The timeline was re-run after the fixes: unchanged.
- Birth-time test:
  - 19:15 Lagna Cancer 13°31'. 19:30 Cancer 16°55'. 19:45 Cancer 20°20'.
  - The Lagna stays Cancer from 18:15 to 20:26 IST. **STABLE.**
  - Method 2 gives the same 19:15/19:45 Lagnas.
  - The Moon stays Ardra pada 1 at all three times.
  - NOT stable: Lagna nakshatra (Ashlesha only from 19:29),
    D9 Lagna (Sagittarius 19:29-19:43), D10 Lagna (Leo 19:22-19:34).
    Planet signs in D9/D10 are stable; their HOUSES (counted from the
    D9/D10 Lagna) are not.
  - Dasha dates shift about 62 days per 15 min of birth-time error.

### Stage 3 — time periods (code)
`jyotish.py timeline` -> `timeline.json`.
- Rahu dasha balance at birth: 13.80 years, ending 24 Oct 2017.
- Jupiter Mahadasha: 24 Oct 2017 - 24 Oct 2033.
- The whole reading year falls in Jupiter-Venus antardasha
  (6 Sep 2025 - 7 May 2028). Pratyantars:
  - Rahu: 21 Aug 2026 - 14 Jan 2027
  - Jupiter: 14 Jan - 24 May 2027
  - Saturn: 24 May - 25 Oct 2027
- After that: Jupiter-Sun (7 May 2028 - 23 Feb 2029),
  then Jupiter-Moon (to 25 Jun 2030).
- Sensitivity of the Jupiter-Venus start date:
  - 365.2422 or 365.2564-day year: same day.
  - Lahiri ICRC: same day. Lahiri 1940: 8 days earlier. VP285: 3 days later.
  - 360-day year: 15 May 2025 (minority convention, not used).
  - Birth at 19:15: 7 Nov 2025. Birth at 19:45: 6 Jul 2025.
  - So the antardasha is safe. Pratyantar edges carry about ±2 months
    if the birth time is off by 15 min.
- Transits (mean node; true-node dates in the json):
  - Saturn: Pisces (L9, M10) until 3 Jun 2027; Aries (L10, M11) until
    20 Oct 2027; Pisces again to 23 Feb 2028; Aries to 8 Aug 2029.
  - Jupiter: Leo 31 Oct 2026; back to Cancer 25 Jan 2027; Leo 26 Jun 2027.
  - Rahu to Capricorn (L7, M8), Ketu to Cancer (L1, M2) on 5 Dec 2026.
    True node: 25 Nov 2026.
- Saturn phases (from the Moon, Gemini):
  - Kantaka (10th from Moon) while Saturn is in Pisces.
  - No Sade Sati and no Ashtama in the year.
  - Sade Sati starts 8 Aug 2029 (brief), then fully on 17 Apr 2030.
- Eclipses in the window:
  - Annular solar, 6 Feb 2027, Cap 23°23': 7th house, 3° from Venus.
  - Total solar, 2 Aug 2027, Cancer 15°40': 1.25° from the Lagna degree.
  - Three penumbral lunar eclipses.
- At window start (11 Oct 2026): a new moon in Virgo. Mars (debilitated)
  and Jupiter (exalted) are together in Cancer on the Lagna. Venus (the
  antardasha lord) is retrograde in Libra since 3 Oct, direct 14 Nov.

## Stage 4 — confidence tracker (competing readings per life area)

Status: PRIOR (before research). These will be updated as verified
sources come in. Format: reading — confidence — basis.

### Company and money
- A. Steady builder year. Gains come through clients and partners: Venus
  (11th lord) sits in the 7th and is the antardasha lord. Saturn moves to
  the 11th from the Moon on 3 Jun 2027. — prior: medium
- B. Partner and deal friction. Venus is 6th from Jupiter (a 6/8 dasha
  pair). Rahu enters the 7th on 5 Dec 2026, so partners may be unusual or
  foreign, with some fog. — prior: medium
- C. Effort-heavy: money comes through service, competition and debt
  (the 2-6 Dainya exchange). Saturn 10th from the Moon brings work
  pressure until Jun 2027. — prior: medium

### Acting and fame
- A. The public and arts side is strong (Rahu in the 10th, Venus antardasha),
  but this year prepares rather than launches. — prior: medium
- B. The way in is through father and teachers: 5th lord Mars sits in the
  9th. Timing ties to Mars and Sun periods (Jupiter-Sun 2028, Jupiter-Mars
  2030). — prior: low-medium
- C. Real recognition comes later, in the Saturn mahadasha (2033+). — prior: low

### Father and family
- A. The father is a strong, active support and a source of luck (yogakaraka
  Mars in the 9th). — prior: medium
- B. Some friction with father or ego clashes: Sun in the 6th, debilitated
  in D9. — prior: low-medium

### Health and energy (routine only)
- A. Energy follows sleep and mind: Lagna lord Moon in the 12th with Saturn.
  Routine is the lever. — prior: medium
- B. Restless or low-energy patches while Ketu is on the Lagna (Dec 2026 on)
  and Mars is retrograde in Cancer (Mar-Apr 2027). — prior: medium

### Love
- A. Romance is active: Venus antardasha, Venus in the 7th. — prior: medium
- B. Unusual attractions or confusion: Rahu transits the 7th from Dec 2026. — prior: medium

### Learning
- A. Sharp, analytic, competitive mind: Budha-Aditya in the 6th, stationary
  Mercury. Good for self-study and technical depth. — prior: medium

### Travel
- A. Travel and foreign links are favoured: Lagna lord in the 12th,
  Saturn in the 12th, Rahu entering the 7th. — prior: medium

## Next
- Stage 4: research + confidence tracker.
- Stage 5: LIFE-READING.md.

## Open questions
- Lagna sits 15' into Ashlesha (Pushya/Ashlesha cusp). The sign isn't at
  risk. The nakshatra flips to Pushya if birth was before 19:29.
  Present both.
- The birth tithi is 15 (Purnima) by only 0.1°. Chaturdashi ends minutes
  before birth, so the tithi is time-sensitive. It's minor for the reading.
- Dasha dates depend on the Moon's exact degree: 1' of Moon is about 8
  days of dasha. Done in Stage 3: the antardasha is safe, the pratyantar
  edges are ±2 months.
