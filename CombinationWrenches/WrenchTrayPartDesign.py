"""
WrenchTrayPartDesign - build the complete wrench organizer tray as native,
fully parametric PartDesign geometry driven by the document's VarSets.

Running build_all() on an empty document reproduces the whole model from the
CSV: the parameter VarSets, the ten pocket profiles, their lane packing, and
the tray that subtracts them.

Each size becomes one PartDesign::Body named ProfileGr<nn>, built from three
pads at three different depths plus two chamfers for the floor flares:

    SkNeck<nn> -> PadNeck<nn>    depth H0 + Hu + TopOffset
    SkFork<nn> -> PadFork<nn>    depth Hg + TopOffset
    SkRing<nn> -> PadRing<nn>    depth Hu + (H0 + Hr)/2 + TopOffset
    FlareRing<nn>                chamfer on the ring/neck step
    FlareFork<nn>                chamfer on the neck/fork step

Every sketch is fully constrained (DoF 0) and every dimension is an expression
referencing VarSetGr<nn> (the measured data) and VarSet (the fit parameters),
so changing a parameter rebuilds the geometry.

This is the PartDesign counterpart to WrenchTrayPart.py, which produces the
same pockets as static Part solids. The two are NOT identical by design - see
the note on the ring/neck strip below.

The tray outline is six lines - top edge, one long bevel, a short flat above
the largest size, then the right, bottom and left walls. It is fully
constrained, every dimension an expression onto TrayDerived, which in turn
reads the profiles' own placements. OutlineStepLength is the single free
design choice: it fixes where the bevel lands and therefore its slope.

Public functions:
    build_all(doc, csv_path)        everything, from CSV to finished tray
    build_varsets(doc, csv_path)    VarSet, VarSetGr<nn>, TrayDerived
    build_profile(doc, gr)          one size  -> ProfileGr<nn>
    build_all_profiles(doc, sizes)  all sizes -> list of bodies
    pack_lanes(doc, sizes)          position the profiles, tight
    build_tray(doc, sizes)          WrenchTray = slab minus the profiles
    verify_tray(doc, sizes)         containment, gaps and wall checks
    profile_geometry(doc, gr)       the computed numbers, without building

Usage from the FreeCAD Python console:

    import WrenchTrayPartDesign as wpd
    wpd.build_all(App.ActiveDocument)
"""

# =============================================================================
# CLAUDE: things learned the hard way - read before changing.
#
# - body.addObject(feature) makes that feature the body's Tip IMMEDIATELY, so
#   `body.Tip.Shape` afterwards is the new (still empty) feature's null shape.
#   Always capture the previous tip BEFORE adding a dressup feature. This cost
#   a debugging round: step_edge() found zero edges and raised IndexError.
#
# - Chamfer edges MUST be found by geometry, never by hardcoded index. Each
#   chamfer changes the edge numbering of everything downstream: the fork
#   junction was Edge21 before the ring chamfer and Edge33 after. Worse, the
#   ring chamfer creates its own short edge at the neck floor, which is a
#   plausible-looking wrong answer - hence the leftmost/rightmost rule.
#
# - The flare chamfer cannot be the full step height. At exactly (Hr-H0)/2 the
#   chamfer consumes the entire step face and OCC returns an invalid shape.
#   Verified cliff on Gr06: 2.649 works, 2.650 fails. Hence FLARE_EPS.
#
# - FlareAngle is NOT a parameter here. An "Equal distance" chamfer is 45 deg
#   by construction; the ramp angle lives in the chamfer type, not in a VarSet.
#
# - Internal object names cannot start with a digit - FreeCAD silently rewrites
#   "06_PadNeck" to "_06_PadNeck". Hence the suffix form, PadNeck06.
#
# - This build differs slightly from WrenchTrayPart.build_pocket_solid():
#   that one cuts EVERYTHING left of ring_x_max to the ring depth, including
#   the strip of shaft running beside the tilted ring. Three pads instead cut
#   that strip to the shaft depth, which is what the real wrench needs. Gr06:
#   4918.26 mm3 here vs 4923.23 mm3 there. The difference is intentional.
#
# - sketch.solve() returns a SOLVER STATUS CODE, not the degrees of freedom.
#   0 means "solved", not "fully constrained". Use sketch.FullyConstrained.
#   An earlier version summed solve() and printed it as DoF - it read 0 for
#   sketches it had never actually checked.
#
# - FreeCAD's dependency graph is per-OBJECT, not per-property. SlabHeight and
#   the Outline* values cannot live on VarSet: VarSet.SlabHeight reading
#   VarSetGr19.Hg makes VarSet depend on VarSetGr19, whose RingXMax reads
#   VarSet.HeadStretch, and the cycle is rejected even though no single
#   property is circular. TrayDerived is that third object.
#
# - Lane packing must use a real shape distance, not a bbox pitch. Divider is
#   an outline-to-outline minimum; bbox spacing wastes 58 mm over ten lanes.
#   The search runs on flat footprints, which is exact here: all pockets start
#   at z=0 and only narrow going down, so the 3D minimum distance between two
#   of them is the distance between their z=0 outlines.
#
# - The tray outline does NOT guarantee containment by construction - a bevel
#   can cut a corner off a pocket if the parameters change. verify_tray()
#   cuts every profile against the slab and expects 0 mm3 outside. An earlier
#   midpoint-band staircase leaked 1007 mm3 exactly this way.
# =============================================================================

