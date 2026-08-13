# Combination Wrenches (Ring-und-Gabelschlüssel)

Measurements of metric combination wrenches (Ringschlüssel = ring/box end,
Gabelschlüssel = open-end), transcribed from a handwritten measurement sheet.

The end goal is a 3D-printable (**TPU**, flexible) drawer-organizer insert
holding all 10 wrenches.

## Files

- `Abmessungen.csv` — measured dimensions per wrench size (`;`-delimited).
- `Abmessungen.jpg` — photo of the original handwritten sheet.
- `WrenchTrayPartDesign.py` — **the current generator.** Builds the whole
  tray as native parametric PartDesign driven by VarSets: parameters, the ten
  pocket profiles, the lane packing, and the slab that subtracts them.
  `import WrenchTrayPartDesign as wpd; wpd.build_all(App.ActiveDocument)`
  on an empty document reproduces the entire model from the CSV — verified,
  delta 0.000000 mm³ against a from-scratch rebuild. It does **not** create
  the raised size numbers; those are hand-built in the saved document (see
  Size labels).
- `WrenchTrayPart.py` — the earlier Part-based generator, producing the same
  pockets as static solids. Kept as the reference the PartDesign build is
  checked against, as the source of the validated 1:1 drawings, and as the
  owner of the CSV reader (`load_wrench_rows`, imported by the other module).
- `Printables/` — a downloaded reference insert for a Gedore set, for
  visual comparison only (CC BY-NC-SA, not used in the design).

## Columns

The sheet groups the measurements as **Dicke** (thickness), **Länge**
(length) and **Höhe** (height):

| Column | Group | Meaning |
|--------|-------|---------|
| `Gr`   | —      | Größe (size), e.g. wrench size 6, 7, 8 ... 19 |
| `D0`   | Dicke  | Thickness at the neck (shaft between ring and fork) |
| `Dr`   | Dicke  | Thickness at the ring end |
| `Dg`   | Dicke  | Thickness at the fork (open-end) |
| `L`    | Länge  | Total (overall) length of the wrench |
| `Lr`   | Länge  | Length of the ring section |
| `Lg`   | Länge  | Length of the fork section |
| `H0`   | Höhe   | Height of the neck |
| `Hr`   | Höhe   | Height of the ring |
| `Hg`   | Höhe   | Height of the fork |
| `Hu`   | Höhe   | "Oben" — how far the fork's top rises above the neck's top |

**Thickness vs. height matters.** Lay a wrench flat on the bench: `D*` is
how tall it stands (the thin dimension), `H*` is how wide the head looks
from above. For size 6 the ring is only 5.0 mm thick but 11.9 mm across.

The ring is **centred** on the shaft's centreline; the fork is **not** —
it sits higher, and `Hu` is exactly that offset. The fork is the tallest
part of the wrench in every recorded size, so the fork's top is the natural
reference plane for the whole tool.

Sizes jump (6, 7, 8, 9, 10, 12, 13, 14, 15, 19) matching standard wrench
size steps — not every consecutive size was recorded.

## Source sketch

The original sheet has two small reference drawings above the table:

- A side-view outline of the wrench giving the length dimensions
  (`L`, `Lr`, `Lg`) and the thicknesses (`D0`, `Dr`, `Dg`).
- An end-on view of the ring/fork profile giving the height dimensions
  (`H0`, `Hr`, `Hg`, `Hu`).

Note: the sheet labels the fourth height `Ho`; it is really `Hu`
("upper distance"), corrected in the CSV.

## Terminology

- **Ringschlüssel** = ring spanner / box-end wrench
- **Gabelschlüssel** = open-end wrench / open-end spanner
- A tool combining both ends (as measured here) = **combination wrench**
  (British English: ring and open-end spanner)

---

# Insert design

The wrenches stand **on edge** in narrow slots. This is the key point, and
getting it backwards wastes a lot of time: the top-view slot width comes from
the `D*` (thickness) columns, the slot depth from the `H*` (height) columns.

## Top-view outline — VALIDATED

