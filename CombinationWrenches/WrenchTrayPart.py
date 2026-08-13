"""
WrenchTrayPart - generate the pocket solids for a 3D-printable drawer-organizer
tray for a set of combination (ring-and-open-end) wrenches.

Reads Abmessungen.csv (';'-delimited, one row per wrench size) and produces one
POSITIVE solid per wrench - the shape to subtract from a tray body. The tray
body itself is built separately (by hand), so this module never makes slabs.

The pockets are laid out in parallel lanes, left-aligned, packed so that
neighbouring pockets clear each other by exactly `divider`. That measured
spacing matters: stacking bounding boxes instead wastes ~49 mm across the set,
because adjacent pockets are widest at different x.

Each pocket is built as the intersection of two profiles, which is exactly how
the design was validated on paper:

    pocket = (top-view outline extruded down) INTERSECT (front-view profile
                                                         extruded sideways)

The top view gives the plan shape (tilted ring, stretched heads, gripped
neck); the front view gives the stepped floor depths and the 45 degree flare
ramps. See README.md for the full derivation and the validation record.

Placement conventions, so a separately built slab lines up:
    top face at z = 0, pockets cut downward
    left-aligned at x = outer_wall
    first lane starts outer_wall below y = 0, lanes run toward -y

Public functions:
    build_pockets(doc=None, **params)
        Main entry point - the positive pocket solids, laid out in their lanes.
    pack_lanes(faces, outer_wall, divider, tight=True)
        Lane y-offsets. Tight packing measures the real outline-to-outline
        distance instead of stacking bounding boxes.
    build_pocket_solid(row, height, **params)
        The pocket void for one wrench, as a solid, in local coordinates.
    build_pocket_outline(row, **params)
        The 2D top-view plan shape. Returns (face, info).
    pocket_depths(row, top_offset)
        Ring / neck / fork depths below the tray's top surface.
    load_wrench_rows(csv_path=None)
        Parse the CSV into a list of dicts with numeric values.

Usage from the FreeCAD Python console:

    import WrenchTrayPart as wi
    wi.build_pockets(App.ActiveDocument)

    # or with tweaked fit / spacing:
    wi.build_pockets(App.ActiveDocument, neck_grip=0.5, divider=5.0)
"""

# =============================================================================
# CLAUDE: things learned the hard way in this project - read before changing
# any of these, they are not arbitrary.
#
# - The wrenches stand ON EDGE. Top-view slot width comes from the D* columns
#   (Dicke/thickness), pocket depth from the H* columns (Hoehe/height).
#   Getting this backwards wastes a lot of time.
#
# - The ring depth region must extend to the ROTATED ring polygon's max x, not
#   to Lr. Stretching + tilting push the ring's inner-bottom corner 2.5mm
#   (Gr06) to 5.0mm (Gr19) past Lr. Cutting that sliver at the shallower neck
#   depth leaves a step that physically stops the wrench seating.
#
# - The ring's left-shift after rotation scales with the STRETCHED length,
#   1.2*Lr*(1-cos15), not Lr*(1-cos15). Don't hard-code it; just translate by
#   min(x of rotated corners) - rx0.
#
# - The neck band must start at 0.6*Lr, not 0.5*Lr. The stretched ring swings
#   further down under the tilt, and at 0.5 the neck pokes above the ring's
#   top edge on Gr15 (needs 0.535) and Gr19 (needs 0.530).
#
# - Do NOT use Part::MultiFuse to combine the lane blocks. It reliably returns
#   a NULL or silently empty shape on generated geometry even when the same
#   .Shape objects fuse fine directly in Python. Fuse in a plain loop and store
#   the result in one Part::Feature. (Same finding as TaperedLetters.py.)
#
# - Do NOT delete-and-recreate objects that a TechDraw view points at.
#   FreeCAD links bind to object identity, not name; the view's Source goes
#   empty and the page keeps rendering stale geometry with no error. All object
#   creation here mutates .Shape in place on an existing object if present.
#
# - Building the pocket by extruding each depth region separately and unioning
#   them was the first approach tried. It works, but reconciling the ring's
#   15deg plan tilt with the floor flare is fiddly and easy to get subtly
#   wrong. The profile-intersection used here is equivalent, shorter, and
#   ties directly to the two drawings that were actually validated on paper.
# =============================================================================

