# 04 — Protocole du test transport

> Le premier test, celui qui décide de tout le reste. Objectif : prouver (ou
> réfuter) l'hypothèse §1 du doc 03 — transport sample-accurate et **cohérent
> entre pistes**. Bonus : il exerce aussi §2 et §3 en même temps.

Aucune extension requise. On utilise le **fallback deux passes AudioSuite** et un
insert instrumenté. L'AAX existe déjà ; ici on ne fait qu'ajouter du *logging*
autour du câblage du doc 02.

## Matériel de test

- Un fichier son avec des **transitoires nets et espacés** (claps, ou une
  slate). Éviter le bruit continu : on veut des repères de corrélation francs.
- Une session MC neuve, sample rate fixé et connu (ex. 48 kHz).
- Un dossier de sortie pour les captures mmap (chemin en dur, ou variable
  d'env), inspectable hors ligne.

## Instrumentation minimale à ajouter à l'insert

Dans `RenderAudio`, quand `IsTransportPlaying` :

1. Lire `blockStartSample = GetCurrentNativeSampleLocation`.
2. Détecter discontinuité vs buffer précédent → nouveau segment (doc 02 §Lien 1).
3. `push` l'audio + `blockStartSample` dans le port du registre (doc 02 §Lien 2).
4. Écrire une ligne de log : `role, blockStartSample, numSamples, sampleRate,
   firstSampleValue, epochId`.

Rien d'autre. L'insert reste bit-transparent (recopie l'entrée en sortie sans la
toucher).

## Manip A — Cohérence entre pistes (le cœur de §1)

1. Poser **le même clip** sur **deux pistes** (piste 1, piste 2), **calés au
   même Start TC** sur la timeline.
2. Insert instrumenté sur chaque piste. `role` = 0 sur l'une, 1 sur l'autre
   (peu importe, on veut juste deux ports distincts).
3. Poser In/Out autour de la zone à transitoires, lancer la lecture.
4. Arrêter. Récupérer les deux captures.

### Vérifications (offline, script d'analyse)

- **V1 — estampilles identiques.** Pour chaque buffer aligné, `blockStartSample`
  piste 1 == piste 2. Tolérance : **0 sample**. Un écart constant non nul =
  latence de plugin non compensée (voir §Pièges) ; un écart variable = transport
  incohérent → **§1 rouge**.
- **V2 — offset de corrélation nul.** Corréler capture 1 contre capture 2 (même
  méthode GCC-PHAT que le vrai produit, doc 05). Pic attendu à **0 sample**.
  Tolérance maquette : ±1 sample. Un pic non nul alors que V1 est bonne = le
  contenu diffère malgré des estampilles égales → suspecter un resample MC (§2).
- **V3 — monotonie.** Sur chaque capture, les `blockStartSample` successifs (hors
  discontinuité volontaire) sont strictement croissants et contigus
  (`start[n+1] == start[n] + num[n]`). Sinon : buffers réordonnés ou dupliqués.

## Manip B — Sample-accuracy absolue (repère physique)

1. Un seul clip, une piste, un transitoire dont on connaît la position **dans le
   fichier source** (ex. clap à 5,000 s → sample 240000 @ 48 k).
2. Le clip commence à un Start TC connu sur la timeline.
3. Lecture, capture.
4. Vérifier que la position du transitoire **détectée dans la capture** (via
   corrélation) correspond, une fois convertie par la base timeline, à la
   position attendue `StartTC_samples + 240000`. Tolérance : ±1 sample.

Manip B valide que `GetCurrentNativeSampleLocation` est non seulement cohérent
(Manip A) mais **absolument juste** — indispensable pour le chemin métadonnées
(doc 02 §Lien 3, chemin 1).

## Manip C — Statics vs mmap (§3, en passant)

1. L'insert incrémente aussi un `static` global à chaque buffer.
2. Une passe AudioSuite « sonde » : au render, elle lit ce `static` et le
   reporte (log / marqueur).
3. Si la valeur lue par l'AudioSuite reflète les écritures de l'insert →
   **statics partagés** (§3 vert, chemin (a) disponible). Sinon → mmap
   obligatoire (chemin (b)), ce qui est de toute façon le défaut.

## Fallback deux passes AudioSuite (sans extension)

Quand il n'y a pas d'extension pour piloter la lecture bornée :

- **Passe 1 (boom) — Preview/Analyze.** AudioSuite en mode *Preview* sur le
  segment boom : capture uniquement, ne rend rien. Dépose dans le registre.
- **Passe 2 (lav) — Render.** AudioSuite sur le segment lav, **mêmes In/Out** :
  lit la capture boom du registre, calcule δ (fingerprint, doc 02 §Lien 3
  chemin 2), applique, rend.

La contrainte **In/Out identiques** garantit la base timeline commune sans
transport piloté. C'est laborieux mais ça débloque toute la validation avant
d'écrire une seule ligne d'extension.

## Critère de réussite

| | Attendu | Rouge |
|-|---------|-------|
| V1 estampilles | identiques, 0 sample | écart variable → §1 mort |
| V2 corrélation | pic à 0 (±1) | pic non nul → resample MC |
| V3 monotonie | contigu, croissant | trous/doublons → transport non fiable |
| Manip B | ±1 sample vs physique | dérive → estampille inexploitable pour métadonnées |
| Manip C | static lu = static écrit | non → mmap obligatoire |

**Si V1+V2+V3+B sont verts : le projet tient.** On peut construire le reste.
Sinon, basculer sur les replis du doc 03 et re-cadrer avant tout
développement.
