# Trade Time Machine

Local, **read-only** proof of concept for the 2026 Lana Straw **Premier** (ESPN league `1851323`) and **Champeens** (ESPN league `1695026336`) leagues. Use the league, game-week, and team filters to narrow the Archive. Transaction game weeks turn over at **12:00 AM Central every Tuesday**, after Monday Night Football; the first bucket begins at the August 30 cutoff. It loads completed ESPN trades **from August 30, 2026 onward (Central league time)**, excluding earlier draft-correction transactions. It shows exactly who each team received, and compares the actual fantasy points those acquired players scored in **completed scoring weeks ending after the trade**.

This is a **hypothetical hold** for each individual deal: the received players remain credited to their original recipient for all subsequent eligible weeks, even if that manager later trades them to someone else. The later trade also appears separately as its own hypothetical hold. **The trade week is included once complete even when the trade occurred during that week** (for example, a Thursday evening trade counts that week's final scores). It is labeled in the table because player points could have been scored *before* the trade. Totals across trades therefore overlap and must **not** be added together as manager season totals. Points include bench performances and do not measure actual points earned by a manager, replacement value, lineup changes, playoff odds, or future draft dollars/FAAB included in a deal. No winner is declared.

## Leaderboards

The top of the page ranks trades (top 3 per board, per league under "All leagues") , always across all trades regardless of the league/team filters:

Tied values share the same competition rank (for example, `1, 1, 1`; the next distinct value would be `4`) rather than being assigned an arbitrary order.

- **Most active traders**: managers ranked by the number of completed deals they participated in, using the same inclusive August 30 Central-time cutoff as the archive.
- **Holding Steady**: managers with the fewest completed deals, including managers who have not traded at all (the full team list comes from each league's standings). Because zero-trade ties are common, managers tied on a count share one entry that notes how many are tied, and entries are ranked `1, 2, 3` by distinct trade count.
- **Wins Traded For / Wins Traded Away**: rank managers by the matchup results their combined weekly trades improved or worsened versus the no-weekly-trades alternate. A W counts as 1, a tie as 0.5, and an L as 0; unchanged results do not count. Wins Traded For shows the count as wins and Wins Traded Away as losses (e.g. "0.5 losses" for a W→T). A manager can appear on both boards in different weeks. Rankings link to that manager's Weekly Moves cards.
- **Most players exchanged**: total players received by both sides (newest first on ties).
- **Biggest Roster Swings**: the largest absolute point swings for a manager's completed weekly trade bundle, comparing actual matchup points with the modeled no-weekly-trades lineup. Signed values show whether the manager scored more or fewer points; a matchup result need not change. Each entry links to that specific manager-week on Weekly Moves.
- **Most Traded Player**: players moved in at least two completed deals, with the path of teams they passed through (most trades first, then most recently traded). Each entry opens that player's latest deal on the Archive page.
- **Left on the Bench**: the most points a manager left on the bench in a single completed week, i.e. the best possible lineup from that week's roster (excluding IR) minus the starters' actual points. The detail names the top-scoring bench player. The generator stores these per manager-week under `alternate_standings.weeks[].lineups`; leagues without that data (such as historical snapshots) show an empty board.
- **Biggest Margin of Victory**: the largest actual winning score differences in completed weekly matchups, including managers who made no trades. Each entry shows the winner, opponent, week, and final score; ties are excluded and the same manager can appear for multiple wins. The generator stores all actual matchups under `alternate_standings.weeks[].matchups`; snapshots without this data show an empty board rather than a partial ranking.

When the snapshot has more than one league, each league's leaderboards and charts sit in a collapsible section (open by default); click the league name to collapse or expand it. Weekly rankings include only completed manager-weeks. Clicking a trade ranking opens that deal directly on the Archive page.

The dedicated **Trade Charts** page (`docs/charts.html`), immediately after Leaderboards in the header navigation, shows three per-league charts (`docs/lib/charts.js` computes the data; `docs/lib/leaderboard-charts.js` draws it):

Trades per week and Trade partners sit side by side on wide screens, with Net roster swing spanning the row below. On smaller screens they stack in that order.

- **Trades per week**: completed deals per game week, including quiet weeks as zero; the week in progress is marked with `*`.
- **Trade partners**: a heatmap of how many deals each pair of managers has made, including managers who have not traded.
- **Net roster swing**: each manager's summed Weekly Moves point swing (actual minus the no-weekly-trades lineup) across verified manager-weeks; rows link to that manager's Weekly Moves cards.

The site has five pages linked from the header: **Leaderboards** (`docs/index.html`), **Trade Charts** (`docs/charts.html`), **Weekly Moves** (`docs/weekly.html`: manager-week trade bundles), **Archive** (`docs/archive.html`: filters and trade detail), and **Alternate Universe** (`docs/alternate.html`). Each page loads one ES module from `docs/pages/`, and shared code lives in `docs/lib/`; see `AGENTS.md` for the code layout. Leaderboard and Weekly Moves trade links open the selected deal directly on the Archive page. The Alternate Universe page replays the completed Premier and Champeens matchups.

## Weekly Roster Moves (prototype)

Each card has a collapsed **Final lineup** disclosure showing the actual end-of-week box-score roster, player slots, and points, grouped into Starters, Bench, and IR. Starters appear in QB, RB, WR, TE, RB/WR/TE, K order, with any other starter slots afterward. Bench and IR points are not part of the matchup score. The generator stores these players under `weekly_roster_moves.rows[].final_lineup`; older snapshots without the field explicitly show that the lineup is unavailable.

The Weekly Moves page is the app's canonical matchup-outcome model. It combines every trade a manager completed within the same Tuesday-to-Tuesday game week. Players acquired and then traded away within that interval cancel from the net roster diff. It compares the manager's actual weekly score and result with a projection-selected lineup that undoes the week's net trade changes; if the opponent also traded that week, the opponent's bundle is undone too. Actual waiver and free-agent choices remain in place. League, game-week, and manager filters let you inspect the results behind the leaderboard totals. Manager-week cards show the newest weeks first by default, with a week-order control to switch to oldest first.

Cards mark an improved result relative to the no-weekly-trades model as **Clutch** (green), and a worsened result as **Oof** (red); unchanged results have no badge. The adjacent W/L/T arrow shows the modeled result transition. Point differences alone do not determine the badge, since an opponent's weekly moves can also change the outcome.

This is a reconstruction, not an exact pair of historical Tuesday roster snapshots: ESPN weekly box-score rosters provide the ending roster evidence and accepted trades provide the diff. Weeks without a completed box score are excluded. The page labels this limitation and links back to every underlying trade.

The Archive no longer calculates whether an individual trade flipped a matchup. It retains the exchange, raw received-player points, and weekly swing chart as descriptive context; isolating one trade is misleading when a manager completes several deals in the same week.

## Alternate Universe standings (2026 experiment)

It shows three records and points-for totals per team: **Real** uses the actual ESPN box-score starting lineup; **Current optimal** chooses the best-scoring legal starters from that week's actual roster; **No trades** chooses the best-scoring legal starters after moving known post-August-30 traded players back to the team that first sent them. The optimizer uses the league's active roster slots and each player's ESPN eligibility, assigning a player at most once. Wins/losses/ties use the actual schedule (ties count as half a win). **Δ wins compares No trades with Current optimal**, not with Real, so it separates modeled roster changes from the benefit of optimizing lineups. That page has its own league selector, and no data from the current unfinished week is included.

This is **not a reconstructed Aug 30 roster or a prediction**: the model starts from each week's actual box-score roster, keeps actual waiver and free-agent acquisitions (which reset a traded player's baseline ownership), and rewinds only players in recovered trade records. Unrostered players stay out; it does not enforce roster size or model hypothetical cuts, future waiver choices, injuries, lineup locks, or whether an owner would have started the optimal lineup. A midweek transaction can therefore affect that whole scoring week. Champeens' trade reconstruction may miss movements and is labeled accordingly. Do not treat these standings as actual standings or a trade verdict.

## Weekly swing chart

Each trade's detail panel includes a dependency-free SVG bar chart of each side's received-player points per eligible week. The trade week is shaded and marked `*`. A `⇄` marks a week where the **cumulative** leader changed, and the caption summarises who leads. The week table below remains the accessible text version; the chart also has a full `aria-label`.

## Champeens data source

ESPN's activity feed (`recent_activity`) is members-only, and the configured ESPN account can read Champeens but is not a member. For that league the generator rebuilds trades from accepted-trade records (`mTransactions2`) plus roster history (`mRoster`): players currently on a roster with an acquisition type of `TRADE` at the accepted (or, for trades under league review, the next executed) timestamp, and direct team-to-team roster moves during that scoring period that aren't explained by a waiver or free-agent add. **Players later dropped or traded again can be missing**, and an accepted trade whose players can't be recovered is skipped. The UI labels these trades as reconstructed. Checked against Premier's real feed, this method found every trade with no wrong players; it missed one player each in four trades.

## Live site

Published with GitHub Pages at <https://randall-krauskopf.github.io/trade-time-machine/>. GitHub Pages serves the `docs/` folder of `main`, so every push redeploys it. **The site and `docs/data.json` are public**, so never commit credentials or Discord exports.

## Refresh the snapshot

The generator (`trade_time_machine/`, run with `generate.py` or `python -m trade_time_machine`) runs independently of other checkouts. It needs Python 3.12+ and the `espn-api` dependency in this repo's `requirements.txt`. Set the season, league IDs, labels, and inclusive trade cutoff in `generator.json`; the league's Tuesday week boundary and cutoff are interpreted in **America/Chicago**. Keys should be unique because they identify each league in the generated data. The `receipts` flag applies only when a local Discord export is explicitly supplied; the optional `discord` section lists the server (`guild_id`) and the allowlisted channel IDs (as strings) the importer accepts. To use another configuration file, pass `--config path/to/config.json`.

```bash
cd trade-time-machine
python3 -m venv .venv
.venv/bin/python -m pip install -r requirements.txt
test -e .env || cp .env.example .env
# Add your ESPN_S2 and SWID to .env if a league is private.
.venv/bin/python generate.py
```

You can instead set `ESPN_S2` and `SWID` as environment variables (both are required together for private leagues); environment variables override `.env`. Use `--env-file path/to/file` for a different local credentials file, and `--output path/to/file.json` to avoid replacing `docs/data.json`. The default output is `docs/data.json`. Credentials are never written into the snapshot, and `.env` and `.venv` are git-ignored. To preview locally, run `npm run serve` (or `python3 -m http.server 8000 --directory docs`) and open <http://localhost:8000/>. The pages are ES modules and fetch JSON, so opening the files directly from disk (`file://`) will not work.

## Discord receipts (deferred)

The Archive does not display Discord content. `trade_time_machine/receipts.py` retains an experimental local-export importer as groundwork, but publishing receipts is deferred in `ToDo.md` until the league approves the privacy and consent model. Never commit credentials, message exports, or private channel content.

## Historical Supabase transform (read-only)

`trade_time_machine/historical.py` translates historical Supabase rows into the current `data.json` schema. By default it produces an **Archive-only** snapshot (`alternate_standings` and `weekly_roster_moves` are `null`). It also includes the full team-season list so Holding Steady counts zero-trade managers. Received-player points come from `league_roster_entries`; an unavailable player-week stays `null`, never zero.

For completed historical seasons, scored weeks come from roster rows with non-null points rather than `league_seasons.weeks_total` (which covers only the regular season). Historical records that show player movement in only one direction keep the empty sent/received list on the other side; the database does not describe any non-player compensation. Do not treat the result as a complete accounting of draft picks or cash.

Database access is deliberately narrower than a normal Supabase client:

- `trade_time_machine/supabase_source.py` has fixed `SELECT` queries and no write method.
- The connection must report the exact role `supabase_read_only_user`.
- Extraction starts with `BEGIN READ ONLY` and rejects the session unless `transaction_read_only` is `on`.
- Queries run one table at a time to avoid the temporary-disk failure found during the audit.
- The CLI has no default output under `docs/`, so an audit cannot replace the published snapshot accidentally.

If you have a direct database URL, copy `historical-2025.example.json`, replace `REPLACE_WITH_VERIFIED_2025_CUTOFF` with the verified draft-correction cutoff, and put the direct read-only PostgreSQL URL in the ignored `.env` as `SUPABASE_DATABASE_URL`. Then run:

```bash
.venv/bin/python -m trade_time_machine.historical_cli \
  --config historical-2025.json \
  --output trade-time-machine-2025.json
```

If access is available only through the Supabase MCP server, no password is needed:

1. Run each SELECT in `historical-2025-queries.sql` separately. They are read-only and each returns one `data` JSON array.
2. Create `historical-2025-raw/` in the repo root; it is Git-ignored.
3. Copy each result array into the matching filename: `leagues.json`, `seasons.json`, `teams.json`, `team_seasons.json`, `trades.json`, and `roster_entries.json`.
4. Run the same transform with `--input`; without `--with-weekly`, this path does not read `.env` or connect to Supabase:

```bash
.venv/bin/python -m trade_time_machine.historical_cli \
  --config historical-2025.json \
  --input historical-2025-raw \
  --output trade-time-machine-2025.json
```

The offline input may also be one JSON object whose keys are those six filenames without `.json`. The local config, raw export, and transformed snapshot are Git-ignored; do not force-add the raw export, which contains internal database UUIDs. The transformed output omits them.

To add verified historical Weekly Moves and the matchup-based leaderboards, rerun either command above with `--with-weekly`. This opt-in step reads the 2025 leagues from ESPN using `ESPN_S2` and `SWID` from the ignored `.env` (or the environment), but still makes **no Supabase connection** when `--input` is used. It verifies ESPN team IDs and box-score totals, reconstructs no-trade lineups from historical projections, and omits a manager-week when a departed player's actual points, projection, or eligibility cannot be verified. If an opponent also traded that week, an uncertain opponent outcome is omitted as well. The `weekly_roster_moves.omitted` list identifies excluded `{week, team_id}` pairs; weekly leaderboards are partial when it is nonempty. `alternate_standings` remains unavailable. The snapshot remains local and ignored; do not copy it into `docs/` without separately reviewing a publication plan.

The transform recalculates `transaction_week` from the UTC timestamp using the app's Central-time calendar instead of trusting Supabase's stored `week`. Public trade IDs remain `timestamp-team1-team2`; Supabase UUIDs are never published. Validate and review the output before considering any season for the site.

## Checks

```bash
.venv/bin/python -m pip install -r requirements-dev.txt
npm ci && npx playwright install chromium

npm test              # Python unit, golden-snapshot, and data-contract tests + JS unit tests
npm run test:smoke    # Playwright: every page loads, deep links resolve, bad schema versions are explained
npm run coverage      # Python branch coverage (minimum 95%) and JS coverage
npm run lint          # ruff
```

GitHub Actions runs lint, unit, and smoke tests on every push and pull request. `docs/data.json` must match `schema/data.schema.json`; `AGENTS.md` describes how to change that contract and refresh the golden fixture.

The scoring window includes the trade week once completed, but excludes the week currently in progress. Week boundaries assume the NFL season starts on the Thursday after Labor Day (September 10 in 2026); check this assumption if reusing the prototype in a later season. Missing player scores are shown as unavailable, not zero. ESPN `recent_activity` pages are fetched until exhausted; non-trade transactions are ignored.
