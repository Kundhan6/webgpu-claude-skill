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

### Stage 2 — verify (code part done; web part pending)
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
  (11.03°/day). That fits. Web confirmation is pending (background agent).
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

## Next
- Stage 2: fold in the web check (full-moon date, published Lahiri value)
  and the blind recompute + rule audit from the background agents.
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
