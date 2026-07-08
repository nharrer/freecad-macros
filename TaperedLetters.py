"""
TaperedLetters - build tapered, filleted PartDesign Bodies from letter/text
faces (e.g. a Draft ShapeString), for engraved or 3D-printed signage.

Given a planar face (which may have one hole, like A/O/P/Q/R), builds a
draft/taper by lofting between a slightly-eroded bottom copy and a more
eroded top copy of the outline, then fillets its sharp vertical corners and
top rim. Handles a whole multi-letter ShapeString too, by splitting it into
one face per letter, building a Body for each, and fusing them all into one
final solid.

Also includes lower-level helpers for rounding sharp/spike corners of a
planar wire (including near-cusp corners, e.g. where two font curves meet,
via a true tangent-arc fillet - not just a position-continuous chamfer) and
for making eroded/grown offset copies of a face.

Public functions:
    create_tapered_letter(doc, object_name, height, name, ...)
        Main entry point - see module usage example below.
    round_face_corners(doc, source_name, new_name, radius=0.3, threshold=30,
                        strip_threshold=0.005, strip_first=False)
        Round every sharp corner of a face's outer wire and holes.
    make_offset_face(doc, source_name, new_name, offset, join=0, z=None)
        Erode the outer wire / grow the hole wires of a face by `offset`.

Usage from the FreeCAD Python console:

    import TaperedLetters as tl
    tl.create_tapered_letter(App.ActiveDocument, "Face002", height=10.0, name="R1")

    # or on a whole ShapeString holding multiple letters/digits:
    tl.create_tapered_letter(App.ActiveDocument, "ShapeString001", height=10.0, name="Text")
"""

# =============================================================================
# CLAUDE: things tried that FAILED during development - read before
# reintroducing any of these approaches, they are dead ends on this kind of
# font/letter geometry, not just bad luck.
#
# - Part::Extrusion.TaperAngle directly on a holed letter face: fails with
#   "OCCError: BRepCheck_Analyzer::Init() - NULL shape" at *any* angle
#   magnitude (even 0.01deg) and either sign. Looked at first like a single
#   sharp/spike corner was the cause, but it still failed after that corner
#   was cleanly fillet-fixed - root cause was never fully pinned down for
#   this direct approach, hence the offset+loft+cut pipeline instead.
#
# - Part.Face.makeOffset2D with join=1 (tangent) or join=2 (intersection):
#   reliably raises "result of offsetting is null!" on real letter wires,
#   both before and after cleanup. Only join=0 (arc) works - but it can
#   leave near-zero-length sliver edges (down to ~0.0005mm) at tight/complex
#   curve regions; see _strip_degenerate_edges.
#
# - Part::Loft fed a whole Face-with-hole as one section: silently IGNORES
#   the inner wire and produces a solid with the hole filled in, with no
#   error at all. Confirmed via volume matching the "hole ignored" case, not
#   the correct one. This is why outer and inner wires must be lofted as two
#   completely separate solids and combined with Part::Cut.
#
# - PartDesign::AdditiveLoft: fails with NULL shape on the *same* wires that
#   loft fine via plain Part::Loft (tried both as a combined multi-wire
#   profile and as an outer-only profile). More fragile than Part::Loft for
#   reasons never identified - stick with Part::Loft + Part::Cut.
#
# - Turning offset-derived wires into Sketcher sketches: Sketcher rejects
#   Part::GeomOffsetCurve outright ("Unsupported geometry type"). Converting
#   via Shape.toNurbs() first "fixes" that, but the resulting BSpline
#   geometry then breaks even plain Part::Loft (NULL shape) on wires that
#   lofted fine before the toNurbs() round-trip. Don't route through
#   sketches for this geometry; build lofts from raw Part::Feature wires.
#
# - Part::MultiFuse / Part::MultiCommon fed PartDesign::Body shapes: reliably
#   produce a NULL shape (MultiFuse) or a silently empty result (MultiCommon,
#   0 solids, no error) even when fusing/intersecting the exact same
#   `.Shape` objects directly in Python works immediately. Also saw
#   MultiCommon return a *stale* volume across several Size-less
#   touch()+recompute() attempts, masking that it was actually stuck - only
#   a fresh object revealed the real failure. Workaround used throughout:
#   compute the boolean directly on .Shape in Python and store the result in
#   a plain Part::Feature (loses live parametric association - see
#   create_tapered_letter's docstring/comments).
#
# - PartDesign::Chamfer on a tapered letter's top rim: fails at *every*
#   tested size (0.05mm-1.0mm) with self-intersecting/unorientable-shape or
#   outright NULL shape - tried the full edge set, a sliver-filtered set, and
#   an outline-only set (excluding the vertical fillet's tiny transition
#   arcs). Confirmed independently via the FreeCAD GUI too (manual chamfer
#   attempt, same failure). PartDesign::Fillet on the identical edges/radius
#   works every time - use Fillet for the top rim, not Chamfer.
#
# - Morphological "opening" (erode then dilate by the same radius) to fix a
#   concave/reflex spike corner: doesn't touch it at all - opening only
#   rounds convex corners by construction. "Closing" (dilate then erode) was
#   tried as the concave counterpart and failed outright at every radius
#   tested (0.05-0.30mm) - the dilate step alone blows up on a thin
#   near-cusp reflex feature before it can ever erode back.
#
# - Blanket "opening" applied to a whole wire to round ordinary convex
#   corners: worked at some radii (e.g. 0.05, 0.15mm) but at others
#   (e.g. 0.10, 0.40mm) introduced brand-new degenerate sliver edges at an
#   unrelated spot on the wire - non-monotonic with radius, so "just use a
#   smaller radius" isn't a safe assumption; each radius has to be verified.
#
# - Rounding a sharp corner with a naive 3-point arc (through the two trim
#   points and a chord-midpoint blended toward the original vertex): valid,
#   closed geometry, but only position-continuous (G0) - left a visible ~53
#   degree kink at each junction, not truly tangent. Superseded by a proper
#   two-tangent-line fillet construction (see _fillet_wire), which is
#   G1-continuous. That construction still needs a small-enough radius for
#   the corner's sharpness, or the projected trim point runs off into
#   extrapolated nonsense on the underlying curve (seen concretely: radius=1
#   on a ~24deg corner produced a vertex ~90mm outside the letter's actual
#   bounding box).
# =============================================================================

