"""Read desk name cards in student shots and check them against face matches.

    python analysis/name_cards.py <session_dir> <section> [every_s]

A name card is independent ground truth: if the card under a face and the face match
agree, both are right. Cards are read with Apple's on-device text recognition on zoomed
tiles (the cards are ~10 px tall at 1080p). A card is linked to the nearest face above it.
Writes name_cards.json (aggregates).
"""
import difflib
import json
import sys
from collections import Counter
from pathlib import Path

import cv2
import numpy as np
from ocrmac import ocrmac
from PIL import Image

sess, section = Path(sys.argv[1]), sys.argv[2]
every = float(sys.argv[3]) if len(sys.argv) > 3 else 3.0
g = np.load(sess / "gallery.npz")
names = [str(n) for n in g["names"]]
sections = g["sections"]
f = np.load(sess / "faces.npz")
ft, fbox, fbi, fbs, fss = f["t"], f["box"], f["best_idx"], f["best"], f["second"]
named = (fbs >= 0.50) & ((fbs - fss) >= 0.05)
per_t = Counter(ft.tolist())
crowd_ts = sorted(t for t, n in per_t.items() if n >= 3)
# thin to one frame per `every` seconds
picked, last = [], -1e9
for t in crowd_ts:
    if t - last >= every:
        picked.append(t); last = t
low = [n.lower() for n in names]


def card_name(text):
    s = " ".join(text.split()).lower()
    if len(s) < 5 or " " not in s:
        return None
    m = difflib.get_close_matches(s, low, n=1, cutoff=0.85)
    return low.index(m[0]) if m else None


cap = cv2.VideoCapture(str(sess / "camera.mp4"))
stats = Counter()
card_people, agree_people, wrong_pairs = set(), set(), []
for t in picked:
    cap.set(cv2.CAP_PROP_POS_MSEC, t * 1000)
    ok, img = cap.read()
    if not ok:
        continue
    H, W = img.shape[:2]
    tw, th = 640, 360
    cards = {}
    for y in range(int(H * 0.25), H - th + 1, 270):
        for x in range(0, W - tw + 1, 427):
            crop = cv2.resize(img[y:y + th, x:x + tw], None, fx=3, fy=3, interpolation=cv2.INTER_CUBIC)
            for text, conf, (bx, by, bw, bh) in ocrmac.OCR(Image.fromarray(cv2.cvtColor(crop, cv2.COLOR_BGR2RGB)),
                                                           recognition_level="accurate").recognize():
                k = card_name(text) if conf >= 0.5 else None
                if k is None:
                    continue
                # ocrmac boxes are normalised with origin bottom-left
                cx = x + (bx + bw / 2) * tw
                cy = y + (1 - by - bh / 2) * th
                cards[k] = (cx, cy)
    stats["frames"] += 1
    stats["cards_read"] += len(cards)
    sel = ft == t
    for k, (cx, cy) in cards.items():
        card_people.add(k)
        stats["cards_" + ("in_section" if sections[k] == section else "other_section")] += 1
        best, bd = None, 1e9
        for j in np.where(sel)[0]:
            x, y, w, h = fbox[j]
            fx_, fy_ = x + w / 2, y + h
            if fy_ < cy and abs(fx_ - cx) < 1.5 * w and cy - fy_ < 4 * h:
                d = np.hypot(fx_ - cx, (cy - fy_) / 2)
                if d < bd:
                    best, bd = j, d
        if best is None:
            stats["card_no_face_above"] += 1
            continue
        if not named[best]:
            stats["card_face_unnamed"] += 1
        elif int(fbi[best]) == k:
            stats["card_face_agree"] += 1
            agree_people.add(k)
        else:
            stats["card_face_disagree"] += 1
            wrong_pairs.append((names[k], names[int(fbi[best])], round(float(fbs[best]), 3)))
cap.release()

face_named_sec = {int(i) for i in fbi[named] if sections[int(i)] == section}
card_sec = {k for k in card_people if sections[k] == section}
res = {
    "student_shot_frames_read": stats["frames"],
    "cards_read_total": stats["cards_read"],
    "cards_in_section": stats["cards_in_section"], "cards_other_section": stats["cards_other_section"],
    "distinct_students_with_readable_card": len(card_sec),
    "card_vs_face": {"agree": stats["card_face_agree"], "disagree": stats["card_face_disagree"],
                     "face_not_named": stats["card_face_unnamed"], "no_face_found_above_card": stats["card_no_face_above"]},
    "students_confirmed_by_both": len({k for k in agree_people if sections[k] == section}),
    "students_named_by_face": len(face_named_sec),
    "students_named_by_card_only": len(card_sec - face_named_sec),
    "students_named_by_either": len(card_sec | face_named_sec),
    "disagreements": len(wrong_pairs),
}
(sess / "name_cards.json").write_text(json.dumps(res, indent=2))
(sess / "name_cards_internal.json").write_text(json.dumps({"disagree_pairs_card_face_score": wrong_pairs}, indent=1))
print(json.dumps(res, indent=2))
