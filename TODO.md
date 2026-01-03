Resume hybrid 500-citation runs with token cap ~120 LLM pairs/day.
   Steps:
   1) Prioritize contentious seeds: EDGES 2018Natur.555...67B (finish remaining cites), late-time DESI 2025PhRvD.112f3548C, EDE 2024PhRvL.132v1002E; then others (H0 ladder/lensing, FRB, radius valley) later.
   2) For each seed: run citation_analysis.py with --citing-limit 500, --ref-limit 50; apply regex prefilter; LLM classify only high-signal/uncertain citations up to the daily token cap (~120 pairs).
   3) Track token estimates; defer overflow to next day.
   Sessions: H0 = 3, FRB = 4, Radius Valley = 5. Use existing /tmp/*-network*.json when present.
   Working dir: /home/roboscientist/haruspex
