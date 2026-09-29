"""Trade Time Machine generator.

Reads Lana Straw league data from ESPN and writes the static snapshot
(`docs/data.json`) that powers the site. The pipeline, in order:

1. `config`       – read generator.json and ESPN credentials.
2. `espn_source`  – fetch trade activity (or rebuild it for members-only leagues).
3. `trades`       – turn activity into trade records with received-player points.
4. `receipts`     – attach nearby Discord messages (optional, local export only).
5. `standings`    – Alternate Universe standings (rewind every trade).
6. `weekly_moves` – grade each manager's bundled trades per game week.
7. `snapshot`     – assemble one league's snapshot; `cli` writes all leagues.

`game_weeks` holds the league calendar rules and `lineups` the lineup math,
and both are shared by several stages. `models` documents the output shapes.
"""
