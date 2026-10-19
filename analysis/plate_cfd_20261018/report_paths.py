"""Keep numerical workspace stable while published results live under Docs."""
from pathlib import Path

ANALYSIS_ROOT = Path(__file__).resolve().parent
PROJECT_ROOT = ANALYSIS_ROOT.parent.parent
REPORT_ROOT = PROJECT_ROOT / 'Docs/tests/cfd/2026-10-18_fixed_plate'
RESULTS_ROOT = REPORT_ROOT / 'results'