Printed 1:1 (TechDraw, A4 landscape, content 236.5 × 201.7 mm) alongside a
100 mm calibration bar that measured exactly 100 mm. Real wrenches laid on
the printout fit nicely (spot-checked, not all 10 sizes).

Per size, in local coordinates with the ring at x = 0:

| Part | Geometry |
|------|----------|
| ring rect | `Lr` × (`Dr` + 2·`ring_clr`), stretched **20 % about its own centre**, rotated **15°** about its **inner-top corner** so the outer end swings *down*, then shifted left so its outer extreme returns to `−0.1·Lr` |
| fork rect | `Lg` × (`Dg` + 2·`fork_clr`), stretched 20 % about its centre |
| neck band | (`D0` − `neck_grip`) wide, spanning **`0.6·Lr` … `L`** |

Outline = ring ∪ neck ∪ fork.

**Clearances** (parameters, not constants):

| Parameter | Value | Purpose |
|-----------|-------|---------|
| `ring_clr` / `fork_clr` | **+1.0 mm per side** | loose drop-in fit |
| `neck_grip` | **−0.3 mm total** | interference fit — the flexible TPU grips the shaft, so the wrench is held by its neck while the ends sit loose |
| head stretch | **1.2** | end play along the wrench axis; scales with size (≈1.2 mm on Gr06, ≈3.0 mm on Gr19) |

**Why `0.6·Lr` for the neck start:** the stretched ring rectangle swings
further down under the 15° tilt, so at `0.5·Lr` the neck band pokes above the
ring's top edge on the larger sizes. Measured minimum across all 10 sizes was
0.535 (Gr15) and 0.530 (Gr19); 0.6 clears everything.

The 15° ring offset is standard on combination wrenches — it lets the tool be
flipped end-for-end for extra socket positions in tight spots.

## Pocket depth (front view) — VALIDATED

Printed 1:1 across two A4 landscape sheets (sizes 6–12 and 13–19, each with
its own calibration bar) and matched against the real wrenches. **All ten fit
perfectly in both views.**

Reference plane is the **fork's top** (the wrench's highest point), depths
measured downward from there:

| Region | Depth |
|--------|-------|
| fork   | `Hg` |
| neck   | `H0 + Hu` |
| ring   | `Hu + (H0 + Hr) / 2` |

The ring term follows from the ring being *centred* on the shaft's centreline
(which sits at depth `Hu + H0/2`) and extending `Hr/2` either side. Verified
arithmetically across all 10 rows: ring depth always falls between neck and
fork, and the fork is always deepest — so the fork sets the slab height.

**No vertical clearance.** The measured depths fit as-is; the pocket floors
are cut to exactly the values above.

### Floor flare

The neck is not a constant height — it widens before meeting each head. A
pocket floor with a hard step at the head would leave the wrench resting on
that step instead of seating. So each head's inner-bottom corner is joined to
the neck floor by a **triangular ramp at 45°** (`FLARE_DEG`), on the *lower*
side only — the upper side needs no transition because the pocket is open at
the top.

At 45° the horizontal run equals the depth step, e.g. Gr19: 7.35 mm on the
ring side, 12.40 mm on the fork side; Gr06: 2.65 mm and 4.30 mm.

### Top alignment and recess

All wrenches are **aligned with each other at the top**, and sit **2 mm below
the tray's top surface** (`TOP_OFFSET`).

The alignment falls out of the depth model automatically: every pocket is
measured down from the fork's top, and the fork is the tallest point on every
size, so a common reference plane aligns all ten wrench tops. Pockets simply
reach different depths beneath it.

`TOP_OFFSET` is then added uniformly to all three depths, so the pocket walls
stand 2 mm proud of every wrench:

| Region | Depth below tray top |
|--------|----------------------|
| fork   | `Hg + TOP_OFFSET` |
| neck   | `H0 + Hu + TOP_OFFSET` |
| ring   | `Hu + (H0 + Hr)/2 + TOP_OFFSET` |

### Walls and footprint

| Parameter | Value |
|-----------|-------|
| `outer_wall` | 6 mm |
| `divider` | 4 mm — *minimum clearance between adjacent pockets* |

