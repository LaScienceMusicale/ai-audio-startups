#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Test de bout en bout, sans données réelles.

Synthétise un chant harmonique « type montalentii », une référence et une
archive factice (chant noyé dans du bruit de ruisseau + un leurre
inharmonique), puis vérifie que fit() puis scan_archive() retrouvent les
occurrences au-dessus du seuil. Sert de garde-fou au pipeline.

    python selftest.py
"""
import os
import tempfile

import numpy as np
import soundfile as sf

import detect_grenouille_corse as d


SR = 22050


def synth_call(rng, harmonic=True, f0=700.0, dur=0.45):
    """Un cri : suite de pulses. Harmonique (montalentii) ou bruité (leurre)."""
    t = np.linspace(0, dur, int(dur * SR), endpoint=False)
    env = np.exp(-((t - dur / 2) ** 2) / (2 * (dur / 6) ** 2))
    if harmonic:
        sig = sum((1.0 / k) * np.sin(2 * np.pi * f0 * k * t) for k in range(1, 6))
    else:
        sig = rng.standard_normal(t.size)  # inharmonique = large bande
    # Cadence de pulses ~ 20 Hz
    pulses = 0.5 + 0.5 * np.sign(np.sin(2 * np.pi * 20 * t))
    return (sig * env * pulses).astype(np.float32)


def stream(rng, n_calls, harmonic=True, noise=0.02, gap=(0.6, 1.2)):
    parts = []
    for _ in range(n_calls):
        parts.append(synth_call(rng, harmonic=harmonic,
                                 f0=rng.uniform(650, 760)))
        parts.append(np.zeros(int(rng.uniform(*gap) * SR), dtype=np.float32))
    y = np.concatenate(parts)
    y += noise * rng.standard_normal(y.size).astype(np.float32)  # bruit de ruisseau
    return y / (np.max(np.abs(y)) + 1e-9)


def main():
    rng = np.random.default_rng(0)
    work = tempfile.mkdtemp(prefix="sonocene_selftest_")
    ref = os.path.join(work, "reference.wav")
    arch = os.path.join(work, "archives")
    out = os.path.join(work, "detections")
    os.makedirs(arch, exist_ok=True)

    # Référence : le chant de Thibault (propre, harmonique).
    sf.write(ref, stream(rng, 8, harmonic=True, noise=0.01), SR)

    # Archive Roché #1 : contient 3 occurrences de la grenouille corse.
    sf.write(os.path.join(arch, "roche_corse_1971.wav"),
             stream(rng, 3, harmonic=True, noise=0.05), SR)
    # Archive Roché #2 : un leurre inharmonique (autre discoglosse / eau).
    sf.write(os.path.join(arch, "roche_leurre.wav"),
             stream(rng, 4, harmonic=False, noise=0.05), SR)

    p = d.Params()
    model = os.path.join(work, "empreinte.npz")
    d.fit(ref, model, p)
    dets = d.scan_archive(model, arch, out, threshold=0.90, p=p)
    # relire l'empreinte pour vérifier la sérialisation
    _ = d.Empreinte.load(model)

    corse = [x for x in dets if "corse" in x.fichier]
    leurre = [x for x in dets if "leurre" in x.fichier]
    print(f"\n[selftest] détections chant corse (attendu >=1) : {len(corse)}")
    print(f"[selftest] détections sur le leurre (attendu 0)   : {len(leurre)}")

    assert corse, "Aucune occurrence retrouvée dans l'archive positive."
    assert not leurre, "Faux positif sur le leurre inharmonique."
    assert all(x.probabilite >= 0.90 for x in dets), "Seuil non respecté."
    print("\n[selftest] OK — le pipeline détecte le chant et rejette le leurre.")


if __name__ == "__main__":
    main()
