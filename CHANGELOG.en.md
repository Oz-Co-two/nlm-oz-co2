# Changelog (Non-Linear Mapper, Oz-Co2 edition)

The main changes from the original Non-Linear Mapper by helba, newest version first.
For basic usage, see the [tutorial](docs/tutorial.en.md), the [advanced tutorial](docs/tutorial-advanced.en.md) and the original manual.

日本語: [CHANGELOG.md](CHANGELOG.md)

<!-- Format: one "## v1.2.3-oz" heading per version. Top-level bold items ("- **...**") are the headlines shown in the in-app
update notice (tools/make_release.py puts them into update.json). Keep the same versions and the same number of headlines as CHANGELOG.md. -->

## v1.4.1-oz

- **Fixed text that was not translated in the English UI**
  Text that was still shown in Japanese in the English UI is now in English (the bar count in NLE clips, the action names and buttons in the shortcut editor,
  light behavior names, color palette hints, "Assets" in MEDIA, the duplicate notes indicator, some Preferences items, messages at the bottom of the screen, etc.).
  - When the UI language was switched, the INFO screen nodes and the shortcut lists could keep showing the previous language.
  - In the exe version, the file type names in the file dialogs and the type names of .nlmf / .nlmclip shown in Explorer now follow the UI language.
  - Added an English section to the bundled "はじめにお読みください.txt" (Read me first).
- **Added English versions of the README and the tutorials**
  [README.en.md](README.en.md), [basic tutorial](docs/tutorial.en.md) and [advanced tutorial](docs/tutorial-advanced.en.md). You can switch between Japanese and English at the top of each tutorial.
  The screenshots in the English tutorials show the English UI.

## v1.4.0-oz

- **Added auto lighting**
  Generates basic lights that follow the notes. Use "Auto lighting…" in the File menu, "Auto light" on the LIGHTING toolbar,
  or "💡 Auto lighting…" on a map check item that reports too few lights.
  - The lights are made to satisfy the light items of the map check (insufficient lighting in BS Map Check, R10.A and R7.B in the NLM BL criteria list).
    Only red and blue (vanilla) colors are used.
  - The lights are built from the difficulty with the most notes and the same lights are placed in every difficulty that has content.
    A new light lane is added at the top and the lights go into an "Auto light" clip, so your existing lights are kept
    (where they overlap, delete or mute one of the lanes to choose).
  - Adding to all difficulties can be undone with a single Ctrl+Z.
- **Added cover image fixing**
  When the map check reports that the cover image is not square, too small, or not png/jpg, you can fix it with "🖼 Fix cover image…" on that item.
  - Choose how to make it square: "Crop the center (default) / Stretch / Pad with a border (you can choose the border color)".
    Images smaller than 256×256 are enlarged to 256×256, and formats other than png/jpg are converted to png.
  - The original image file is not changed. The fixed image is used only when exporting and in the map check.
    You can go back to the original image any time with "Stop fixing" on the cover image node of the INFO screen.
- **The Music placement is now applied to the exported song.egg**
  Moving the start of the Music clip in the NLE, or splitting and trimming it, is now applied to the audio of the exported song.egg.
  Previously only the lead-in silence was applied, so the song and the map could be out of sync in the game even though they matched in the editor.
  The song select preview position and the song length used by the map check are calculated from the same placement.
- **Improvements to "Load song data"**
  - BPM changes in the map are now imported as tempo parts. If audio is already loaded, you are asked whether to import them
    (the app cannot tell whether it is the same song or a different one).
  - Note angle offsets, customData and similar values are now kept through to the export (V3 maps only).
  - The added nodes are placed where they do not overlap the existing nodes on the INFO screen. When the INFO screen does not fit right after opening,
    it is zoomed out a little so that the top heading and the buttons of the export node are visible.
- **Added an advanced tutorial** ([docs/tutorial-advanced.md](docs/tutorial-advanced.md), Japanese)
  Explains, chapter by chapter with images, operations that speed up your work, how to use tempo, lights and the INFO screen,
  and the checks before publishing (map check, BL criteria list, estimate difficulty).