import math

import FreeCAD as App
import Part


def create_tapered_letter(doc, object_name, height, name=None,
                           offset_bottom=0.1, offset_top=1.0,
                           vertical_radius=1.0, top_radius=1.0,
                           sharp_angle_threshold=10.0):
    """Build a tapered, filleted PartDesign Body from a letter face - or,
    if object_name's shape is a multi-letter compound (e.g. a ShapeString
    holding a whole word), split it into one face per letter, build a Body
    for each, and fuse them all into one final solid.

    Args:
        doc: the FreeCAD document to build into.
        object_name: name of the source object - either a single letter's
            Part::Feature face, or a multi-face compound (e.g. a Draft
            ShapeString holding a whole word/number).
        height: extrusion height (mm) from bottom (z=0) to top (z=height).
        name: base name used to derive all generated objects' names (for
            a multi-face source, combined with the source's own Label as
            a prefix, so running this on several different ShapeStrings
            never collides). Defaults to the source object's own Label -
            override it if that's not meaningful, or to build a second,
            differently-configured variant from the same source without
            clashing with the first.
        offset_bottom: erosion/growth distance (mm) for the bottom
            section's offset copy (outer wire shrinks, hole wires grow
            by this amount).
        offset_top: same as offset_bottom, but for the top section - the
            difference between offset_bottom and offset_top over
            `height` is what defines the taper angle.
        vertical_radius: fillet radius (mm) applied to the sharp outer
            vertical edges (step 5) - see sharp_angle_threshold for which
            edges qualify.
        top_radius: fillet radius (mm) applied to the top face's rim
            edges (step 6, both outer and hole boundary, if any).
        sharp_angle_threshold: minimum dihedral angle (degrees) between
            two adjacent side faces for their shared vertical edge to be
            considered a real corner worth filleting - see
            _dihedral_angle().

    Returns the single Body (single-face input) or a Part::Feature holding
    the fused result of all the per-letter Bodies (multi-face input).
    """
    src = doc.getObject(object_name)
    name_was_default = name is None
    if name_was_default:
        name = src.Label
    faces = src.Shape.Faces
    if len(faces) <= 1:
        return _create_tapered_letter_single(doc, object_name, height, name,
                                              offset_bottom, offset_top,
                                              vertical_radius, top_radius,
                                              sharp_angle_threshold)

    # Prefix with the source object's own label so running this on several
    # different ShapeStrings (each with its own letters/digits) never
    # collides - without it, e.g. two texts both called with name="Text"
    # would silently delete-and-replace each other's objects. Skip doubling
    # it up when name defaulted to the label in the first place.
    prefix = src.Label if name_was_default else "%s_%s" % (src.Label, name)

    bodies = []
    group_members = []
    for i, f in enumerate(faces):
        letter_name = "%s_%d" % (prefix, i)
        face_obj_name = letter_name + "_SourceFace"
        face_obj = _make_feature(doc, face_obj_name, f, visible=False)
        body = _create_tapered_letter_single(doc, face_obj_name, height, letter_name,
                                              offset_bottom, offset_top,
                                              vertical_radius, top_radius,
                                              sharp_angle_threshold)
        bodies.append(body)
        group_members += [face_obj, body]

    letters_group_name = src.Label + "_Letters"
    letters_group = doc.getObject(letters_group_name)
    if letters_group:
        doc.removeObject(letters_group_name)
    letters_group = doc.addObject("App::DocumentObjectGroup", letters_group_name)
    letters_group.Group = group_members
    letters_group.Visibility = False
    for o in group_members:
        o.Visibility = False
    doc.recompute()

    # Part::MultiFuse reliably fails with a NULL-shape error on Body outputs
    # in this session (even though fusing the same shapes directly in Python
    # works fine) - so the boolean is done directly on the shapes and stored
    # in a plain Part::Feature instead of relying on MultiFuse's recompute.
    fused_shape = bodies[0].Shape
    for b in bodies[1:]:
        fused_shape = fused_shape.fuse(b.Shape)
    fuse_obj = _make_feature(doc, prefix + "_Fuse", fused_shape, visible=True)
    fuse_obj.Label = src.Label + "_Part"
    return fuse_obj


