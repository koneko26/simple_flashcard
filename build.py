"""Build a standalone Flashcards.exe using PyInstaller.

Usage:
    python build.py

Produces:
    dist/Flashcards.exe   - the standalone executable
    dist/cards.csv        - editable card data (learned flags reset)
    dist/README.txt       - usage notes for the recipient
    Flashcards.zip        - the entire dist/ folder zipped for sharing
"""
import csv
import os
import shutil
import struct
import subprocess
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
SOURCE = os.path.join(HERE, "flashcard.pyw")
APP_NAME = "Flashcards"
ICON_PATH = os.path.join(HERE, "icon.ico")
CARDS_SRC = os.path.join(HERE, "cards.csv")
DIST_DIR = os.path.join(HERE, "dist")
BUILD_DIR = os.path.join(HERE, "build")
SPEC_PATH = os.path.join(HERE, f"{APP_NAME}.spec")
ZIP_PATH = os.path.join(HERE, APP_NAME)  # make_archive adds .zip

README_TEXT = """Flashcards
============

How to start
------------
Double-click Flashcards.exe.
No installation required.

How to add or edit cards
------------------------
Open cards.csv with Excel or any text editor.

Columns:
    english   - the English sentence
    japanese  - the Japanese translation
    category  - any tag for grouping (e.g. travel, business)
    active    - 1 to include this card, 0 to skip
    learned   - 1 if memorized (auto-updated by the app)

Save the file, then restart the app to reload.

Need help?
----------
Click the [ ? ] button at the top of the window, or press F1.
"""


def ensure_pyinstaller():
    try:
        import PyInstaller  # noqa: F401
        return
    except ImportError:
        pass
    print(">> Installing PyInstaller...")
    subprocess.check_call(
        [sys.executable, "-m", "pip", "install", "--quiet", "pyinstaller"]
    )


def write_icon(path, size=32):
    """Write a 32x32 .ico file (blue square with white 'F') using only stdlib."""
    blue = (0xF6, 0x6D, 0x2F, 0xFF)   # BGRA for #2f6df6
    white = (0xFF, 0xFF, 0xFF, 0xFF)
    pixels = [blue] * (size * size)

    for y in range(size):
        for x in range(size):
            in_vbar = 10 <= x <= 14 and 7 <= y <= 25
            in_top = 10 <= x <= 23 and 7 <= y <= 11
            in_mid = 10 <= x <= 20 and 14 <= y <= 17
            if in_vbar or in_top or in_mid:
                pixels[y * size + x] = white

    # ICO pixel rows are bottom-up
    rows = [pixels[i * size:(i + 1) * size] for i in range(size)]
    rows.reverse()
    pixel_bytes = b"".join(
        struct.pack("BBBB", b, g, r, a)
        for row in rows for (b, g, r, a) in row
    )
    and_mask = bytes(size * size // 8)

    bih = struct.pack(
        "<IIIHHIIIIII",
        40, size, size * 2, 1, 32, 0,
        len(pixel_bytes), 0, 0, 0, 0,
    )
    image_data = bih + pixel_bytes + and_mask
    icondir = struct.pack("<HHH", 0, 1, 1)
    entry = struct.pack(
        "<BBBBHHII",
        size, size, 0, 0, 1, 32, len(image_data), 22,
    )
    with open(path, "wb") as f:
        f.write(icondir + entry + image_data)


def prepare_cards_csv(dst):
    """Copy cards.csv to dst, resetting learned flags so recipients start fresh."""
    if not os.path.isfile(CARDS_SRC):
        return False
    with open(CARDS_SRC, "r", encoding="utf-8-sig", newline="") as f:
        rows = list(csv.DictReader(f))
    for row in rows:
        row["learned"] = "0"
    with open(dst, "w", encoding="utf-8", newline="") as f:
        writer = csv.DictWriter(
            f, fieldnames=["english", "japanese", "category", "active", "learned"],
        )
        writer.writeheader()
        writer.writerows(rows)
    return True


def write_readme(dst):
    with open(dst, "w", encoding="utf-8") as f:
        f.write(README_TEXT)


def clean(*paths):
    for p in paths:
        if os.path.isdir(p):
            shutil.rmtree(p, ignore_errors=True)
        elif os.path.isfile(p):
            try:
                os.remove(p)
            except OSError:
                pass


def build():
    if not os.path.isfile(SOURCE):
        sys.exit(f"ERROR: source not found: {SOURCE}")

    ensure_pyinstaller()
    write_icon(ICON_PATH)
    clean(SPEC_PATH, BUILD_DIR, DIST_DIR, ZIP_PATH + ".zip")

    args = [
        sys.executable, "-m", "PyInstaller",
        "--onefile",
        "--windowed",
        "--name", APP_NAME,
        "--icon", ICON_PATH,
        "--noconfirm",
        "--log-level", "WARN",
        SOURCE,
    ]
    print(">> Running PyInstaller (this can take 1-2 minutes)...")
    subprocess.check_call(args)

    csv_dst = os.path.join(DIST_DIR, "cards.csv")
    readme_dst = os.path.join(DIST_DIR, "README.txt")
    csv_ok = prepare_cards_csv(csv_dst)
    write_readme(readme_dst)

    # Remove intermediate artifacts but keep dist/ and icon
    clean(SPEC_PATH, BUILD_DIR)

    # Zip the dist folder for one-file sharing
    shutil.make_archive(ZIP_PATH, "zip", DIST_DIR)

    exe_path = os.path.join(DIST_DIR, f"{APP_NAME}.exe")
    print()
    print(">> Build complete")
    print(f"   {exe_path}")
    if csv_ok:
        print(f"   {csv_dst}")
    print(f"   {readme_dst}")
    print(f"   {ZIP_PATH}.zip   <- share this file")


if __name__ == "__main__":
    try:
        build()
    except subprocess.CalledProcessError as e:
        sys.exit(f"ERROR: build failed (exit code {e.returncode})")
