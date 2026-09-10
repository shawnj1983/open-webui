# NetworkChuck — Mac Studio networking / AI cluster scrape

## Primary video
- **Title:** Ethernet is DEAD?? Mac Studio is 100x FASTER!!
- **URL:** https://www.youtube.com/watch?v=bFgTxr5yst0
- **Channel:** NetworkChuck

## Related video
- **Title:** I built an AI supercomputer with 5 Mac Studios
- **URL:** https://www.youtube.com/watch?v=Ju0ndy2kwlw

## Core claim
Chuck clusters multiple **Mac Studios** for local AI. The bottleneck is not GPU/VRAM — it is **networking latency/bandwidth** when splitting big models across machines.

## Maximize bandwidth (what the video pushes)
1. **Thunderbolt 5** between Mac Studios (2× Thunderbolt 4 bandwidth) instead of relying on Ethernet alone for model shard traffic.
2. Previous cluster on TB4 / 10GbE was painfully slow for pipeline-parallel inference (tokens wait on each Mac in sequence).
3. Newer Apple connectivity / clustering approach is framed as dramatically faster (title: **100x FASTER**) vs the old Ethernet-bound setup — networking fix, not a bigger GPU.
4. Unified memory on each Mac Studio = huge effective **VRAM** pool (example cited: 512GB unified per high-end Studio; cluster totals in the multi‑TB range across machines).

## Maximize VRAM (unified memory angle)
- Apple Silicon uses **unified memory** (CPU+GPU share one pool) — so system RAM *is* GPU memory for local LLMs.
- Clustering lets you run models too big for one machine by splitting layers across Studios (with Exo / MLX-style tooling in related videos).
- Cost framing in transcript: huge unified-memory cluster vs many NVIDIA H100s for similar VRAM capacity.

## Practical takeaway
If the goal is “maximize bandwidth + maximize VRAM” for local AI on Mac Studio:
- Buy/config **max unified memory** on each Studio (that *is* your VRAM).
- Interconnect with **Thunderbolt 5** (not just 10Gb Ethernet) for cluster traffic.
- Expect Ethernet-only clusters to look “dead” for big sharded models because of latency between layer hops.
