# 02 — La connexion exacte

> L'AAX existe déjà. Ce qui manquait, c'est **le câblage** : comment l'insert
> lit le transport, comment il dépose sa capture, comment l'AudioSuite la
> relit — et sous quel format. Ce document spécifie ce contrat, indépendamment
> du code existant.

Trois liens à câbler :

1. **Insert → Transport** : d'où vient l'estampille temporelle.
2. **Insert ↔ Insert ↔ AudioSuite** : par où transitent les captures (le
   registre partagé).
3. **Base timeline commune → δ(t)** : comment les estampilles se combinent en
   un décalage.

---

## Lien 1 — Insert → Transport

### D'où lire la position

Dans le rendu (`AAX_CEffectDirect::RenderAudio` / `RenderAudio_Native`),
l'insert obtient le transport et lit la position **sample** du buffer courant
sur la timeline de session :

```cpp
// Pseudocode AAX — à mapper sur ton implémentation existante.
AAX_ITransport* transport = Controller()->GetTransport();

int64_t blockStartSample = 0;
bool     isPlaying       = false;
transport->GetCurrentNativeSampleLocation(&blockStartSample); // début du buffer
transport->IsTransportPlaying(&isPlaying);
```

Points de contrat, **à figer par le test transport (doc 04)** :

- `GetCurrentNativeSampleLocation` renvoie le sample du **premier échantillon du
  buffer**, sur la timeline de session. L'échantillon `i` du buffer est donc à
  `blockStartSample + i`.
- **`Native` et non `Tick`.** On veut des samples, pas des ticks de tempo — le
  décalage physique boom/lav est en samples, invariant au tempo.
- On ne capture **que si `isPlaying`**. À l'arrêt, la position peut être figée
  ou incohérente ; une capture à l'arrêt polluerait le registre.
- La granularité est le **buffer**, pas l'échantillon : toute la capture d'un
  buffer partage `blockStartSample` comme origine. C'est suffisant car on garde
  l'audio échantillon par échantillon et l'origine est exacte.

### Ce qu'on estampille

Pour chaque buffer accepté, l'insert connaît :

| Champ | Source |
|-------|--------|
| `timelineSampleStart` | `GetCurrentNativeSampleLocation` |
| `numSamples` | argument de `RenderAudio` |
| `sampleRate` | `Controller()->GetSampleRate()` |
| échantillons | le buffer d'entrée (copie, avant tout traitement — l'insert est bit-transparent) |

L'insert **copie l'entrée telle quelle vers le registre puis la recopie
inchangée vers la sortie**. Aucune modification du signal : c'est ce qui garantit
la transparence bit-à-bit (validation, doc 03 §2).

### Discontinuités = fin de segment de capture

Si `timelineSampleStart` du buffer courant **n'est pas** égal à
`(précédent timelineSampleStart) + (précédent numSamples)`, il y a eu saut
(locate, boucle, arrêt/reprise). On **clôt le segment de capture courant et on
en ouvre un nouveau**. Une capture est donc une liste de segments contigus, pas
un flux continu. C'est cette détection qui protège des locates et des boucles de
lecture (checklist doc 06 §Timing).

---

## Lien 2 — Le registre partagé

### Deux implémentations, une seule interface

L'interface vue par le code audio est la même dans les deux cas :

```cpp
struct HalAlignRegistry {
    // Enregistrement / retrait d'un port de capture. HORS thread audio.
    CaptureHandle open(const CaptureKey& key);   // sous verrou
    void          close(CaptureHandle h);         // sous verrou

    // Chemin chaud. Thread audio. SANS verrou.
    void  push(CaptureHandle h, int64_t timelineSampleStart,
               const float* samples, int32_t numSamples);
    // Lecture par l'AudioSuite. HORS thread audio.
    bool  snapshot(const CaptureKey& key, CaptureView* out); // sous verrou
};
```

Règle d'or, celle confirmée par Sound Radix : **le verrou ne protège que la
table des ports (open/close/snapshot), jamais `push`.** `push` écrit dans un
ring-buffer pré-alloué appartenant à un port déjà ouvert ; il ne touche jamais
la structure que le verrou protège.

#### (a) Statics C++ — le chemin natif MC

MC charge l'AAX **in-process**. Un `static HalAlignRegistry g_registry;` dans le
binaire du plugin est donc **partagé** entre l'insert boom, l'insert lav et
l'instance AudioSuite — *à condition que les trois soient la même image chargée
une seule fois*. **C'est exactement l'hypothèse que valide le doc 03 §3.** Si
elle tient, c'est le chemin le plus simple et le plus rapide.

#### (b) Fichier mappé mémoire — le chemin robuste (préféré)

Un `mmap` (POSIX) / `CreateFileMapping`+`MapViewOfFile` (Win) sur un fichier de
capture partagé. **Préféré**, pour trois raisons :

1. **Robustesse** : survit si MC charge des images séparées (multi-projet,
   bundles distincts) ou si l'AudioSuite tourne dans un contexte process
   distinct — là où les statics ne sont **pas** partagés.
2. **Longues captures** : une scène de 20 min à 48 kHz stéréo = ~460 Mo. En RAM
   statique c'est lourd et non persistant ; en fichier mappé, l'OS pagine et la
   capture survit à un crash de session.
3. **Débogage** : le fichier est inspectable hors ligne (doc 04 utilise ça).

**Décision par défaut : (b), avec (a) comme court-circuit optionnel** si le test
§3 prouve que les statics sont partagés dans ta version de MC. Le code audio ne
voit que `HalAlignRegistry` ; le choix (a)/(b) est une politique de compilation,
pas une réécriture.

