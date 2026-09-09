"""
Genere un effet mosaique/grille (N x M tuiles) a partir d'un seul clip video :
duplique le clip sur plusieurs pistes, applique un Crop different sur chacune
pour isoler la portion de l'image qui lui correspond (facon reveal Instagram),
et ajoute en option un flash Fusion (Brightness/Contrast) par tuile.

La tuile en haut a gauche reutilise directement le clip source deja present sur
la timeline (pas de duplicata inutile). Les tuiles suivantes sont generees en
balayage haut -> bas puis gauche -> droite, et chacune a son point d'entree
source avance de i x stagger frames pour rester synchronisee avec le decalage
de son apparition sur la timeline.

Une petite interface demande la taille de la grille avant de lancer.

A executer depuis la console Python de Resolve (Workspace > Console > Py3)
ou depuis le menu Workspace > Scripts.
Necessite DaVinci Resolve Studio (l'API de scripting n'est pas dispo en version gratuite).
"""

import random

# Pas d'autre import necessaire : "resolve", "fusion" et "bmd" sont deja definis
# dans le contexte de la Console Resolve, du menu Workspace > Scripts, ou des
# render scripts.

# ============ CONFIG PAR DEFAUT (repris dans l'UI, modifiable a chaque lancement) ============
DEFAULT_ROWS = 4
DEFAULT_COLS = 4
DEFAULT_STAGGER_FRAMES = 4       # decalage en frames entre chaque tuile (0 = reveal instantane)
DEFAULT_ADD_FLASH = True         # ajoute un node Brightness/Contrast (Fusion) sur chaque tuile
DEFAULT_ADD_GRID_OVERLAY = False # ajoute un calque de dessus avec les lignes de la grille (experimental)
DEFAULT_RANDOMIZE_ORDER = False  # ordre d'apparition aleatoire au lieu de haut->bas, gauche->droite

CLIP_NAME = None                 # nom exact du clip dans le Media Pool ; None = clip selectionne
CROP_NORMALIZED = False          # False: Crop attend des pixels (cf. panneau Inspector) ; True: fraction 0-1
FLASH_START_FRAME = 0            # frame du clip ou Brightness = FLASH_START_BRIGHTNESS
FLASH_END_FRAME = 4              # frame du clip ou Brightness = FLASH_END_BRIGHTNESS
FLASH_END_BRIGHTNESS = 0.0       # 0.0 = noir, fixe
# ===============================================================================================


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
    """Retourne (mediaPoolItem, originalTimelineItem_ou_None).
    originalTimelineItem n'est renseigne que si le clip vient d'une selection
    sur la timeline : on pourra alors le reutiliser comme tuile (0,0) au lieu
    d'en dupliquer une copie."""
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
        "Impossible de resoudre le clip source. "
        "Selectionne le clip sur la timeline OU dans le Media Pool avant de lancer, "
        "ou renseigne CLIP_NAME."
    )


def apply_crop_and_flash(item, r, c, grid_rows, grid_cols, timeline_width, timeline_height, add_flash, flash_start_brightness):
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
        print(f"Flash ignore sur la tuile ({r},{c}) : Fusion comp non cree (echec connu de l'API).")
        return

    media_in = comp.FindTool("MediaIn1")
    media_out = comp.FindTool("MediaOut1")
    if not media_in or not media_out:
        for tool in comp.GetToolList().values():
            tool_id = tool.ID
            if tool_id == "MediaIn" and not media_in:
                media_in = tool
            elif tool_id == "MediaOut" and not media_out:
                media_out = tool

    if not media_in or not media_out:
        print(f"Flash ignore sur la tuile ({r},{c}) : MediaIn/MediaOut introuvables dans le comp.")
        return

    bc = comp.AddTool("BrightnessContrast")
    bc.Input = media_in.Output
    media_out.Input = bc.Output
    bc.Brightness = comp.AddTool("BezierSpline")  # active l'animation sur ce paramètre
    bc.Brightness[FLASH_START_FRAME] = flash_start_brightness
    bc.Brightness[FLASH_END_FRAME] = FLASH_END_BRIGHTNESS


def add_grid_overlay_clip(media_pool, source_item, grid_rows, grid_cols,
                           base_start_frame, clip_frames, track_index):
    """Ajoute un calque au-dessus de la grille avec un node Fusion 'Grid' pour
    dessiner les lignes de separation. ATTENTION : les noms d'input exacts du
    tool 'Grid' n'ont pas ete verifies (contrairement au reste du script) -
    le node est cree et branche, mais ses parametres sont affiches en console
    pour etre regles ensuite plutot que devines a l'aveugle."""
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
        print("Impossible de creer le comp Fusion pour la grille (echec connu de l'API).")
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
        print("Le node 'Grid' n'a pas pu etre cree - le nom exact du tool reste a confirmer.")
        return

    media_out.Input = grid_tool.Output

    # A confirmer ensemble avant de regler ces valeurs : nombre de lignes,
    # epaisseur, couleur. Une fois les vrais noms connus (via le print
    # ci-dessous), on les fixera ici avec grid_tool.SetInput(nom, valeur).
    print(f"Calque de grille cree (piste {track_index}). Inputs disponibles sur le node 'Grid' :")
    try:
        print(list(grid_tool.GetInputList()))
    except Exception as e:
        print(f"(impossible de lister les inputs : {e})")