import csv
import math
import os

import FreeCAD as App
import Part


# --- fit and geometry parameters (all validated - see README.md) -------------

RING_CLR = 1.0            # mm per side, loose drop-in fit at the ring end
FORK_CLR = 1.0            # mm per side, loose drop-in fit at the fork end
NECK_GRIP = 0.3           # mm TOTAL undersize; TPU grips the shaft here
HEAD_STRETCH = 1.2        # heads 20% longer, about their own centre
RING_TILT_DEG = 15.0      # standard combination-wrench ring offset
NECK_OVERLAP = 0.6        # neck band starts at this fraction of Lr
FLARE_DEG = 45.0          # floor ramp between neck and each head
TOP_OFFSET = 2.0          # wrench tops sit this far below the tray surface

# --- tray parameters ---------------------------------------------------------

FLOOR_THICKNESS = 5.0     # material below the deepest pocket
OUTER_WALL = 6.0          # tray perimeter wall
DIVIDER = 4.0             # minimum clearance between adjacent pockets

CSV_NAME = "Abmessungen.csv"
COLUMNS = ("D0", "Dr", "Dg", "L", "Lr", "Lg", "H0", "Hr", "Hg", "Hu")


# --- CSV ---------------------------------------------------------------------

def load_wrench_rows(csv_path=None):
    """Read Abmessungen.csv into a list of dicts, ascending by size.

    `Gr` is parsed as int, every other column as float. Raises ValueError
    naming the offending size on malformed data.
    """
    if csv_path is None:
        csv_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), CSV_NAME)

    rows = []
    with open(csv_path, newline="") as handle:
        for lineno, raw in enumerate(csv.DictReader(handle, delimiter=";"), start=2):
            try:
                row = {"Gr": int(raw["Gr"])}
                for col in COLUMNS:
                    row[col] = float(raw[col])
            except (TypeError, ValueError, KeyError) as exc:
                raise ValueError(
                    "%s line %d: bad or missing value (%s)" % (csv_path, lineno, exc))
            rows.append(row)

    if not rows:
        raise ValueError("%s contains no data rows" % csv_path)
    rows.sort(key=lambda r: r["Gr"])
    return rows


# --- small geometry helpers --------------------------------------------------

def _stretch(x0, x1, factor):
    """Grow the span x0..x1 by `factor` about its own midpoint."""
    mid = (x0 + x1) / 2.0
    half = (x1 - x0) / 2.0 * factor
    return mid - half, mid + half


def _rect(x0, x1, width):
    """Axis-aligned rectangle as (x, y) corner tuples, centred on y = 0."""
    half = width / 2.0
    return [(x0, -half), (x1, -half), (x1, half), (x0, half)]


def _rotate_about(pts, pivot, angle):
    """Rotate (x, y) tuples about `pivot` by `angle` radians, CCW."""
    px, py = pivot
    out = []
    for x, y in pts:
        dx, dy = x - px, y - py
        out.append((px + dx * math.cos(angle) - dy * math.sin(angle),
                    py + dx * math.sin(angle) + dy * math.cos(angle)))
    return out


def _face_xy(pts, z=0.0):
    """Planar face from (x, y) tuples, in the plane z = const."""
    vec = [App.Vector(x, y, z) for x, y in pts]
    return Part.Face(Part.makePolygon(vec + [vec[0]]))


def _face_xz(pts, y=0.0):
    """Planar face from (x, z) tuples, in the plane y = const."""
    vec = [App.Vector(x, y, z) for x, z in pts]
    return Part.Face(Part.makePolygon(vec + [vec[0]]))


