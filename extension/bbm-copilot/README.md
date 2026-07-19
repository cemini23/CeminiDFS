# CeminiDFS BBM Copilot

Chrome extension for CeminiDFS Best Ball Mania draft assistance. Read-only panel with manual board sync.

**Total JS: ~250 lines** | No build step | Vanilla JS only | v1.3.4+ supports `app.underdogsports.com` with 2026 board selectors (`player-cell-wrapper`, `[role="grid"]`, etc.) and ancestor-aware scoring

## Installation

1. Open Chrome and navigate to `chrome://extensions/`
2. Enable "Developer mode" (toggle in top-right)
3. Click "Load unpacked"
4. Select the `/Users/claudiobarone/Projects/CeminiDFS/extension/bbm-copilot/` folder

Note: Icon files are transparent placeholders - replace with actual BBM-themed icons if desired.

## Usage

1. Start the CeminiDFS backend:
   ```bash
   cemini bbm serve --slot <N>
   ```

2. Open the extension popup (click the icon in Chrome toolbar)
3. Enter your draft ID and click Save
4. Navigate to your Underdog BBM draft
5. The floating panel appears top-right
6. Click "Scan Board" to sync available players (manual only)
7. View top-3 recommendations (auto-refreshes every 3s when panel open)

## Features

- **Draggable panel** - grab the header to move anywhere
- **Read-only** - no auto-picks, no clicks on Underdog
- **Manual sync** - "Scan Board" button queries the DOM for player names
- **Record pick** - "Rec" on each recommendation POSTs to `/api/pick` (ledger only; you still click Underdog)
- **Auto-polling** - recommendations refresh every 3 seconds
- **Dark compact UI** - matches draft assistant aesthetics

## Terms of Service

This extension is a **read-only informational tool**. It does not:
- Automatically draft players
- Click buttons on Underdog Fantasy
- Violate any site Terms of Service

All actions require manual user interaction.

## Credits

Panel architecture and UX pattern forked from [draft-co-pilot](https://github.com/howrealizdat/draft-co-pilot) - thank you for the excellent vanilla JS draggable panel implementation.

## Development

No build step required. Pure vanilla JS, CSS, HTML.

To modify:
1. Edit files directly
2. Click the refresh icon in `chrome://extensions/` for the extension
3. Reload the Underdog page
