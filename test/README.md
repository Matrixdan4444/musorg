# Match Stress Parts

This folder contains one-click batch runners for the frozen remaining match-stress parts `4/10` through `10/10`.

Files:
- `run-part-4-of-10.command` ... `run-part-10-of-10.command`: Finder-friendly launchers for each frozen part.
- `run_match_part.py`: shared driver that loads the manifest, scans only the configured artist directories, resumes from checkpoint state, and writes a detailed JSON report.
- `parts_manifest.json`: frozen artist split for the remaining library parts.
- `results/`: checkpoint and report output folder.

Behavior:
- default library path: `/Volumes/Music`
- default workers: `2`
- default cache mode: cold-cache (`--use-cache` is off)
- checkpoint/resume: repeated runs continue from `test/results/part-*-of-10.state.json`

Outputs:
- state file: `test/results/part-*-of-10.state.json`
- report file: `test/results/part-*-of-10.report.json`

Manual usage example:

```bash
./venv/bin/python test/run_match_part.py 4
```
