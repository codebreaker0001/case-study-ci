"""Download (if needed) and run Synthea to generate raw synthetic patient CSVs.

Usage:
    python scripts/run_synthea.py          # full run, population size from config
    python scripts/run_synthea.py 100      # override population size (e.g. for a test run)
"""
import json
import subprocess
import sys
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]

# Pinned to the v4.0.0 release (requires JDK 17+); see DATA_LINEAGE.md / Decisions log
# for why this version and why modules are not restricted via -m.
JAR_URL = "https://github.com/synthetichealth/synthea/releases/download/v4.0.0/synthea-with-dependencies.jar"
JAR_SIZE = 201164144

JAR_DIR = ROOT / "data" / "synthea_jar"
JAR_PATH = JAR_DIR / "synthea-with-dependencies.jar"
RAW_DIR = ROOT / "data" / "synthea_raw"
CONFIG_PATH = ROOT / "config" / "synthea_run.json"
PROPERTIES_PATH = JAR_DIR / "synthea.properties"


def ensure_jar() -> Path:
    if JAR_PATH.exists() and JAR_PATH.stat().st_size == JAR_SIZE:
        print(f"[run_synthea] using cached jar at {JAR_PATH}")
        return JAR_PATH
    JAR_DIR.mkdir(parents=True, exist_ok=True)
    print(f"[run_synthea] downloading {JAR_URL} ...")
    urllib.request.urlretrieve(JAR_URL, JAR_PATH)
    actual = JAR_PATH.stat().st_size
    if actual != JAR_SIZE:
        raise RuntimeError(f"downloaded jar size {actual} != expected {JAR_SIZE}; download may be corrupt")
    print(f"[run_synthea] downloaded jar ({actual} bytes)")
    return JAR_PATH


def write_properties() -> Path:
    RAW_DIR.mkdir(parents=True, exist_ok=True)
    JAR_DIR.mkdir(parents=True, exist_ok=True)
    lines = [
        "exporter.csv.export = true",
        "exporter.csv.included_files = patients.csv,conditions.csv",
        "exporter.fhir.export = false",
        f"exporter.baseDirectory = {RAW_DIR.as_posix()}/",
    ]
    PROPERTIES_PATH.write_text("\n".join(lines) + "\n")
    return PROPERTIES_PATH


def load_config() -> dict:
    return json.loads(CONFIG_PATH.read_text())


def run(population_size: int | None = None) -> None:
    config = load_config()
    pop = population_size or config["population_size"]
    jar = ensure_jar()
    props = write_properties()
    cmd = [
        "java", "-jar", str(jar),
        "-p", str(pop),
        "-s", str(config["seed"]),
        "-cs", str(config["clinician_seed"]),
        "-r", str(config["reference_date"]),
        "-c", str(props),
        config["state"],
    ]
    if config.get("city"):
        cmd.append(config["city"])
    print(f"[run_synthea] running: {' '.join(cmd)}")
    subprocess.run(cmd, check=True, cwd=ROOT)
    print(f"[run_synthea] done, raw CSVs under {RAW_DIR / 'csv'}")


if __name__ == "__main__":
    pop_override = int(sys.argv[1]) if len(sys.argv) > 1 else None
    run(pop_override)
