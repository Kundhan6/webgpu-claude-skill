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

## Stage 4 — research and confidence tracker

### How the research was done
- Nine topic groups (self/mind, career, money, 6-8-12 and learning, love,
  father and acting, dashas, transits, remedies). One agent researched each
  topic, then a second agent tried to refute every claim and re-checked every
  source. 105 findings in all: 93 confirmed by 2+ sources, 12 single-source.
- Main texts reached: BPHS (Santhanam tr. and enjoylearningsanskrit
  Sanskrit), Phaladeepika (Sastri tr., wisdomlib), Saravali (Santhanam tr.),
  Brihat Jataka (Sastri and Neely), Jataka Parijata (Sastri), Uttara
  Kalamrita, Hora Sara, Brihat Samhita. Modern: B.V. Raman, P.V.R.
  Narasimha Rao, Sanjay Rath, Pulippani (Gochar Phaladeepika).
- Limits: some fact-checkers ran out of web searches and had to verify by
  fetching the cited pages directly. Pages that returned HTTP 429 were
  dropped. Health wording that went beyond energy and routine was left out
  on purpose.

### Corrections the fact-checkers caught (they change the reading)
- BPHS 41.16 names the 9th and 5th lords as wealth-givers, NOT the 2nd and
  9th (a popular site mistranslates it). So the Jupiter (9L) and Mars (5L)
  periods are the classical money windows; the Sun period is not.
- Jupiter-Venus antardasha: BPHS's favourable Venus verses are NOT met.
  The verse that IS met is 56.43, Venus 6th from Jupiter: friction with kin
  and partners. The favourable case rests on Phaladeepika 21.43 and 20.49.
- Mercury with the Sun counts as malefic (BPHS 3.11). That weakens Adhi
  and the "gain through enemies" reading of the 2nd lord in the 6th.
- Sarala and Vimala promises come from Phaladeepika alone. Parashara
  (BPHS 23.5-6, 24.96, 24.138) and Raman's practice point the other way.
- The full 9th-10th lord Raja yoga is NOT formed (no Jupiter-Mars link).
  What IS met: Uttara Kalamrita II.82 (Rahu in the 10th, trikona lord
  Mars in the 9th) and Jataka Parijata XV.60/63 (10th lord in a benefic
  navamsa: authority, fame).
- Venus is not the livelihood planet by Phaladeepika 5.1. That makes it
  Jupiter (from the Lagna) or Mars (from the Moon and the Sun).
- Saturn in Aries (11th from the Moon) is classically good, but it is
  debilitated there (Phaladeepika 26.32: good results void). Mars in Libra
  (24 Aug - 8 Oct 2027) blocks it by vedha (obstruction). So the 2027
  "gains" are weak; they point to 2028-29.
- The Rahu pratyantar (to 14 Jan 2027) is adverse in BPHS 61.78. The
  Jupiter pratyantar (to 24 May 2027) is the best stretch (BPHS 61.79,
  plus Phaladeepika 20.34/20.59: dasha lord transiting the Lagna).
- Kemadruma: on BPHS's own wording (Santhanam) it does not even form here.
- The father: BPHS 7.3 reads parents from D12, where the Sun is in its own
  sign Leo. The D9 debility is a modern overlay. Night birth: Brihat
  Jataka 4.5 makes Saturn the co-significator of the father.

### Confidence by life area (updated after research)
Format: reading - confidence - why.

**Company and money**
- A. Effort-led rise with backing. Mars (yogakaraka) is the 10th lord in
  the 9th (BPHS 24.117; JP XV.60/63). The Jupiter mahadasha is a 9th-lord
  period (BPHS 48.6, 41.16). UK II.82 is met. Peak 14 Jan - 24 May 2027.
  - MEDIUM. Many classical supports, but the antardasha is 6/8.
- B. A friction-heavy year with partners and rivals; money leaks.
  BPHS 56.43, PD 20.28-29, BPHS 61.78 (Rahu pratyantar), Saturn 10th from
  the Moon (PD 26.23, Brihat Samhita 104.45), Dainya exchange (PD 6.32-33),
  2nd lord in the 6th (BPHS 13.1-2).
  - MEDIUM. Equally well sourced. Strongest Oct 2026 - Jan 2027, Mar-Apr 2027.
- C. The year builds the structure; the real money window is later
  (Saturn's 11th-from-Moon gains are void in 2027; Jupiter return 26 Oct
  2027; Jupiter-Mars 2030-31 per BPHS 41.16).
  - MEDIUM-LOW. Rests on derived timing rules.
