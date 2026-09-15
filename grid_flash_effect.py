"""
Genere un effet mosaique/grille (N x M tuiles) a partir d'un seul clip video :
duplique le clip sur plusieurs pistes, applique un Crop different sur chacune
pour isoler la portion de l'image qui lui correspond (facon reveal Instagram),
et ajoute en option un flash Fusion (Brightness/Contrast) par tuile.

L'ordre d'apparition est defini par un "motif" : chaque cellule recoit un
numero d'etape. Plusieurs cellules partageant le meme numero apparaissent en
meme temps. Motifs predefinis disponibles, ou motif dessine a la main via une
grille de champs numeriques.

La cellule d'etape 0 reutilise le clip source deja present sur la timeline
(pas de duplicata inutile) ; elle n'est pas deplacee.

A executer depuis la console Python de Resolve (Workspace > Console > Py3,
onglet Py3 et non Lua) ou depuis le menu Workspace > Scripts.
Necessite DaVinci Resolve Studio.
"""

import random

# "resolve", "fusion" et "bmd" sont deja definis dans le contexte Resolve.

# ============ CONFIG PAR DEFAUT ============
DEFAULT_ROWS = 4
DEFAULT_COLS = 4
DEFAULT_STAGGER_FRAMES = 4
DEFAULT_ADD_FLASH = True
DEFAULT_ADD_GRID_OVERLAY = False
DEFAULT_FLASH_FRAMES = 4

CLIP_NAME = None                 # None = clip selectionne (timeline ou Media Pool)
CROP_NORMALIZED = False          # False: Crop en pixels ; True: fraction 0-1
FLASH_START_FRAME = 0            # frame de depart du flash (fixe)
FLASH_END_BRIGHTNESS = 0.0       # valeur d'arrivee du flash (fixe)

PATTERNS = [
    "Haut-gauche -> bas-droite",
    "Bas-droite -> haut-gauche",
    "Diagonale (haut-gauche)",
    "Cercle depuis le centre",
    "Cercle vers le centre",
    "Ligne par ligne",
    "Colonne par colonne",
    "Aleatoire",
    "Personnalise (dessine)",
]

# rempli par la fenetre de dessin : {(r, c): numero_etape}
CUSTOM_PATTERN = {}
# ===========================================


def build_pattern(pattern_name, grid_rows, grid_cols):
    """Retourne {(r, c): step} ou step est le numero d'etape (0 = premier).
    Plusieurs cellules peuvent partager le meme step."""
    cells = [(r, c) for r in range(grid_rows) for c in range(grid_cols)]
    center_r = (grid_rows - 1) / 2
    center_c = (grid_cols - 1) / 2

    if pattern_name == "Personnalise (dessine)":
        if not CUSTOM_PATTERN:
            raise RuntimeError(
                "Aucun motif personnalise defini. Clique sur 'Dessiner le motif' d'abord."
            )
        raw = dict(CUSTOM_PATTERN)
    elif pattern_name == "Haut-gauche -> bas-droite":
        raw = {cell: i for i, cell in enumerate(cells)}
    elif pattern_name == "Bas-droite -> haut-gauche":
        raw = {cell: i for i, cell in enumerate(reversed(cells))}
    elif pattern_name == "Diagonale (haut-gauche)":
        raw = {(r, c): r + c for (r, c) in cells}
    elif pattern_name == "Cercle depuis le centre":
        raw = {(r, c): round(((r - center_r) ** 2 + (c - center_c) ** 2) ** 0.5 * 2)
               for (r, c) in cells}
    elif pattern_name == "Cercle vers le centre":
        dists = {(r, c): round(((r - center_r) ** 2 + (c - center_c) ** 2) ** 0.5 * 2)
                 for (r, c) in cells}
        max_d = max(dists.values())
        raw = {cell: max_d - d for cell, d in dists.items()}
    elif pattern_name == "Ligne par ligne":
        raw = {(r, c): r for (r, c) in cells}
    elif pattern_name == "Colonne par colonne":
        raw = {(r, c): c for (r, c) in cells}
    elif pattern_name == "Aleatoire":
        shuffled = cells[:]
        random.shuffle(shuffled)
        raw = {cell: i for i, cell in enumerate(shuffled)}
    else:
        raise RuntimeError(f"Motif inconnu : {pattern_name}")

    # normalise les valeurs en etapes consecutives 0..k-1 en conservant les ex aequo
    ordered_values = sorted(set(raw.values()))
    remap = {v: i for i, v in enumerate(ordered_values)}
    return {cell: remap[v] for cell, v in raw.items()}


