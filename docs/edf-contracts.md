# EDF contracts and TIC calendar codes

Reviewed on 1 November 2026 for residential Linky meters (up to 36 kVA).

The parser recognizes the meter's tariff calendar, not the commercial offer name.
In standard TIC, `NGTF` contains the supplier-programmed calendar name, `LTARF`
contains the current tariff label, and `NTARF` identifies the active supplier
index. Enedis specifies 16 characters for `NGTF` and `LTARF`, and up to ten
supplier indexes (`EASF01`–`EASF10`). Their meanings depend on the programmed
calendar. The specification does not publish an exhaustive EDF code registry.
See [Enedis-MOP-CPT_002E, sections 6.2.2–6.2.3](https://www.enedis.fr/media/2035/download).

## Recognized codes

Spaces, padding and ASCII letter case are ignored. All other characters must
match; partial names are rejected. Original meter labels and indexes are retained
for publishing.

| TIC mode | Accepted calendar code | Internal contract |
| --- | --- | --- |
| Historical | `BASE` | `C_BASE` |
| Historical | `HC..` | `C_HC` |
| Historical | `EJP.` | `C_EJP` |
| Historical | `BBR` and four-character `BBRx` variants, including `BBR(` | `C_TEMPO` |
| Standard | `BASE` | `C_BASE` |
| Standard | `H PLEINE/CREUSE` | `C_HC` |
| Standard | `H SUPER CREUSES` | `C_HEURES_SUPER_CREUSES` (existing nonseasonal support) |
| Standard | `EJP` | `C_EJP` |
| Standard | `TEMPO` | `C_TEMPO` |
| Standard | `ZEN FLEX`, `Pointe Mobile` | `C_ZEN_FLEX` |
| Standard | `HSC ETE HIVER` | `C_ZEN_ESTIVAL` |
| Standard | `SEM WE` | `C_SEM_WE` |
| Standard | `HC et Week-End` | `C_HC_WE` (existing code retained) |
| Standard | `HC SEM ET HC WE` | `C_HC_SEM_WE` |
| Standard | `SEM WE LUNDI`, `SEM WE MERCREDI`, `SEM WE VENDREDI` | Existing `C_SEM_WE_*` contracts |
| Standard | `HC SEM WE LUNDI`, `HC SEM WE MERCR`, `HC SEM WE VENDR` | Separate `C_HC_SEM_WE_*` contracts |

The `HC` weekday variants remain distinct from the corresponding calendar without
that prefix. The abbreviated Wednesday/Friday forms fit the meter's 16-character
field. No guess based on the number of nonzero indexes is made: old indexes can
remain nonzero after changing offers.

When `NGTF` is absent, exact Tempo labels (`HC/HP BLEU`, `HC/HP BLANC`,
`HC/HP ROUGE`, or `HC/HP ROUG`) can identify Tempo. A present unknown `NGTF` is
never replaced by a guess from `LTARF`. An isolated `HC`, `HP`, `HSC`, or color
does not identify a calendar.

## Review of EDF offer families

EDF's commercial names do not require separate enums when they use the same
Base or peak/off-peak calendar. The following is a review of tariff structures;
it is not a claim that every meter carrying an offer emits the same `NGTF`.

| EDF offer family | Tariff structure and parser coverage |
| --- | --- |
| Tarif Bleu | Base and peak/off-peak calendars; Tempo and existing EJP support retained. |
| [Zen Fixe](https://particulier.edf.fr/fr/accueil/electricite-gaz/zen-fixe.html), [Zen Online](https://particulier.edf.fr/fr/accueil/electricite-gaz/zen-online.html) | Base or peak/off-peak options; reuse `C_BASE` / `C_HC` when the meter sends those calendars. |
| [Vert Électrique](https://particulier.edf.fr/fr/accueil/electricite-gaz/vert-electrique.html), [Vert Électrique Régional](https://particulier.edf.fr/fr/accueil/electricite-gaz/vert-electrique-regional.html) | Base or peak/off-peak options; same calendar handling. |
| [Zen Week-End](https://particulier.edf.fr/fr/accueil/electricite-gaz/zen-week-end.html), Vert Électrique Week-End | Weekend variants, with or without weekday off-peak hours. Recognized weekend calendars are listed above; the brand is not inferred. |
| [Zen Week-End Plus](https://particulier.edf.fr/fr/accueil/electricite-gaz/zen-week-end-plus.html) | Weekend plus Monday, Wednesday or Friday, with or without weekday off-peak hours. Separate `SEM WE` and `HC SEM WE` codes. |
| [Vert Électrique Auto](https://particulier.edf.fr/fr/accueil/electricite-gaz/vert-electrique-auto.html) | Off-peak and optional weekend structures; handled through the programmed calendar. |
| [Zen Week-End option Flex](https://particulier.edf.fr/fr/accueil/electricite-gaz/zen-flex.html) | Eco/Sobriété peak and off-peak periods; `ZEN FLEX` and observed `Pointe Mobile` calendar names. |
| [Zen Estival](https://particulier.edf.fr/fr/accueil/electricite-gaz/zen-estival.html) | Six seasonal rates: summer/winter × peak/off-peak/super off-peak. The supplied frame confirms `HSC ETE HIVER` and `LTARF=HSC Hiver`, with `NTARF=4`. |

Public EDF offer pages establish tariff structures, rather than a complete list of
TIC names or supplier-index ordering. `HSC ETE HIVER` is taken directly from the
reported meter frame; its association with Zen Estival follows EDF's documented
seasonal super-off-peak structure. No customer identifiers are included here.

Additional first-hand evidence for calendar names:

- [Zen Flex meter report](https://github.com/Koenkk/zigbee2mqtt/issues/19790):
  the subscriber reports `Pointe Mobile` and `HC Jnormal`.
- [Peak/off-peak weekday/weekend meter capture](https://community.jeedom.com/t/puissance-par-phase-en-teleinfo-linky-standard/70191):
  `HC SEM ET HC WE`; also recognized in the
  [Domoticz decoder](https://github.com/domoticz/domoticz/blob/master/hardware/TeleinfoBase.cpp).
- [Wednesday weekend-option meter capture](https://forum.hacf.fr/t/monitoring-electricite-avec-la-teleinfo-node-red-influxdb/4546?page=8):
  `HC SEM WE MERCR`. The Monday and Friday spellings are accepted parallel forms;
  independent captures for those two new HC-prefixed forms were not found.
- Existing project codes (`HC et Week-End`, the three `SEM WE` weekday codes,
  `ZEN FLEX`, and the historical families) remain supported. `SEM WE` is accepted
  as the corresponding plain weekend spelling; an independent capture was not
  found in this review.

## Reporting and verification

MQTT/Home Assistant, HTTP, and Zigbee retain the generic standard TIC labels,
including `NGTF`, `LTARF`, `NTARF`, `EAST`, and `EASF01`–`EASF10`. Recognition does
not rename energy indexes or assign tariff prices. Existing validity checks may
omit unavailable or unused zero-valued indexes.

The Tuya cloud product has a fixed contract enum and only total/HP/HC aggregate
fields. Newly recognized seasonal and weekend calendars, plus the previously
unhandled `HC et Week-End` calendar, publish the `EAST` total without inventing
HP/HC splits. Their cloud contract enum falls back to `INCONNU`; firmware logs
show the recognized local calendar. Individual seasonal indexes remain available
through MQTT/HTTP/Zigbee. Full named seasonal rates in the Tuya app would require
changes to the cloud product schema and verified register mappings.

Run the host tests with:

```sh
python3 -B -m unittest discover -s firmware/tests -v
```

Contract tests compile and execute the actual C parser with a host C compiler.
They cover the reported seasonal frame, existing and additional calendar codes,
historical Tempo variants, padding/case, corrupt/truncated input, missing-calendar
fallback, stable enum IDs, and complete Tuya fallback tables. Build the firmware
with ESP-IDF separately; no device flash is part of this change.