- When ffmpeg is not found, the message now suggests `winget install Gyan.FFmpeg` and mentions that NLM must be restarted after installing it
- **Bug fixes**
  - In place mode, jumping to the start, the end or a marker (Ctrl+← / Ctrl+→, the transport bar buttons, etc.) or pressing "." shifted the fixed camera
  - Dragging the head of a chain to the left always pointed it up-left
  - Right after "Load song data", difficulties that were not open were left out of the export and the map check
  - Reopening a project saved with a split or trimmed Music clip lost the split
  - Several Undo (Ctrl+Z) fixes: clips and lanes created automatically when placing or pasting in the 3D view were left behind after Undo /
    pressing Undo quickly in a row could move notes to another clip (or lose them) / moving, renaming and deleting markers could not be undone /
    locks shifted when undoing lane additions or removals / undoing a received difficulty did not restore the clips /
    undoing after choosing the output folder again could change the export destination
  - Cancelling a paste in the 3D view with Esc or right-click left the automatically created clip and an empty Undo step behind.
    Cancelling a light paste needed Esc twice
  - Mirroring did not mirror the note angle offset or the arc's winding direction (clockwise / counter-clockwise)
  - Notes on a locked lane could be overwritten in the 3D view
  - Actions that change nothing (a drag that did not move, a wheel step that did not change the value, clicking the edge of the Music clip, etc.)
    added Undo steps or marked the project as unsaved. Dragging the circle in the color picker added a large number of Undo steps
  - NLE fixes: the split mode (R) position did not snap / moving the Music and clips together stopped short of beat 0 /
    grabbing the Music where it was cut off at the edge of the view trimmed it / the input box for renaming a light clip was misplaced
  - The automatic tempo detection could pick double or half the tempo (e.g. 60 BPM for 120 BPM)
  - With vanilla colors, the light color pie (C key) wrote custom colors (with vanilla it now switches between ①, ② and white)
  - The cover image thumbnail on the INFO screen could stay old after changing the image
  - The notice shown right after loading a song covered the transport bar, so its buttons could not be pressed
  - Exporting without ffmpeg could end in a connection error instead of the message explaining how to install it

## v1.3.0-oz

