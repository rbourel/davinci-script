# Grid Flash Effect — DaVinci Resolve Script

Generates an N×M mosaic/grid effect from a single clip, with an optional
per-tile Fusion flash. Requires **DaVinci Resolve Studio** (scripting API
is not available in the free version).

## Install

1. Copy `grid_flash_effect.py` into your Resolve Scripts folder:

   - **Windows:** `C:\ProgramData\Blackmagic Design\DaVinci Resolve\Fusion\Scripts\Utility`
   - **macOS:** `/Library/Application Support/Blackmagic Design/DaVinci Resolve/Fusion/Scripts/Utility`
   - **Linux:** `/opt/resolve/Fusion/Scripts/Utility`

   (Use the `Edit` subfolder instead of `Utility` if you only want it to
   show up on the Edit page.)

2. Restart if needed Resolve if it was already open.

## Usage

1. On the timeline, select the clip you want to turn into a grid (or select
   it in the Media Pool bin instead).
2. Go to **Workspace > Scripts > grid_flash_effect**.
3. In the popup, set rows, columns, stagger (frames), and whether to add the
   flash effect, then click **Generate**.

You can also paste the script's content directly into **Workspace > Console
> Py3** for quick testing without installing it.

## Notes

- The top-left tile reuses your originally selected clip in place — it's not
  moved, so make sure it's already roughly where you want the grid to start.
- Crop values are computed in the timeline's resolution, not the source
  clip's native resolution.
- A few constants at the top of the file (`CLIP_NAME`, `CROP_NORMALIZED`,
  flash frame/brightness values) aren't in the UI — edit them directly in
  the script if needed.
