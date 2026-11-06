"""Print instructions and dependency status; no installs or secret exposure."""
import shutil
import subprocess
import sys
from pathlib import Path

def version(cmd):
    exe = shutil.which(cmd)
    if not exe:
        return "NOT FOUND"
    try:
        return subprocess.check_output([cmd, "-version" if cmd in {"ffmpeg", "ffprobe"} else "--version"],
                                       text=True, stderr=subprocess.DEVNULL, timeout=4).splitlines()[0]
    except (OSError, subprocess.SubprocessError):
        return "installed (version query unavailable)"

print("NextPhase Shorts — local setup doctor")
print("Python:", sys.version.split()[0])
for name in ("node", "npm", "ffmpeg", "ffprobe", "docker"):
    print(f"{name:8s} {version(name)}")
print("\nREADME.md has setup commands; paid accounts/API keys are NOT needed for Phase 1.")
