# Architecture de sa3-endless

Un sample de quelques secondes entre, un flux audio sans fin sort. Stable Audio 3
génère par morceaux ; tout le reste du système existe pour que la sortie, elle,
soit continue.

## Le chemin du son

```
  fichier .wav
       │  samples.load_sample  (resample, stéréo, normalise)
       ▼
   ┌────────────────────────────── Streamer (thread) ──────────────────────────────┐
   │   history ──► contexte (10 s) ──► Engine.continue_audio ──► chunk ──► crossfade│
   │      ▲                                                                    │    │
   │      └────────────────────────────────────────────────────────────────────┘    │
   └───────────────────────────────────┬───────────────────────────────────────────┘
                                       │  queue (lookahead)
   ┌───────────────────────────────────▼───────────────────────────────────────────┐
   │  ContinuousStream : feeder (thread) ──► RingBuffer (30 s) ◄── read(n) callback │
   └───────────────────────────────────┬───────────────────────────────────────────┘
                                       ▼
                          carte son (PortAudio)  et/ou  WavSink
```

Trois fils d'exécution, jamais couplés : le générateur travaille à son rythme, le
feeder remplit le tampon, la carte son tire dedans à cadence fixe.

## Les cinq pièces

| Module | Rôle | Pourquoi il existe |
|---|---|---|
| `engine.py` | `Engine.continue_audio(contexte, durée)` renvoie la suite | Isole le modèle. `StableAudioEngine` appelle l'inpainting de SA3, `MockEngine` boucle le sample. Changer de modèle ne touche à rien d'autre. |
| `streamer.py` | Produit les chunks, colle les coutures | Le crossfade et la mémoire du passé vivent ici, pas dans le moteur. |
| `ring.py` | Tampon circulaire thread-safe | Découple production et lecture. La lecture ne bloque jamais. |
| `continuous.py` | Feeder, chunks adaptatifs, mode maintien | Transforme « des morceaux » en « un flux ». |
| `sinks.py` / `cli.py` / `demo.py` | Sorties, pilotage, rendu d'écoute | Les entrées-sorties, séparées de la logique. |

Convention unique dans tout le code : `numpy` float32, forme `[canaux, échantillons]`,
au `sample_rate` du moteur.

## Les quatre décisions qui font marcher le truc

**1. Continuer, pas générer.** Chaque appel passe les dernières secondes jouées en
`inpaint_audio` avec le masque ouvert après leur fin. Le modèle ne part pas d'une
page blanche : il prolonge un timbre, une dynamique, une matière. Le prompt texte
est optionnel et pèse moins que le contexte audio.

**2. Recouvrement et crossfade à puissance constante.** On demande toujours
`overlap + chunk + overlap`. Les premières secondes recouvrent la fin du chunk
précédent, fondues en cosinus/sinus : pas de clic, pas de creux de niveau. Les
dernières sont gardées de côté pour la couture suivante.

**3. Tampon d'avance et callback.** La carte son appelle `read(n)` depuis son
thread temps réel et obtient toujours ses échantillons. Une génération lente ne
provoque jamais de coupure, seulement une baisse du niveau du tampon.

**4. Deux soupapes quand le modèle traîne.** Si le facteur temps réel monte, les
chunks s'allongent, ce qui amortit le coût fixe du contexte. Si le tampon passe
sous le seuil bas, le flux boucle le contexte récent, crossfadé et calé pour finir
exactement là où le modèle reprendra. Le son devient répétitif, il ne s'arrête pas.

## Pilotage en direct

`reseed(audio)` et `set_prompt(texte)` sont posés sous verrou et lus par le
générateur au chunk suivant. Un re-seed n'est pas une coupure : le nouveau sample
est crossfadé sur ce qui joue, puis devient le contexte. Exposé au clavier et en
OSC (`/reseed`, `/prompt`, `/stop`) pour Max, Pd ou SuperCollider.

## Ce qui est vérifié, et ce qui ne l'est pas

17 tests tournent sans le modèle grâce à `MockEngine` : continuité au niveau de
l'échantillon aux coutures, zéro underrun avec un moteur rapide, zéro silence avec
un moteur plus lent que le temps réel, croissance des chunks adaptatifs, et un
faux `StableAudioModel` qui reprend la signature exacte de `generate` en amont.

Non vérifié : la génération avec les vrais poids. Vitesse et qualité réelles
restent à mesurer sur Apple Silicon ou GPU, avec `sa3-endless-demo`.

## Étendre

Écrire un moteur, c'est une classe avec `sample_rate`, `channels` et
`continue_audio`. Magenta RealTime, un modèle maison ou un simple granulateur
s'y branchent sans toucher au streaming.