- Leading: A and B together. Mixed, and best from mid-Jan to May 2027.

**Acting and fame**
- A. Fame indicators exist but are contested. Rahu in the 10th (PD 8.27
  famous vs PD 16.28). Mars links the 5th and 10th and aspects the 3rd
  (modern actor rule). The Moon in the 12th ("film", one modern source).
  - LOW-MEDIUM.
- B. The arts come in as a skill, and the path runs through father and
  teachers. The 10th lord in the 9th (Raman: father's great influence,
  hereditary line). Venus is not the livelihood planet (PD 5.1) and is a
  functional malefic (BPHS 34.27).
  - MEDIUM.
- C. Timing: 2026-27 is preparation. The best windows are 2028-29:
  Jupiter-Sun antardasha (May 2028 - Feb 2029; Raman: Sun aspected by
  Jupiter gives success in the Sun's sub-period; BPHS 56.52), and the
  double transit on the 10th from the Lagna (29 Feb - 25 Jul 2028;
  27 Dec 2028 - 30 Mar 2029).
  - LOW-MEDIUM. Timing rests on modern techniques.

**Father and family**
- A. A strong, influential father who is a source of fortune. The 9th from
  the Sun holds the 9th lord (PD 15.21-22). The Sun is own-sign in D12.
  Yogakaraka Mars is in the 9th. Raman: father's great influence.
  - MEDIUM.
- B. An intense or demanding bond, with a father who is often busy.
  The Mars-in-9th verses are harsh (PD 8.10, BJ 20.6). Saturn aspects the
  9th and its lord. PD 16.25 (Sun in a dusthana) gets low weight.
  - LOW-MEDIUM.

**Health and energy (routine only)**
- A. Energy follows mind and sleep: Lagna lord Moon in the 12th with Saturn
  (BPHS 24.12; PD 8.7 "indolent"; Uttara Kalamrita on the 12th and sleep).
  - MEDIUM.
- B. Strong fighting energy: Sun in the 6th (Saravali 30.7: vigour,
  digestive fire; Satyacharya: malefics good in 6/8/12).
  - MEDIUM.
- Watch windows: Ketu on the Lagna from 5 Dec 2026; Mars debilitated on
  the Lagna 10 Mar - 26 Apr 2027; the Saturn pratyantar ("slight trouble",
  BPHS 61.80); 2-9 Aug 2027 (eclipse, then Ketu on the Lagna degree).
  - MEDIUM-LOW.

**Love**
- A. Warm, romantic, practical partner energy: Venus in the 7th (BPHS 18.3,
  BJ 20.8 "lovers' tiffs", PD 8.18; JagannathHora: practical, ambitious
  partner).
  - MEDIUM.
- B. Friction and confusion this year: BPHS 56.43, BPHS 61.78 (to 14 Jan
  2027), Rahu in the 7th from the Lagna from 5 Dec 2026, eclipse near
  Venus 6 Feb 2027.
  - MEDIUM. Counter: Pulippani reads Rahu over Venus (16 Feb 2027) as good.

**Learning**
- A. A sharp, competitive, analytic mind: Budha-Aditya (Saravali 15.4,
  PD 18.1), Mercury in the 6th (PD 8.12), 5th lord in the 9th (BPHS 24.57:
  author), 9th lord in the 2nd (BPHS 24.98: scholar), 4th lord in the 7th
  (BPHS 24.43: learned).
  - HIGH. Many texts agree and it is time-safe.
- B. Study comes in bursts, with breaks; self-study suits him better
  (Raman: "interrupted education"; Mercury's avasthas; PD 8.12 idleness).
  - MEDIUM.

**Travel**
- A. Much movement and foreign links: BPHS 23.11 (12th lord with malefics,
  12th aspected by malefics), Saravali 23.23 via BJ 18.20.
  - MEDIUM.
- B. Travel for purpose, roots at home (BPHS 23.12 benefic side: full Moon
  in the 12th, Jupiter's aspect on Mercury).
  - LOW-MEDIUM.
- This year: business travel themes while Jupiter is on the Lagna
  (Jan-Jun 2027, Pulippani ch. 28) and in the Saturn pratyantar.

## Next
- Stage 4: synthesis workflow (competing readings per area, month by
  month, critic) is running; fold its output into this tracker.
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
