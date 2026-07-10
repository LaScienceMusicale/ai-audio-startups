#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Voyage en Sonocène — Épisode 2 (Corse, secteur Boziu) : « Le chant sans nom »

Détection probabiliste du chant de la grenouille peinte de Corse
(Discoglossus montalentii) dans les archives sonores de Jean-Claude Roché.

Démarche
--------
1. DÉCOMPOSITION DU SIGNAL
   On part d'un enregistrement de référence du chant (la prise de terrain de
   Thibault, cf. https://www.instagram.com/p/Dah3CFAFYwZ/). On segmente les
   cris, on en extrait une « empreinte sonore » : spectrogramme moyen (matched
   filter) + vecteur de descripteurs (fréquence dominante, structure
   harmonique, cadence des pulses, enveloppe temporelle, MFCC).

   La structure HARMONIQUE est le trait diagnostique : le chant de
   D. montalentii est harmonique (proche d'un Bombina), là où les autres
   discoglosses (dont le très proche D. sardus) ont un chant inharmonique.

2. MODÈLE PROBABILISTE
   Deux scores complémentaires, calibrés dans [0, 1] :
     - un filtre adapté (matched filter) : corrélation croisée normalisée du
       spectrogramme de référence contre chaque fenêtre glissante de l'archive ;
     - une vraisemblance one-class (Gaussienne / GMM) apprise sur les
       descripteurs des cris de référence (on ne dispose que de positifs).
   Les deux scores sont fusionnés en une probabilité de détection.

3. BALAYAGE DES ARCHIVES ROCHÉ
   Fenêtre glissante sur chaque enregistrement, suppression des non-maxima,
   on conserve les pics.

4. INSTANCES > 90 % → ÉCOUTE
   Toute détection de probabilité >= 0.90 est exportée en clip .wav + fiche
   (fichier source, horodatage, probabilité) pour écoute humaine.

   Enjeu narratif : D. montalentii n'a été décrite qu'en 1984. Une occurrence
   retrouvée dans une bande Roché antérieure serait un chant capté avant que la
   science ne nomme l'espèce.

Usage
-----
    # 1. Construire l'empreinte à partir de l'enregistrement de référence
    python detect_grenouille_corse.py fit \
        --reference refs/thibault_boziu.wav \
        --model empreinte_montalentii.npz

    # 2. Balayer un panel d'archives Roché et exporter les instances > 90 %
    python detect_grenouille_corse.py scan \
        --model empreinte_montalentii.npz \
        --archive archives_roche/ \
        --out detections/ \
        --threshold 0.90

Dépendances : voir requirements.txt (numpy, scipy, librosa, soundfile, scikit-learn).
"""

from __future__ import annotations

import argparse
import json
import os
import sys
from dataclasses import dataclass, asdict
from glob import glob
from typing import List, Tuple

import numpy as np

# Imports lourds isolés pour un message d'erreur clair si l'environnement
# n'est pas prêt (le pipeline reste lisible sans eux installés).
try:
    import librosa
    import soundfile as sf
except ImportError as exc:  # pragma: no cover
    print(
        "Dépendances manquantes : installez-les avec\n"
        "    pip install -r requirements.txt\n"
        f"(détail : {exc})",
        file=sys.stderr,
    )
    raise


# --------------------------------------------------------------------------- #
# Paramètres acoustiques
# --------------------------------------------------------------------------- #

@dataclass
class Params:
    """Paramètres d'analyse, calés sur l'écologie acoustique de l'espèce.

    D. montalentii : espèce montagnarde, chant nocturne, énergie principale
    dans les basses/moyennes fréquences avec harmoniques. On borne l'analyse
    pour rester robuste au bruit de ruisseau (large bande) et aux stridulations
    d'orthoptères (hautes fréquences).
    """
    sr: int = 22050              # fréquence d'échantillonnage de travail
    n_fft: int = 1024
    hop: int = 256
    fmin: float = 200.0          # Hz — sous le chant, on coupe le grondement d'eau
    fmax: float = 4000.0         # Hz — au-dessus, on coupe les insectes
    win_sec: float = 0.60        # durée d'une fenêtre d'analyse (≈ un cri)
    hop_sec: float = 0.10        # pas de la fenêtre glissante
    nms_sec: float = 0.40        # rayon de suppression des non-maxima
    export_pad_sec: float = 0.75 # marge autour d'un clip exporté pour l'écoute


# Position de la tonalité de pic dans le vecteur de descripteurs (cf. call_features).
TONAL_IDX = 3


# --------------------------------------------------------------------------- #
# Décomposition du signal
# --------------------------------------------------------------------------- #

def load_audio(path: str, sr: int) -> np.ndarray:
    """Charge un fichier audio en mono, ré-échantillonné, normalisé."""
    y, _ = librosa.load(path, sr=sr, mono=True)
    if y.size == 0:
        raise ValueError(f"Fichier vide : {path}")
    peak = np.max(np.abs(y))
    return y / peak if peak > 0 else y


def logmel(y: np.ndarray, p: Params) -> np.ndarray:
    """Spectrogramme mel logarithmique, borné en fréquence (l'empreinte visuelle)."""
    S = librosa.feature.melspectrogram(
        y=y, sr=p.sr, n_fft=p.n_fft, hop_length=p.hop,
        fmin=p.fmin, fmax=p.fmax, n_mels=48, power=2.0,
    )
    return librosa.power_to_db(S, ref=np.max)


def peak_tonality(y: np.ndarray, p: Params) -> float:
    """Tonalité de la trame la plus tonale de la fenêtre, dans [0, 1].

    Trait diagnostique de D. montalentii : son chant est harmonique/tonal
    (proche d'un Bombina), là où les autres discoglosses et le bruit de ruisseau
    sont inharmoniques/large bande. On mesure la tonalité par 1 - platitude
    spectrale (Wiener entropy) et l'on retient la trame la plus tonale : un cri
    n'occupe qu'une partie de la fenêtre, le bruit d'eau n'est jamais tonal.
    """
    S = np.abs(librosa.stft(y, n_fft=p.n_fft, hop_length=p.hop))
    freqs = librosa.fft_frequencies(sr=p.sr, n_fft=p.n_fft)
    band = (freqs >= p.fmin) & (freqs <= p.fmax)
    flat = librosa.feature.spectral_flatness(S=S[band] + 1e-10)[0]
    return float(1.0 - np.min(flat))


def call_features(y: np.ndarray, p: Params) -> np.ndarray:
    """Vecteur de descripteurs d'un cri (une fenêtre d'analyse).

    Combine : fréquence dominante, centroïde et bande spectrale, tonalité de
    pic (trait diagnostique), cadence des pulses (via l'enveloppe), et 13 MFCC
    (timbre).
    """
    S = np.abs(librosa.stft(y, n_fft=p.n_fft, hop_length=p.hop))
    freqs = librosa.fft_frequencies(sr=p.sr, n_fft=p.n_fft)
    band = (freqs >= p.fmin) & (freqs <= p.fmax)
    Sb, fb = S[band], freqs[band]

    spectrum = Sb.mean(axis=1) + 1e-12
    f_dom = float(fb[np.argmax(spectrum)])
    centroid = float(np.sum(fb * spectrum) / np.sum(spectrum))
    bandwidth = float(np.sqrt(np.sum(((fb - centroid) ** 2) * spectrum) / np.sum(spectrum)))

    # Cadence des pulses : rythme de l'enveloppe d'énergie du cri.
    env = librosa.onset.onset_strength(y=y, sr=p.sr, hop_length=p.hop)
    if env.size > 4 and np.any(env > 0):
        ac = librosa.autocorrelate(env)
        ac[0] = 0
        lag = int(np.argmax(ac[1:]) + 1)
        pulse_rate = float(p.sr / p.hop / lag) if lag > 0 else 0.0
    else:
        pulse_rate = 0.0

    mfcc = librosa.feature.mfcc(y=y, sr=p.sr, n_mfcc=13,
                                n_fft=p.n_fft, hop_length=p.hop).mean(axis=1)

    return np.concatenate([
        [f_dom, centroid, bandwidth, peak_tonality(y, p), pulse_rate],
        mfcc,
    ]).astype(np.float64)


def segment_calls(y: np.ndarray, p: Params) -> List[Tuple[int, int]]:
    """Segmente les cris de l'enregistrement de référence via détection d'onsets."""
    onsets = librosa.onset.onset_detect(
        y=y, sr=p.sr, hop_length=p.hop, units="samples", backtrack=True,
    )
    win = int(p.win_sec * p.sr)
    # Période réfractaire : on fusionne les onsets trop proches pour ne pas
    # déclencher sur chaque pulse d'un même cri (un cri = une fenêtre).
    refractory = int(0.5 * p.win_sec * p.sr)
    segments = []
    last = -refractory
    for start in onsets:
        if start - last < refractory:
            continue
        end = min(start + win, len(y))
        if end - start >= win // 2:
            segments.append((int(start), int(end)))
            last = start
    # Repli : si aucun onset net, on tronçonne régulièrement.
    if not segments:
        step = win
        segments = [(s, min(s + win, len(y))) for s in range(0, len(y) - win // 2, step)]
    return segments


# --------------------------------------------------------------------------- #
# Modèle probabiliste
# --------------------------------------------------------------------------- #

@dataclass
class Empreinte:
    """Empreinte sonore = filtre adapté + modèle statistique des descripteurs.

    Les deux scores (filtre adapté, vraisemblance) sont calibrés à partir de la
    distribution observée sur les cris de RÉFÉRENCE : on mémorise la médiane et
    l'échelle de chacun, pour qu'un vrai positif sature près de 1.
    """
    template: np.ndarray      # spectrogramme mel de référence (normalisé)
    feat_mean: np.ndarray     # moyenne des descripteurs (rapport, journal)
    feat_std: np.ndarray      # écart-type des descripteurs
    mf_center: float          # point 50 % du calibrage du filtre adapté
    mf_scale: float           # échelle (raideur) du calibrage du filtre adapté
    tonal_center: float       # point 50 % du calibrage de la tonalité
    tonal_scale: float        # échelle du calibrage de la tonalité
    params: dict

    def save(self, path: str) -> None:
        np.savez_compressed(path, **{k: np.asarray(v, dtype=object)
                                     if k == "params" else np.asarray(v)
                                     for k, v in asdict(self).items()})

    @staticmethod
    def load(path: str) -> "Empreinte":
        d = np.load(path, allow_pickle=True)
        return Empreinte(
            template=d["template"], feat_mean=d["feat_mean"], feat_std=d["feat_std"],
            mf_center=float(d["mf_center"]), mf_scale=float(d["mf_scale"]),
            tonal_center=float(d["tonal_center"]), tonal_scale=float(d["tonal_scale"]),
            params=d["params"].item(),
        )


def _calibrate(x: float, center: float, scale: float) -> float:
    """Sigmoïde : 0.5 au point `center`, croissante, saturant vers 1 au-dessus.

    `center` est le seuil de bascule (50 %), calé sous la distribution des vrais
    positifs de référence ; `scale` fixe la raideur. L'argument est borné pour
    éviter tout dépassement de exp().
    """
    arg = np.clip((x - center) / (scale + 1e-9), -30.0, 30.0)
    return float(1.0 / (1.0 + np.exp(-arg)))


def fit(reference_path: str, model_path: str, p: Params) -> Empreinte:
    """Construit l'empreinte à partir de l'enregistrement de référence."""
    y = load_audio(reference_path, p.sr)
    segments = segment_calls(y, p)
    if len(segments) < 2:
        raise ValueError(
            "Trop peu de cris détectés dans la référence — fournir un "
            "enregistrement plus long ou plus propre."
        )
    print(f"[fit] {len(segments)} cris segmentés dans la référence.")

    # Filtre adapté : spectrogramme mel moyen des cris, normalisé (moyenne 0, norme 1).
    mels = [logmel(y[s:e], p) for s, e in segments]
    width = min(m.shape[1] for m in mels)
    template = np.mean([m[:, :width] for m in mels], axis=0)
    template = template - template.mean()
    template /= (np.linalg.norm(template) + 1e-12)

    # Descripteurs des cris → statistiques (rapport, calibrage harmonique).
    feats = np.vstack([call_features(y[s:e], p) for s, e in segments])
    mean, std = feats.mean(axis=0), feats.std(axis=0)

    # Calibrage du filtre adapté : distribution de la corrélation des cris de
    # référence contre le template. On place le point de bascule sous cette
    # distribution pour accepter les vrais positifs, plus bruités sur le terrain.
    mf = np.array([_matched_filter_score(m[:, :width], template) for m in mels])
    mf_med, mf_sd = float(np.median(mf)), float(max(np.std(mf), 0.05))
    mf_center = mf_med - 0.5 * mf_sd
    mf_scale = 0.6 * mf_sd

    # Calibrage de la tonalité (trait diagnostique de l'espèce). Idem : bascule
    # sous la distribution de référence, pente réglée par l'écart-type (planché).
    tonal = feats[:, TONAL_IDX]
    t_med, t_sd = float(np.median(tonal)), float(max(np.std(tonal), 0.06))
    tonal_center = t_med - 1.5 * t_sd
    tonal_scale = 0.5 * t_sd

    emp = Empreinte(
        template=template, feat_mean=mean, feat_std=std,
        mf_center=mf_center, mf_scale=mf_scale,
        tonal_center=tonal_center, tonal_scale=tonal_scale,
        params=asdict(p),
    )
    emp.save(model_path)
    print(f"[fit] Empreinte enregistrée → {model_path}  "
          f"(filtre: bascule={mf_center:.2f} | tonalité: bascule={tonal_center:.2f})")
    return emp


def _matched_filter_score(mel_win: np.ndarray, template: np.ndarray) -> float:
    """Corrélation croisée normalisée dans [0, 1] entre une fenêtre et le modèle."""
    w = min(mel_win.shape[1], template.shape[1])
    a = mel_win[:, :w] - mel_win[:, :w].mean()
    b = template[:, :w] - template[:, :w].mean()
    denom = np.linalg.norm(a) * np.linalg.norm(b) + 1e-12
    return float(np.clip(np.sum(a * b) / denom, 0.0, 1.0))


def _tonality_score(feat: np.ndarray, emp: Empreinte) -> float:
    """Probabilité de tonalité compatible avec l'espèce, dans [0, 1].

    La tonalité du chant de D. montalentii est son trait diagnostique (chant
    harmonique/tonal, proche d'un Bombina, vs chant inharmonique des autres
    discoglosses et du bruit d'eau). Un cri franchement inharmonique est rejeté.
    """
    return _calibrate(float(feat[TONAL_IDX]), emp.tonal_center, emp.tonal_scale)


def probability(mel_win: np.ndarray, feat: np.ndarray, emp: Empreinte) -> float:
    """Probabilité de détection = fusion (moyenne géométrique) des deux évidences.

    La moyenne géométrique est sévère : la FORME spectrale (filtre adapté) ET la
    TONALITÉ doivent concorder pour approcher 1. Un ruisseau dont le spectre
    « ressemble » mais sans tonalité est rejeté, et un son tonal de mauvaise
    forme spectrale (autre oiseau/amphibien) l'est aussi.
    """
    s_mf = _calibrate(_matched_filter_score(mel_win, emp.template), emp.mf_center, emp.mf_scale)
    s_tonal = _tonality_score(feat, emp)
    return float(np.sqrt(max(s_mf, 0.0) * max(s_tonal, 0.0)))


# --------------------------------------------------------------------------- #
# Balayage des archives
# --------------------------------------------------------------------------- #

@dataclass
class Detection:
    fichier: str
    debut_sec: float
    fin_sec: float
    probabilite: float


def scan_file(path: str, emp: Empreinte,
              p: Params, threshold: float) -> List[Detection]:
    """Fenêtre glissante sur un enregistrement + suppression des non-maxima."""
    y = load_audio(path, p.sr)
    win = int(p.win_sec * p.sr)
    hop = int(p.hop_sec * p.sr)
    if len(y) < win:
        return []

    scores, centers = [], []
    for start in range(0, len(y) - win + 1, hop):
        seg = y[start:start + win]
        mel = logmel(seg, p)
        feat = call_features(seg, p)
        prob = probability(mel, feat, emp)
        scores.append(prob)
        centers.append(start + win // 2)

    scores = np.asarray(scores)
    centers = np.asarray(centers)

    # Suppression des non-maxima : un pic par voisinage, au-dessus du seuil.
    nms_rad = int(p.nms_sec * p.sr)
    dets: List[Detection] = []
    order = np.argsort(scores)[::-1]
    taken = np.zeros(len(scores), dtype=bool)
    for i in order:
        if scores[i] < threshold or taken[i]:
            continue
        keep = np.abs(centers - centers[i]) < nms_rad
        taken |= keep
        c = centers[i]
        dets.append(Detection(
            fichier=os.path.basename(path),
            debut_sec=round(max(0, c - win // 2) / p.sr, 2),
            fin_sec=round(min(len(y), c + win // 2) / p.sr, 2),
            probabilite=round(float(scores[i]), 4),
        ))
    dets.sort(key=lambda d: d.debut_sec)
    return dets


def export_clip(src_path: str, det: Detection, out_dir: str, p: Params) -> str:
    """Exporte un clip .wav autour d'une détection, pour écoute humaine."""
    y = load_audio(src_path, p.sr)
    a = max(0, int((det.debut_sec - p.export_pad_sec) * p.sr))
    b = min(len(y), int((det.fin_sec + p.export_pad_sec) * p.sr))
    stem = os.path.splitext(det.fichier)[0]
    name = f"{stem}__{det.debut_sec:07.2f}s__p{int(det.probabilite * 100):03d}.wav"
    out = os.path.join(out_dir, name)
    sf.write(out, y[a:b], p.sr)
    return out


def scan_archive(model_path: str, archive: str, out_dir: str,
                 threshold: float, p: Params) -> List[Detection]:
    """Balaie un panel d'archives, exporte les instances >= seuil, écrit un rapport."""
    emp = Empreinte.load(model_path)
    os.makedirs(out_dir, exist_ok=True)

    exts = ("*.wav", "*.flac", "*.aiff", "*.aif", "*.mp3", "*.ogg")
    files = sorted(
        f for pat in exts
        for f in (glob(os.path.join(archive, "**", pat), recursive=True)
                  if os.path.isdir(archive) else [archive] * (archive.endswith(pat[1:])))
        if os.path.isfile(f)
    )
    if not files:
        print(f"[scan] Aucun fichier audio trouvé dans {archive}", file=sys.stderr)
        return []
    print(f"[scan] {len(files)} enregistrements à analyser (seuil = {threshold:.0%}).")

    all_dets: List[Detection] = []
    for i, f in enumerate(files, 1):
        try:
            dets = scan_file(f, emp, p, threshold)
        except Exception as exc:  # un fichier corrompu ne doit pas tout arrêter
            print(f"[scan] ! {os.path.basename(f)} ignoré ({exc})", file=sys.stderr)
            continue
        for d in dets:
            export_clip(f, d, out_dir, p)
        all_dets.extend(dets)
        flag = f"  → {len(dets)} instance(s) > {threshold:.0%}" if dets else ""
        print(f"[scan] ({i}/{len(files)}) {os.path.basename(f)}{flag}")

    all_dets.sort(key=lambda d: d.probabilite, reverse=True)
    report = os.path.join(out_dir, "detections.json")
    with open(report, "w", encoding="utf-8") as fh:
        json.dump([asdict(d) for d in all_dets], fh, ensure_ascii=False, indent=2)

    print(f"\n[scan] {len(all_dets)} instance(s) >= {threshold:.0%} exportée(s) dans {out_dir}/")
    print(f"[scan] Rapport : {report}")
    if all_dets:
        print("[scan] À écouter en priorité :")
        for d in all_dets[:10]:
            print(f"        {d.probabilite:.0%}  {d.fichier}  @ {d.debut_sec:.1f}s")
    return all_dets


# --------------------------------------------------------------------------- #
# CLI
# --------------------------------------------------------------------------- #

def main(argv=None) -> int:
    parser = argparse.ArgumentParser(
        description="Détection probabiliste du chant de la grenouille corse "
                    "(Discoglossus montalentii) dans les archives Roché.")
    sub = parser.add_subparsers(dest="cmd", required=True)

    pf = sub.add_parser("fit", help="Construire l'empreinte depuis la référence.")
    pf.add_argument("--reference", required=True, help="Enregistrement de référence (.wav).")
    pf.add_argument("--model", default="empreinte_montalentii.npz", help="Fichier d'empreinte de sortie.")

    ps = sub.add_parser("scan", help="Balayer un panel d'archives et exporter les >90%.")
    ps.add_argument("--model", required=True, help="Fichier d'empreinte (issu de 'fit').")
    ps.add_argument("--archive", required=True, help="Dossier (ou fichier) d'archives Roché.")
    ps.add_argument("--out", default="detections", help="Dossier de sortie (clips + rapport).")
    ps.add_argument("--threshold", type=float, default=0.90, help="Seuil de probabilité (défaut 0.90).")

    args = parser.parse_args(argv)
    p = Params()

    if args.cmd == "fit":
        fit(args.reference, args.model, p)
    elif args.cmd == "scan":
        scan_archive(args.model, args.archive, args.out, args.threshold, p)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