### Discipline thread audio (les accès non verrouillés)

- `push` n'alloue jamais, ne verrouille jamais, n'appelle jamais l'OS (sauf
  l'écriture mmap, qui est un `memcpy` vers une page déjà mappée — pas un
  syscall par appel).
- Chaque port a **son** ring-buffer. Un seul producteur (l'insert) par port, un
  seul consommateur (l'AudioSuite, hors thread audio, après arrêt de lecture).
  → pas de contention réelle, un `atomic` d'index en tête suffit.
- `open`/`close`/`snapshot` prennent le verrou et ne sont **jamais** appelés
  depuis `RenderAudio`. `open` se fait à l'instanciation du plugin,
  `snapshot` au moment du render AudioSuite (déclenché par l'utilisateur, hors
  audio temps réel).

---

## Format de capture — versionné dès le v1

> Piège majeur signalé : **versionner le format de capture dès le v1.** Un
> insert d'une build et un AudioSuite d'une autre ne doivent jamais se
> mécomprendre en silence.

En-tête du segment partagé (mmap) ou du registre statique :

```
Offset  Taille  Champ
0       4       MAGIC        = 'HALX' (0x484C4158)
4       2       formatMajor  (incompatible si différent → refus + message)
6       2       formatMinor  (compatible ascendant)
8       4       headerBytes  (taille de cet en-tête, pour extension future)
12      4       sampleRate   (Hz, uint32)
16      4       channels     (uint32)
20      4       sampleFormat (0 = float32 natif)
24      8       epochId      (uint64 : identifie UNE session de lecture ; voir ci-dessous)
32      4       portCount
36      ...      table des ports
```

Par port :

```
portId          (uint32 ; stable pour un couple track+instance)
role            (uint32 : 0 = boom, 1 = lav)
keyHash         (uint64 : hash de CaptureKey, voir plus bas)
segmentCount    (uint32)
ringHeadSample  (atomic uint64 : dernier sample écrit)
[segments...]   : {timelineSampleStart:int64, offsetInRing:uint64, numSamples:int64}
[ring audio]    : float32 entrelacés
```

Règles de version :

- **`formatMajor` différent → refus explicite** (« capture format vX, plugin
  attend vY, réaligne avec des builds cohérentes »). Jamais d'interprétation
  hasardeuse.
- **`formatMinor` supérieur côté lecteur** : on lit quand même en ignorant les
  champs inconnus (en-tête auto-décrit par `headerBytes`).
- **`epochId`** : régénéré à chaque nouvelle session de lecture (par l'extension,
  ou par un top de l'utilisateur en mode fallback). L'AudioSuite refuse une
  capture dont l'`epochId` ne correspond pas à la passe attendue → protège du
  **re-render silencieux après trim** et du **multi-projet** (checklist doc 06).

---

## Lien 3 — Base timeline commune → δ(t)

C'est le point qui justifie toute l'architecture.

Les deux inserts estampillent avec **le même** `GetCurrentNativeSampleLocation`,
donc sur **le même référentiel timeline**. Pour une caractéristique acoustique
commune (un transitoire, un mot), on connaît :

- `p_boom` = position timeline (samples) de la feature dans la capture boom,
- `p_lav`  = position timeline (samples) de la feature dans la capture lav.

Le décalage physique lav→boom est :

```
δ_samples = p_lav_feature − p_boom_feature
δ_ms      = 1000 · δ_samples / sampleRate
```

Mais on ne « trouve » pas les features à la main : on **corrèle** la capture lav
contre la capture boom sur la fenêtre de recherche (±45 ms, doc 05). Le pic de
corrélation **est** `δ_samples`. La base timeline commune sert à **caler la
fenêtre** au bon endroit (on corrèle boom[t] contre lav[t], pas boom entier
contre lav entier), et à **désambiguïser** quand plusieurs pics existent.

### Les deux chemins vers δ, côté AudioSuite

L'AudioSuite sur le lav a besoin de δ. Deux sources :

1. **Chemin métadonnées (extension présente).** L'extension a déjà calculé δ à
   partir des deux captures et l'a écrit (marqueur / registre). L'AudioSuite le
   lit et l'applique. Rapide, déterministe.
2. **Chemin fingerprint (fallback, ou vérification).** L'AudioSuite **ne reçoit
   pas** le boom (mono-entrée). Mais son entrée = le même signal lav que celui
   capturé par l'insert lav. Il **corrèle son entrée contre la capture boom du
   registre** (via `snapshot`, sur la base timeline commune) → retrouve δ
   lui-même. C'est ce chemin qui rend la maquette **fonctionnelle sans
   extension** (doc 04).

Dans les deux cas, l'AudioSuite applique ensuite : décalage entier +
**délai fractionnaire interpolé** pour le sous-sample + **polarité** (doc 05),
puis rend. Longueur de sortie **= longueur d'entrée** (contrat AudioSuite,
validation doc 03 §2).

---

## CaptureKey — comment un port se nomme

Pour que l'AudioSuite retrouve **la bonne** capture, la clé doit être stable et
sans ambiguïté :

```cpp
struct CaptureKey {
    uint64_t epochId;      // la session de lecture courante
    uint32_t role;         // boom / lav
    uint64_t sourceHash;   // hash(Source File + Start TC du master clip)
};
```

`sourceHash` s'appuie sur des métadonnées qui **survivent au render** (Source
File, Start TC — cf. doc 01 « pourquoi les métadonnées survivent »). En mode
fallback sans extension, l'extension ne fournit pas `sourceHash` : on tombe alors
sur le **fingerprint pur** (le signal lui-même est la clé), d'où l'importance du
chemin 2 ci-dessus.