def find_clip_by_name(folder, name):
    for clip in folder.GetClipList():
        if clip.GetName() == name:
            return clip
    for sub in folder.GetSubFolderList():
        found = find_clip_by_name(sub, name)
        if found:
            return found
    return None


def resolve_source(media_pool, timeline):
    """Retourne (mediaPoolItem, originalTimelineItem_ou_None)."""
    if CLIP_NAME:
        item = find_clip_by_name(media_pool.GetRootFolder(), CLIP_NAME)
        if not item:
            raise RuntimeError(f"Clip '{CLIP_NAME}' introuvable dans le Media Pool.")
        return item, None

    selected_timeline_items = timeline.GetSelectedClips() if hasattr(timeline, "GetSelectedClips") else None
    if selected_timeline_items:
        original_item = selected_timeline_items[0]
        return original_item.GetMediaPoolItem(), original_item

    selected_bin_clips = media_pool.GetSelectedClips()
    if selected_bin_clips:
        first = selected_bin_clips[0]
        mp_item = first if not hasattr(first, "GetMediaPoolItem") else first.GetMediaPoolItem()
        return mp_item, None

    raise RuntimeError(
        "Impossible de resoudre le clip source. Selectionne le clip sur la timeline "
        "OU dans le Media Pool avant de lancer, ou renseigne CLIP_NAME."
    )


def apply_crop_and_flash(item, r, c, grid_rows, grid_cols, timeline_width, timeline_height,
                          add_flash, flash_start_brightness, flash_end_frame):
    left = c / grid_cols
    right = (grid_cols - c - 1) / grid_cols
    top = r / grid_rows
    bottom = (grid_rows - r - 1) / grid_rows

    if not CROP_NORMALIZED:
        left, right = int(left * timeline_width), int(right * timeline_width)
        top, bottom = int(top * timeline_height), int(bottom * timeline_height)

    item.SetProperty("CropLeft", left)
    item.SetProperty("CropRight", right)
    item.SetProperty("CropTop", top)
    item.SetProperty("CropBottom", bottom)

    if not add_flash:
        return

    comp = item.AddFusionComp()
    if not comp:
        comp_count = item.GetFusionCompCount()
        if comp_count and comp_count > 0:
            comp = item.GetFusionCompByIndex(comp_count)
    if not comp:
        print(f"Flash ignore sur la tuile ({r},{c}) : Fusion comp non cree.")
        return

    media_in = comp.FindTool("MediaIn1")
    media_out = comp.FindTool("MediaOut1")
    if not media_in or not media_out:
        for tool in comp.GetToolList().values():
            if tool.ID == "MediaIn" and not media_in:
                media_in = tool
            elif tool.ID == "MediaOut" and not media_out:
                media_out = tool
    if not media_in or not media_out:
        print(f"Flash ignore sur la tuile ({r},{c}) : MediaIn/MediaOut introuvables.")
        return

    bc = comp.AddTool("BrightnessContrast")
    bc.Input = media_in.Output
    media_out.Input = bc.Output
    bc.Brightness = comp.AddTool("BezierSpline")
    bc.Brightness[FLASH_START_FRAME] = flash_start_brightness
    bc.Brightness[flash_end_frame] = FLASH_END_BRIGHTNESS


def add_grid_overlay_clip(media_pool, source_item, base_start_frame, clip_frames, track_index):
    """Calque de dessus avec un node Fusion 'Grid'. Les noms d'inputs exacts du
    tool restent a confirmer : ils sont affiches en console pour etre regles."""
    result = media_pool.AppendToTimeline([{
        "mediaPoolItem": source_item,
        "startFrame": 0,
        "endFrame": clip_frames - 1,
        "trackIndex": track_index,
        "recordFrame": base_start_frame,
        "mediaType": 1,
    }])
    if not result:
        print("Echec de creation du calque de grille.")
        return
    item = result[0]

    comp = item.AddFusionComp()
    if not comp:
        comp_count = item.GetFusionCompCount()
        if comp_count and comp_count > 0:
            comp = item.GetFusionCompByIndex(comp_count)
    if not comp:
        print("Impossible de creer le comp Fusion pour la grille.")
        return

    media_out = comp.FindTool("MediaOut1")
    if not media_out:
        for tool in comp.GetToolList().values():
            if tool.ID == "MediaOut":
                media_out = tool
                break
    if not media_out:
        print("MediaOut introuvable dans le comp de la grille.")
        return

    grid_tool = comp.AddTool("Grid")
    if not grid_tool:
        print("Le node 'Grid' n'a pas pu etre cree - nom exact du tool a confirmer.")
        return
    media_out.Input = grid_tool.Output

    print(f"Calque de grille cree (piste {track_index}). Inputs du node 'Grid' :")
    try:
        print(list(grid_tool.GetInputList()))
    except Exception as e:
        print(f"(impossible de lister les inputs : {e})")