def _create_tapered_letter_single(doc, face_name, height, name,
                                   offset_bottom=0.1, offset_top=1.0,
                                   vertical_radius=1.0, top_radius=1.0,
                                   sharp_angle_threshold=10.0):
    """Build a tapered, filleted PartDesign Body from a single letter face.

    1. 0.1mm offset copy of the face at z=0.
    2. 1mm offset copy of the face at z=height.
    3. Outer/inner wires lofted separately, then cut (Part::Loft on a whole
       face-with-hole silently ignores the hole - see round-trip history in
       this session - so outer and inner must be lofted independently).
    4. Result becomes a new PartDesign::Body's BaseFeature.
    5. All outer (non-hole) vertical edges filleted with vertical_radius.
    6. The top face's rim edges filleted with top_radius.

    Only handles 0 or 1 holes (i.e. not letters like B - raise if found).
    """
    src = doc.getObject(face_name)
    face = src.Shape.Faces[0]
    outer_wire = face.OuterWire
    inner_wires = [w for w in face.Wires if not w.isSame(outer_wire)]
    if len(inner_wires) > 1:
        raise NotImplementedError(
            "%s has %d holes; letters with more than one hole (e.g. B) "
            "aren't supported yet." % (face_name, len(inner_wires)))
    has_hole = len(inner_wires) == 1

    bottom = make_offset_face(doc, face_name, name + "_Bottom", offset_bottom, z=0.0)
    top = make_offset_face(doc, face_name, name + "_Top", offset_top, z=height)
    bottom.Visibility = False
    top.Visibility = False

    fb = bottom.Shape.Faces[0]
    ft = top.Shape.Faces[0]
    ob, ot = fb.OuterWire, ft.OuterWire

    ob_obj = _make_feature(doc, name + "_OuterBottom", Part.Face(ob), visible=False)
    ot_obj = _make_feature(doc, name + "_OuterTop", Part.Face(ot), visible=False)
    loft_outer = _make_loft(doc, name + "_LoftOuter", ob_obj, ot_obj)

    # bottom/top aren't referenced via any FreeCAD property link (their wires
    # were copied out, not linked), so the tree would show them as orphans
    # unless placed somewhere explicitly - a folder keeps them tidy. Every
    # other helper (ob_obj/ot_obj/ib_obj/it_obj and, when there's no hole,
    # loft_outer) IS already referenced by a Sections/Base/Tool property, so
    # FreeCAD's tree view auto-nests it under its consumer (Loft or Cut) -
    # adding it to Group too would just make it appear twice.
    sections_name = name + "_Sections"
    sections_folder = doc.getObject(sections_name)
    if sections_folder:
        doc.removeObject(sections_name)
    sections_folder = doc.addObject("App::DocumentObjectGroup", sections_name)
    sections_folder.Group = [bottom, top]
    sections_folder.Visibility = False

    # Kept in construction order so the Body tree reads top-to-bottom the
    # same way the shape was actually built (inputs before the solid they
    # produce, which is before the Body's base-feature wrapper).
    helper_objs = [sections_folder]

    if has_hole:
        ib = [w for w in fb.Wires if not w.isSame(ob)][0]
        it = [w for w in ft.Wires if not w.isSame(ot)][0]
        ib_obj = _make_feature(doc, name + "_InnerBottom", Part.Face(ib), visible=False)
        it_obj = _make_feature(doc, name + "_InnerTop", Part.Face(it), visible=False)
        loft_inner = _make_loft(doc, name + "_LoftInner", ib_obj, it_obj)

        cut_name = name + "_Cut"
        cut = doc.getObject(cut_name)
        if cut:
            doc.removeObject(cut_name)
        cut = doc.addObject("Part::Cut", cut_name)
        cut.Base = loft_outer
        cut.Tool = loft_inner
        cut.Visibility = False
        doc.recompute()
        solid = cut
        # loft_outer/loft_inner are now claimed (auto-nested) by cut via its
        # Base/Tool properties - only cut itself needs to be in Group.
        helper_objs += [cut]
    else:
        doc.recompute()
        solid = loft_outer
        # nothing claims loft_outer in this branch, so list it explicitly.
        helper_objs += [loft_outer]

    body_name = name + "_Body"
    body = doc.getObject(body_name)
    if body:
        doc.removeObject(body_name)
    body = doc.addObject("PartDesign::Body", body_name)
    body.BaseFeature = solid
    doc.recompute()
    # Assigning an external (non-PartDesign) shape to BaseFeature makes
    # FreeCAD auto-create a PartDesign::FeatureBase wrapper around it - that
    # wrapper isn't added to Group automatically, which leaves it floating
    # outside the Body in the tree view unless we add it ourselves. It isn't
    # returned by body.BaseFeature (that just echoes back `solid`), so find
    # it by looking for the FeatureBase object that wraps `solid`.
    wrapper = next((o for o in doc.Objects
                    if o.TypeId == "PartDesign::FeatureBase" and o.BaseFeature == solid), None)
    if wrapper:
        wrapper.Visibility = False
        wrapper.Label = name + "_BaseFeature"
    group = helper_objs + ([wrapper] if wrapper else [])
    body.Group = group
    doc.recompute()

    # Step 5: fillet outer (non-hole) vertical edges.
    inner_vertical_starts = []
    if has_hole:
        for e in loft_inner.Shape.Edges:
            bb = e.BoundBox
            if (bb.ZMax - bb.ZMin) > height * 0.99:
                inner_vertical_starts.append(e.Vertexes[0].Point)

    def is_inner_pt(pt, tol=0.05):
        return any((pt.x - p.x) ** 2 + (pt.y - p.y) ** 2 < tol ** 2
                   for p in inner_vertical_starts)

    outer_vertical_names = []
    for i, e in enumerate(body.Shape.Edges):
        bb = e.BoundBox
        if (bb.ZMax - bb.ZMin) <= height * 0.99 or is_inner_pt(e.Vertexes[0].Point):
            continue
        angle = _dihedral_angle(body.Shape, e)
        if angle is not None and angle > sharp_angle_threshold:
            outer_vertical_names.append("Edge%d" % (i + 1))

    # An empty edge list makes PartDesign::Fillet produce a NULL shape (e.g.
    # a "0" has no sharp corners at all) - skip the feature entirely rather
    # than create a broken one, and just carry the current tip forward.
    if outer_vertical_names:
        fillet_v_name = name + "_FilletVertical"
        fv = doc.getObject(fillet_v_name)
        if fv:
            doc.removeObject(fillet_v_name)
        fv = doc.addObject("PartDesign::Fillet", fillet_v_name)
        fv.Base = (body.Tip, outer_vertical_names)
        fv.Radius = vertical_radius
        fv.Visibility = False
        body.Group = list(body.Group) + [fv]
        body.Tip = fv
        doc.recompute()
    else:
        fv = body.Tip

    # Step 6: fillet the top face's rim edges (both outer and hole, if any).
    # (Chamfer was tried here first but reliably produces invalid/self-
    # intersecting geometry on this rim at 1mm, confirmed both via script
    # and manual GUI attempts - fillet works reliably at the same size.)
    top_edge_names = []
    for i, e in enumerate(fv.Shape.Edges):
        bb = e.BoundBox
        if abs(bb.ZMin - height) < 1e-3 and abs(bb.ZMax - height) < 1e-3:
            top_edge_names.append("Edge%d" % (i + 1))

    if top_edge_names:
        fillet_t_name = name + "_FilletTop"
        ft_obj = doc.getObject(fillet_t_name)
        if ft_obj:
            doc.removeObject(fillet_t_name)
        ft_obj = doc.addObject("PartDesign::Fillet", fillet_t_name)
        ft_obj.Base = (fv, top_edge_names)
        ft_obj.Radius = top_radius
        ft_obj.Visibility = True
        body.Group = list(body.Group) + [ft_obj]
        body.Tip = ft_obj
        doc.recompute()

    return body


