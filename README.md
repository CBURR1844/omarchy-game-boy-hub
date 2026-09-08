# Game Boy Hub

A native Omarchy bar plugin for GB, GBC and GBA games, powered by mGBA.
Click the controller icon beside Tailscale. Select a game and click Play, or
double-click a game. Right-click the icon to open mGBA directly.

## Requirements

- Omarchy with the Quattro shell plugin system.
- Python 3 (included with Omarchy).
- `mgba-qt`, installed with `omarchy pkg add mgba-qt`.

## Install

```bash
omarchy plugin add https://github.com/CBURR1844/omarchy-game-boy-hub --enable
```

The plugin does not include ROMs, firmware, saves, cheats, or ROM patches.
Supply only game files that you are permitted to use.

## Library

- Search games by title or system; star favorites and use the Recent filter.
- ROMs: `~/Games/Game Boy/ROMs`. Add more folders from the panel.
- Saves: `~/Games/Game Boy/Saves`, with separate directories for each ROM and patch.
- Screenshots: `~/Games/Game Boy/Screenshots`.
- Settings: `~/.config/game-boy-hub/library.json`.
- Emulator startup log: `~/.local/state/game-boy-hub/emulator.log`.

Place additional `.gba`, `.gb`, `.gbc`, `.zip` or `.7z` files in a library
folder and reopen the panel or click refresh. ZIP archives containing multiple
ROMs must be extracted into a library folder to select individual games;
the Setup tab reports archives that could not be indexed. ZIPs with one ROM
are listed under the ROM's actual name. 7z archives are handed to mGBA.

## Gameplay

| Action | Default key |
| --- | --- |
| Direction pad | Arrow keys |
| A / B | X / Z |
| L / R | A / S |
| Start / Select | Enter / Backspace |
| Hold fast-forward | Tab |
| Toggle fast-forward | Shift+Tab |
| Hold rewind | Backtick (`) |
| Pause | Ctrl+P |
| Save state, slots 1–9 | Shift+F1 through Shift+F9 |
| Load state, slots 1–9 | F1 through F9 |

These keys apply while the emulator window has focus. Map a controller or
change shortcuts in **Tools → Settings**.

Setup offers 2×, 4×, 8× and unlimited fast-forward, rewind, and fullscreen
startup. Default: 4× fast-forward, rewind on, windowed. These preferences
apply on the next launch. For a running game, use **Emulation → Fast forward
speed**. Rewind keeps a finite history (600 snapshots), not a full playthrough.

## Cheats and ROM hacks

Select a game and click **Find cheats**, or use the **Cheats** tab. The finder
computes the ROM's SHA-1 locally, identifies its title using the No-Intro
metadata in Libretro's public database, then suggests cheat lists with matching
title, region and revision. ROM contents are never uploaded. The identity is
an exact ROM match; the cheat-list match is based on its published name, so it
does not guarantee that every code works.

Choose a list, search for the codes you want, select them, and click **Import
selected**. On the next launch from the Hub, they appear under **Tools → Cheats**,
all initially off. Enable only the desired codes there. For a game already
running, use the Load button in its Cheats window to open the exported `.cheats`
file shown by the Hub. Imports are staged in `~/Games/Game Boy/Cheats/Imported`.

Existing cheat files are backed up before a new import is applied. After that,
the Hub preserves the edits and enabled states saved by mGBA. Re-importing
replaces the list on next launch; the previous list remains in its `.backup-*`
file. Imports for base games and patched games are kept separate.

Matching `.cheats` and `.cht` files beside the ROM, inside its save folder, or
under `~/Games/Game Boy/Cheats` also appear in Find cheats. Native `.cheats`
files beside a ROM are picked up automatically on launch if it has no existing
cheat file. Libretro and mGBA lists can be previewed and converted; incomplete
codes, placeholder values and RetroArch-specific memory cheats are omitted.

The database downloads only when needed and is cached for offline reuse under
`~/.local/state/game-boy-hub/cheat-cache`. Unknown ROM checksums and attached ROM
patches do not receive online base-game matches. Extract 7z archives first for
checksum matching. Local files remain detectable if the database is unreachable.

In mGBA, open **Tools → Cheats** to add codes matching the game and revision.
Cheats are saved and loaded automatically in that game's save directory.

For IPS, UPS or BPS patches, select the base game in the panel, click
**Patch…**, select the patch, then **Play**. The original ROM is unchanged;
mGBA applies the patch at launch. **Clear** returns to the base game and its
original save directory. A patch needs the exact ROM revision it was made for.
An already-patched `.gba` file can be played directly as a separate game.

Keep a chosen patch at its configured path. Different patch paths get
separate saves. Existing `.sav` and `.cht` files beside a base ROM are copied
to its save directory only if the destination does not already exist.
To import a save manually, close the game first and use its folder under Saves.

mGBA also supplies recording, screenshots, controller mapping, sensors and
local multiplayer. Feature availability varies by system/game. Network link
play, achievements and universal ROM compatibility are not promised by this
plugin. See https://github.com/mgba-emu/mgba for the emulator's feature list.

## Removal

```bash
omarchy plugin remove bam1844.game-boy --yes
```

Removal deletes the plugin checkout. It preserves ROMs, saves, screenshots,
cheats, patches, and settings under `~/Games/Game Boy`,
`~/.config/game-boy-hub`, and `~/.local/state/game-boy-hub`.

To hide the widget without removing it, run
`omarchy plugin disable bam1844.game-boy`.

## Data and network access

The plugin runs locally and starts `mgba-qt` only when you launch a game. It
writes library settings under `~/.config/game-boy-hub` and game data under
`~/Games/Game Boy`. It never modifies or deletes ROMs. Removing a folder in
the UI only removes that path from the library settings.

Find cheats makes on-demand HTTPS requests to GitHub's API and raw content
service for the public Libretro database. It hashes the selected ROM locally;
ROM contents and saves are never uploaded. The downloaded index and selected
lists are cached under `~/.local/state/game-boy-hub/cheat-cache`.

## Development

Validate the manifest and run the Python tests:

```bash
omarchy plugin validate .
python3 -m unittest discover -s tests -v
```

Game Boy Hub is available under the MIT License. See [LICENSE](LICENSE).
