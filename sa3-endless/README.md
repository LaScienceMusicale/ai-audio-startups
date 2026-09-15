# sa3-endless

Charge des samples de quelques secondes et laisse-les se prolonger indéfiniment
avec [Stable Audio 3](https://github.com/Stability-AI/stable-audio-3).
Pensé pour une installation sonore : ça tourne seul, ça ne s'arrête pas, et on
peut changer de sample ou de prompt en direct (clavier ou OSC).

*Endless sound continuation from short samples with Stable Audio 3, for sound
installations. Streams to the sound card, records to WAV, controllable over OSC.*

## Comment ça marche

```
sample (3 s) ─► contexte ─► Stable Audio 3 (inpainting après la fin) ─► chunk ─► ring buffer ─► carte son
                  ▲                                                                  │           (callback)
                  └──────────────────── dernières secondes jouées ◄──────────────────┘
```

Le modèle génère par morceaux, mais la sortie est un flux continu :

1. Le sample amorce le flux.
2. Le générateur (thread) demande au modèle la suite des dernières `--context`
   secondes jouées (`inpaint_mask_start` = fin du contexte). Les `--overlap`
   dernières secondes sont régénérées et crossfadées à puissance constante :
   aucune couture audible.
3. Les chunks alimentent un ring buffer de `--buffer` secondes. La carte son tire
   dedans par petits blocs (`--blocksize`) depuis son callback temps réel : la
   lecture ne dépend jamais du modèle.
4. La longueur des chunks s'adapte à la vitesse mesurée (`rtf`) : plus le modèle
   est lent, plus les chunks sont longs, ce qui amortit le coût du contexte.
5. Si malgré tout le buffer passe sous `--low-water`, le flux ne s'arrête pas :
   il boucle le contexte récent (crossfadé, et se terminant exactement là où le
   modèle reprendra) jusqu'à ce que la génération rattrape.

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
| `--buffer` | 30 s | audio gardé en avance dans le ring buffer |
| `--low-water` | 3 s | seuil sous lequel le contexte est bouclé en attendant le modèle |
| `--preroll` | 4 s | audio bufferisé avant de démarrer la lecture |
| `--max-chunk` | 30 s | plafond de la longueur de chunk adaptative |
| `--blocksize` | 1024 | taille des blocs du callback audio |
| `--steps` | 8 | pas de diffusion |
| `--switch-every` | 0 | re-seed automatique depuis un autre sample (secondes) |
| `--osc-port` | 0 | port UDP pour le contrôle OSC |

Le log affiche pour chaque chunk le facteur temps réel (`rtf`). S'il reste
au-dessus de 1 même avec des chunks longs, le flux tient grâce aux boucles de
maintien mais devient répétitif : baisser `--context` ou `--steps`, ou passer
sur GPU. Avec `-v`, un état du buffer (secondes d'avance, holds, underruns)
s'affiche toutes les 10 s.

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
from sa3_endless import ContinuousStream, StableAudioEngine
from sa3_endless.samples import load_sample

engine = StableAudioEngine("small-sfx")
engine.load()
seed = load_sample("bell.wav", engine.sample_rate, engine.channels)
stream = ContinuousStream(engine, seed).start()
stream.wait_preroll()

while True:
    block = stream.read(1024, block=True)   # float32 [channels, 1024], toujours sans trou
    ...                                     # envoyer où vous voulez

stream.reseed(load_sample("wind.wav", engine.sample_rate, engine.channels))
stream.set_prompt("rain on a tin roof")
```

`Streamer` (niveau chunk) reste disponible si vous voulez gérer le buffer vous-même.

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