def round_face_corners(doc, source_name, new_name, radius=0.3, threshold=30,
                        strip_threshold=0.005, strip_first=False):
    """Round every sharp corner (outer wire + all holes) of `source_name`'s
    face and store the result as a new Part::Feature `new_name`.

    Set strip_first=True when the source face came out of makeOffset2D -
    it may contain near-zero-length sliver edges that should be removed
    before fillet detection runs.
    """
    src = doc.getObject(source_name)
    face = src.Shape.Faces[0]
    outer_wire = face.OuterWire
    inner_wires = [w for w in face.Wires if not w.isSame(outer_wire)]

    if strip_first:
        outer_wire = _strip_degenerate_edges(outer_wire, strip_threshold)
        inner_wires = [_strip_degenerate_edges(w, strip_threshold) for w in inner_wires]

    new_outer, _ = _fillet_wire(outer_wire, radius, threshold)
    new_inners = [_fillet_wire(w, radius, threshold)[0] for w in inner_wires]

    final_face = _face_from_wires(new_outer, new_inners)

    obj = doc.getObject(new_name)
    if obj:
        doc.removeObject(new_name)
    obj = doc.addObject("Part::Feature", new_name)
    obj.Shape = final_face
    obj.Placement = src.Placement
    doc.recompute()
    return obj


