# Trade Time Machine

Local, **read-only** proof of concept for the 2026 Lana Straw **Premier** (ESPN league `1851323`) and **Champeens** (ESPN league `1695026336`) leagues. Use the league, game-week, and team filters to narrow the Archive. Transaction game weeks turn over at **12:00 AM Central every Tuesday**, after Monday Night Football; the first bucket begins at the August 30 cutoff. It loads completed ESPN trades **from August 30, 2026 onward (Central league time)**, excluding earlier draft-correction transactions. It shows exactly who each team received, and compares the actual fantasy points those acquired players scored in **completed scoring weeks ending after the trade**.

This is a **hypothetical hold** for each individual deal: the received players remain credited to their original recipient for all subsequent eligible weeks, even if that manager later trades them to someone else. The later trade also appears separately as its own hypothetical hold. **The trade week is included once complete even when the trade occurred during that week** (for example, a Thursday evening trade counts that week's final scores). It is labeled in the table because player points could have been scored *before* the trade. Totals across trades therefore overlap and must **not** be added together as manager season totals. Points include bench performances and do not measure actual points earned by a manager, replacement value, lineup changes, playoff odds, or future draft dollars/FAAB included in a deal. No winner is declared.

## Leaderboards

The top of the page ranks trades (top 3 per board, per league under "All leagues") , always across all trades regardless of the league/team filters:

- **Most active traders**: managers ranked by the number of completed deals they participated in, using the same inclusive August 30 Central-time cutoff as the archive.
- **Most players exchanged**: total players received by both sides (newest first on ties).
- **Fastest regret**: difference in the first eligible week only; `*` marks when that week is the trade week.

Trades without a completed eligible week are left off the points boards. Clicking a trade ranking opens that deal directly on the Archive page.

The site has four pages linked from the header: **Leaderboards** (`docs/index.html`), **Archive** (`docs/archive.html`: filters and trade detail), **Weekly Moves** (`docs/weekly.html`: manager-week trade bundles), and **Alternate Universe** (`docs/alternate.html`, rendered by `docs/alternate.js`). Leaderboard and Weekly Moves trade links open the selected deal directly on the Archive page. The Alternate Universe page replays the completed Premier and Champeens matchups.

## Weekly Roster Moves (prototype)

The Weekly Moves page is the app's canonical matchup-outcome model. It combines every trade a manager completed within the same Tuesday-to-Tuesday game week. Players acquired and then traded away within that interval cancel from the net roster diff. It compares the manager's actual weekly score and result with a projection-selected lineup that undoes the week's net trade changes; if the opponent also traded that week, the opponent's bundle is undone too. Actual waiver and free-agent choices remain in place.

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

The generator reuses the ESPN helper library and private `.env` from the `AI-playground` repo (`fantasy-football-league/scripts`). It expects that repo to be checked out next to this one; otherwise set `FF_SCRIPTS_DIR` to the `scripts` folder.

```bash
cd trade-time-machine
../AI-playground/fantasy-football-league/scripts/.venv/bin/python generate.py
git add docs/data.json && git commit -m "Refresh trade snapshot" && git push
```

Credentials are read from `scripts/.env` and **never written** into the snapshot. To preview locally, run `python3 -m http.server 8000 --directory docs` and open <http://localhost:8000/> (opening the file directly cannot fetch JSON).

## Discord receipts (deferred)

The Archive does not display Discord content. `generate.py` retains an experimental local-export importer as groundwork, but publishing receipts is deferred in `ToDo.md` until the league approves the privacy and consent model. Never commit credentials, message exports, or private channel content.

## Checks

```bash
../AI-playground/fantasy-football-league/scripts/.venv/bin/python -m unittest -v test_generate.py
```

The scoring window includes the trade week once completed, but excludes the week currently in progress. Week boundaries assume the NFL season starts on the Thursday after Labor Day (September 10 in 2026); check this assumption if reusing the prototype in a later season. Missing player scores are shown as unavailable, not zero. ESPN `recent_activity` pages are fetched until exhausted; non-trade transactions are ignored.