For reference, the Printables model measures **5.85 mm** outer wall and
**~7 mm** dividers — but it is printed in rigid plastic. In TPU the walls also
have to resist splaying, or the neck's interference grip is lost.

### Lane packing

`divider` is a **true minimum distance between pocket outlines**, not a
bounding-box pitch. Stacking bounding boxes wastes a lot: adjacent pockets are
widest at *different* x (one lane's ring bottom corner vs the next lane's ring
pivot corner), so boxes that touch leave 3–8 mm of dead space between the
actual pockets — 48.8 mm over the whole set.

`pack_lanes(tight=True)` instead slides each lane up until its measured
outline-to-outline distance equals `divider`.

| packing | width |
|---------|-------|
| bounding-box, 5 mm | 210.7 mm |
| tight, 5 mm | 161.9 mm |
| **tight, 4 mm** | **152.5 mm** |

Note the closest approach is a *point* contact between two ring corners, so
the wall is only `divider` thick right there and thicker everywhere else.

Resulting tray: **248.5 (L) × 152.5 (W) × 46.2 (H) mm**, stepped on the right
(see Decisions). Fits a 300 × 300 bed with room to spare.

### Slab height

`floor_thickness` = **5 mm** of material below the deepest pocket, giving:

| | mm |
|---|---|
| `TOP_OFFSET` | 2.0 |
| deepest pocket (Gr19 fork, `Hg`) | 39.2 |
| `floor_thickness` | 5.0 |
| **total slab height** | **46.2** |

The slab is sized by the single deepest pocket, so smaller sizes leave more
material beneath them — Gr06's fork pocket bottoms out 16.2 mm down, leaving
30 mm of solid below it.

Note the recess is applied to the *tray*, not the wrench profile: the
`FrontGr*` drawings are the wrench outline (what was validated on paper) and
are unaffected by `TOP_OFFSET`.

## Decisions

- **Layout:** simple parallel lanes, every wrench the same way round
  (ring left, fork right), sorted ascending by size. An alternating/nested
  layout was considered and rejected.
- **Left-aligned:** each lane's pocket bounding box sits exactly `outer_wall`
  from the tray's left edge, so the ring ends line up. (The pockets' own left
  extents differ slightly, −1.20 mm on Gr06 to −2.96 mm on Gr19, because the
  20 % head stretch scales with `Lr`.)
- **Block:** flat slab, uniform height, but **stepped on the right** —
  each lane is only as long as its own wrench needs, giving a staircase
  outline like the Printables reference. Saves 29 % of the volume
  (2.42 → 1.71 dm³) with no loss of function.
- **Fusing the 10 lanes:** use a plain Python `.fuse()` loop into a single
  `Part::Feature`. Do **not** use `Part::MultiFuse` — see the documented
  dead-ends block in `../TaperedLetters.py`.

## Working notes

**Never delete-and-recreate an object a TechDraw view points at.** FreeCAD
links bind to object *identity*, not name. `doc.removeObject(name)` followed
by `doc.addObject(..., name)` leaves the view's `Source` as `[]`, and the page
keeps rendering its last cached geometry with no error and no visual cue —
even with `Page.KeepUpdated = True`. This silently printed a stale ring length
for several iterations. Mutate `obj.Shape` in place instead; if a recreate is
unavoidable, re-point every dependent link explicitly and assert
`view.Source` is non-empty.

Related: dimensions reference sub-elements positionally (`Vertex0`, `Edge7`),
so re-pointing a view's `Source` can leave them measuring something else
entirely. Verify or rebuild them.

Also note `Name` is immutable in FreeCAD; only `Label` can be renamed. And
labels must be unique, so creating a replacement while the original still
holds the label auto-increments it (`TopGr06` → `TopGr001`).

**`Shape.copy()` can silently break TechDraw rendering for edge-only
compounds.** Recreating an object by assigning `new.Shape = old.Shape.copy()`
worked fine for the outline *faces*, but the calibration bar — a
`Part.makeCompound` of 12 bare edges with no face — then refused to project
into the view. The object was valid, visible and correctly listed in
`view.Source`, yet contributed 0 edges to the render. Rebuilding the identical
geometry from scratch fixed it immediately. When recreating edge-only objects,
rebuild the shape rather than copying it.