def make_offset_face(doc, source_name, new_name, offset, join=0, z=None):
    """Erode the outer wire / grow the inner (hole) wires of source_name's
    face by `offset`, storing the result as new Part::Feature `new_name`.
    Pass z to place the result at that height (e.g. the taper's top)."""
    src = doc.getObject(source_name)
    face = src.Shape.Faces[0]
    outer_wire = face.OuterWire
    inner_wires = [w for w in face.Wires if not w.isSame(outer_wire)]

    shrunk = Part.Face(outer_wire).makeOffset2D(-offset, join, False, False, True)
    grown_inner_wires = [
        Part.Face(w).makeOffset2D(offset, join, False, False, True).Wires[0]
        for w in inner_wires
    ]

    final_face = _face_from_wires(shrunk.Wires[0], grown_inner_wires)

    obj = doc.getObject(new_name)
    if obj:
        doc.removeObject(new_name)
    obj = doc.addObject("Part::Feature", new_name)
    obj.Shape = final_face
    if z is not None:
        obj.Placement = App.Placement(App.Vector(0, 0, z), App.Rotation())
    doc.recompute()
    return obj


def _is_matched(ordered, ordered_verts, i):
    e = ordered[i]
    p_start = ordered_verts[i]
    v_at_first = e.Vertexes[0].Point
    return (v_at_first - p_start).Length < 1e-6


