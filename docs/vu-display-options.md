# VU Meter Display Options — 480×320 (3.5")

Design reference: **Magnat MR 780** — black chassis, amber/orange vacuum tubes,
horizontal lines, vintage stereophonic receiver aesthetic.

---

## Option A — Analog Needle VU Meters (Recommended)

Two symmetric needle gauges, black background, amber/orange arc.
Faithful to the MR 780 character — a tube receiver of this class would
originally have shipped with exactly this style of VU meter.

```
┌────────────────────────────────────────────────────────┐
│                                                        │
│        L                          R                   │
│    ╱────────────╲             ╱────────────╲          │
│   ╱  -20 -10 0 +3╲           ╱  -20 -10 0 +3╲        │
│  │       │                  │       │         │       │
│   ╲______╱                   ╲______╱                 │
│     VU L                       VU R                   │
│                                                        │
│  ──────── Jazzanova · Summer Keeps On ────────        │
└────────────────────────────────────────────────────────┘
```

**Palette**
- Background: black `#000000`
- Arc scale + needle: amber `#FF8C00` / `#FFA500`
- Labels (-20, -10, 0, +3): dim amber `#CC6600`
- Track title footer: white or light amber

**Pros:** Most authentic to the equipment; elegant at any distance.
**Cons:** Needle physics require interpolation/smoothing logic (peak hold, ballistics).

---

## Option B — Vertical LED Bar Graph (Vintage Rack Style)

Wide vertical bars, segmented into colour zones — reminiscent of 1980s
rack-mount amplifiers and spectrum analysers.

```
┌────────────────────────────────────────────────────────┐
│  L                                              R      │
│  █                                              █  ←+3 │
│  █                                              █      │
│  █  ← yellow                        yellow  →  █      │
│  █                                              █      │
│  █  ← green                          green  →  █      │
│  █                                              █      │
│  ════════════════════════════════════════════          │
│        Jazzanova  ·  Summer Keeps On                   │
└────────────────────────────────────────────────────────┘
```

**Palette**
- Segments green → yellow → red: `#00CC44` / `#FFAA00` / `#FF2200`
- Background: black
- Inactive segments: very dark version of the segment colour (~10% brightness)

**Pros:** Highly readable at distance; simple to implement.
**Cons:** Less in keeping with the tube-receiver aesthetic of the MR 780.

---

## Option C — Glow Tube Columns (Vacuum Tube Simulation)

Four columns simulating glowing vacuum tubes — directly mirrors the
physical tubes visible on the MR 780 front panel.

```
┌────────────────────────────────────────────────────────┐
│                                                        │
│     ╔═══╗    ╔═══╗    ╔═══╗    ╔═══╗                 │
│     ║░░░║    ║▒▒▒║    ║▓▓▓║    ║▒▒▒║                 │
│     ║░░░║    ║▒▒▒║    ║▓▓▓║    ║▒▒▒║  ← amber glow   │
│     ║░░░║    ║░░░║    ║▒▒▒║    ║░░░║                 │
│     ╚═══╝    ╚═══╝    ╚═══╝    ╚═══╝                 │
│      L1       L2       R1       R2                     │
│                                                        │
│         Eric Clapton · Pilgrim                         │
└────────────────────────────────────────────────────────┘
```

**Palette**
- Tube glow: amber/orange gradient `#FF6600` → `#FF2200` at peak
- Glass border: dark grey `#333333`
- Background: black

**Pros:** Most visually striking; directly references the MR 780 tubes.
**Cons:** Abstract — not a standard metering format; less precise for level reading.

---

## Decision

**Option A selected** for implementation as the primary VU mode.

Rationale: the MR 780 is a tube receiver with a vintage aesthetic. Analog
needle VU meters are the natural companion — they match the equipment's
character without looking like a software simulation.

Options B and C remain available for future implementation as alternative
`display_mode` values (e.g. `vu_bars`, `vu_tubes`).

---

## Implementation notes (Option A)

- VU data source: `/tmp/oceano-vu.sock` — Unix socket, 8-byte frames
  (`float32 left RMS + float32 right RMS`, little-endian), published by
  `oceano-source-detector` at ~5 frames/sec (one per audio buffer of 8192
  samples at 44.1 kHz ≈ 186 ms).
- Needle ballistics: apply attack/decay smoothing
  (fast attack ~50 ms, slow decay ~300 ms) to avoid jitter.
- Peak hold: hold peak position for ~1.5 s before falling.
- Scale: dBFS, range -40 dB to +3 dB. Map RMS float [0.0, 1.0] to dBFS
  via `20 * log10(rms)`, clamp to display range.
- Layout: two gauge arcs side by side, track title + artist in footer,
  optional playback source badge (AirPlay / Physical) top-right.
