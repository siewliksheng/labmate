> **Provenance note** (not part of the report itself): the prelab checklist
> data here is real — `formaldehyde`'s hazard statements came from a live
> PubChem lookup, `E. coli K-12`'s BSL-1 rating came from the local
> biosafety table, and the ethanol gap is a genuine unresolved lookup, not
> staged. The Markdown synthesis below (Summary/Suggested Next Steps
> wording) is representative example output, hand-written for this commit
> since no live LLM backend was configured in the session that generated
> it. This file itself, and `example_report.html` next to it, both went
> through the real `labmate.experiment.generate_report()` /
> `labmate.report_render.render_report_html()` code paths — only the LLM
> call inside `generate_report()` was substituted with this canned text.

---

## Escalations

None occurred during this experiment.

## Summary

A plasmid DNA extraction was performed from an E. coli K-12 overnight culture using alkaline lysis and ethanol precipitation, with the resulting product visualized by formaldehyde-fixed gel electrophoresis.

## Prelab Safety Checklist

| Item | Status | Notes |
|---|---|---|
| Formaldehyde (gel fixation) | Resolved | H302, H314, H330 -- fume hood + goggles required |
| E. coli K-12 culture | Resolved | BSL-1 -- standard microbiological practices, non-pathogenic lab strain |
| Ethanol (precipitation step) | Unresolved, acknowledged | No matching entry in the local biosafety/SDS lookup -- signed off by dr. lin (PI) with the gap explicitly acknowledged |

Required PPE: nitrile gloves, lab coat, safety goggles, fume hood for formaldehyde steps.

## Observations / Results

1. Culture OD600 = 0.68 at harvest (t=4h) -- overnight culture, flask A
2. Gel electrophoresis (image) -- single clean band ~1.2kb, consistent with expected plasmid size -- lane 3
3. Yield: 42 ng/uL, A260/A280 = 1.87 -- Nanodrop reading post-extraction

## Suggested Next Steps

> A260/A280 of 1.87 is within the acceptable range for plasmid DNA but slightly below the 1.8-2.0 ideal window -- consider an additional wash step if downstream sensitive applications (e.g. sequencing) are planned.
>
> Since the ethanol hazard lookup came back unresolved, consider adding ethanol to the lab local SDS reference table so future prelab checks for this protocol resolve automatically.