def _tangent_at_vertex(ordered, ordered_verts, i):
    e = ordered[i]
    fp, lp = e.FirstParameter, e.LastParameter
    if _is_matched(ordered, ordered_verts, i):
        return e.tangentAt(fp), e.tangentAt(lp)
    else:
        return e.tangentAt(lp).negative(), e.tangentAt(fp).negative()


def _ang_between(v1, v2):
    d = v1.dot(v2) / (v1.Length * v2.Length)
    d = max(-1.0, min(1.0, d))
    return math.degrees(math.acos(d))


def _find_sharp(wire, threshold=30):
    ordered = wire.OrderedEdges
    ordered_verts = [v.Point for v in wire.OrderedVertexes]
    n = len(ordered)
    sharp = []
    for i in range(n):
        prev = _tangent_at_vertex(ordered, ordered_verts, i - 1)
        curr = _tangent_at_vertex(ordered, ordered_verts, i)
        a = _ang_between(prev[1], curr[0])
        if a > threshold:
            sharp.append((i, round(a, 3), ordered_verts[i]))
    return sharp


def _strip_degenerate_edges(wire, threshold=0.005):
    """Remove near-zero-length edges (offset-algorithm artifacts) and bridge
    the resulting gaps with short connector lines."""
    ordered = wire.OrderedEdges
    ordered_verts = [v.Point for v in wire.OrderedVertexes]
    n = len(ordered)
    kept = [(i, e) for i, e in enumerate(ordered) if e.Length > threshold]

    new_edges = []
    m = len(kept)
    for k in range(m):
        idx, e = kept[k]
        new_edges.append(e)
        next_idx, _ = kept[(k + 1) % m]
        end_pt = ordered_verts[(idx + 1) % n]
        start_pt_of_next = ordered_verts[next_idx]
        gap = (end_pt - start_pt_of_next).Length
        if gap > 1e-9:
            new_edges.append(Part.LineSegment(end_pt, start_pt_of_next).toShape())
    return Part.Wire(new_edges)