def generate_grid(grid_rows, grid_cols, stagger_frames, add_flash, add_grid_overlay, randomize_order, flash_start_brightness):
    project = resolve.GetProjectManager().GetCurrentProject()
    if not project:
        raise RuntimeError("Aucun projet ouvert.")

    timeline = project.GetCurrentTimeline()
    if not timeline:
        raise RuntimeError("Aucune timeline active.")

    media_pool = project.GetMediaPool()
    source_item, original_item = resolve_source(media_pool, timeline)

    n_tiles = grid_rows * grid_cols
    n_new_duplicates = n_tiles - 1 if original_item else n_tiles
    if add_grid_overlay:
        n_new_duplicates += 1  # une piste de plus pour le calque de grille

    current_tracks = timeline.GetTrackCount("video")
    for _ in range(n_new_duplicates):
        timeline.AddTrack("video")

    clip_frames = int(source_item.GetClipProperty("Frames"))
    timeline_width = int(project.GetSetting("timelineResolutionWidth"))
    timeline_height = int(project.GetSetting("timelineResolutionHeight"))

    # balayage haut -> bas, puis gauche -> droite (ou ordre aleatoire)
    tiles = [(r, c) for r in range(grid_rows) for c in range(grid_cols)]

    if original_item:
        # (0,0) reste toujours en premier : c'est le clip deja sur la timeline,
        # il ne peut pas etre deplace, donc son decalage reste 0 quoi qu'il arrive.
        tiles.remove((0, 0))
        if randomize_order:
            random.shuffle(tiles)
        tiles.insert(0, (0, 0))
    elif randomize_order:
        random.shuffle(tiles)

    base_start_frame = original_item.GetStart() if original_item else timeline.GetStartFrame()

    placed = 0
    next_new_track = current_tracks + 1

    for i, (r, c) in enumerate(tiles):
        record_frame = base_start_frame + i * stagger_frames
        source_start = i * stagger_frames  # avance le point d'entree pour rester synchro avec le decalage

        if i == 0 and original_item:
            # reutilise le clip deja present sur la timeline, recadre sur place
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

        apply_crop_and_flash(item, r, c, grid_rows, grid_cols, timeline_width, timeline_height, add_flash, flash_start_brightness)
        placed += 1

    print(f"{placed}/{n_tiles} tuiles placees - grille {grid_rows}x{grid_cols}, stagger={stagger_frames}f.")

    if add_grid_overlay:
        add_grid_overlay_clip(media_pool, source_item, grid_rows, grid_cols,
                               base_start_frame, clip_frames, next_new_track)


# ============================= INTERFACE =============================
ui = fusion.UIManager
dispatcher = bmd.UIDispatcher(ui)

win = dispatcher.AddWindow(
    {
        "ID": "GridMosaicWin",
        "WindowTitle": "Generateur de grille mosaique",
        "Geometry": [200, 200, 340, 380],
    },
    [
        ui.VGroup(
            {"Spacing": 12},
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
                ui.CheckBox({"ID": "Flash", "Text": "Ajouter le flash Fusion", "Checked": DEFAULT_ADD_FLASH}),
                ui.HGroup({}, [
                    ui.Label({"Text": "Brightness de début", "Weight": 0.5}),
                    ui.ComboBox({"ID": "FlashStart"}),
                ]),
                ui.CheckBox({"ID": "GridOverlay", "Text": "Ajouter un calque de grille (expérimental)", "Checked": DEFAULT_ADD_GRID_OVERLAY}),
                ui.CheckBox({"ID": "Randomize", "Text": "Ordre d'apparition aléatoire", "Checked": DEFAULT_RANDOMIZE_ORDER}),
                ui.VGap(10),
                ui.Button({"ID": "GenerateBtn", "Text": "Generer la grille"}),
            ],
        )
    ],
)

items = win.GetItems()
items["FlashStart"].AddItem("-1")
items["FlashStart"].AddItem("1")
items["FlashStart"].CurrentIndex = 0  # -1 par defaut


def on_close(ev):
    dispatcher.ExitLoop()


def on_generate(ev):
    rows = int(items["Rows"].Value)
    cols = int(items["Cols"].Value)
    stagger = int(items["Stagger"].Value)
    flash = items["Flash"].Checked
    grid_overlay = items["GridOverlay"].Checked
    randomize_order = items["Randomize"].Checked
    flash_start_brightness = float(items["FlashStart"].CurrentText)
    win.Hide()
    try:
        generate_grid(rows, cols, stagger, flash, grid_overlay, randomize_order, flash_start_brightness)
    except Exception as e:
        print(f"Erreur : {e}")
    dispatcher.ExitLoop()


win.On.GridMosaicWin.Close = on_close
win.On.GenerateBtn.Clicked = on_generate

win.Show()
dispatcher.RunLoop()
win.Hide()