def generate_grid(grid_rows, grid_cols, stagger_frames, add_flash, add_grid_overlay,
                  pattern_name, flash_start_brightness, flash_end_frame):
    project = resolve.GetProjectManager().GetCurrentProject()
    if not project:
        raise RuntimeError("Aucun projet ouvert.")
    timeline = project.GetCurrentTimeline()
    if not timeline:
        raise RuntimeError("Aucune timeline active.")

    media_pool = project.GetMediaPool()
    source_item, original_item = resolve_source(media_pool, timeline)

    steps = build_pattern(pattern_name, grid_rows, grid_cols)

    n_tiles = grid_rows * grid_cols
    n_new_duplicates = n_tiles - 1 if original_item else n_tiles
    if add_grid_overlay:
        n_new_duplicates += 1

    current_tracks = timeline.GetTrackCount("video")
    for _ in range(n_new_duplicates):
        timeline.AddTrack("video")

    clip_frames = int(source_item.GetClipProperty("Frames"))
    timeline_width = int(project.GetSetting("timelineResolutionWidth"))
    timeline_height = int(project.GetSetting("timelineResolutionHeight"))

    base_start_frame = original_item.GetStart() if original_item else timeline.GetStartFrame()

    # cellule qui reutilise le clip original : une de celles d'etape 0
    # (elle ne peut pas etre deplacee, donc elle doit apparaitre en premier)
    reuse_cell = None
    if original_item:
        step0_cells = sorted([cell for cell, s in steps.items() if s == 0])
        reuse_cell = step0_cells[0] if step0_cells else None

    # tuiles triees par etape, pour que les pistes suivent l'ordre d'apparition
    ordered_cells = sorted(steps.keys(), key=lambda cell: (steps[cell], cell))

    placed = 0
    next_new_track = current_tracks + 1

    for (r, c) in ordered_cells:
        step = steps[(r, c)]
        record_frame = base_start_frame + step * stagger_frames
        source_start = step * stagger_frames

        if (r, c) == reuse_cell:
            item = original_item
        else:
            track_index = next_new_track
            next_new_track += 1
            result = media_pool.AppendToTimeline([{
                "mediaPoolItem": source_item,
                "startFrame": source_start,
                "endFrame": clip_frames - 1,
                "trackIndex": track_index,
                "recordFrame": record_frame,
                "mediaType": 1,
            }])
            if not result:
                print(f"Echec sur la tuile ({r},{c}) - piste {track_index}")
                continue
            item = result[0]

        apply_crop_and_flash(item, r, c, grid_rows, grid_cols, timeline_width,
                              timeline_height, add_flash, flash_start_brightness, flash_end_frame)
        placed += 1

    n_steps = len(set(steps.values()))
    print(f"{placed}/{n_tiles} tuiles placees - grille {grid_rows}x{grid_cols}, "
          f"motif '{pattern_name}', {n_steps} etapes, stagger={stagger_frames}f.")

    if add_grid_overlay:
        add_grid_overlay_clip(media_pool, source_item, base_start_frame, clip_frames, next_new_track)


# ============================= INTERFACE =============================
ui = fusion.UIManager
dispatcher = bmd.UIDispatcher(ui)


def open_pattern_editor(grid_rows, grid_cols):
    """Fenetre de dessin : une case numerique par cellule. Meme numero =
    apparition simultanee. Remplit CUSTOM_PATTERN."""
    rows_ui = []
    for r in range(grid_rows):
        row_fields = []
        for c in range(grid_cols):
            existing = CUSTOM_PATTERN.get((r, c), r * grid_cols + c + 1)
            row_fields.append(ui.SpinBox({
                "ID": f"Cell_{r}_{c}",
                "Value": existing,
                "Minimum": 1,
                "Maximum": 999,
            }))
        rows_ui.append(ui.HGroup({"Spacing": 4}, row_fields))

    editor = dispatcher.AddWindow(
        {
            "ID": "PatternEditorWin",
            "WindowTitle": "Dessiner le motif (meme numero = simultane)",
            "Geometry": [260, 260, 90 * grid_cols + 60, 46 * grid_rows + 110],
        },
        [
            ui.VGroup({"Spacing": 6}, rows_ui + [
                ui.VGap(8),
                ui.Button({"ID": "PatternOkBtn", "Text": "Valider le motif"}),
            ])
        ],
    )
    editor_items = editor.GetItems()

    def on_editor_close(ev):
        dispatcher.ExitLoop()

    def on_pattern_ok(ev):
        CUSTOM_PATTERN.clear()
        for r in range(grid_rows):
            for c in range(grid_cols):
                CUSTOM_PATTERN[(r, c)] = int(editor_items[f"Cell_{r}_{c}"].Value)
        print(f"Motif personnalise enregistre ({grid_rows}x{grid_cols}).")
        editor.Hide()
        dispatcher.ExitLoop()

    editor.On.PatternEditorWin.Close = on_editor_close
    editor.On.PatternOkBtn.Clicked = on_pattern_ok

    editor.Show()
    dispatcher.RunLoop()
    editor.Hide()