def _make_feature(doc, name, shape, visible=True):
    """Idempotent Part::Feature. Mutates an existing object's Shape rather
    than deleting and recreating it, so downstream links stay intact."""
    obj = doc.getObject(name)
    if obj is None:
        obj = doc.addObject("Part::Feature", name)
        obj.Label = name
    obj.Shape = shape
    if getattr(obj, "ViewObject", None) is not None:
        obj.ViewObject.Visibility = visible
    return obj


# --- top view: the plan outline ---------------------------------------------

def build_pocket_outline(row, ring_clr=RING_CLR, fork_clr=FORK_CLR,
                         neck_grip=NECK_GRIP, head_stretch=HEAD_STRETCH,
                         ring_tilt_deg=RING_TILT_DEG, neck_overlap=NECK_OVERLAP):
    """Top-view plan shape of one wrench's pocket.

    Returns (face, info) where `info` carries the x boundaries the depth
    regions and flares are keyed to:
        ring_x_max  max x of the rotated+shifted ring polygon (NOT Lr)
        fx0, fx1    fork rectangle's stretched span
        neck_x0     where the neck band starts

    Raises ValueError if the neck band's start edge is not enclosed by the
    tilted ring - that would leave a notch in the outline.
    """
    Dr, Dg, D0 = row["Dr"], row["Dg"], row["D0"]
    L, Lr, Lg = row["L"], row["Lr"], row["Lg"]
    tilt = math.radians(ring_tilt_deg)

    ring_w = Dr + 2.0 * ring_clr
    fork_w = Dg + 2.0 * fork_clr
    neck_w = D0 - neck_grip
    if neck_w <= 0.0:
        raise ValueError("Gr%s: neck_grip %.2f >= D0 %.2f" % (row["Gr"], neck_grip, D0))

    rx0, rx1 = _stretch(0.0, Lr, head_stretch)
    fx0, fx1 = _stretch(L - Lg, L, head_stretch)
    neck_x0 = Lr * neck_overlap

    # Ring: rotate about the inner-TOP corner so the outer end swings down,
    # then slide back so the outer extreme returns to rx0.
    ring_pts = _rotate_about(_rect(rx0, rx1, ring_w), (rx1, ring_w / 2.0), tilt)
    shift = min(p[0] for p in ring_pts) - rx0
    ring_pts = [(x - shift, y) for x, y in ring_pts]

    ring = _face_xy(ring_pts)
    neck = _face_xy(_rect(neck_x0, L, neck_w))
    fork = _face_xy(_rect(fx0, fx1, fork_w))

    for y in (-neck_w / 2.0, neck_w / 2.0):
        if not ring.isInside(App.Vector(neck_x0, y, 0.0), 1e-6, True):
            raise ValueError(
                "Gr%s: neck band at x=%.2f is not enclosed by the tilted ring; "
                "raise neck_overlap (currently %.2f)" % (row["Gr"], neck_x0, neck_overlap))

    face = ring.fuse(neck).fuse(fork).removeSplitter()
    # OCC will not always merge the coplanar pieces across the ring's tilted
    # junction, so several faces is normal and harmless. What must hold is
    # that none of them has a hole - that would mean a notch in the outline.
    holed = [i for i, f in enumerate(face.Faces) if len(f.Wires) != 1]
    if holed:
        raise ValueError("Gr%s: outline has hole(s) in face(s) %s"
                         % (row["Gr"], holed))

    info = {"ring_x_max": max(p[0] for p in ring_pts),
            "rx0": rx0, "fx0": fx0, "fx1": fx1, "neck_x0": neck_x0,
            "ring_w": ring_w, "fork_w": fork_w, "neck_w": neck_w}
    return face, info


# --- front view: the depth profile ------------------------------------------

def pocket_depths(row, top_offset=TOP_OFFSET):
    """Depths (positive, measured down from the tray's top surface) of the
    three pocket regions. The fork's top is the wrench's highest point, so a
    common reference plane aligns all sizes at the top."""
    H0, Hr, Hg, Hu = row["H0"], row["Hr"], row["Hg"], row["Hu"]
    return {"ring": Hu + (H0 + Hr) / 2.0 + top_offset,
            "neck": H0 + Hu + top_offset,
            "fork": Hg + top_offset}