import math

import FreeCAD as App
import Part
import Sketcher

SIZES = (6, 7, 8, 9, 10, 12, 13, 14, 15, 19)

PARAMS = "VarSet"                 # fit parameters
WRENCH = "VarSetGr%02d"           # measured data, per size
BODY = "ProfileGr%02d"
DERIVED = "TrayDerived"           # values that would make VarSet cyclic
TRAY = "WrenchTray"

FLARE_EPS = "0.01mm"              # keeps the chamfer off the degenerate case

COLUMNS = ("D0", "Dr", "Dg", "L", "Lr", "Lg", "H0", "Hr", "Hg", "Hu")

# name, type, default, group, tooltip
FIT = (
    ("RingClearance", "App::PropertyLength", 1.0, "Fit",
     "mm per side, loose drop-in fit at the ring end"),
    ("ForkClearance", "App::PropertyLength", 1.0, "Fit",
     "mm per side, loose drop-in fit at the fork end"),
    ("NeckGrip", "App::PropertyLength", 0.3, "Fit",
     "mm TOTAL undersize; the TPU grips the shaft here"),
    ("HeadStretch", "App::PropertyFloat", 1.2, "Fit",
     "heads this much longer, about their own centre"),
    ("RingTilt", "App::PropertyAngle", 15.0, "Fit",
     "standard combination-wrench ring offset"),
    ("NeckOverlap", "App::PropertyFloat", 0.6, "Fit",
     "neck band starts at this fraction of Lr"),
    ("TopOffset", "App::PropertyLength", 2.0, "Fit",
     "wrench tops sit this far below the tray surface"),
    ("OuterWall", "App::PropertyLength", 6.0, "Tray",
     "tray perimeter wall"),
    ("Divider", "App::PropertyLength", 4.0, "Tray",
     "minimum outline-to-outline clearance between pockets"),
    ("FloorThickness", "App::PropertyLength", 5.0, "Tray",
     "material below the deepest pocket"),
)

RING_X_MAX = ("Lr * (1 + VarSet.HeadStretch) / 2"
              " + (Dr + 2 * VarSet.RingClearance) * sin(VarSet.RingTilt)"
              " - VarSet.HeadStretch * Lr * (1 - cos(VarSet.RingTilt))")


# --- parameters -------------------------------------------------------------

def _wrench_rows(csv_path=None):
    """The CSV reader lives in WrenchTrayPart - one parser, one place."""
    try:
        import WrenchTrayPart as wip
    except ImportError:
        raise ImportError("WrenchTrayPart.py must sit next to this module; "
                          "it owns the CSV reader")
    return wip.load_wrench_rows(csv_path)


def _varset(doc, name):
    obj = doc.getObject(name)
    if obj is None:
        obj = doc.addObject("App::VarSet", name)
        obj.Label = name
    return obj


