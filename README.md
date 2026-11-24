[![make.fun · news-image-20261124](https://make.fun/badge/news-image-20261124.svg)](https://make.fun/bounty/news-image-20261124?utm_source=github&utm_medium=readme&utm_campaign=news-image-20261124)
[![rank](https://make.fun/badge/news-image-20261124/moonku-ai/news-image-20261124-v3/rank.svg)](https://make.fun/bounty/news-image-20261124/leaderboard?utm_source=github&utm_medium=readme&utm_campaign=news-image-20261124)
[![reward](https://make.fun/badge/news-image-20261124/moonku-ai/news-image-20261124-v3/reward.svg)](https://make.fun/bounty/news-image-20261124?utm_source=github&utm_medium=readme&utm_campaign=news-image-20261124)

# THE WORLD IN ONE DAY — Tuesday 24 November 2026

Sum up 24 November's world news in one image. Pure Python stdlib program
that renders a 1024×1024 broadsheet PNG: NATO sends an AWACS early-warning
jet to Poland after a Russian drone and three cruise missiles breach Polish
airspace, Senegal's AFCON title is restored by CAS, Sanofi buys Insmed for
$41 billion, fourteen nations back the ICJ's Myanmar genocide ruling, and a
5.6-magnitude quake shakes Nepal — plus markets, a world map and the day in
brief.

## Run

```sh
python3 main.py            # writes entry-v3.png (1024x1024, deterministic)
python3 test_main.py       # local tests: atlas, fit, dims, determinism
```

`main.py` reads `atlas.bin` (glyph atlas built from system fonts by
`tools/make_atlas.py`; no network, no third-party packages). Two runs
produce byte-identical PNG output.

## Bounty

[news-image-20261124 on make.fun](https://make.fun/bounty/news-image-20261124)
