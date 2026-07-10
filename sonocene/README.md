# Voyage en Sonocène

Dépôt de travail du dossier de la série documentaire **« Voyage en Sonocène »**
(5 × 24′) et de son volet scientifique « science musicale ».

Thibault Noirot, jeune audio-naturaliste, part sur les traces de **Jean Roché**,
fondateur de l'audio-naturalisme français. Il retourne exactement là où Roché a
posé son micro un demi-siècle plus tôt, réenregistre chaque paysage sonore et le
compare à l'original, pour mesurer la métamorphose du vivant — entre science et
musique, et pour nous apprendre à écouter.

---

## 1. Les contraintes du dossier *(check-list)*

> On commence par les contraintes, puis vient le dossier lui-même.

**Partie éditoriale** → [`dossier/01-partie-edito.md`](dossier/01-partie-edito.md)

- [x] Titre et format (durée et nombre d'épisodes)
- [x] Résumé court présentant la série (≤ 1200 caractères)
- [x] Note d'intention et de réalisation
- [x] Synopsis du pilote envisagé
- [x] Court résumé de chacun des autres épisodes (≤ 1200 caractères / épisode)
- [ ] Moodboard *(si pertinent)* — à fournir
- [ ] Filmographie et CV des auteur·ice·s et réal — à fournir

**Partie production** → [`dossier/02-partie-production.md`](dossier/02-partie-production.md)

- [ ] Note de production
- [ ] Lettre de candidature (société unique ; nom, coordonnées tél./postales/
      courriel du·de la responsable du dossier)
- [ ] Filmographie de la société de production
- [ ] Budget et plan de financement prévisionnels — développement (incl. pilote)
- [ ] Budget et plan de financement prévisionnels — production de la série

**Partie administrative** → [`dossier/03-partie-admin.md`](dossier/03-partie-admin.md)

- [ ] Lettre introductive et de confidentialité
- [ ] Extrait K-bis de moins de trois mois
- [ ] Chiffres d'affaires globaux, bilans, comptes de résultats et annexes
      comptables (ou équivalents reconnus)

*(État au dépôt : partie éditoriale rédigée ; production et administratif à
compléter par la société.)*

---

## 2. Le dossier

| Partie | Fichier |
|---|---|
| Éditoriale | [`dossier/01-partie-edito.md`](dossier/01-partie-edito.md) |
| Production | [`dossier/02-partie-production.md`](dossier/02-partie-production.md) |
| Administrative | [`dossier/03-partie-admin.md`](dossier/03-partie-admin.md) |

**Retour éditorial & production** sur le dossier :
[`RETOUR-DOSSIER.md`](RETOUR-DOSSIER.md)

---

## 3. Volet scientifique — la grenouille corse

L'épisode 2 (Corse) repose sur une vraie démarche d'analyse du signal, prototypée
ici : décomposition du chant de la **grenouille peinte de Corse**
(*Discoglossus montalentii*) et **modèle probabiliste** pour détecter ses
éventuelles occurrences dans les archives de Roché, puis extraire les instances
dépassant **90 %** pour les écouter.

→ [`grenouille-corse/`](grenouille-corse/README.md) — méthodologie, code et test.

---

## Arborescence

```
sonocene/
├── README.md                     ← vous êtes ici (contraintes + sommaire)
├── RETOUR-DOSSIER.md             ← retour éditorial & production
├── dossier/
│   ├── 01-partie-edito.md
│   ├── 02-partie-production.md
│   └── 03-partie-admin.md
└── grenouille-corse/             ← volet « science musicale » (épisode 2)
    ├── README.md                 ← la démarche expliquée
    ├── detect_grenouille_corse.py
    ├── selftest.py
    └── requirements.txt
```