win = dispatcher.AddWindow(
    {
        "ID": "GridMosaicWin",
        "WindowTitle": "Generateur de grille mosaique",
        "Geometry": [200, 200, 380, 470],
    },
    [
        ui.VGroup(
            {"Spacing": 10},
            [
                ui.HGroup({}, [
                    ui.Label({"Text": "Lignes", "Weight": 0.5}),
                    ui.SpinBox({"ID": "Rows", "Value": DEFAULT_ROWS, "Minimum": 1, "Maximum": 20}),
                ]),
                ui.HGroup({}, [
                    ui.Label({"Text": "Colonnes", "Weight": 0.5}),
                    ui.SpinBox({"ID": "Cols", "Value": DEFAULT_COLS, "Minimum": 1, "Maximum": 20}),
                ]),
                ui.HGroup({}, [
                    ui.Label({"Text": "Stagger (frames)", "Weight": 0.5}),
                    ui.SpinBox({"ID": "Stagger", "Value": DEFAULT_STAGGER_FRAMES, "Minimum": 0, "Maximum": 200}),
                ]),
                ui.HGroup({}, [
                    ui.Label({"Text": "Motif", "Weight": 0.5}),
                    ui.ComboBox({"ID": "Pattern"}),
                ]),
                ui.Button({"ID": "DrawBtn", "Text": "Dessiner le motif..."}),
                ui.CheckBox({"ID": "Flash", "Text": "Ajouter le flash Fusion", "Checked": DEFAULT_ADD_FLASH}),
                ui.HGroup({}, [
                    ui.Label({"Text": "Brightness de début", "Weight": 0.5}),
                    ui.ComboBox({"ID": "FlashStart"}),
                ]),
                ui.HGroup({}, [
                    ui.Label({"Text": "Durée du flash (frames)", "Weight": 0.5}),
                    ui.SpinBox({"ID": "FlashFrames", "Value": DEFAULT_FLASH_FRAMES, "Minimum": 1, "Maximum": 200}),
                ]),
                ui.CheckBox({"ID": "GridOverlay", "Text": "Ajouter un calque de grille (expérimental)", "Checked": DEFAULT_ADD_GRID_OVERLAY}),
                ui.VGap(8),
                ui.Button({"ID": "GenerateBtn", "Text": "Generer la grille"}),
            ],
        )
    ],
)

items = win.GetItems()

for p in PATTERNS:
    items["Pattern"].AddItem(p)
items["Pattern"].CurrentIndex = 0

items["FlashStart"].AddItem("-1")
items["FlashStart"].AddItem("1")
items["FlashStart"].CurrentIndex = 0


def on_close(ev):
    dispatcher.ExitLoop()


def on_draw(ev):
    rows = int(items["Rows"].Value)
    cols = int(items["Cols"].Value)
    win.Hide()
    try:
        open_pattern_editor(rows, cols)
    except Exception as e:
        print(f"Erreur (editeur de motif) : {e}")
    # bascule automatiquement sur le motif personnalise
    items["Pattern"].CurrentIndex = PATTERNS.index("Personnalise (dessine)")
    win.Show()


def on_generate(ev):
    rows = int(items["Rows"].Value)
    cols = int(items["Cols"].Value)
    stagger = int(items["Stagger"].Value)
    flash = items["Flash"].Checked
    grid_overlay = items["GridOverlay"].Checked
    pattern_name = items["Pattern"].CurrentText
    flash_start_brightness = float(items["FlashStart"].CurrentText)
    flash_end_frame = int(items["FlashFrames"].Value)
    win.Hide()
    try:
        generate_grid(rows, cols, stagger, flash, grid_overlay, pattern_name,
                      flash_start_brightness, flash_end_frame)
    except Exception as e:
        print(f"Erreur : {e}")
    dispatcher.ExitLoop()


win.On.GridMosaicWin.Close = on_close
win.On.DrawBtn.Clicked = on_draw
win.On.GenerateBtn.Clicked = on_generate

win.Show()
dispatcher.RunLoop()
win.Hide()