def _prop(obj, typ, name, group, tip, value=None, expr=None, force=False):
    """Add the property if missing. An existing VALUE is left alone unless
    force - the user tunes those. Expressions are structural, always set."""
    fresh = name not in obj.PropertiesList
    if fresh:
        obj.addProperty(typ, name, group, tip)
    if value is not None and (fresh or force):
        setattr(obj, name, value)
    if expr is not None:
        obj.setExpression(name, expr)
    return fresh


def build_varsets(doc, csv_path=None, sizes=SIZES, force=False):
    """VarSet (fit + tray parameters), one VarSetGr<nn> per size, TrayDerived.

    Idempotent: re-running adds anything missing and refreshes expressions,
    but never overwrites a value you have tuned unless force=True.
    """
    g = _varset(doc, PARAMS)
    for name, typ, val, grp, tip in FIT:
        _prop(g, typ, name, grp, tip, value=val, force=force)

    rows = {r["Gr"]: r for r in _wrench_rows(csv_path)}
    for gr in sizes:
        if gr not in rows:
            raise ValueError("Gr%d is not in the CSV" % gr)
        v = _varset(doc, WRENCH % gr)
        _prop(v, "App::PropertyInteger", "Gr", "Measured",
              "wrench size, mm across flats", value=gr, force=force)
        for col in COLUMNS:
            _prop(v, "App::PropertyLength", col, "Measured",
                  "measured %s" % col, value=rows[gr][col], force=force)
        _prop(v, "App::PropertyLength", "RingXMax", "Derived",
              "max x of the tilted ring outline", expr=RING_X_MAX)

    td = _varset(doc, DERIVED)
    _prop(td, "App::PropertyLength", "SlabHeight", "Tray",
          "top offset + deepest pocket + floor",
          expr="VarSet.TopOffset + %s.Hg + VarSet.FloorThickness"
               % (WRENCH % max(sizes)))
    doc.recompute()
    return g, td


# --- geometry ---------------------------------------------------------------

def profile_geometry(doc, gr):
    """Everything the sketches need, computed from the VarSets."""
    v, g = doc.getObject(WRENCH % gr), doc.getObject(PARAMS)
    if v is None or g is None:
        raise ValueError("missing VarSet for Gr%02d" % gr)

    s = g.HeadStretch
    tilt = math.radians(g.RingTilt.Value)
    Lr, Lg, L = v.Lr.Value, v.Lg.Value, v.L.Value

    d = {"neck_w": v.D0.Value - g.NeckGrip.Value,
         "ring_w": v.Dr.Value + 2 * g.RingClearance.Value,
         "fork_w": v.Dg.Value + 2 * g.ForkClearance.Value,
         "d_neck": v.H0.Value + v.Hu.Value + g.TopOffset.Value,
         "d_ring": v.Hu.Value + (v.H0.Value + v.Hr.Value) / 2 + g.TopOffset.Value,
         "d_fork": v.Hg.Value + g.TopOffset.Value,
         "nx0": Lr * g.NeckOverlap, "nx1": L,
         "rx0": Lr / 2 - Lr * s / 2, "rx1": Lr / 2 + Lr * s / 2,
         "fx0": (L - Lg / 2) - Lg * s / 2, "fx1": (L - Lg / 2) + Lg * s / 2,
         "ring_len": Lr * s, "tilt": tilt}

    # ring corners: rotate about the inner-top corner, then slide back so the
    # outer extreme returns to rx0
    hw = d["ring_w"] / 2.0
    pts = [(d["rx0"], hw), (d["rx1"], hw), (d["rx1"], -hw), (d["rx0"], -hw)]
    px, py = d["rx1"], hw
    rot = [(px + (x - px) * math.cos(tilt) - (y - py) * math.sin(tilt),
            py + (x - px) * math.sin(tilt) + (y - py) * math.cos(tilt)) for x, y in pts]
    shift = min(p[0] for p in rot) - d["rx0"]
    d["ring_pts"] = [(x - shift, y) for x, y in rot]
    return d


