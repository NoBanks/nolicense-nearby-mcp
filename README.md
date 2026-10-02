# nolicense-nearby-mcp

MCP server for **No License Nearby**, an artist-owned sync licensing catalog of 880+ tracks. The artist owns 100% of
every master and every publishing share, so one license clears the music.

Let Claude, Cursor or any video and editing agent search the catalog, audition tracks, see live license prices and
build a quote, then hand the buyer the pre-filled license page.

Live catalog: https://license.nomusicnearby.com

## No API key needed

All tools are read-only and use the public catalog. This MCP never submits license requests and never takes payment:
buying happens on the No License Nearby website, where you submit a license request and usage rights activate after
payment.

## Install

```bash
pip install nolicense-nearby-mcp
# or run without installing
uvx nolicense-nearby-mcp
```

## Configure

```json
{
  "mcpServers": {
    "nolicense": {
      "command": "uvx",
      "args": ["nolicense-nearby-mcp"]
    }
  }
}
```

Claude Code:

```bash
claude mcp add nolicense -- uvx nolicense-nearby-mcp
```

Optional: `NOLICENSE_API_BASE` (defaults to https://license.nomusicnearby.com).

## Tools

| Tool | What it does | Example prompt |
|---|---|---|
| `search_tracks` | Search by title, genre, mood, energy and musical key (filters combine) | "Find chill electronic tracks under 3 minutes for my vlog." |
| `get_track` | Details for one track | "Tell me about track 660." |
| `get_preview_url` | Audition link for a track | "Let me hear Showerhead." |
| `list_license_tiers` | Live prices: Social Media, TV + Streaming, Film | "What does a film license cost?" |
| `quote_license` | Quote for one or more tracks, including the multi-track discount | "Quote 3 tracks for social media." |
| `get_license_checkout_link` | The license page pre-filled with the track, plus the steps to finish | "I want to license Dat Piano for my film." |

Prices are always read live from the catalog, never hardcoded. Tempo search is not available yet because tempo data
is still being added to the catalog.

## Development

```bash
pip install -e ".[dev]"
pytest
```

## License

MIT
