"""Stable anonymous ids (S01..S58) and made-up names for the public edition.

The id order is the salted hash the paper uses. Pseudonyms come from mixed lists of first and last names; none
equals any real name in the four-section gallery, and no student keeps their own first or last name.
"""
import hashlib
import json
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parents[1]
FIRST = """Maya Leo Priya Sam Nadia Omar Grace Kenji Lucia Arjun Hana Mateo Zara Felix Amara Theo Ines Ravi Sofia Jonah
Leila Marco Aiko Daniel Esme Tariq Clara Hugo Mei Noah Anya Diego Freya Kofi Lena Ivan Ruth Kai Selin Jamal Nora Elias
Yuki Bruno Alma Rohan Talia Victor Kira Simon Lina Oscar Dana Malik Iris Pablo Wren Amir Elena Tomas Mira Joel""".split()
LAST = """Chen Okafor Larsen Patel Moreau Kim Alvarez Nakamura Rossi Haddad Novak Mensah Silva Ibrahim Walsh Tanaka Costa
Fischer Reyes Banerjee Olsen Petrov Abara Lindqvist Duarte Sato Kaur Brennan Yilmaz Mwangi Dubois Ortega Hoang Weber
Castillo Adeyemi Lund Varga Mori Santos Klein Osei Marsh Herrera Bauer Quinn Farah Lopez Kowalski Ito Navarro Hale""".split()


def load():
    portal = json.loads((ROOT / "data" / "portal" / "portal.json").read_text())
    roster = portal["roster"]
    order = sorted(roster, key=lambda r: hashlib.sha256(("SALT-NOT-PUBLISHED" + r["id"]).encode()).hexdigest())
    sid = {r["name"]: f"S{i + 1:02d}" for i, r in enumerate(order)}
    real = {str(n) for n in np.load(ROOT / "data" / "media" / "2026-10-08-core-section-a" / "gallery.npz")["names"]}
    real_parts = {p.lower() for n in real for p in n.split()}
    used, fake = set(), {}
    for r in order:
        own = {p.lower() for p in r["name"].split()}
        h = int(hashlib.sha256(("SALT-NOT-PUBLISHED" + r["id"]).encode()).hexdigest(), 16)
        for k in range(len(FIRST) * len(LAST)):
            f = FIRST[(h + k) % len(FIRST)]
            l_ = LAST[(h // 97 + k * 7) % len(LAST)]
            name = f"{f} {l_}"
            if (name not in real and name not in used and f not in {u.split()[0] for u in used}
                    and f.lower() not in own and l_.lower() not in own and l_.lower() not in real_parts):
                break
        used.add(name)
        fake[r["name"]] = name
    return portal, sid, fake


if __name__ == "__main__":
    _, sid, fake = load()
    for real_name in sorted(sid, key=sid.get)[:5]:
        print(sid[real_name], fake[real_name])
    print(len(set(fake.values())), "unique pseudonyms")
