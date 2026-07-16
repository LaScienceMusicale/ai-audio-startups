# 01 — Architecture

## Le problème, réduit à une phrase

Deux signaux (boom, lav) enregistrent la même scène. On veut aligner le lav sur
le boom au sample près, dans MC. MC ne propose aucun des trois mécanismes que
les plugins multi-entrée utilisent ailleurs :

- pas de **sidechain** (donc pas d'entrée auxiliaire dans un insert),
- pas d'**ARA** (donc pas d'accès hors-ligne à la timeline par le plugin),
- pas d'**AudioSuite multi-entrée** (le render ne voit qu'un seul clip).

La conséquence : aucune brique ne voit à la fois le boom et le lav. Il faut donc
que **plusieurs instances du même plugin s'échangent de l'information** en
dehors du chemin audio classique.

## La méthode de fond (confirmée par Sound Radix)

Communication inter-instances **sans sidechain** : des globals statiques C++
partagés entre instances du même plugin. Registre verrouillé **uniquement hors
thread audio** ; accès non verrouillés, prudents, dans le pipeline audio. Dans
MC, l'AAX tourne **in-process**, donc les statics sont réellement partagés entre
instances. On préfère malgré tout un **fichier mappé mémoire** pour la
robustesse et les longues captures (voir doc 02).

## Le trio

```
                    ┌───────────────────────────────────────────┐
                    │            Extension MC (SDK Extensions)    │
                    │  lit la timeline (segments, Start TC,       │
                    │  Source File), pilote la lecture bornée,    │
                    │  pose des marqueurs. Cerveau métadonnées.   │
                    └───────────────┬───────────────────────────┘
                                    │ orchestration (lecture bornée In/Out)
                    ┌───────────────┴───────────────┐
                    ▼                                ▼
        ┌───────────────────────┐        ┌───────────────────────┐
        │  Insert AAX (boom)     │        │  Insert AAX (lav)      │
        │  bit-transparent       │        │  bit-transparent       │
        │  capture timestampée   │        │  capture timestampée   │
        └───────────┬───────────┘        └───────────┬───────────┘
                    │   GetCurrentNativeSampleLocation │
                    └───────────────┬──────────────────┘
                                    ▼
                        ┌───────────────────────┐
                        │  Registre partagé       │  ← statics + mmap (doc 02)
                        │  (base timeline commune)│
                        └───────────┬───────────┘
                                    │ lit δ(t) ou re-corrèle
                                    ▼
                        ┌───────────────────────┐
                        │  AudioSuite (lav)       │
                        │  applique δ(t)+polarité │
                        │  rend le clip           │
                        └───────────────────────┘
```

### 1. Extension MC (SDK Extensions, ex-Panel SDK)

Cerveau métadonnées et orchestration. Lit la timeline (segments, Start TC,
Source File), pilote la lecture bornée sur la plage de la scène, pose les
marqueurs de résultat. **Hors périmètre de la maquette v0** — le fallback sans
extension (deux passes AudioSuite, doc 04 §Fallback) permet de tout valider
avant de l'écrire.

### 2. Inserts AAX bit-transparents (boom + lav)

Pendant une lecture de la scène, chaque insert capture son audio **timestampé
sur la timeline commune** via `AAX_ITransport::GetCurrentNativeSampleLocation`.
Bit-transparent = l'audio ressort **identique** à l'entrée (le plugin ne fait
que capturer, jamais modifier). C'est ce qui permet de le laisser posé en
permanence. Le calcul de δ(t) se fait sur la base timeline commune (doc 02).

### 3. AudioSuite sur le clip lav

Retrouve sa position soit via les métadonnées de l'extension, soit par
**fingerprint** : corrélation de son entrée AudioSuite contre la capture lav
stockée dans le registre. Même signal des deux côtés → pic de corrélation
quasi parfait. Applique δ(t) + polarité, rend.

## Pourquoi les métadonnées survivent

L'AudioSuite rendu est un **effet de clip** : le render crée un precompute mais
le segment **référence toujours le master clip d'origine**. Start TC, Source
File, nom — tout reste pour l'AAF et le conform.

**À ne jamais faire :** export/réimport WAV, ou création d'un nouveau master
clip. Les deux cassent la traçabilité vers la source de plateau.

## Workflow utilisateur final

1. Clic **« Align scene »** dans l'extension.
2. Lecture automatique de la plage → les inserts capturent.
3. Render AudioSuite des clips lav → δ(t) + polarité appliqués.
4. Marqueur posé : *« aligné, δ = X ms »*.

**Fallback sans extension** (= maquette v0) : deux passes AudioSuite sur In/Out
identiques. Preview (capture) sur le boom, puis render sur le lav. Détaillé
dans le doc 04.