def _depth_profile(row, info, top_offset=TOP_OFFSET, flare_deg=FLARE_DEG,
                   x_lo=None, x_hi=None):
    """The front-view floor profile as (x, z) tuples: flat at the ring depth,
    ramping up to the neck depth, ramping back down to the fork depth."""
    d = pocket_depths(row, top_offset)
    tan = math.tan(math.radians(flare_deg))
    run_ring = (d["ring"] - d["neck"]) / tan
    run_fork = (d["fork"] - d["neck"]) / tan

    ring_end = info["ring_x_max"]
    fork_start = info["fx0"]

    if ring_end + run_ring >= fork_start - run_fork:
        raise ValueError(
            "Gr%s: the ring and fork flares overlap (%.2f >= %.2f); "
            "increase flare_deg" % (row["Gr"], ring_end + run_ring, fork_start - run_fork))

    floor = [(x_lo, -d["ring"]),
             (ring_end, -d["ring"]),
             (ring_end + run_ring, -d["neck"]),
             (fork_start - run_fork, -d["neck"]),
             (fork_start, -d["fork"]),
             (x_hi, -d["fork"])]
    # close the profile along the top surface
    return floor + [(x_hi, 0.0), (x_lo, 0.0)], run_ring, run_fork


# --- the pocket solid --------------------------------------------------------

def build_pocket_solid(row, height, top_offset=TOP_OFFSET, flare_deg=FLARE_DEG,
                       **outline_kw):
    """The pocket void for one wrench, as a solid sitting below z = 0.

    Built as (plan outline extruded down) INTERSECT (depth profile extruded
    sideways), which reproduces exactly the two drawings validated on paper
    and needs no special handling for the ring's plan tilt.
    """
    face, info = build_pocket_outline(row, **outline_kw)
    bb = face.BoundBox
    pad = 1.0

    prism = face.extrude(App.Vector(0, 0, -height))

    profile_pts, run_ring, run_fork = _depth_profile(
        row, info, top_offset=top_offset, flare_deg=flare_deg,
        x_lo=bb.XMin - pad, x_hi=bb.XMax + pad)
    width = bb.YLength + 2.0 * pad
    profile = _face_xz(profile_pts, y=bb.YMin - pad).extrude(App.Vector(0, width, 0))

    pocket = prism.common(profile)
    if pocket.isNull() or not pocket.Solids:
        raise ValueError("Gr%s: pocket intersection produced no solid" % row["Gr"])

    # The outline may be several coplanar faces (see build_pocket_outline), so
    # the intersection comes back as several solids. Consolidate them.
    if len(pocket.Solids) > 1:
        merged = pocket.Solids[0]
        for extra in pocket.Solids[1:]:
            merged = merged.fuse(extra)
        pocket = merged.removeSplitter()

    info = dict(info, run_ring=run_ring, run_fork=run_fork,
                depths=pocket_depths(row, top_offset),
                x_min=bb.XMin, x_max=bb.XMax, y_len=bb.YLength)
    return pocket, info


# --- lane layout -------------------------------------------------------------

