# Trade Time Machine

Local, **read-only** proof of concept for the 2026 Lana Straw **Premier** (ESPN league `1851323`) and **Champeens** (ESPN league `1695026336`) leagues. Use the league and team filters to view either league or both together. It loads completed ESPN trades **from August 30, 2026 onward (Central league time)**, excluding earlier draft-correction transactions. It shows exactly who each team received, and compares the actual fantasy points those acquired players scored in **completed scoring weeks ending after the trade**.

This is a **hypothetical hold** for each individual deal: the received players remain credited to their original recipient for all subsequent eligible weeks, even if that manager later trades them to someone else. The later trade also appears separately as its own hypothetical hold. **The trade week is included once complete even when the trade occurred during that week** (for example, a Thursday evening trade counts that week's final scores). It is labeled in the table because player points could have been scored *before* the trade. Totals across trades therefore overlap and must **not** be added together as manager season totals. Points include bench performances and do not measure actual points earned by a manager, replacement value, lineup changes, playoff odds, or future draft dollars/FAAB included in a deal. No winner is declared.

## Leaderboards

The top of the page ranks trades (top 3 per board, per league under "All leagues") and follows the league/team filters:

- **Biggest swing**: absolute difference between each side's hypothetical-hold totals across all eligible weeks.
- **Most players exchanged**: total players received by both sides (newest first on ties).
- **Fastest regret**: difference in the first eligible week only; `*` marks when that week is the trade week.

Trades without a completed eligible week are left off the points boards. Clicking an entry opens the trade.

## Champeens data source

ESPN's activity feed (`recent_activity`) is members-only, and the configured ESPN account can read Champeens but is not a member. For that league the generator rebuilds trades from accepted-trade records (`mTransactions2`) plus roster history (`mRoster`): players currently on a roster with an acquisition type of `TRADE` at the accepted (or, for trades under league review, the next executed) timestamp, and direct team-to-team roster moves during that scoring period that aren't explained by a waiver or free-agent add. **Players later dropped or traded again can be missing**, and an accepted trade whose players can't be recovered is skipped. The UI labels these trades as reconstructed. Checked against Premier's real feed, this method found every trade with no wrong players; it missed one player each in four trades.

## Live site

Published with GitHub Pages at <https://randall-krauskopf.github.io/trade-time-machine/>. GitHub Pages serves the `docs/` folder of `main`, so every push redeploys it. **The site and `docs/data.json` are public**, so never commit credentials or Discord exports.

## Refresh the snapshot

The generator reuses the ESPN helper library and private `.env` from the `AI-playground` repo (`fantasy-football-league/scripts`). It expects that repo to be checked out next to this one; otherwise set `FF_SCRIPTS_DIR` to the `scripts` folder.

```bash
cd trade-time-machine
../AI-playground/fantasy-football-league/scripts/.venv/bin/python generate.py
git add docs/data.json && git commit -m "Refresh trade snapshot" && git push
```

Credentials are read from `scripts/.env` and **never written** into the snapshot. To preview locally, run `python3 -m http.server 8000 --directory docs` and open <http://localhost:8000/> (opening the file directly cannot fetch JSON).

## Optional Discord receipts

There is no automated Supabase credential in this workspace. If you export the `discord_messages` table as JSON using an authorized, read-only connection, supply an array of rows containing `guild_id`, `channel_id`, `message_id`, `sent_at`, `author_name`, `content` (and optionally `deleted_at`, `author_bot`). A `{ "messages": [...] }` wrapper also works:

```bash
../AI-playground/fantasy-football-league/scripts/.venv/bin/python generate.py \
  --discord-export discord-export.json
```

The importer accepts only the Premier guild/channel allowlist documented in the AI-playground `fantasy-football-league/scripts/README.md`; all other channels (including old Champeens channels), bots, and deleted messages are excluded. Receipts are therefore attached to Premier trades only. It displays at most four messages per trade that mention a traded player's name within **48 hours either side** of the transaction. These are nearby mentions, not necessarily opinions about the trade. Each quote includes author, time, channel and a Discord permalink. The browser renders all user text as plain text, never HTML. `discord-export.json` is ignored by Git. **Because this site is public, a snapshot generated with a Discord export publishes those quotes**; only commit one with league approval.

If you can run SQL against Supabase, a suitable read-only export query is:

```sql
SELECT guild_id, channel_id, message_id, sent_at, author_name, content, deleted_at, author_bot
FROM public.discord_messages
WHERE guild_id = 1160416084235661426
  AND channel_id IN (
    1160416085326188555, 1160416085326188556, 1281464082809098260,
    1160416085326188557, 1278801017726570617
  )
  AND deleted_at IS NULL
  AND sent_at >= '2026-08-28';
```

Export the result as a JSON array into `discord-export.json`; never put database keys or private messages in the file. Without an export, the interface explicitly reports that no Discord messages were imported.

## Checks

```bash
../AI-playground/fantasy-football-league/scripts/.venv/bin/python -m unittest -v test_generate.py
```

The scoring window includes the trade week once completed, but excludes the week currently in progress. Week boundaries assume the NFL season starts on the Thursday after Labor Day (September 10 in 2026); check this assumption if reusing the prototype in a later season. Missing player scores are shown as unavailable, not zero. ESPN `recent_activity` pages are fetched until exhausted; non-trade transactions are ignored.