def _step_edge(shape, z, max_len, pick):
    """Head/neck junction edges lie wholly at the neck floor and are short.
    The ring junction is the leftmost such edge, the fork junction the
    rightmost. Never reference these by index - see the notes above."""
    found = []
    for i, e in enumerate(shape.Edges):
        bb = e.BoundBox
        if (abs(bb.ZMin - z) < 1e-6 and abs(bb.ZMax - z) < 1e-6
                and e.Length < max_len):
            found.append((e.CenterOfMass.x, "Edge%d" % (i + 1)))
    if not found:
        raise ValueError("no junction edge found at z=%.4f" % z)
    found.sort()
    return (found[0] if pick == "min" else found[-1])[1]


# --- sketch helpers ---------------------------------------------------------

def _xy_plane(body):
    """The body's OWN XY plane. doc.getObject("XY_Plane") would hand back the
    first body's plane and quietly link every sketch across body scopes."""
    for f in body.Origin.OriginFeatures:
        if f.Role == "XY_Plane":
            return f
    raise ValueError("%s has no XY plane" % body.Name)


def _rect_sketch(doc, body, name, x0, x1, halfh, exprs):
    sk = doc.addObject("Sketcher::SketchObject", name)
    sk.Label = name
    body.addObject(sk)
    sk.AttachmentSupport = [(_xy_plane(body), "")]
    sk.MapMode = "FlatFace"
    pts = [(x0, -halfh), (x1, -halfh), (x1, halfh), (x0, halfh)]
    for i in range(4):
        a, b = pts[i], pts[(i + 1) % 4]
        sk.addGeometry(Part.LineSegment(App.Vector(a[0], a[1], 0),
                                        App.Vector(b[0], b[1], 0)), False)
    for i in range(4):
        sk.addConstraint(Sketcher.Constraint("Coincident", i, 2, (i + 1) % 4, 1))
    for gi in (0, 2):
        sk.addConstraint(Sketcher.Constraint("Horizontal", gi))
    for gi in (1, 3):
        sk.addConstraint(Sketcher.Constraint("Vertical", gi))
    for cn, gi, val in (("X0", 0, x0), ("X1", 1, x1)):
        sk.renameConstraint(sk.addConstraint(
            Sketcher.Constraint("DistanceX", -1, 1, gi, 1, val)), cn)
    for cn, gi, val in (("YLo", 0, -halfh), ("YHi", 2, halfh)):
        sk.renameConstraint(sk.addConstraint(
            Sketcher.Constraint("DistanceY", -1, 1, gi, 1, val)), cn)
    for cn, expr in exprs.items():
        sk.setExpression("Constraints.%s" % cn, expr)
    doc.recompute()
    return sk


def _ring_sketch(doc, body, name, geo, V):
    sk = doc.addObject("Sketcher::SketchObject", name)
    sk.Label = name
    body.addObject(sk)
    sk.AttachmentSupport = [(_xy_plane(body), "")]
    sk.MapMode = "FlatFace"
    pts = geo["ring_pts"]
    for i in range(4):
        a, b = pts[i], pts[(i + 1) % 4]
        sk.addGeometry(Part.LineSegment(App.Vector(a[0], a[1], 0),
                                        App.Vector(b[0], b[1], 0)), False)
    for i in range(4):
        sk.addConstraint(Sketcher.Constraint("Coincident", i, 2, (i + 1) % 4, 1))
    for i in range(3):
        sk.addConstraint(Sketcher.Constraint("Perpendicular", i, i + 1))
    for cn, con in (
            ("RingLen", Sketcher.Constraint("Distance", 0, geo["ring_len"])),
            ("RingWidth", Sketcher.Constraint("Distance", 1, geo["ring_w"])),
            ("RingTilt", Sketcher.Constraint("Angle", 0, geo["tilt"])),
            ("PivotX", Sketcher.Constraint("DistanceX", -1, 1, 0, 2, pts[1][0])),
            ("PivotY", Sketcher.Constraint("DistanceY", -1, 1, 0, 2, pts[1][1]))):
        sk.renameConstraint(sk.addConstraint(con), cn)
    sk.setExpression("Constraints.RingLen", "VarSet.HeadStretch * %s.Lr" % V)
    sk.setExpression("Constraints.RingWidth",
                     "%s.Dr + 2 * VarSet.RingClearance" % V)
    sk.setExpression("Constraints.RingTilt", "VarSet.RingTilt")
    sk.setExpression("Constraints.PivotX",
                     "%s.Lr * (1 + VarSet.HeadStretch) / 2"
                     " - VarSet.HeadStretch * %s.Lr * (1 - cos(VarSet.RingTilt))"
                     % (V, V))
    sk.setExpression("Constraints.PivotY",
                     "(%s.Dr + 2 * VarSet.RingClearance) / 2" % V)
    doc.recompute()
    return sk