def pack_lanes(faces, outer_wall=OUTER_WALL, divider=DIVIDER, tight=True):
    """Lane y-offsets for a list of already left-aligned outline faces.

    tight=True  slide each lane up until its real outline-to-outline distance
                to the previous one is exactly `divider`. Adjacent pockets are
                widest at different x (one's ring bottom corner vs the next
                one's ring pivot), so stacking bounding boxes leaves 3-8 mm of
                dead space per gap - 48.8 mm over the whole set.
    tight=False stack bounding boxes with divider/2 either side. Required if
                each lane cuts its own pocket out of its own rectangular slab,
                because tight lanes overlap and would refill each other.

    Returns a list of y offsets, one per face (faces are not modified).
    """
    offsets = [-outer_wall - faces[0].BoundBox.YMax]
    prev = faces[0].copy()
    prev.translate(App.Vector(0, offsets[0], 0))

    for face in faces[1:]:
        if tight:
            # start clear of the previous lane, then bisect back toward it
            start = prev.BoundBox.YMin - divider - face.BoundBox.YMax - 20.0
            lo, hi = 0.0, 40.0
            for _ in range(40):
                mid = (lo + hi) / 2.0
                probe = face.copy()
                probe.translate(App.Vector(0, start + mid, 0))
                if prev.distToShape(probe)[0] > divider:
                    lo = mid
                else:
                    hi = mid
            dy = start + lo
        else:
            dy = prev.BoundBox.YMin - divider - face.BoundBox.YMax

        offsets.append(dy)
        prev = face.copy()
        prev.translate(App.Vector(0, dy, 0))

    return offsets


def build_pockets(doc=None, csv_path=None, name_fmt="PocketGr%02d",
                  group_name="WrenchPockets", outer_wall=OUTER_WALL,
                  divider=DIVIDER, floor_thickness=FLOOR_THICKNESS,
                  top_offset=TOP_OFFSET, tight=True, **kw):
    """Build the positive pocket solids only - no slab.

    These are the shapes to subtract from a tray body built separately. Each
    is left-aligned `outer_wall` from x = 0 and packed in y so neighbouring
    pockets clear each other by exactly `divider`.

    Returns the list of Part::Feature objects.
    """
    if doc is None:
        doc = App.ActiveDocument
    if doc is None:
        raise ValueError("no active document")

    rows = load_wrench_rows(csv_path)
    height = top_offset + max(r["Hg"] for r in rows) + floor_thickness

    # Lay out on the 2D outlines - cheap, and the horizontal gap is what the
    # wall thickness actually depends on.
    faces, dxs = [], []
    for row in rows:
        face, _ = build_pocket_outline(row, **kw)
        dx = outer_wall - face.BoundBox.XMin
        face.translate(App.Vector(dx, 0, 0))
        faces.append(face)
        dxs.append(dx)

    dys = pack_lanes(faces, outer_wall, divider, tight=tight)

    objs, solids = [], []
    for row, dx, dy in zip(rows, dxs, dys):
        pocket, _ = build_pocket_solid(row, height, top_offset=top_offset, **kw)
        pocket.translate(App.Vector(dx, dy, 0))
        objs.append(_make_feature(doc, name_fmt % row["Gr"], pocket))
        solids.append(pocket)

    if group_name:
        grp = doc.getObject(group_name)
        if grp is None:
            grp = doc.addObject("App::DocumentObjectGroup", group_name)
            grp.Label = group_name
        grp.Group = objs
    doc.recompute()

    placed = []
    for face, dy in zip(faces, dys):
        moved = face.copy()
        moved.translate(App.Vector(0, dy, 0))
        placed.append(moved)
    gaps = [placed[i].distToShape(placed[i + 1])[0] for i in range(len(placed) - 1)]

    bb = Part.makeCompound(solids).BoundBox
    print("--- pockets (positives) ---")
    print("count        : %d" % len(objs))
    print("packing      : %s" % ("tight" if tight else "bounding-box"))
    print("extent       : %.1f x %.1f x %.1f mm"
          % (bb.XLength, bb.YLength, bb.ZLength))
    print("slab height  : %.1f mm" % height)
    print("volume       : %.3f dm3" % (sum(s.Volume for s in solids) / 1e6))
    print("tray footprint would be %.1f x %.1f mm  (outer wall %.1f)"
          % (bb.XMax + outer_wall, bb.YLength + 2 * outer_wall, outer_wall))
    print("gaps (target %.1f) : %s"
          % (divider, " ".join("%.2f" % g for g in gaps)))
    return objs


if __name__ == "__main__":
    print(__doc__)
    print("Run from the FreeCAD console:  import WrenchTrayPart as wi; "
          "wi.build_pockets(App.ActiveDocument)")
