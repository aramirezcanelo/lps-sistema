from pathlib import Path
import os

def load_env(path):
    path=Path(path)
    if path.exists():
        for line in path.read_text(encoding="utf-8").splitlines():
            line=line.strip()
            if line and not line.startswith("#") and "=" in line:
                key,value=line.split("=",1)
                os.environ.setdefault(key.strip(),value.strip().strip("\"'"))