**Verify renders by measuring, not by asserting.** `view.getVisibleEdges()`
returns the *cached* render and can lag a source change, so a reading taken
straight after re-linking may be stale. Print the real count and compare it to
the expected total rather than printing an assumed total alongside it — an
assumed label next to a stale number looks like confirmation when it is not.

## Current state

FreeCAD document `WrenchOrganizer`:

| Object | Contents |
|--------|----------|
| `VarSet` | the 12 fit/tray parameters |
| `VarSetGr06`…`VarSetGr19` | the CSV, one VarSet per size, plus derived `RingXMax` |
| `TrayDerived` | `SlabHeight` plus the five `Outline*` values driving `TraySketch` |
| `ProfileGr06`…`ProfileGr19` | parametric pocket bodies |
| `WrenchTray` | the finished tray, including the hand-built size labels |
| `Label06`…`Label19` | Draft ShapeStrings (inside `WrenchTray`), one per size |
| `LabelPad06`…`LabelPad19` | 0.6 mm pads of those strings, chained after `Chamfer` |
| `TopViewGroup` / `FrontViewGroup` | flat 2D faces, the 1:1 paper validation record |

### Parameters live in VarSets

`VarSet` holds the fit parameters; each `VarSetGr<nn>` holds one CSV row plus a
derived `RingXMax`. Every sketch dimension is an expression referencing them, so
changing a parameter rebuilds the geometry.

**`SlabHeight` lives on `TrayDerived`, not `VarSet`.** FreeCAD's dependency
graph is **per-object, not per-property**: `VarSet.SlabHeight` reading
`VarSetGr19.Hg` makes `VarSet` depend on `VarSetGr19`, and `RingXMax` reading
`VarSet.HeadStretch` closes the loop. FreeCAD rejects it as cyclic even though
no single property is circular. A third object breaks the cycle.

`RingXMax` has a closed form — the max-x corner is the ring's inner-*bottom*
one, at `(0, −w)` from the pivot, so the rotation contributes exactly
`w·sin(tilt)`:

```
RingXMax = Lr*(1+HeadStretch)/2 + (Dr + 2*RingClearance)*sin(RingTilt)
                                - HeadStretch*Lr*(1 - cos(RingTilt))
```

### Tray architecture

Ten independent profile bodies, subtracted via one `PartDesign::Boolean` of
type **Cut**. The result is still a `PartDesign::Body`, so chamfers and fillets
can be added afterwards — verified.

The alternative (pocketing all ten profiles into one body) was rejected. Both
give a single editable body, but option 1 keeps the tray's own history at three
features instead of ~82, isolates failures to one profile, positions each lane
with a single `Placement` instead of baking offsets into 30 sketches, and — most
importantly — keeps each chamfer referencing only its own profile's topology.

Verified: slab 1318918.98 − pockets 202696.42 = **1116222.56 mm³, delta
0.000000**, one valid solid.

### Rebuilding from source

`wpd.build_all(doc)` on an empty document reproduces the parametric tray:
VarSets from the CSV, ten profiles, the packing, the tray, then `verify_tray()`.
Verified against a from-scratch rebuild — identical profile volumes and lane x
positions, delta 0.000000 mm³. The size labels are **not** part of that; a
from-scratch rebuild has a bare tray, and the numbers have to be put back by
hand (or copied from the saved document).

Lane **y** positions come out 0.008–0.029 mm lower than the values in the
saved document. `pack_lanes()` floors each placement to two decimals, and
flooring moves a lane *away* from its neighbour, so gaps land at 4.001–4.008
instead of exactly 4.000 and the error accumulates down the stack. Deliberate:
readable placements that can only ever be safe.

### The tray outline

`TraySketch` is a **six-line diagonal outline**, not a staircase: top edge, one
long bevel, a short flat above Gr19, then the right, bottom and left walls.

```
(0, 0) ──────────── (DiagX, 0)
                          ╲
                            ╲            (Right − StepLength, StepY) ── (Right, StepY)
                                                                              │
(0, Bottom) ───────────────────────────────────────────────── (Right, Bottom)
```

