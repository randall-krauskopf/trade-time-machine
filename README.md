# Trade Time Machine

Local, **read-only** proof of concept for the 2026 Lana Straw **Premier** (ESPN league `1851323`) and **Champeens** (ESPN league `1695026336`) leagues. Use the league and team filters to view either league or both together. It loads completed ESPN trades **from August 30, 2026 onward (Central league time)**, excluding earlier draft-correction transactions. It shows exactly who each team received, and compares the actual fantasy points those acquired players scored in **completed scoring weeks ending after the trade**.

This is a **hypothetical hold** for each individual deal: the received players remain credited to their original recipient for all subsequent eligible weeks, even if that manager later trades them to someone else. The later trade also appears separately as its own hypothetical hold. **The trade week is included once complete even when the trade occurred during that week** (for example, a Thursday evening trade counts that week's final scores). It is labeled in the table because player points could have been scored *before* the trade. Totals across trades therefore overlap and must **not** be added together as manager season totals. Points include bench performances and do not measure actual points earned by a manager, replacement value, lineup changes, playoff odds, or future draft dollars/FAAB included in a deal. No winner is declared.

## Leaderboards

The top of the page ranks trades (top 3 per board, per league under "All leagues") , always across all trades regardless of the league/team filters:

- **Matchup movers**: total real results flipped by the trade (both sides), then the largest net lineup-point change; the detail shows who gained the most wins.
- **Most players exchanged**: total players received by both sides (newest first on ties).
- **Fastest regret**: difference in the first eligible week only; `*` marks when that week is the trade week.

Trades without a completed eligible week are left off the points boards. Clicking an entry opens the trade, clearing the filters if they would hide it.

## Alternate Universe standings (2026 experiment)

The site has two pages linked from the header: **Trades** (`docs/index.html`: leaderboards, archive, and trade detail) and **Alternate Universe** (`docs/alternate.html`, rendered by `docs/alternate.js`). The Alternate Universe page replays the completed Premier and Champeens matchups. It shows three records and points-for totals per team: **Real** uses the actual ESPN box-score starting lineup; **Current optimal** chooses the best-scoring legal starters from that week's actual roster; **No trades** chooses the best-scoring legal starters after moving known post-August-30 traded players back to the team that first sent them. The optimizer uses the league's active roster slots and each player's ESPN eligibility, assigning a player at most once. Wins/losses/ties use the actual schedule (ties count as half a win). **Δ wins compares No trades with Current optimal**, not with Real, so it separates modeled roster changes from the benefit of optimizing lineups. That page has its own league selector (independent of the Trades page filters), and no data from the current unfinished week is included.

This is **not a reconstructed Aug 30 roster or a prediction**: the model starts from each week's actual box-score roster, keeps actual waiver and free-agent acquisitions (which reset a traded player's baseline ownership), and rewinds only players in recovered trade records. Unrostered players stay out; it does not enforce roster size or model hypothetical cuts, future waiver choices, injuries, lineup locks, or whether an owner would have started the optimal lineup. A midweek transaction can therefore affect that whole scoring week. Champeens' trade reconstruction may miss movements and is labeled accordingly. Do not treat these standings as actual standings or a trade verdict.

## Matchup impact

Each trade's detail panel opens with **matchup impact**, built from ESPN box scores (real lineups) for both leagues:

- **Started vs benched**: points the received players scored in the lineup vs on the bench.
- **No-trade alternate**: received starters are removed, and each vacated slot (dedicated slots before flex) is filled with the eligible bench or traded-away player with the highest ESPN **projection** for that week, so the choice doesn't use hindsight. A traded-away player can also replace a remaining starter projected lower. Actual points are then summed.
- **Re-scored matchup**: the real score and opponent score are compared with the alternate. When the opponent was the trade partner, both sides are re-run. A changed W/L/T is a **flipped result**; **wins added** sums real minus alternate results (W=1, T=0.5, L=0).
- The trade week is only counted if the received players already appear in that week's lineups.

The card says **No results flipped** when none changed. **0 net wins** can instead mean that results *did* flip but gains and losses canceled out; a tie can produce a half-win. Win totals are shown without decimals unless a half-win is involved.

Assumptions: managers don't always start their best players, so the refill is an estimate; unrelated waiver moves and drops aren't undone (all traded-away players are added back); a slot with no eligible replacement scores 0; Champeens reconstruction gaps carry over. It's a what-if, not a verdict.

When a player received in the original exchange is later **traded again by that recipient**, matchup impact for **both original sides** stops at the first such re-trade. The detail names the player and last counted week. A midweek re-trade's week is included only when that player's box-score lineup still belongs to the original recipient and not the new recipient; ambiguous or missing lineups stop at the preceding week. Ordinary waiver moves and lineup changes don't trigger this cutoff. Reconstruction gaps in Champeens can hide a re-trade, so the cutoff can only use trades in the snapshot. **Raw Player Points does not stop**: its hypothetical hold continues independently.

Scoring Week 1 begins the Thursday after Labor Day; subsequent ESPN scoring weeks begin Tuesday in league time, after Monday Night Football. A Tuesday trade therefore cannot count the previous week's raw points or matchup.

The older **raw player points** section (formerly the "hypothetical hold") remains below for context.

## Weekly swing chart

Each trade's detail panel includes a dependency-free SVG bar chart of each side's received-player points per eligible week. The trade week is shaded and marked `*`. A `⇄` marks a week where the **cumulative** leader changed, and the caption summarises who leads. The week table below remains the accessible text version; the chart also has a full `aria-label`.

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