def _pad(doc, body, sk, name, depth_expr):
    p = doc.addObject("PartDesign::Pad", name)
    p.Label = name
    body.addObject(p)
    p.Profile = sk
    p.Reversed = True
    p.setExpression("Length", depth_expr)
    doc.recompute()
    return p


def _chamfer(doc, body, name, base, edge, size_expr):
    ch = doc.addObject("PartDesign::Chamfer", name)
    ch.Label = name
    body.addObject(ch)
    ch.Base = (base, [edge])
    ch.ChamferType = "Equal distance"
    ch.Size = 1.0
    ch.setExpression("Size", size_expr)
    doc.recompute()
    return ch


# --- the profile body -------------------------------------------------------

def build_profile(doc, gr):
    """One size as a fully parametric PartDesign body. Returns the body."""
    V, SUF, name = WRENCH % gr, "%02d" % gr, BODY % gr
    geo = profile_geometry(doc, gr)

    stale = [name] + [p + SUF for p in ("SkNeck", "PadNeck", "SkFork", "PadFork",
                                        "SkRing", "PadRing", "FlareRing", "FlareFork")]
    for n in stale:
        if doc.getObject(n):
            doc.removeObject(n)
    doc.recompute()

    body = doc.addObject("PartDesign::Body", name)
    body.Label = name

    sk = _rect_sketch(doc, body, "SkNeck" + SUF, geo["nx0"], geo["nx1"],
                      geo["neck_w"] / 2, {
                          "X0": "%s.Lr * VarSet.NeckOverlap" % V,
                          "X1": "%s.L" % V,
                          "YLo": "-(%s.D0 - VarSet.NeckGrip) / 2" % V,
                          "YHi": "(%s.D0 - VarSet.NeckGrip) / 2" % V})
    _pad(doc, body, sk, "PadNeck" + SUF,
         "%s.H0 + %s.Hu + VarSet.TopOffset" % (V, V))

    sk = _rect_sketch(doc, body, "SkFork" + SUF, geo["fx0"], geo["fx1"],
                      geo["fork_w"] / 2, {
                          "X0": "%s.L - %s.Lg * (1 + VarSet.HeadStretch) / 2" % (V, V),
                          "X1": "%s.L - %s.Lg * (1 - VarSet.HeadStretch) / 2" % (V, V),
                          "YLo": "-(%s.Dg + 2 * VarSet.ForkClearance) / 2" % V,
                          "YHi": "(%s.Dg + 2 * VarSet.ForkClearance) / 2" % V})
    _pad(doc, body, sk, "PadFork" + SUF, "%s.Hg + VarSet.TopOffset" % V)

    sk = _ring_sketch(doc, body, "SkRing" + SUF, geo, V)
    _pad(doc, body, sk, "PadRing" + SUF,
         "%s.Hu + (%s.H0 + %s.Hr) / 2 + VarSet.TopOffset" % (V, V, V))

    # NOTE: capture the tip BEFORE adding the chamfer - addObject() makes the
    # new (empty) feature the tip immediately.
    z, max_len = -geo["d_neck"], 3 * geo["neck_w"]
    prev = body.Tip
    ch = _chamfer(doc, body, "FlareRing" + SUF, prev,
                  _step_edge(prev.Shape, z, max_len, "min"),
                  "(%s.Hr - %s.H0) / 2 - %s" % (V, V, FLARE_EPS))
    _chamfer(doc, body, "FlareFork" + SUF, ch,
             _step_edge(ch.Shape, z, max_len, "max"),
             "%s.Hg - %s.H0 - %s.Hu - %s" % (V, V, V, FLARE_EPS))

    for o in body.Group:
        if o.ViewObject is not None:
            o.ViewObject.Visibility = (o is body.Tip)
    doc.recompute()
    return body