It is **fully constrained** (17 constraints, 0 DoF) and every dimension is an
expression onto `TrayDerived`:

| Constraint | Property | Expression |
|---|---|---|
| `DiagX` | `OutlineDiagX` | `Gr06.Placement.x + L + (HeadStretch−1)/2·Lg + OuterWall` |
| `Right` | `OutlineRight` | same, on Gr19 |
| `StepY` | `OutlineStepY` | `Gr19.Placement.y + (Dg + 2·ForkClearance)/2 + OuterWall` |
| `Bottom` | `OutlineBottom` | `Gr19.Placement.y + w·(0.5 − cos tilt) − HeadStretch·Lr·sin tilt − OuterWall`, `w = Dr + 2·RingClearance` |
| `StepLength` | `OutlineStepLength` | **literal 22 mm** — the one free design choice |

`StepLength` is arbitrary: it fixes where the bevel lands on the step line and
therefore the bevel's slope. Everything else is derived, so the walls around
Gr19 are exactly `OuterWall` on both the right and the top.

Two closed forms worth keeping. The **local xmin** of a profile is
`−(HeadStretch−1)/2·Lr` — the tilt and the left-shift cancel exactly, leaving
only the stretch. The **local ymin** is `w·(0.5 − cos tilt) − HeadStretch·Lr·sin tilt`
at the tilted ring's outer-bottom corner.

The top-left corner is pinned to the sketch origin, which encodes the packing's
convention that every pocket sits `OuterWall` from the left and top walls. That
holds as long as the placements are generated by the packing step; changing
`OuterWall` without re-running it widens the right and bottom walls only.

**The bevel does not guarantee containment the way per-lane strips did.** An
earlier attempt at a staircase from midpoint bands leaked 1007 mm³ — tight-packed
lanes interleave in y, so a cut at the midpoint between neighbours leaves part of
a long pocket hanging over a shorter lane's band. The diagonal avoids that by
clearing every lane by construction, but only for the current parameters:
**re-run the containment check after any parameter change** (cut each profile
against `TrayPad`, expect 0.0000 mm³ each). Current clearances to the bevel,
perpendicular: Gr06 8.88, Gr07 9.71, Gr08 8.81, Gr09 10.10, Gr10 10.88,
**Gr12 5.57** (tightest), Gr13 7.74, Gr14 10.30, Gr15 14.56.

### Size labels

Raised size numbers on the tray top, **hand-built in the FreeCAD document**,
not emitted by `WrenchTrayPartDesign.py`. They are ordinary PartDesign pads
of Draft ShapeStrings, so the text stays editable (`String`, `Size`,
`Placement`) after the fact.

**Do not bake this into the generator.** Placement is visual — especially
where the bevel eats the wall to the right of a two-digit number — and a
full recompute of the pad chain on this body is slow enough to freeze the
GUI.

Each size is a pair inside `WrenchTray`, immediately adjacent in the body's
group so the pad's profile is in scope:

```
… Chamfer
ShapeString     (Label06)  ->  LabelPad06
ShapeString001  (Label07)  ->  LabelPad07
…
ShapeString009  (Label19)  ->  LabelPad19   ← current Tip
```

How each pair was made:

1. `Draft.make_shapestring(String, FontFile, Size=6.0, Tracking=0)` with
   `MakeFace = True`. Font is DejaVu Sans Bold
   (`/usr/share/fonts/dejavu/DejaVuSans-Bold.ttf`).
2. Place the string on the top plane (`z = 0`). Most sizes sit just past the
   fork, centred on the shaft. **Gr19** has no wall to the right, so it sits
   **below the fork head**. **Gr12** was nudged down and in by hand so the
   two-digit glyph clears the bevel (the default “right of fork, shaft
   centre” placement hangs off the outline there).
3. `PartDesign::Pad` named `LabelPad<nn>`, `Length = 0.6 mm`,
   `Reversed = False` (up, out of the top face). `BaseFeature` is the
   previous tip, so the chain is Chamfer → Pad06 → Pad07 → … → Pad19.
4. Put the ShapeString **inside** `WrenchTray` with
   `body.insertObject(ss, pad, after=False)` — i.e. immediately before its
   pad. Hide the 2D overlay; the pad is the visible solid.

