import os
import json

def scan():
    print("🔍 Scanning DirectorX folder for video generation entry points...")
    for r, ds, fs in os.walk("."):
        if "output" in r or ".git" in r: continue
        for f_name in fs:
            if f_name.endswith((".py", ".json")):
                path = os.path.join(r, f_name)
                try:
                    with open(path, "r", encoding="utf-8") as file:
                        content = file.read()
                        if "video" in content.lower() or "animate" in content.lower() or "vhs" in content.lower():
                            print(f"📁 Match found: {path}")
                except: pass

if __name__ == "__main__": scan()