def _fillet_wire(wire, radius, threshold=30):
    """Replace every corner sharper than `threshold` degrees with a true
    tangent-arc fillet of the given radius (classic two-tangent-line
    construction, using the actual curve's tangent/position at each trim
    point - accurate even for near-cusp spikes as long as radius is small
    enough that the curve doesn't deviate much from its tangent line over
    the trim distance)."""
    ordered = wire.OrderedEdges
    ordered_verts = [v.Point for v in wire.OrderedVertexes]
    n = len(ordered)

    sharp_idxs = [i for i, _, _ in _find_sharp(wire, threshold)]

    edge_start_trim = {}
    edge_end_trim = {}
    arc_after = {}

    for sharp_idx in sharp_idxs:
        prev_i = (sharp_idx - 1) % n
        e10 = ordered[prev_i]
        e11 = ordered[sharp_idx]
        m10 = _is_matched(ordered, ordered_verts, prev_i)
        m11 = _is_matched(ordered, ordered_verts, sharp_idx)

        V = ordered_verts[sharp_idx]
        _, T_in_end = _tangent_at_vertex(ordered, ordered_verts, prev_i)
        T_out_start, _ = _tangent_at_vertex(ordered, ordered_verts, sharp_idx)

        u1 = T_in_end.negative(); u1.normalize()
        u2 = App.Vector(T_out_start.x, T_out_start.y, T_out_start.z); u2.normalize()
        theta = math.radians(_ang_between(u1, u2))

        t = radius / math.tan(theta / 2)
        d = radius / math.sin(theta / 2)
        bis = u1 + u2; bis.normalize()
        C = V + bis * d
        P1 = V + u1 * t
        P2 = V + u2 * t

        u_a = e10.Curve.parameter(P1)
        u_b = e11.Curve.parameter(P2)
        pa = e10.Curve.value(u_a)
        pb = e11.Curve.value(u_b)

        va = (pa - C); va.normalize()
        vb = (pb - C); vb.normalize()
        vm = va + vb; vm.normalize()
        mid_pt = C + vm * radius
        arc_edge = Part.Arc(pa, mid_pt, pb).toShape()

        if m10:
            edge_end_trim[prev_i] = u_a
        else:
            edge_start_trim[prev_i] = u_a
        if m11:
            edge_start_trim[sharp_idx] = u_b
        else:
            edge_end_trim[sharp_idx] = u_b

        arc_after[prev_i] = arc_edge

    new_edges = []
    for i in range(n):
        e = ordered[i]
        start_u = edge_start_trim.get(i, e.FirstParameter)
        end_u = edge_end_trim.get(i, e.LastParameter)
        if i in edge_start_trim or i in edge_end_trim:
            new_e = Part.Edge(e.Curve, start_u, end_u)
        else:
            new_e = e
        new_edges.append(new_e)
        if i in arc_after:
            new_edges.append(arc_after[i])

    new_wire = Part.Wire(new_edges)
    return new_wire, sharp_idxs


def _face_from_wires(outer_wire, inner_wires):
    """Part.Face(outer, inner) sometimes misclassifies a rebuilt inner wire
    as a second outer lobe instead of a hole (area = outer+inner instead of
    outer-inner). Detect that and reverse the inner wire as a fix."""
    if not inner_wires:
        return Part.Face(outer_wire)

    expected = Part.Face(outer_wire).Area - sum(Part.Face(w).Area for w in inner_wires)
    face = Part.Face([outer_wire] + inner_wires)
    if abs(face.Area - expected) < 0.01:
        return face
    return Part.Face([outer_wire] + [w.reversed() for w in inner_wires])


def _make_feature(doc, name, shape, visible=True):
    obj = doc.getObject(name)
    if obj:
        doc.removeObject(name)
    obj = doc.addObject("Part::Feature", name)
    obj.Shape = shape
    obj.Visibility = visible
    return obj


def _make_loft(doc, name, sec1, sec2):
    obj = doc.getObject(name)
    if obj:
        doc.removeObject(name)
    obj = doc.addObject("Part::Loft", name)
    obj.Sections = [sec1, sec2]
    obj.Solid = True
    obj.Ruled = False
    obj.Closed = False
    obj.Visibility = False
    return obj


def _dihedral_angle(shape, edge):
    """Angle (degrees) between the normals of the two faces meeting at
    `edge`, evaluated right at the edge - ~0 for a smooth/tangent join
    (e.g. a curve that got split into multiple edges for parametric
    reasons, not an actual corner), and large (e.g. ~90) for a real crease.
    Returns None if the edge doesn't have exactly two adjacent faces."""
    adj_faces = [f for f in shape.Faces if any(e2.isSame(edge) for e2 in f.Edges)]
    if len(adj_faces) != 2:
        return None
    mid = edge.valueAt((edge.FirstParameter + edge.LastParameter) / 2.0)
    normals = []
    for f in adj_faces:
        u, v = f.Surface.parameter(mid)
        n = f.normalAt(u, v)
        if f.Orientation == "Reversed":
            n = n.negative()
        normals.append(n)
    d = normals[0].dot(normals[1]) / (normals[0].Length * normals[1].Length)
    d = max(-1.0, min(1.0, d))
    return math.degrees(math.acos(d))


if __name__ == "__main__":
    doc = App.ActiveDocument
    if doc is None:
        print("No active document.")
    else:
        print("TaperedLetters macro loaded. Example:")
        print('  import TaperedLetters as tl')
        print('  tl.create_tapered_letter(App.ActiveDocument, "Face002", height=10.0, name="R1")')
