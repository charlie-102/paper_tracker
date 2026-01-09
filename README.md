# Paper Implementation Tracker

Automatically tracks GitHub repositories for **low-level vision** papers (super-resolution, denoising, restoration, etc.) that have **reproducible pretrained weights**.

This tracker runs weekly to find new papers with released weights, detect when promised weights become available, and maintain a curated list of reproducible implementations.

## Latest Results

| Resource | Description |
|----------|-------------|
| [**Read the Report**](results/latest.md) | Full list of tracked repositories with weights |
| [**Download CSV**](results/latest.csv) | Spreadsheet format for filtering and analysis |

## Schedule

The tracker runs automatically every **Monday at 8:00 AM UTC**.

Results are committed directly to this repository, so you can:
- Watch this repo to get notified of updates
- Check back weekly for new papers with weights
- Browse the [results/](results/) folder for historical snapshots

## What It Tracks

- **Repositories with weights**: Papers that have released pretrained models (HuggingFace, Google Drive, GitHub Releases, etc.)
- **Coming soon**: Papers that promise weights will be released
- **Fresh releases**: Papers where weights were just made available

### Conferences Detected

CVPR, ECCV, ICCV, ICLR, NeurIPS, ICML, AAAI, SIGGRAPH, and arXiv preprints.

## For Developers

Want to run the tracker locally, customize search queries, or contribute?

See the [Development Guide](docs/DEVELOPMENT.md) for:
- Installation and CLI usage
- Configuration options
- Python API
- Adding new detection patterns

## License

MIT