def build_all_profiles(doc=None, sizes=SIZES):
    """Build every size and report the verification checks."""
    if doc is None:
        doc = App.ActiveDocument
    if doc is None:
        raise ValueError("no active document")

    bodies = []
    print("--- PartDesign profiles ---")
    print(" Gr    volume     solids  valid  sketches  states")
    for gr in sizes:
        b = build_profile(doc, gr)
        sks = [o for o in b.Group if o.TypeId == "Sketcher::SketchObject"]
        loose = sum(0 if s.FullyConstrained else 1 for s in sks)
        st = sorted({s for o in b.Group for s in o.State})
        print(" %2d  %10.4f  %5d   %-5s  %d/%d constrained  %s"
              % (gr, b.Shape.Volume, len(b.Shape.Solids), b.Shape.isValid(),
                 len(sks) - loose, len(sks), ",".join(st)))
        bodies.append(b)
    return bodies


# --- lane packing -----------------------------------------------------------

def _face(pts):
    v = [App.Vector(x, y, 0) for x, y in pts]
    return Part.Face(Part.makePolygon(v + [v[0]]))


def _footprint(geo):
    """The pocket's outline at z=0 - its widest cross-section, since the pads
    only step down and the chamfers only remove material at the floor."""
    hw, fw = geo["neck_w"] / 2.0, geo["fork_w"] / 2.0
    neck = _face([(geo["nx0"], -hw), (geo["nx1"], -hw),
                  (geo["nx1"], hw), (geo["nx0"], hw)])
    fork = _face([(geo["fx0"], -fw), (geo["fx1"], -fw),
                  (geo["fx1"], fw), (geo["fx0"], fw)])
    return neck.fuse(fork).fuse(_face(geo["ring_pts"])).removeSplitter()


def _tight_y(placed, fp, x, divider, tol=1e-5):
    """Largest y (highest lane position) keeping every placed outline at least
    `divider` away. Bisection, because the distance has no closed form once
    the tilted ring overhangs its neighbour."""
    # lo is bbox-safe. hi tops out level with what is already placed - push
    # past that and the lane clears the far side, distance grows again and
    # the bisection's monotonicity is gone.
    lo = placed.BoundBox.YMin - divider - fp.BoundBox.YMax
    hi = placed.BoundBox.YMax - fp.BoundBox.YMax
    while hi - lo > tol:
        mid = (lo + hi) / 2.0
        probe = fp.copy()
        probe.translate(App.Vector(x, mid, 0))
        if placed.distToShape(probe)[0] >= divider:
            lo = mid
        else:
            hi = mid
    return lo


def pack_lanes(doc, sizes=SIZES, apply=True):
    """Stack the profiles in lanes, ring ends left-aligned at OuterWall and
    each lane as high as Divider allows. Returns [(gr, x, y)].

    Divider is a true outline-to-outline minimum, not a bounding-box pitch:
    a short lane's fork end tucks under its longer neighbour's ring.
    """
    g = doc.getObject(PARAMS)
    wall, divider = g.OuterWall.Value, g.Divider.Value

    lanes, done = [], []
    for gr in sizes:
        fp = _footprint(profile_geometry(doc, gr))
        bb = fp.BoundBox
        x = wall - bb.XMin
        if not done:
            y = -wall - bb.YMax
        else:
            # floor(): rounding a lane DOWN moves it away from its neighbour,
            # so the printed 2-decimal placement never eats into Divider.
            y = math.floor(_tight_y(Part.makeCompound(done), fp, x,
                                    divider) * 100.0) / 100.0
        moved = fp.copy()
        moved.translate(App.Vector(x, y, 0))
        done.append(moved)
        lanes.append((gr, x, y))
        if apply:
            body = doc.getObject(BODY % gr)
            if body is None:
                raise ValueError("build the profiles before packing (%s)" % (BODY % gr))
            body.Placement = App.Placement(App.Vector(x, y, 0), App.Rotation())
    doc.recompute()
    return lanes


