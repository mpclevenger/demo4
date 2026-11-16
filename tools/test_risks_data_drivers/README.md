# Made-up risk and driver files (TEST only)

**Not real risks.** Made-up copies in the shape of the risk assessment engine's config, for the TEST environment
and for trying out the metric-to-risk linking prompts. Production reads `config/risks/` and never this folder.

- `air.cyber.yaml`, `air.change.yaml`, `air.ops.yaml`, `air.data.yaml`: one file per domain, two risks each,
  keyed by risk ID (`air.cyber.01`, `air.cyber.02`, ...). The IDs match the made-up risk assessments that
  `tools/make_test_data.py` writes, so family pages in TEST show risk names.
- `driver_mapping.yaml`: the drivers (`RD01`, ...) the risks name. TRUST doesn't read it; it's here so the set is
  complete.

To use them on TEST, set the config var `TRUST_RISKS=tools/test_risks` (deployment wiki, TEST section). Metric
cards only list risks once `card.risks` in `config/metrics.json` names their IDs; that file is shared with
production, so link real risk IDs there, not these.

## `test_risks_data_drivers/` (a copy for the data drivers)

The same made-up files with five more drivers answered from TRUST's data (`RD11`, `RD15`, `RD21`, `RD25`, `RD53`), two
of which the two Change risks use, so the Risk site's "answered from data" box and ratings can be tried on TEST. The
plain `tools/test_risks/` stays as it is because several tests pin its 21 drivers. Use
`TRUST_RISKS=tools/test_risks_data_drivers` to try it.
