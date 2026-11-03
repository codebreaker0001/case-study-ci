"""One-command run of the full pipeline: generate -> metrics -> bridge ->
unified + DQ -> LLM extraction eval -> HTML view. Requires data/synthea_seed
to already exist (committed); re-run src/generate/synthea_base.py +
src/generate/augment.py first only if regenerating from scratch.
"""
import subprocess
import sys

STEPS = [
    "src.generate.overlay",
    "src.unified.unified",
    "src.dq.dq",
    "src.bridge.bridge",
    "src.extract.extract",
    "src.viz.build_reconciliation",
]

for step in STEPS:
    print(f"\n=== {step} ===")
    result = subprocess.run([sys.executable, "-m", step])
    if result.returncode != 0:
        print(f"[run_all] {step} failed, stopping.")
        sys.exit(1)

print("\n[run_all] done. Open outputs/reconciliation.html")
