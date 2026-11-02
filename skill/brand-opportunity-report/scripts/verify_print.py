#!/usr/bin/env python3
"""Print-readiness checks for finished brand-check PDFs.

Every failure here has actually shipped or nearly shipped at some point:
non-embedded Helvetica from a missing font weight, Apple Color Emoji as a
Type 3 bitmap font, a CTA with nothing a reader can act on in print.

Usage: python3 verify_print.py FILE.pdf [FILE.pdf ...]
Exit code is non-zero if any file fails a hard check.
"""
import glob
import os
import re
import subprocess
import sys

MM = 72 / 25.4
A4 = (210, 297)
BLEED_A4 = (216, 303)


def _run(cmd):
    try:
        return subprocess.run(cmd, capture_output=True, text=True,
                              timeout=120).stdout
    except Exception:
        return ""


def check_fonts(path):
    """Every glyph must travel with the file, and none as a Type 3 bitmap."""
    out = _run(["pdffonts", path])
    problems, names = [], []
    for line in out.splitlines()[2:]:
        parts = line.split()
        if len(parts) < 6:
            continue
        name, ftype = parts[0], " ".join(parts[1:-5])
        emb = parts[-5]
        names.append(name)
        if emb == "no":
            problems.append(f"font not embedded: {name}")
        if "Type 3" in ftype:
            problems.append(f"Type 3 bitmap font (will not print cleanly): {name}")
        if "Helvetica" in name and emb == "no":
            problems.append(f"Helvetica substitution: {name}")
    if not names:
        problems.append("no fonts found at all (is this a real PDF?)")
    return problems, names


def check_geometry(path):
    import fitz
    problems, sizes = [], []
    d = fitz.open(path)
    for i, p in enumerate(d):
        w, h = round(p.rect.width / MM), round(p.rect.height / MM)
        sizes.append((w, h))
        ok_trim = abs(w - A4[0]) <= 1 and abs(h - A4[1]) <= 1
        ok_bleed = abs(w - BLEED_A4[0]) <= 1 and abs(h - BLEED_A4[1]) <= 1
        if not (ok_trim or ok_bleed):
            problems.append(f"page {i+1} is {w}x{h}mm, not A4 or A4+bleed")
    d.close()
    return problems, sizes


def check_qr(path):
    """A mailed piece needs a code that actually resolves."""
    try:
        import cv2
    except ImportError:
        return ["cannot verify QR (opencv not installed)"], None
    tmp = "/tmp/_vp_qr"
    for f in glob.glob(tmp + "*.png"):
        os.remove(f)
    _run(["pdftoppm", "-r", "300", "-png", path, tmp])
    found = None
    for f in sorted(glob.glob(tmp + "*.png")):
        img = cv2.imread(f)
        if img is None:
            continue
        ok, info, _, _ = cv2.QRCodeDetector().detectAndDecodeMulti(img)
        if ok:
            for s in info:
                if s:
                    found = s
                    break
        if found:
            break
    for f in glob.glob(tmp + "*.png"):
        os.remove(f)
    if not found:
        return ["no scannable QR code found"], None
    if not found.startswith("http"):
        return [f"QR does not hold a URL: {found!r}"], found
    return [], found


EMOJI = re.compile("[\U0001F000-\U0001FAFF\U00002600-\U000027BF"
                   "\U0001F1E6-\U0001F1FF\U0000FE0F]")


def check_text(path):
    txt = _run(["pdftotext", path, "-"])
    problems = []
    hits = sorted(set(EMOJI.findall(txt)))
    if hits:
        problems.append(f"emoji left in printed text: {''.join(hits)}")
    if "[X]" in txt or "{{" in txt or "{brand}" in txt:
        problems.append("unfilled placeholder left in the copy")
    return problems, len(txt)


def main(paths):
    failed = 0
    for path in paths:
        print(f"\n=== {os.path.basename(path)} ===")
        if not os.path.exists(path):
            print("  MISSING"); failed += 1; continue
        problems = []
        fp, names = check_fonts(path)
        gp, sizes = check_geometry(path)
        qp, qr = check_qr(path)
        tp, nchars = check_text(path)
        problems += fp + gp + qp + tp
        print(f"  pages     {len(sizes)} at {sizes[0][0]}x{sizes[0][1]}mm"
              if sizes else "  pages     none")
        print(f"  fonts     {len(names)} embedded: {', '.join(n.split('+')[-1] for n in names)}")
        print(f"  QR        {qr or 'none'}")
        print(f"  text      {nchars} chars extracted")
        if problems:
            failed += 1
            for p in problems:
                print(f"  FAIL      {p}")
        else:
            print("  PASS      print-ready")
    print(f"\n{len(paths) - failed}/{len(paths)} files print-ready")
    return 1 if failed else 0


if __name__ == "__main__":
    if len(sys.argv) < 2:
        sys.exit(__doc__)
    sys.exit(main(sys.argv[1:]))
