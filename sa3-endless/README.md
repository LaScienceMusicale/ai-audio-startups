# sa3-endless

Charge des samples de quelques secondes et laisse-les se prolonger indéfiniment
avec [Stable Audio 3](https://github.com/Stability-AI/stable-audio-3).
Pensé pour une installation sonore : ça tourne seul, ça ne s'arrête pas, et on
peut changer de sample ou de prompt en direct (clavier ou OSC).

*Endless sound continuation from short samples with Stable Audio 3, for sound
installations. Streams to the sound card, records to WAV, controllable over OSC.*

## Comment ça marche

```
sample (3 s) ──► contexte (10 s max) ──► Stable Audio 3 inpainting ──► +8 s ──► lecture
                     ▲                    (masque après la fin)              │
                     └──────────────── les dernières secondes jouées ◄───────┘
```

1. Le sample amorce le flux.
2. Le moteur reçoit les dernières `--context` secondes jouées et demande au modèle
   de générer la suite (`inpaint_mask_start` = fin du contexte).
3. Les `--overlap` dernières secondes sont régénérées et crossfadées à puissance
   constante pour cacher la couture.
4. Les chunks sont générés `--lookahead` chunks en avance et joués bout à bout.

Le contexte audio pèse plus que le prompt texte : le modèle prolonge le timbre
et la dynamique du sample. Un prompt reste possible pour orienter la dérive.

## Installation

Python 3.10+. Le modèle Small tourne sur CPU ou Apple Silicon, Medium demande un GPU NVIDIA.

```bash
git clone https://github.com/lasciencemusicale/sa3-endless
cd sa3-endless
python -m venv .venv && source .venv/bin/activate
pip install -e ".[audio,osc,sa3]"
```

L'extra `sa3` installe `stable-audio-3` depuis GitHub (torch 2.7.1 inclus). Les
poids se téléchargent depuis Hugging Face au premier lancement ; il faut avoir
accepté la [Stability AI Community License](https://stability.ai/license) sur
la page du modèle et être connecté avec `huggingface-cli login`.

## Utilisation

```bash
# un dossier de samples, modèle SFX, sortie sur la carte son
sa3-endless --samples ./samples --model small-sfx

# avec un prompt, enregistrement en parallèle, changement de sample toutes les 3 min
sa3-endless --samples ./samples --prompt "wind through metal" --output session.wav --switch-every 180 --shuffle

# rendu hors ligne de 10 minutes, sans carte son
sa3-endless --samples drone.wav --render 600 --output drone_10min.wav

# vérifier la chaîne audio sans modèle (boucle le sample)
sa3-endless --samples ./samples --engine mock
```

Options utiles :

| option | défaut | rôle |
|---|---|---|
| `--chunk` | 8 s | audio nouveau par génération |
| `--context` | 10 s | passé donné au modèle (plus court = plus rapide, moins cohérent) |
| `--overlap` | 0.5 s | zone régénérée et crossfadée |
| `--lookahead` | 2 | chunks générés en avance |
| `--steps` | 8 | pas de diffusion |
| `--switch-every` | 0 | re-seed automatique depuis un autre sample (secondes) |
| `--osc-port` | 0 | port UDP pour le contrôle OSC |

Le log affiche pour chaque chunk le facteur temps réel (`rtf`). S'il dépasse 1,
la génération est plus lente que la lecture : augmenter `--chunk`, baisser
`--context` ou `--steps`, ou passer sur GPU.

### Contrôle en direct

Clavier (Entrée après chaque commande) :

```
n              sample suivant
s <nom|index>  amorcer avec ce sample
p <texte>      changer le prompt
p              retirer le prompt
q              quitter
```

OSC (`--osc-port 9000`), depuis Max, Pd, SuperCollider ou TouchOSC :

```
/reseed            sample suivant
/reseed 2          sample d'index 2
/reseed "cloche"   premier sample dont le nom contient "cloche"
/prompt "rain on a tin roof"
/stop
```

Un re-seed n'est jamais brutal : le nouveau sample est crossfadé sur la fin de
ce qui joue, puis le modèle continue à partir de lui.

## Utiliser depuis Python

```python
from sa3_endless import StableAudioEngine, Streamer, StreamConfig
from sa3_endless.samples import load_sample

engine = StableAudioEngine("small-sfx")
engine.load()
seed = load_sample("bell.wav", engine.sample_rate, engine.channels)
stream = Streamer(engine, seed, StreamConfig(chunk_seconds=8)).start()

while True:
    chunk = stream.next_chunk()   # float32 [channels, samples]
    ...                           # envoyer où vous voulez
```

`MockEngine` remplace le modèle pour les tests et le développement du patch.

## Développement

```bash
pip install -e ".[dev]"
pytest
```

Les tests n'ont pas besoin du modèle : ils utilisent `MockEngine`.

## Licence

Code sous licence MIT. Les poids Stable Audio 3 sont sous
[Stability AI Community License](https://stability.ai/license) : à vérifier pour
un usage commercial.