**Labels must be unique.** Name the string `Label06` and the pad
`LabelPad06`. If both try to be `Label07`, FreeCAD silently renames the
second to `Label002` and the tree no longer matches.

**The ShapeString must live in the same body as the pad.** A pad whose
`Profile` points at a document-root ShapeString still builds a correct
solid, but PartDesign warns:

```
PartDesign::Pad: Link(s) to object(s) 'ShapeString009' go out of the
allowed scope 'LabelPad19'. Instead, the linked object(s) reside within 'N/A'.
```

`insertObject` is required here, not `addObject`. `body.addObject(ss)` makes
the ShapeString the Tip immediately, so `body.Tip.Shape` becomes the 2D
faces and the tray solid vanishes from the tip until you put it back.

Rejected, in order:

- A baked `Part.makeWireString` solid assigned onto a `PartDesign::Feature`
  in an extra body, then `PartDesign::Boolean` Fuse into `WrenchTray`.
  Works, but the text is a dead solid — changing “6” to “7” means rebuilding
  the shape in Python. The ShapeString pad is the same number of features
  without the extra body.
- Padding the ShapeString while it still sat at document root. Looks fine;
  the out-of-scope warning is the only symptom, and it is real.

Mutate `ShapeString.Placement` / `.String` in place and recompute. Do not
delete-and-recreate a pad a later pad uses as `BaseFeature`. And do not
recompute the whole ten-pad chain in a tight loop — that is what froze the
GUI during the first placement pass.

---

# Construction details

Everything above is *what* was decided and validated. This section is the
*how* — the implementation choices that are not derivable from the design
description alone.

## Coordinate convention

Work per wrench in local coordinates: **x** along the wrench (ring at x ≈ 0,
fork at x ≈ `L`), **y** across its thickness, **z** vertical with the tray's
top surface at **z = 0** and pockets cut downward (negative z).

## Top-view outline, precisely

With `ring_w = Dr + 2·ring_clr`, `fork_w = Dg + 2·fork_clr`,
`neck_w = D0 − neck_grip`, and `stretch(a, b, f)` growing the span `a…b` by
factor `f` about its own midpoint:

```
rx0, rx1 = stretch(0, Lr, 1.2)            # -0.1*Lr .. 1.1*Lr
fx0, fx1 = stretch(L - Lg, L, 1.2)        # L-1.1*Lg .. L+0.1*Lg

ring: rectangle (rx0..rx1) x (-ring_w/2 .. +ring_w/2),
      rotated +15 deg about the pivot (rx1, +ring_w/2)   [inner-TOP corner],
      then translated in -x so that min(x) of the rotated corners == rx0
fork: rectangle (fx0..fx1) x (-fork_w/2 .. +fork_w/2)
neck: rectangle (0.6*Lr .. L)  x (-neck_w/2 .. +neck_w/2)
```

Rotation is counter-clockwise in the xy-plane, which sends the ring's **outer**
end **downward** (−y). The resulting left-shift is
`(rx1 − rx0)·(1 − cos 15°)` = `1.2·Lr·(1 − cos 15°)` — note it scales with the
*stretched* length, not `Lr` (0.49 mm on Gr06, 1.21 mm on Gr19). Rather than
hard-coding it, just translate by `min(x of rotated corners) − rx0`.

Sanity checks worth keeping: the fused outline must be a single face with a
single outer wire, and the neck band's start edge (both corners at
`x = 0.6·Lr`) must lie *inside* the rotated ring polygon.

## Depth region boundaries

The regions are clipped by **x**, and the boundaries are **not** simply `Lr`
and `L−Lg`:

| Region | x range |
|--------|---------|
| ring   | `x < ring_x_max` |
| neck   | `ring_x_max ≤ x < fx0` |
| fork   | `x ≥ fx0` |

where `ring_x_max` is the **maximum x of the rotated, shifted ring polygon** —
*not* `Lr`. Stretching and tilting push the ring's inner-bottom corner well
past `Lr`: **+2.52 mm on Gr06 rising to +5.01 mm on Gr19**. If that protruding
sliver were cut at the shallower neck depth it would form a step under the
ring and physically stop the wrench seating.

