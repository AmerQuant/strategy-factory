# configs/costs

Cost profiles (F-0.2.1 … F-0.2.4). A symbol without a profile cannot run (`sfac costs validate`).

- `*.yaml` (one profile per file): the T06 **placeholder** profiles (`status: placeholder`).
  They stay as the fallback of the asset-class groups in `assignments.yaml`.
- `assignments.yaml` (hand-written): asset-class groups and symbol entries. US equities that
  are not at the broker use the generated `us_share_cfd_proxy` (D-324, placeholder).
- `moneta/` (T06b, broker Moneta Markets MT5 ECN, D-520 … D-526, D-315 … D-325):
  - hand-written: `moneta.yaml` (build rules), `mapping.yaml` (mapping thresholds),
    `dukascopy_map.csv` (D-323), `symbol_overrides.csv` (manual broker ↔ research pairs and
    `UNMAPPABLE` entries; the user confirms review candidates here);
  - generated, never edit: `moneta_spec.csv` + `.meta.json` (`sfac costs moneta import`, with
    the broker file's SHA-256), `moneta_profiles.yaml`, `assignments.yaml`, `symbol_map.csv`
    (`sfac costs moneta build`, which also writes `docs/reviews/T06b_mapping_review.csv`).

After changing overrides or rules: `sfac costs moneta build`, `sfac universe generate`,
`sfac costs validate`, `sfac universe validate`.
