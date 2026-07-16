# 05 — DSP

Le DSP est volontairement classique et conservateur. La difficulté du projet
est la **connexion** (doc 02), pas l'estimation de délai. On prend donc les
méthodes éprouvées, réglées pour le plateau.

## Détection du délai — GCC-PHAT

**GCC-PHAT** (Generalized Cross-Correlation with Phase Transform) plutôt que
corrélation croisée simple : on blanchit le spectre avant la corrélation inverse.

```
R(f)   = X_boom(f) · conj(X_lav(f))
GCC(f) = R(f) / |R(f)|            (phase transform : ne garde que la phase)
c(τ)   = IFFT( GCC(f) )
δ      = argmax_τ c(τ)
```

Pourquoi PHAT : **robuste au bruit de plateau** et à la coloration (le boom et
le lav ont des timbres différents — distance, capsule, proximité). En ne gardant
que la phase, on aligne sur la **structure temporelle** commune, pas sur
l'amplitude, ce qui pique nettement même quand les deux micros « sonnent »
différemment.

## Fenêtre de recherche — ±45 ms

On cherche δ dans **±45 ms** seulement. Justification physique : le retard
boom↔lav vient surtout de la distance micro (~1 ms/34 cm) plus de petits
décalages d'horloge/enregistreur. ±45 ms couvre très large (≈15 m de
séparation) tout en excluant les faux pics lointains.

- Fenêtre étroite = moins de faux positifs, calcul plus rapide.
- La **base timeline commune** (doc 02 §Lien 3) centre la fenêtre au bon endroit
  → on corrèle `boom[t]` contre `lav[t±45ms]`, pas les captures entières.
- Si §1 est rouge (pas de timeline fiable), la fenêtre doit s'élargir → plus de
  risque de faux pic, d'où l'importance du seuil de confiance ci-dessous.

## Délai fractionnaire — interpolé

`argmax` sur la corrélation donne δ au **sample** près. Le vrai décalage est
sous-sample. Deux étages :

1. **Interpolation parabolique** du pic de corrélation → estimation
   sous-sample de δ (raffine l'argmax entier).
2. **Filtre de délai fractionnaire** (interpolation Lagrange / sinc fenêtré)
   pour appliquer la partie fractionnaire à l'audio lav.

Sans ça, on laisse jusqu'à ½ sample d'erreur — audible en peigne quand boom et
lav se somment.

## Latence — constante, déclarée, jamais dynamique

> **La PDC (Plugin Delay Compensation) de MC est fragile.**

- L'insert et l'AudioSuite déclarent une **latence fixe**, connue à la
  compilation.
- **Jamais** de latence qui varie selon le contenu ou le δ estimé. Une latence
  dynamique désynchronise la PDC de MC et décale tout le mix en silence.
- Le délai variable (le δ lui-même) est appliqué **dans le signal** par le filtre
  fractionnaire, pas déclaré à l'hôte. L'hôte ne voit qu'une latence constante.

## Lissage de δ(t) — contre le warble

Si δ est ré-estimé au fil du temps (dérive d'horloge entre enregistreurs), la
valeur brute bruite → **warble** (modulation de hauteur audible). On lisse :

- δ(t) filtré passe-bas très lent (constante de temps ≫ durée d'un mot).
- Limite de pente (slew) sur δ(t) : le décalage ne peut pas bouger plus vite
  qu'un seuil → pas de saut audible.
- Pour la plupart des scènes, δ est **constant** ; le lissage ne sert que pour
  les longues prises à dérive d'horloge.

## Polarité

Boom et lav peuvent être en **opposition de phase** (câblage, capsule). Après
alignement, on teste la corrélation à polarité normale vs inversée ; on garde
celle qui **maximise** la corrélation. Appliqué comme un simple signe sur le lav.

## Seuil de confiance — bypass par défaut si corrélation faible

- On calcule un **score de confiance** = hauteur du pic PHAT normalisée /
  ratio pic-sur-second-pic.
- **Sous le seuil → bypass par défaut** : on ne rend rien, on pose un marqueur
  *« confiance faible, non aligné »*. Mieux vaut ne pas aligner qu'aligner faux.
- Au-dessus → on applique δ + polarité et on pose *« aligné, δ = X ms,
  confiance = Y »*.

Ce garde-fou est ce qui rend le produit sûr en production : dans le doute, il
**ne casse pas** le clip.
