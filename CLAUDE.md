# CLAUDE.md

FreeCAD macro folder (FreeCAD 1.1, Flatpak). Claude talks to the running FreeCAD through the `freecad` MCP server.

## FreeCAD MCP

- If calls fail with "Connection refused", the user has to start the RPC server from the MCP addon workbench in FreeCAD.

## Animating parts

Reference implementation: `TurbineAnimate.FCMacro` (Turbine document in `~/projects/3d/PoolRoboter/`).

- Put all motion in a pure function `pose(t)` that returns the angles and offsets for time `t`, with a fixed `CYCLE` length. Live playback and frame export then share the same motion.
- Animate by setting the body `Placement` (`App.Placement(offset, App.Rotation(axis, angle)).multiply(base)`). Don't recompute. Store the original placements first, restore them afterwards and call `purgeTouched()`.
- Live playback: use a `QtCore.QTimer` driven by `time.monotonic()`. Running the macro again stops it (keep the instance on the `App` module).
- Check the motion for collisions on shape copies: `P.Shape.copy()` with a new `Placement`, then `P.common(A).Volume` over sampled `t`. This is also how to work out thread/clutch handedness instead of guessing.
- Run a macro file from MCP with `runpy.run_path(path, run_name="...")`. Use a name other than `"__main__"` to get only `pose` without starting it.

## Capturing frames

- In some cases the user sets up orientation, zoom and window size by hand. Never call `viewIsometric()`, `fitAll()`, `ViewFit` etc. without asking.
- `get_view`, `get_objects` and `execute_code` with a screenshot switch the view orientation. Always pass `include_screenshot=False` to `execute_code`, and don't use `get_view` or `get_objects` screenshots once the user has arranged the view. To look at the scene, grab the framebuffer (see below) and inspect the PNG.

Recapture from FreeCAD for every layout change: different aspect ratio, background or framing. Don't build layouts afterwards by padding frames or moving overlays around in ffmpeg. If a different aspect ratio is needed, ask the user to resize the 3D view (window or panels) and capture again.

Before capturing, check the 3D view's aspect ratio (`viewport().size()`). If it isn't 16:9, ask the user whether to rearrange the scene first, since 16:9 GIFs fill the cell when posted on Mastodon (see below).

- **Use `grabFramebuffer()`**: it captures exactly what is on screen, including the NaviCube, axis cross and background:
  ```python
  vp = Gui.getDocument(doc).ActiveView.graphicsView().viewport()  # QOpenGLWidget
  Gui.updateGui()                 # after setting the placements
  vp.grabFramebuffer().save(path) # physical pixels (display scaling ~1.4 here)
  ```
- `view.saveImage(path, w, h, "White")` renders off screen at any size, but **without** the NaviCube and axis cross.
- White (or other) background for one capture only, without touching preferences:
  `ActiveView.getViewer().setBackgroundColor(1.0, 1.0, 1.0)`. This takes three separate floats, not a tuple. Afterwards restore it from `User parameter:BaseApp/Preferences/View` → `BackgroundColor` (the user's is `#F7F7F7`, a plain colour). Restore in a `finally` block.
- Write frames under `~/.var/app/org.freecad.FreeCAD/cache/...`. FreeCAD is a Flatpak, and this path is visible to both FreeCAD and the shell.
- **Seamless loop:** `N = CYCLE * FPS` frames at `t = i / FPS` for `i in range(N)`. Never render `t = CYCLE`, because it is identical to frame 0. Make `CYCLE * FPS` an integer (e.g. 5 s × 25 fps = 125).

## Making the GIF

```sh
ffmpeg -framerate 25 -i frame_%04d.png \
  -vf "scale=560:-2:flags=lanczos,split[a][b];[a]palettegen=stats_mode=full[p];[b][p]paletteuse=dither=sierra2_4a" \
  -loop 0 out.gif
```

- 25 fps fits GIF timing exactly (4 cs per frame).
- Size is not linear in resolution. Try a few widths and pick the one closest to the target size.
- zsh: write `${s}:flags=...`, not `$s:flags`, because `:f` is a zsh modifier.
- To preview GIF frames, use `magick in.gif -coalesce ...`. Without `-coalesce` the delta frames look broken.
- Save the output next to the `.FCStd` file.

Reference sizes (5 s, 125 frames, CAD render): 960×900 ≈ 4.2 MB, 560×524 ≈ 2 MB, 480×450 ≈ 1.6 MB, 800×450 ≈ 2 MB.

## Mastodon limits

- **Animated GIFs: at most 921,600 pixels (1280×720 area).** Above that the upload fails with `422 <W>x<H> GIF files are not supported`. The file size was not the problem; 1000×936 was rejected only for its pixel count.
- Default limits are 16 MB for images and 99 MB for videos. Instances can set their own (`https://<instance>/api/v2/instance` → `configuration.media_attachments`).
- GIFs are converted to looping video (gifv) and shown letterboxed (fitted, not cropped) in the post's grid cell. In the user's 3-attachment post the GIF cell was 16:9, so capture at 16:9 to fill it.
- A short silent MP4 is an alternative to GIF: much smaller and without the GIF pixel limit.
