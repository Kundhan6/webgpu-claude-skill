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

## Next
- Stage 2: verify ayanamsa + Moon a second way (pymeeus Meeus ch.47
  + own Lahiri formula; PyEphem as a third); web-check the Jan 2004
  full moon; birth-time test at 7:15 / 7:30 / 7:45 PM.
- Stage 3: dashas + transits -> timeline.json.
- Stage 4: research + confidence tracker.
- Stage 5: LIFE-READING.md.

## Open questions
- Lagna sits 15' into Ashlesha (Pushya/Ashlesha cusp). The sign isn't
  at risk, but the Lagna nakshatra may flip with a small time error. Check this in Stage 2.
- The birth tithi is 15 (Purnima) by only 0.1°. Chaturdashi ends minutes
  before birth, so the tithi is time-sensitive. It's minor for the reading.
- Dasha dates depend on the Moon's exact degree: 1' of Moon is about 8
  days of dasha. Report this sensitivity in Stage 3.