`fx0` is the fork rectangle's stretched inner edge (`L − 1.1·Lg`).

## Floor flare, precisely

Depths (all positive, measured down from z = 0):

```
d_fork = Hg              + TOP_OFFSET
d_neck = H0 + Hu         + TOP_OFFSET
d_ring = Hu + (H0+Hr)/2  + TOP_OFFSET
```

The flare is a ramp on the pocket **floor** between the neck and each head.
In the xz-profile, with `t = tan(FLARE_DEG)`:

```
ring side:  run = (d_ring - d_neck) / t
            from (ring_x_max, -d_ring) rising to (ring_x_max + run, -d_neck)

fork side:  run = (d_fork - d_neck) / t
            from (fx0, -d_fork) rising to (fx0 - run, -d_neck)
```

Both ramps face *into* the neck, i.e. the ring ramp runs toward +x and the
fork ramp toward −x. Only the floor is ramped; the pocket is open at the top
so no ceiling transition is needed.

**2D → 3D: build it as an intersection, not region-by-region.** Both
validated drawings are flat profiles, but the pocket is a solid. The clean way
to combine them — and what `WrenchTrayPart.py` does — is:

```
pocket = (top-view outline extruded down by the slab height)
         INTERSECT
         (front-view depth profile extruded sideways across the width)
```

This reproduces exactly the two drawings that were validated on paper and
needs no special handling for the ring's 15° plan tilt: the tilt lives
entirely in the first operand, the depths entirely in the second.

Both flare ramps end up axis-aligned, which is correct — the transition
happens along the *shaft*, which is axis-aligned, not along the tilted ring.
The ring's own region is simply cut to the full ring depth throughout, and the
ramp begins at `ring_x_max` where the neck band takes over. Cutting a little
deeper than needed under the ring is harmless; cutting too shallow is what
would block seating.

The alternative — extruding each depth region separately and unioning them —
also works but makes reconciling the tilt with the flares fiddly and easy to
get subtly wrong.

## Lane layout

Lanes run in ascending size order along −y, lane 0 (Gr06) at the top.

> **Superseded.** The band arithmetic below describes the original
> one-block-per-lane build and its 210.7 mm width. The current model packs
> tightly — `pack_lanes()` bisects on a real outline-to-outline distance, so a
> short lane's fork end tucks under its neighbour's tilted ring, giving
> 152.5 mm. Kept because the band formulas document what `divider` and
> `outer_wall` mean per lane, which the packer still honours.

```
w_i        = pocket outline's y-extent for size i
top_pad_i  = outer_wall if i == 0            else divider/2
bot_pad_i  = outer_wall if i == last         else divider/2
band_i     = top_pad_i + w_i + bot_pad_i
lane_len_i = outer_wall + pocket_x_extent_i + outer_wall
```

Bands tile the full width with no gaps, summing to
`sum(w) + 9·divider + 2·outer_wall` = 210.7 mm. Each block is
`lane_len_i × band_i × height`, and its pocket sits `top_pad_i` from the
band's top edge and `outer_wall` from its left edge (left-alignment).

`height` = 46.2 mm for every lane (uniform slab).

## Verification

After fusing the ten blocks:

- `shape.isValid()` and `not shape.isNull()`
- `len(shape.Solids) == 1` — proves the lanes actually merged rather than
  remaining ten touching-but-separate solids
- volume ≈ sum of the individual block volumes (they only *touch*, so volume
  is conserved; a mismatch means an unintended overlap or gap)
- overall bounding box ≈ 248.5 × 210.7 × 46.2 mm

Neighbouring blocks meet on coplanar faces. OCC usually fuses these cleanly,
but if a seam artifact appears, give adjacent blocks a small overlap
(≈0.01 mm) rather than fighting the boolean.

**Out of scope** (deliberately, both handled afterwards):

- **Base recess** — hollowing the underside to save material. Applied by hand
  to the finished single solid, so the generator doesn't need to know about it.
- **Splitting the print** — not needed; the 248.5 × 210.7 mm footprint fits
  the 300 × 300 bed.