- **Added "Estimate difficulty" (approximate BeatLeader stars)**
  Open it from "Estimate difficulty (approx. BeatLeader stars)…" in the File menu, or from "★ Estimate difficulty" on the export node of the INFO screen.
  For every exported difficulty it shows the BeatLeader stars (★), the Pass / Tech / Acc ratings, and the stars with speed modifiers (SS / FS / SFS).
  - The calculation needs the add-on plugin [nlm-rating](https://github.com/Oz-Co-two/nlm-rating) (about 19 MB, Windows only).
    It is not bundled with NLM; if you want to use it, press "Install from GitHub" in the panel.
    The downloaded file is checked against the publisher's information (SHA-256) before use. Updates are only checked when you press the button.
  - The values are **approximations** calculated with the source code published by BeatLeader and may differ from the website
    (on 54 ranked maps, 45 had stars within 3%. Acc can come out lower than on BeatLeader).
    This is not an official BeatLeader tool.
  - Difficulties with fewer than 20 notes cannot be rated.
- **In-app updates**
  At startup the app checks GitHub for a new version and, if there is one, shows the headlines of what changed.
  Choose "Update" to download it; the app then restarts to finish the update (your preferences, assets, translations and plugins are kept).
  - The downloaded file is checked against the publisher's information (SHA-256) before use.
  - If you choose "Don't update", you won't be notified at startup again until an even newer version comes out.
    "Check for updates…" in the File menu lets you check and update at any time.
  - The startup check can be turned off with "Check for a new version at startup" in Preferences.
  - The previous version is kept (one generation only) in `_previous_<version>` next to the exe, so you can go back by hand if something goes wrong.
  - This works from v1.3.0-oz on. From v1.2.0-oz or earlier, please update manually this one time.

## v1.2.0-oz

> **One-time step after updating**: when you open an existing project, the export folder is no longer connected automatically
> and a notice appears at the bottom of the screen. Use "Reconnect output folder / cover image" on the export node of the INFO screen
> to select your usual output folder (CustomLevels etc.) again. After selecting it once, it connects automatically as before
> (this comes from the "Security hardening" below).

- **Added "Map check" (BeatLeader criteria)**
  Open it from "Map check (BeatLeader criteria)…" in the File menu, or from "🔍 Map check" on the export node of the INFO screen.
  It checks the exported map with the same rules as [BS Map Check](https://github.com/KivalEvan/BeatSaber-MapCheck),
  which is used in BeatLeader's ranking review. Clicking a beat in the results jumps to that difficulty and position and selects the notes.
  You can keep editing with the panel open and refresh the results with "Check again".
  - The second tab, "**NLM BL criteria list**", is NLM's own checklist that follows the written criteria on the BeatLeader website
    (Ranking Criteria) in their numbered order. Items are grouped into automatic checks, suggested candidates and items to check by eye.
    Its frame and background are teal so it is not mistaken for BS Map Check results (it is only a guide, not an official judgement).
  - The exported Info.dat now writes Shuffle Period as 0 when Shuffle is 0 (to match criterion R1.B.2.
    The game does not use these fields, so gameplay is unchanged).
- **Same-direction warning**
  When you place a note whose direction is within 45° of the previous or next note of the same color, you are warned with a red frame,
  the "SAME DIR" lamp at the top of the screen and a sound. Clicking the lamp jumps to that position. When the note after it ends up
  facing the same way, that later note gets the red frame. Rotating or color-swapping selected notes is checked when you deselect them.
  It can be turned off in Preferences.
- **Converting to a dot note moved to the D key (changed controls)**
  Alt+wheel now only rotates through the 8 arrow directions, without the dot (rotating several selected notes keeps their relative directions).
  To turn selected notes into dot notes, press D. For the brush, D toggles between the dot and the last arrow direction.
- **JD/RT display**
  Next to the BPM field in the header, the app shows the JD (distance from where a note appears to where it disappears),
  the distance to the player position, and the RT (reaction time). They are calculated from BPM, NJS and offset with the game's formula
  (display only; adjust the offset to change them).
- **Security hardening**
  - Fixed an issue where a tampered project file (`.nlmf`) or similar received from someone else could run an embedded script
    just by opening it, which could rewrite files on your PC. Song names and the like are now shown as plain text,
    and a mechanism that blocks embedded scripts (CSP) was added as well.
  - The app can now write only inside output folders you selected yourself in the folder dialog, and only the kinds of files
    an export creates (Info.dat, difficulty files, song.egg, cover image).
  - Closed a path in the internal local server that allowed reading files outside the app folder
    (other websites could never read them; this guards against other programs on the same PC).
  - The startup step that removes the "downloaded from the internet" mark now only touches the app itself (`_internal`)
    (previously it covered the whole folder of the exe, so placing it directly in Downloads also removed the mark from other files).
  - Updated the bundled Python from 3.9 to 3.14 (3.9 is no longer supported;
    the bundled cryptography libraries were also replaced with newer versions).
- **Reorganized wheel controls (changed controls)**
  | | 3D view | 2D views (NLE, Music) |
  |---|---|---|
  | Wheel | Move in time (unchanged) | Move in time (was: zoom) |
  | Ctrl + wheel | Zoom (was: Shift + wheel) | Zoom |
  | Shift + wheel | Chain divisions while a chain is selected (was: Ctrl + wheel) | None |

  When you move in time with the wheel or the ←/→ keys, the 2D views now follow the red cursor even while stopped
  (moving by clicking still leaves the view where it is). Added "Invert 2D view (NLE / Music) wheel scroll" to Preferences
  (separate from the 3D view setting).
- **Previous-note display is easier to read when red and blue land on the same cell**
  Only when the previous red and blue notes are in the same cell, both are drawn smaller and split diagonally (red = top left, blue = bottom right).
- **Added an illustrated tutorial** ([docs/tutorial.md](docs/tutorial.md), Japanese)
  It walks through the basic flow from loading a song and placing notes to exporting and saving.
- **Bug fixes**
  - Fixed chain links being tilted the wrong way (mirrored) in PREVIEW (3D preview)

## v1.1.0-oz

- **Previous-note display (3D view)**
  Helper grids are placed to the left and right of the placement area (red frame in Place mode / yellow frame in Camera-lock mode),
  showing the last placed red and blue notes, with position and direction, semi-transparently. This makes it easier to pick a direction
  that flows from the previous swing. Toggle it with the H key (rebindable) or the checkbox in Preferences.
- **Unsaved lamp and confirmation on exit**
  When there are unsaved changes, the "UNSAVED" lamp at the top of the screen lights up (it turns off if you undo back to the saved state with Ctrl+Z).
  Closing, New, Open or loading a song folder with unsaved changes asks "Save and quit (continue) / Quit (continue) without saving /
  Cancel". Without unsaved changes it proceeds without asking.
- **Song Preview node (the preview section on the song select screen)**
  The setting for the part played on Beat Saber's song select screen moved from the NLE header to the "Song Preview" node on the INFO screen.
  The ▶ Preview button loops that part with fades so you can check it. You can send a marker's position to the start from the marker's right-click menu.
- The version number is shown in the window title (top left) and at the top right of the screen (placed on both sides so a screenshot of either half shows the version)
- Renamed the "jump speed" label to "NJS"
- **Bug fixes**
  - Fixed the song select preview position being off when lead-in silence was used
  - Fixed "New" followed by Save overwriting the original file after opening an .nlmf by double-clicking it
  - Fixed new features being shown in Japanese when an old translation file was in use
- **Security**
  Added a check of where requests come from, because the internal local server could be read and written from other websites.

## v1.0.0-oz

### New features

- **Added a spectrogram (frequency) display**
  When a song is loaded, the whole audio is analyzed and a band showing the strength of each frequency in color
  (black → purple → red → orange → white) is drawn below the waveform in the 2D editor and outside the note area in the 3D view.
  Choruses and quiet parts can be seen at a glance.
- **Tempo parts (tempo changes within a song)**
  Maps that assumed a constant tempo can now have "tempo parts" where the BPM changes at a given beat.
  They are exported as V3 bpmEvents so the tempo really changes in Beat Saber as well. An "Auto-detect all parts" button
  using the existing BPM detection is included.
- **Lead-in silence (ms)**
  Added a field for adding silence at the start of the song. It is reflected in the editor's playback, and on export
  ffmpeg physically writes the silence into the song.egg audio data.
- **song.egg conversion cache**
  The conversion is skipped when the audio is the same as in the last export, so repeated exports are faster.
  There is also a checkbox to force re-conversion.
- **Native connection for the output folder / cover image**
  Because the browser's File System Access API loses its handles when the app restarts, the real absolute paths
  are now saved in the project file and reconnected automatically without a dialog the next time you open it
  (the "Reconnect" button redoes all of them at once).
- Renamed "Edit mode" to "Camera-lock mode" and pulled the view back a little to make it easier to see
- Added a setting to invert the wheel direction (moving in time) in the 3D view
- Added operations that existed but were missing from the shortcut list (split mode R, 4-beat easing
  Shift+Ctrl+arrows, create chain C)
- **Selected notes can be edited with Alt+wheel / F even in Place mode**
  Previously, in Place mode, Alt+wheel (direction) and F (swap color) always applied only to the brush.
  If the note under the cursor is selected, they now apply to the whole selection
  (otherwise only the brush changes, as before).

### Bug fixes

- **Fixed the screen freezing white / the app crashing right after saving**
  It was caused by storing file references (FileSystemHandle) directly in the browser's IndexedDB,
  which crashes natively in the embedded WebView2 environment. That code (including the "recent files" feature)
  was removed and replaced with handling absolute paths through pywebview's native file dialogs.
- Fixed move operations not responding after changing a note's direction with the Alt key (caused by Windows treating Alt
  as a special key)
