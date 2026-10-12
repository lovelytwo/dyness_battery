# Dyness PCAP decoder and protocol references

Run:

```bash
python3 dyness_decode.py captures/sunday.pcap --outdir decoded --tz Australia/Hobart
```

Python 3 standard library; classic PCAP only. Outputs event, field, cell, bank, board CSVs and JSON.

- `dyness_protocol_spec.md`: observed wire format, session sequence, message types and uncertainty.
- `dyness_all_fields.md` / `.csv`: full field inventory with hypotheses and the upstream integration cross-reference.
- `cloud_point_names.json`: official point names (`pointNameCn`) from the Dyness cloud for the bank and a board. Refresh with `DYNESS_API_ID=… DYNESS_API_SECRET=… python3 ../tools/dyness_cloud_points.py out.json`; the output contains serials and the station address, so keep it in `captures/`. The integration reads a copy at `custom_components/dyness_battery/local/point_names.json`; copy the file there after changing it.
- `dyness_decode.py`: reproducible decoder.
- `captures/`: source PCAPs.
- `documents/`: Dyness Open API PDF and the Dyness Monitor serial software.

**Privacy:** source PCAPs contain plaintext authentication material. Do not commit or publish `captures/`. Decoder redacts login payloads but does not sanitize arbitrary secrets that may exist in unknown fields.
