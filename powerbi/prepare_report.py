"""Extract the saved report resources and preserve its local model cache."""
from pathlib import Path
import json
import shutil
import zipfile

ROOT = Path(__file__).resolve().parent
source = ROOT / "olist_ecommerce_analysis.pbix"
backup = ROOT / "backups" / "olist_before_completion.pbix"
backup.parent.mkdir(exist_ok=True)
if not backup.exists():
    shutil.copy2(source, backup)
report = ROOT / "Olist.Report"
with zipfile.ZipFile(source) as archive:
    for name in archive.namelist():
        if name.startswith("Report/"):
            target = report / name.removeprefix("Report/")
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_bytes(archive.read(name))
    cache = ROOT / "Olist.SemanticModel/.pbi/cache.abf"
    cache.parent.mkdir(exist_ok=True)
    data = archive.read("DataModel")
    cache.write_bytes(data)
    print("Model cache:", len(data), "bytes; header:", repr(data[:96]))
print("Existing PBIX preserved:", backup)