# --- the tray ---------------------------------------------------------------

def _outline_exprs(sizes):
    """The tray outline, expressed from the profiles' own placements.

    Two closed forms are folded in. A profile's local xmin is exactly
    -(HeadStretch-1)/2*Lr: the ring tilt and the compensating left-shift
    cancel, leaving only the stretch. Its local ymin is the tilted ring's
    outer-bottom corner, w*(0.5-cos t) - HeadStretch*Lr*sin t.
    """
    first, last = BODY % min(sizes), BODY % max(sizes)
    vf, vl = WRENCH % min(sizes), WRENCH % max(sizes)
    fork_end = ("%s.Placement.Base.x + %s.L"
                " + (VarSet.HeadStretch - 1) / 2 * %s.Lg + VarSet.OuterWall")
    return (
        ("OutlineDiagX", "x where the bevel leaves the top edge",
         fork_end % (first, vf, vf)),
        ("OutlineRight", "right wall, off the longest fork end",
         fork_end % (last, vl, vl)),
        ("OutlineStepY", "flat above the last lane, off its fork edge",
         "%s.Placement.Base.y + (%s.Dg + 2 * VarSet.ForkClearance) / 2"
         " + VarSet.OuterWall" % (last, vl)),
        ("OutlineBottom", "bottom wall, off the last lane's tilted ring",
         "%s.Placement.Base.y"
         " + (%s.Dr + 2 * VarSet.RingClearance) * (0.5 - cos(VarSet.RingTilt))"
         " - VarSet.HeadStretch * %s.Lr * sin(VarSet.RingTilt)"
         " - VarSet.OuterWall" % (last, vl, vl)),
    )


def _tray_sketch(doc, body, td):
    """Six lines: top, bevel, step, right, bottom, left. Fully constrained."""
    dx = td.OutlineDiagX.Value
    rx, sy = td.OutlineRight.Value, td.OutlineStepY.Value
    by, sl = td.OutlineBottom.Value, td.OutlineStepLength.Value
    pts = [(0.0, 0.0), (dx, 0.0), (rx - sl, sy), (rx, sy), (rx, by), (0.0, by)]

    sk = doc.addObject("Sketcher::SketchObject", "TraySketch")
    sk.Label = "TraySketch"
    body.addObject(sk)
    sk.AttachmentSupport = [(_xy_plane(body), "")]
    sk.MapMode = "FlatFace"
    for i in range(6):
        a, b = pts[i], pts[(i + 1) % 6]
        sk.addGeometry(Part.LineSegment(App.Vector(a[0], a[1], 0),
                                        App.Vector(b[0], b[1], 0)), False)
    for i in range(6):
        sk.addConstraint(Sketcher.Constraint("Coincident", i, 2, (i + 1) % 6, 1))
    sk.addConstraint(Sketcher.Constraint("Coincident", 0, 1, -1, 1))
    for gi in (0, 2, 4):
        sk.addConstraint(Sketcher.Constraint("Horizontal", gi))
    for gi in (3, 5):
        sk.addConstraint(Sketcher.Constraint("Vertical", gi))

    for cn, kind, args in (
            ("DiagX", "DistanceX", (-1, 1, 0, 2)),
            ("Right", "DistanceX", (-1, 1, 2, 2)),
            ("StepLength", "DistanceX", (2, 1, 2, 2)),
            ("StepY", "DistanceY", (-1, 1, 2, 1)),
            ("Bottom", "DistanceY", (-1, 1, 4, 1))):
        sk.renameConstraint(sk.addConstraint(
            Sketcher.Constraint(kind, *(args + (0.0,)))), cn)
        sk.setExpression("Constraints.%s" % cn, "%s.Outline%s" % (DERIVED, cn))
    doc.recompute()
    if not sk.FullyConstrained:
        raise ValueError("TraySketch is under-constrained")
    return sk


