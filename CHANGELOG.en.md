# Changelog (Non-Linear Mapper, Oz-Co2 edition)

The main changes from the original Non-Linear Mapper by helba, newest version first.
For basic usage, see the [tutorial](docs/tutorial.md) (Japanese) and the original manual.

日本語: [CHANGELOG.md](CHANGELOG.md)

<!-- Format: one "## v1.2.3-oz" heading per version. Top-level bold items ("- **...**") are the headlines shown in the in-app
update notice (tools/make_release.py puts them into update.json). Keep the same versions and the same number of headlines as CHANGELOG.md. -->

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
