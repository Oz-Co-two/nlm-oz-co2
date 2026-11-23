# Changelog (Non-Linear Mapper, Oz-Co2 edition)

The main changes from the original Non-Linear Mapper by helba, newest version first.
For basic usage, see the [tutorial](docs/tutorial.en.md), the [advanced tutorial](docs/tutorial-advanced.en.md) and the original manual.

日本語: [CHANGELOG.md](CHANGELOG.md)

<!-- Format: one "## v1.2.3-oz" heading per version. Top-level bold items ("- **...**") are the headlines shown in the in-app
update notice (tools/make_release.py puts them into update.json). Keep the same versions and the same number of headlines as CHANGELOG.md. -->

## v2.2.0-oz

- **Added "REPLAY" to the top-left pane (watch your BeatLeader replays inside NLM)**
  Replays you played in Beat Saber after exporting from NLM (the .bsor files saved by the BeatLeader mod) open in the same viewer
  as BeatLeader's web replays (the BL replay app, BeatSaber-Web-Replays). Press Tab over the top-left pane to cycle MEDIA → PREVIEW → REPLAY.
  - The list shows only replays of the song you have open, played on a version exported from NLM (found by song name and mapper name).
    Each row shows the difficulty, date, accuracy, number of misses, practice / failed / quit tags and the modifiers used.
    After playing, come back from Beat Saber and press ↻ to reload the list.
  - Every export keeps a copy of the exported map and song.egg. Even if you edit the map and export again after playing, the replay plays
    with the map you played ("Earlier export" is shown). Versions exported before this version are copied when you open REPLAY,
    if that version is still in the export folder. Replays without a copy are grayed out with "Can't play"
    (NLM does not download maps from BeatSaver or anywhere else).
  - The copies are kept in `replays/` in the same folder as the exe. They are not deleted automatically for now.
  - The replay folder (`UserData\BeatLeader\Replays`) is found automatically from the song folders recorded in MEDIA (BSManager's SharedMaps,
    Beat Saber's CustomLevels) and Steam's default location. If it isn't found, choose it with [Change…] below the list (exe version).
    Replays are only read, never changed.
  - Opening a replay switches NLM to the replay's difficulty (if the project has it).
  - While [Sync] is on, NLM's playback position (NLE and 3D) follows the replay's play, pause and time bar. NLM's ▶, Space, the ruler and ← → also move
    the replay (the replay plays the sound). Quit or failed plays stop at the end of the recording.
  - Turn the mouse wheel over the replay to zoom toward the mouse pointer (1× to 8×).
  - After clicking inside the replay, Tab (switching the pane) and Ctrl shortcuts (save, undo, ...) still work in NLM.
- **Replay scores can be shown on the NLE and the 3D view**
  While [Score] in the REPLAY header is on and the current difficulty matches the replay (Standard plays only), your results are shown on the map.
  - 3D: notes get a ring in the score color. The colors are the same tiers as the BL replay app (115 = 6-color rainbow, 113+ purple, 110+ blue,
    106+ green, 100+ yellow, 99 or less pink). Bad cuts get a thick orange ring, misses a thick red ring (with a large ✕), and bomb hits a thick magenta ring.
    Hover over a note to see its score.
  - NLE: the beat-number strip shows marks for misses ✕, bad cuts ◆, bombs ●, and walls ▬. Click a mark to jump there.
  - Where you edited after playing and no note in the current map matches, no 3D ring is shown and the NLE mark is faded (the counts are in the legend row).
- **The top-left pane header now lists all three screens**
  Instead of the old "MEDIA [TAB] PREVIEW", it shows MEDIA, PREVIEW and REPLAY side by side, with a purple frame around the current one.
  Click another name to switch to it.

## v2.1.2-oz

- **Fixed BeatSaver rejecting exported maps**
  Uploading to BeatSaver failed with "_difficultyBeatmaps[n].`XxxStandard.dat`.lightTranslationEventBoxGroups: Must be present".
  Difficulties made in NLM were missing an item that difficulty .dat files (v3.2.0) must have. NLM now always writes it when exporting.
  - Projects (.nlmf) made with earlier versions are fixed too: just export them again with this version.
- **Map check results now open only the difficulty you're editing**
  This keeps you from mistaking another difficulty's beats for the current one's.
  - The "Same as BS Map Check" and "AutoModder" tabs open only the overall section (song info) and the current difficulty, whose heading gets
    an "Editing" tag. Other difficulties appear as closed headings (the counts are shown; click to open).
  - In the "NLM BL criteria list", findings with beats in another difficulty show only the row (difficulty, text, count); click the row to show the beats.
  - Clicking a beat of another difficulty asks "Switch to … and show it?" before switching. Beats of the current difficulty still jump right away.
  - When you switch difficulties, what is open follows the new current difficulty (re-checking or switching tabs keeps what you opened or closed).
- **Song analysis is faster**
  Calculations that were repeated are now done once. The results are the same as before. For a 3:49 song, analyzing the tempo and structure
  went from about 45 seconds to about 17 seconds.
- **The "Estimate difficulty" plugin nlm-rating v4.1.0 supports BeatLeader's PPv4.1**
  This version follows BeatLeader's PPv4.1 of November 2026 (no NLM update needed: update it from the notice at startup or with "Check for updates" in the panel).
  From now on, the plugin's version follows BeatLeader's PP version (PPv4.1 → 4.1.x).
  - The plugin got bigger, so the size shown in the install guide changed from "about 20 MB" to "about 34 MB".
- **Updated the bundled components**
  Python 3.14.10 (with OpenSSL 3.5.9), pythonnet 3.2.1 and others, including security fixes. Nothing changes in how you use NLM.

## v2.1.1-oz

- **The menus are now split by the flow of your work**
  The items that were all in one "File" menu are now in "File", "Mapping", "Check", "Review" and "Help".
  - File: New, Open, Save, Add folder to MEDIA
  - Mapping: Load music file, Analyze song, Create clips from the analysis and Export section starts as markers (same as the band menu), Auto lighting,
    Export custom song (same as [▶ Export custom song] in INFO; new)
  - Check: Map check (opens the tab you want: same as BS Map Check, NLM BL criteria list, or AutoModder), Estimate difficulty
  - Review: Load, paste, list and export review notes
  - Preferences: like the other menus, it now opens a menu with "Preferences…" (it used to open the settings right away).
  - Help: Tutorial, Advanced tutorial and Changelog (open in your browser), Shortcuts (view and change), Check for updates,
    About NLM (version, license and the versions of installed plugins)
  - The shortcuts shown in the menu now follow the keys you set in Preferences (they used to show the default keys even after you changed them).
- **Installed plugins now tell you about their new versions at startup too**
  If you have installed the "Estimate difficulty" plugin (nlm-rating) or the map check's "AutoModder" plugin (nlm-automodder), NLM checks them
  for new versions right after checking for app updates. When there is one, it shows the changes (the plugin's changelog headlines) in the same
  kind of dialog as app updates.
  - "Update" downloads and installs it. No restart is needed. The previous version is kept, so you can switch back with the version selector in the panel (tab).
  - A version you chose "Don't update" for isn't shown at startup again until a newer one comes out. You can still update later with
    "Check for updates…" in the Help menu or "Check for updates" in the panel.
  - "Check for updates…" in the Help menu also checks installed plugins after the app.
  - Plugins you haven't installed are not checked (NLM doesn't contact GitHub for them). Unchecking "At startup, check for new versions of the app
    and installed plugins" in Preferences turns off both.
- **Fixed old wording staying on screen for people who used an earlier version**
  The exe version copies the UI text (translations) into the lang folder next to the exe the first time it starts, so when a later version
  reworded an existing item, people who had used NLM before kept seeing the old wording (new items were shown fine). Now, if the copied text is
  exactly an earlier version's wording, the current wording is shown. Text you edited yourself in the lang folder is still shown as you wrote it.
- **Updated the "Estimate difficulty" note for BeatLeader's October reweight**
  The nlm-rating plugin v0.2.0 supports BeatLeader's October 2026 reweight (no NLM update needed: update it with "Check for updates" in the panel).
  BeatLeader adjusts each map's Acc from players' scores, so the panel's note no longer says "Acc can come out lower".
  - Fixed the panel's "Check for updates" button wrapping onto three lines when two or more plugin versions are installed (when the version selector is shown).

## v2.1.0-oz

- **NLM can now load ranking review notes and help you check them one by one on the map**
  Review notes in the "beat - text" form (a .txt file or the text of a Discord message), such as the ones you receive in BeatLeader's ranking review,
  can be loaded with "Load review notes…" or "Paste review notes…" in the File menu.
  - The notes are listed in the "📝 Review notes" panel by difficulty, in the order they were written. Click a row to switch to that difficulty
    and jump to that beat with the notes there selected (if nothing is exactly on that beat, the nearest objects are selected).
  - The NLE's beat ruler shows a mark (▼) where there are notes. Click a mark to go to that note in the list.
  - Mark notes you have fixed as "done", and add a reply to each note. The loaded notes, done marks and replies are saved in the project, and Ctrl+Z undoes changes.
  - "Export…" writes the notes with your replies as a .txt in the same form (to send back to the reviewer). It can also write the results of NLM's map check
    (the NLM BL criteria list and more) as an English .txt in the same form (AutoModder's "Import Mod" can read it too). Copy it to the clipboard or save it to the output folder.
  - For difficulties whose beats were converted by "📥 Load song data" (see the "Load song data" item below), the beats in the notes are read as the original map's beats
    and converted to NLM's beats.
  - The size of the list text (11–20 px) can be changed with the "Aa" slider at the left of the count row, or with Ctrl+wheel over the list.
- **The map check has a new "AutoModder" tab (an optional add-on plugin)**
  It runs the automatic checks of AutoModder (a ChroMapper extension that reviewers often use) unchanged inside NLM and shows the results.
  - To use it, install the add-on plugin nlm-automodder (about 12 MB, for Windows) with "📥 Install the plugin…" in the tab
    (NLM connects to GitHub only when you press the install or update-check button).
  - The results are listed for the song info (Info.dat) and each difficulty, most severe first (Error (Unrankable), Warning (Questionable) and so on). Click a beat to jump there.
  - Each difficulty is checked with AutoModder's default settings. AutoModder differs from the current BeatLeader criteria in places (the R5.A vision block formula,
    the wall dodge rate and so on). It is not an official BeatLeader or AutoModder tool, and the results are not ranking decisions.
    The tab has an amber border so that it isn't mistaken for BS Map Check or the NLM BL criteria list.
  - AutoModder uses the song length, so load the audio before checking.
- **v4 maps can now be loaded**
  Songs in the newer format (Info.dat 4.x) can now be put into the NLE by dragging them from MEDIA or with "📥 Load song data" (before, they could only be listed and their audio placed).
  - The tempo is read from AudioData.dat. For lights, the basic lights and boosts are read.
  - NLM still exports in the v3 format. "NJS events", which v3 doesn't have, and "light boxes", which NLM can't read, are lost on export.
    NLM tells you at the bottom of the screen when loading and when exporting.
  - The NJS events are still used by the NLM BL criteria list.
- **Far fewer false findings in the NLM BL criteria list**
  We checked it against 189 BeatLeader ranked maps and fixed the places where maps that passed the review were reported as violations.
  The share of difficulties with no violation went from about 80% to 99%.
  - The angle offset of notes (the fine angle) was calculated in the wrong direction, and fast streams merged separate swings into one (R4.B.1, R4.B.2). Both are fixed.
    Notes of the same color that are slightly off (less than 1 ms) only because of rounding when saved are now treated as placed at the same time.
  - Chains: a zero-length chain is no longer treated as reversed (R6.B.1), the curve is judged by the direction from the head position to each link (R6.B.2, R6.B.3),
    and tiny overhangs from calculation rounding (up to 0.1 cell) are no longer violations (R6.C.2).
  - R3.B (blocked swing start) now only reports objects that are still there when you swing (within 40 ms) (it used to appear in 84% of the ranked difficulties; now 2%).
  - R7.B (bomb lighting) now judges the same way as the reviewers' tool (AutoModder). Brief dark moments of flashing lights no longer trigger it
    (needs review went from 38% to 7% of the ranked difficulties).
  - R8.A (wall dodges) uses the current criteria's numbers (250 ms to dodge, 235 ms as an exception; 2, 3.8 and 4 dodges per second).
    Whether your head really has to move is approximated, so going over the limits is reported as needs review, not as a violation.
  - R8.C (short walls) ignores decorative walls that are entirely outside the four lanes. Objects inside a time skip (the BPM briefly set very high)
    are reported as needs review instead of violations in R8.C and R3.A.1 (overlaps).
  - R4.A.6 (chain length) no longer counts almost-simultaneous shapes as sliders, and doesn't compare when there are no sliders or too few (fewer than 3).
  - For difficulties whose original map had light boxes, the lighting checks (R10.A, R7.B) become manual checks, because NLM can't read those lights.
- **Fixed timing offsets and missing parts when bringing in other people's maps with "📥 Load song data"**
  - Maps whose BPM changes at the very start (beat 0), maps whose BPM changes differ between difficulties, and v2-format BPM changes (event type 100)
    are now loaded with the correct tempo (before, the notes could drift from the music). For maps whose BPM changes differ between difficulties, NLM uses the tempo
    shared by the most difficulties and converts the beats of the other difficulties so that their timing stays the same (it tells you which difficulties were converted).
  - The environment (stage) of the loaded map is now carried over to the export (it used to become Default; if a song is already loaded, the current environment stays).
    If the environment is not available in the 3D preview, ⚠ appears next to the environment name at the top of the screen and the preview shows Default
    (the export keeps the original environment).
  - v3 maps written with zero values left out could break the 3D view and editing, and export arc tails with the head's direction. Fixed.
  - When a map has light boxes (the newer lighting system introduced in v3) or difficulties other than Standard (such as OneSaber, which NLM doesn't load),
    NLM now tells you instead of dropping them silently. Light boxes can't be edited in NLM and are lost on export.
  - Boosts (light color switching) in v3 maps are now loaded (before, they were not loaded and were lost on export).
- **Maps with a huge number of lights no longer freeze NLM after loading**
  Loading a map with around 100,000 lights used to make the screen sluggish, as if frozen, from then on. Fixed (it is ready in a few seconds).
  - While loading, NLM shows the progress, such as "Loading audio…" and "Loading map… Hard (1/3)".
  - When all difficulties together have 150,000 lights or more, NLM tells you once, when opening or loading ("This project has N lights in total"),
    because editing may pause for a moment now and then while checking for unsaved changes.
- **Bug fixes**
  - In the English UI, the node name in the message shown when adding a node in INFO was still in Japanese. Fixed.
  - After saving, just switching difficulties (with the difficulty buttons, the number keys or a beat in the map check) turned on the "unsaved" lamp
    and asked for confirmation when closing, even though nothing had changed. Fixed.
  - When exporting in the v3 format, boosts (light color switching) are now written to the place v3 defines for them (colorBoostBeatmapEvents)
    (before, they were written in a way v3 no longer uses, so they might not work as boosts in the game).
  - After opening an empty difficulty, moving to another difficulty and opening it again, notes and lights could not be placed
    (the message said "... wiring is disconnected"). Fixed.
  - After opening a project with a cover image and then opening another project, the previous cover image could stay in the bottom-right corner. Fixed.
    When the next project had no cover image, or after New, the previous cover image was used for export and the map check, and saving put it into that project.
  - Export failed with "Failed to copy cover image" for a cover restored from the image stored in the project (when the original image file was not found)
    and for a cover placed from MEDIA together with the song info. Fixed.
  - After opening another project or starting a new one, the previous project's output folder could stay "ready", so exports and saved review .txt files
    went into that folder. Fixed. If the opened project's output folder has been chosen on this PC before, it still connects automatically;
    otherwise "Reconnect" is shown.

## v2.0.0-oz

- **NLM can now analyze a song to suggest the BPM and lead-in silence, and to show its structure (verse, chorus, ...)**
  Choose "Analyze song (tempo & structure)…" in the File menu (or "🎼 Analyze song" to the left of the NLE spectrogram). NLM estimates the tempo and suggests a BPM
  and a lead-in silence. If they differ from your current settings, a confirmation window opens; click "Apply suggestion" to use them (Ctrl+Z undoes it).
  - The window also tells you that double or half the BPM follows the same beat, offers candidate B (the lead-in silence shifted by half a beat) when the strong beats
    may be off-beats, points out where the beat shifts once in the middle of the song, and warns when the tempo wanders (a live recording, for example)
    so that no single BPM fits.
  - NLM then analyzes the structure and shows the analysis band (Sections / Segments) in the NLE. The upper row shows sections (a tentative name — Intro, Verse, Pre-chorus, Chorus,
    Interlude, Bridge, Outro — and a number; the same number means the same content; ★ marks the chorus candidate), and the lower row shows finer segments.
    Click the band to move there.
  - The names are only a guess from the order of the sections. Double-click the band to rename all sections with the same number at once.
    Right-click → "Export section starts as markers" turns them into timeline markers.
  - The results and your names are saved in the project. If you change the BPM, the lead-in silence, the Music placement and so on, NLM asks you to analyze again.
  - Analysis takes about 30 seconds to a minute per song, and you can keep editing meanwhile (the progress is shown at the left of the band). Formats such as m4a are read with ffmpeg.
  - When you load a song, NLM asks "Analyze this song?" (with a short explanation of what the analysis gives you). When an analysis finishes, it shows what to do next.
    You can turn both off, and turn them back on in Preferences → "Application" → "Song analysis".
  - Because the analysis components are now included in the app, the download zip has grown to about 118 MB (about 290 MB after extracting).
- **New "Edit only" mode: edit just one note lane**
  Turn it on with the switch on the second row of a note lane's left gutter (or press E over the NLE). Notes you place or paste in 3D then go to that lane only,
  and notes on other lanes can't be edited, as if they were locked. Press it again to turn it off.
  - Clicking a note on another lane shows a small band over the 3D view where you can switch Edit only to that lane, turn Edit only off, or keep it as it is
    (the click itself changes nothing). Box selection quietly leaves out objects on other lanes.
  - The Edit only lane is saved in the project (switching it alone does not mark the project as unsaved).
- **Clips with the same content can now be linked (even across difficulties)**
  Select two or more clips in the NLE and right-click → "🔗 Link" (K key) to choose the parent. Only the parent of linked clips can be edited, and the children
  always have the same content as the parent (for example, fix the first chorus and the second and third choruses change with it). Names and colors follow the parent too.
  - You can't place objects in a child clip. Touching a child shows a band where you can "Jump to parent" or "Unlink". A child can only be trimmed at its right end,
    and any part longer than the parent stays empty.
  - "🔗 Paste linked" (Ctrl+Shift+V) pastes copied clips as children. When you paste into another difficulty, you choose "Link" or "Don't link" each time.
  - "Send notes" and the other items in the difficulty button menu (▼) now have "Link to the parent difficulty" (on by default). The copied clips become children
    of the clips in the source difficulty, so fixing a parent changes every linked difficulty. You can unlink just the parts you need later.
    Right-click → "🔗 Link with clips at the same position in other difficulties…" links them afterwards.
  - Linked clips can't be split or joined (unlink them first). If you delete a parent, you choose the next parent from the remaining clips
    ("Cancel" takes you back to before the deletion).
  - Links are saved in the project. Children are saved with their content, so no notes disappear when you open the file in an older version
    (if a child was edited in an older version, NLM removes that link when opening the file and tells you).
- **You can now create empty clips from the analyzed song structure in one go**
  "🧩 Create clips" to the left of the analysis band (also in the band's right-click menu) adds a new notes lane at the top of the NLE and creates empty clips
  that follow the band (named after the band and its number, such as "Verse S2", in the band's colors). The new lane is set to Edit only, so you can start mapping right away.
  - Choose sections, segments, or both (each on its own lane), and choose the difficulties to create them in.
  - Clips with the same number are linked automatically (you can turn this off). The first clip of each number becomes the parent, so mapping the first chorus
    fills the later choruses too. Clips created in other difficulties are linked to the parents in the open difficulty.
  - Existing notes and lanes are not touched. A single Ctrl+Z removes everything that was created.
- **The NLE is easier to use**
  - A new project starts with one note lane and three light lanes (it no longer keeps the number of lanes from the map you had open before).
    "Lane layout (Notes : Lights = 6 total)" in Preferences is now "Note lanes".
  - When there is no free lane where you drop or paste a clip from MEDIA or the assets, NLM adds a lane at the top instead of refusing.
  - A vertical scrollbar was added to the left of the lane names too (it works the same as the one on the right).
  - The spectrogram and the Music waveform no longer flicker when you zoom out and play.
- **Bug fixes**
  - "Send lighting" in the difficulty button menu (▼) also copied empty note clips when sent to a difficulty that hadn't been opened yet
    (and "Send notes" did the same with light clips). This is fixed, and every send can now be undone with a single Ctrl+Z.
  - Moving, splitting or trimming the Music clip left the spectrogram in its old position. Fixed.
  - Opening project files in old formats (such as ones saved with old versions of the original NLM) could lose part of the map. Fixed.
  - Undoing adding or removing a lane left the clips of other difficulties shifted by one lane. Fixed.
  - "📥 Load song data" could put clips on a lane that wasn't shown. Fixed.
  - Clicking a light lane could select a note clip hidden under it. Fixed.

## v1.6.0-oz

- **You can now adjust the song volume (with automatic adjustment)**
  "Vol" and "Auto" were added to the left of the Music row of the NLE (below the word "Music").
  Click "Auto" to measure the song's loudness and raise it toward an average of -9 LUFS (a typical level for Beat Saber custom songs), stopping before the sound
  would clip (songs that are already loud enough are not raised; Auto never lowers the volume). You can also change the volume by hand with ‹› or by typing a value (±20 dB).
  - It applies to playback as-is, and song.egg is exported at the same volume (exporting it needs ffmpeg).
  - The volume is saved in the project and can be undone with Ctrl+Z. It is separate from "Music volume" in Preferences, which only changes what you hear while editing.
- **The window position and size are now remembered for the next start (exe version)**
  NLM remembers the window's position, its size and whether it was maximized when you close it, and opens the same way next time.
  If the window was on a monitor that is no longer connected, it opens in the center of the screen.

## v1.5.0-oz

- **MEDIA now remembers the song folders you added (exe version)**
  Folders you pick with "Add folder" (such as Beat Saber's CustomLevels) are recorded and loaded automatically the next time you start NLM
  (before, you had to add them again after every restart). Even folders with many songs open quickly from the second time, because NLM reuses what it read last time.
  - A folder that cannot be found is shown dimmed and stays recorded. Right-click the folder → "Reload" to read it again. "−" removes it from the record.
  - Songs with a v4 Info.dat now show their title, artist and so on (loading a v4 map into the NLE is not supported yet).
  - Audio you placed from a recorded folder is loaded automatically when you open the project again.
  - NLM only reads the song folders; it never writes to them.
- **MEDIA now has a detail view, sorting, search and filters**
  You can switch between the grid view and the detail view (one row per difficulty). The detail view lists the title, artist, mapper, difficulty, ★, NJS,
  NPS, length, BPM, upload date, download date, play count and more. Click a column heading to sort, and right-click a heading to show or hide columns.
  - Narrow the list with the search box (title, artist, mapper) and "Filter" (ranges of ★, length, NJS, NPS, BPM and upload date; difficulty, mode and
    ranked status; excluding maps that require Noodle/Chroma; favorites only; unplayed only). The number of matching songs and maps is shown.
  - Dragging a row of the detail view to the NLE puts the map of that row's difficulty into the difficulty you have open (you can borrow a map from another difficulty).
  - In the detail view, the size slider changes the text size of the list (Ctrl + wheel over the list also works). Drag the edge of the catalog on the left to change its width.
  - The controls are now on the heading row of MEDIA. The view, columns, sort order and filters are kept for the next time.
  - Fixed: when you dragged items quickly one after another, the next drop was sometimes ignored.
- **MEDIA now shows each song's upload date, rating and ★, and your own play records (exe version)**
  - NLM downloads the song data used by some Beat Saber mods (BeatSaberScrappedData, built from public information of BeatSaver, BeatLeader and ScoreSaber)
    from jsDelivr at most once a day, and shows the upload date, upvote ratio, ranked status, ★ and more. NLM sends nothing. You can turn this off on the new "MEDIA" tab of Preferences.
  - Songs that are not in the song data show "Unmatched 🔍". When you press 🔍 and confirm, NLM sends only that one song's identifier (hash) to BeatSaver to look it up
    (NLM never asks BeatSaver on its own).
  - NLM reads Beat Saber's play records on your PC (PlayerData.dat) and shows the play count, personal best, full combo and favorites for each difficulty (read only).
    You can change the file location on the "MEDIA" tab of Preferences.
  - For songs without ★, right-click rows of the detail view → "Calculate ★ (NLM est.)" to get an approximate ★ with the "Estimate difficulty" plugin.
    It is shown as "NLM est." in a different color (it is not BeatLeader's official ★). The number of songs calculated at the same time can be changed on the "MEDIA" tab of Preferences.
- **The NLM BL criteria list of the map check now fills in ★ and Tech automatically**
  The ★ and Tech fields of R5.A (whether notes are visible long enough to react) are filled in with values calculated by the "Estimate difficulty" plugin
  (before, you typed them in). If the plugin is not installed, you can install it from "📥 Install the plugin and auto-calculate…".
  - Fields you overwrite get a yellow border and are kept when measuring again ("Back to auto" returns to the calculated value).
  - R11.H.5 (whether the difficulties are in ascending order of ★) is now judged with the same ★. Because the values are approximations, an inverted order is shown as "Check", not as a "Violation".
  - Results are shared with the "Estimate difficulty" panel. If the map has not changed since the last measurement, that result is shown without measuring again.
- **The floating shortcut lists now show a title, and fold into a single line with just the title**
  The bar at the top of each list shows which list it is (Standard, NOTES, LIGHTING, NLE, INFO). Press "—" to fold it into a short line with only the title and the buttons
  (before, a folded list left an empty bar of the same width, and you could not tell which list it was).
- **You can now click "[TAB] next view" at the top left of each area to switch views**
  It switches MEDIA ⇄ PREVIEW, NLE ⇄ INFO and NOTES ⇄ LIGHTING, just like the Tab key.

## v1.4.3-oz

- **The on-screen shortcut list now includes missing actions and shows your own keys**
  The shortcut list shown on screen now includes W (placement pie / light behavior pie), Esc (cancel / exit), Enter (confirm paste),
  the arc winding direction (Shift + Alt + wheel), Ctrl + left click in LIGHTING (place on top of a light), and more.
  - If you change a key on the "Shortcuts" tab of Preferences, the list now shows the new key (before, it kept showing the old one).
- **In LIGHTING, the 1, 2 and 3 keys now pick a color**
  With the mouse over the 3D view, 1, 2 and 3 pick ①, ② and white (left, right and white in Chroma mode). The hint shown when you enter
  LIGHTING already said "1·2·3 = color", but pressing the keys did nothing. You can change the keys on the "Shortcuts" tab.
- **Saving no longer asks for permission at the top edge of the screen**
  When you saved over a project opened with "Open…" or by dragging it in, a small prompt asking whether to allow editing the file appeared
  at the top edge of the screen (easy to miss, and saving waited until you answered it). In the exe version, saving to a file you picked
  or dragged in no longer asks.
- **Improved security**
  NLM now better protects you when a file you received from someone else (.nlmf or an audio file) has been tampered with.
  - Just opening a crafted .nlmf could make Windows connect to a network location written in it (`\\server\...`) and send your
    sign-in credentials (NTLM authentication) to that server. NLM now connects to network locations only when you picked the file or folder
    in a dialog on this PC.
  - Because of this, if a project loads its song or cover image from a location like `\\server\...` (for example on a NAS), please select the
    song or cover image again once after updating (not needed if you used a drive letter such as `Z:\`; export folders still reconnect
    automatically as before).
  - Adding a crafted audio file to MEDIA could freeze the editor. This is fixed.
  - A crafted .nlmf could insert unwanted content into the INFO screen. This is fixed.
  - When you use `python serve.py` (on Linux, etc.), open the editor with the URL that includes an access key, shown at startup (it opens
    in your default browser automatically, and the key changes every time the server starts). This keeps other accounts on the same PC and
    other devices on the network from using the local server. Nothing changes for the exe version.

## v1.4.2-oz

- **You can now grab and move the notes at the ends of an arc**
  Clicking a note at the end of an arc now selects the note, not the arc (before, it grabbed the end of the arc and you could not move the note).
  - When you move the note, the connected end of the arc follows it (moving one end bends the arc; moving both ends moves the whole arc). The head note does not go past the tail's beat.
  - When you move an arc, the notes at both ends move with it. To move only one end of the arc, select the arc and use the small arrows at its head and tail
    (while they are shown, the arrows that move the whole arc are drawn larger).
  - When you change a note's direction (Alt + wheel, D, the direction palette), the direction of the connected arc end changes too.
- **Projects now open where you saved them**
  Saving also records the playhead position and the NLE zoom and scroll position, and opening the project restores them. Just moving the playhead or zooming does not mark the project as unsaved.
  - During playback, the NLE now keeps the playhead at the center of the view and scrolls (before, it moved almost to the right edge and hid behind the shortcut list at the top right).
- **Fixed rare problems**
  - Checking for updates and similar actions could rarely fail because the connection was cut off.
  - If the app quit while saving your preferences, the preferences could be lost (they are now written in full before replacing the old file).

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