def build_tray(doc, sizes=SIZES, step_length=22.0):
    """The slab, minus the ten profiles. Returns the WrenchTray body.

    step_length is the one free choice in the outline - the width of the flat
    above the last lane. It sets where the bevel lands and so its slope.
    """
    td = doc.getObject(DERIVED)
    if td is None:
        raise ValueError("run build_varsets() first")
    for name, tip, expr in _outline_exprs(sizes):
        _prop(td, "App::PropertyDistance", name, "Outline", tip, expr=expr)
    _prop(td, "App::PropertyDistance", "OutlineStepLength", "Outline",
          "free design choice: width of the flat above the last lane",
          value=step_length)
    doc.recompute()

    for n in ("TrayCut", "TrayPad", "TraySketch", TRAY):
        if doc.getObject(n):
            doc.removeObject(n)
    doc.recompute()

    body = doc.addObject("PartDesign::Body", TRAY)
    body.Label = TRAY
    sk = _tray_sketch(doc, body, td)
    pad = _pad(doc, body, sk, "TrayPad", "%s.SlabHeight" % DERIVED)

    cut = doc.addObject("PartDesign::Boolean", "TrayCut")
    cut.Label = "TrayCut"
    body.addObject(cut)
    cut.BaseFeature = pad
    cut.Group = [doc.getObject(BODY % gr) for gr in sizes]
    cut.Type = "Cut"
    doc.recompute()

    sk.ViewObject.Visibility = False
    return body


def verify_tray(doc, sizes=SIZES):
    """Containment, lane gaps and wall thicknesses. Returns True if clean.

    The containment check is the one that matters: nothing in the outline
    guarantees a bevel clears every pocket once the parameters move.
    """
    g, body = doc.getObject(PARAMS), doc.getObject(TRAY)
    slab = doc.getObject("TrayPad").Shape
    divider = g.Divider.Value
    ok = True

    print("--- containment ---")
    for gr in sizes:
        out = doc.getObject(BODY % gr).Shape.cut(slab)
        vol = out.Volume if out.Solids else 0.0
        ok &= vol < 1e-6
        print(" Gr%02d outside the slab: %10.4f mm3 %s"
              % (gr, vol, "" if vol < 1e-6 else "<-- LEAK"))

    print("--- lane gaps (minimum %.2f) ---" % divider)
    shapes = [doc.getObject(BODY % gr).Shape for gr in sizes]
    for i in range(1, len(sizes)):
        d = shapes[i - 1].distToShape(shapes[i])[0]
        ok &= d >= divider - 1e-6
        print(" Gr%02d - Gr%02d : %7.3f mm %s"
              % (sizes[i - 1], sizes[i], d, "" if d >= divider - 1e-6 else "<-- TIGHT"))

    print("--- tray ---")
    sh = body.Shape
    bb = sh.BoundBox
    ok &= sh.isValid() and len(sh.Solids) == 1
    print(" %.1f x %.1f x %.1f mm   %.3f dm3   solids=%d  valid=%s"
          % (bb.XLength, bb.YLength, bb.ZLength, sh.Volume / 1e6,
             len(sh.Solids), sh.isValid()))
    print(" slab %.2f - pockets %.2f = %.2f, delta %.6f"
          % (slab.Volume, slab.Volume - sh.Volume, sh.Volume,
             slab.Volume - sum(s.Volume for s in shapes) - sh.Volume))
    return bool(ok)


def build_all(doc=None, csv_path=None, sizes=SIZES, step_length=22.0):
    """CSV -> parameters -> profiles -> packing -> tray -> checks."""
    if doc is None:
        doc = App.ActiveDocument
    if doc is None:
        raise ValueError("no active document")

    build_varsets(doc, csv_path, sizes)
    build_all_profiles(doc, sizes)

    print("--- lane packing ---")
    for gr, x, y in pack_lanes(doc, sizes):
        print(" Gr%02d at (%7.3f, %8.3f)" % (gr, x, y))

    body = build_tray(doc, sizes, step_length)
    for gr in sizes:
        vo = doc.getObject(BODY % gr).ViewObject
        if vo is not None:
            vo.Visibility = False
    print("--- verification ---" if verify_tray(doc, sizes) else "--- FAILED ---")
    return body


if __name__ == "__main__":
    print(__doc__)
