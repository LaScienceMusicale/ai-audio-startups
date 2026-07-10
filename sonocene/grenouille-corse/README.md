# Grenouille corse — « Le chant sans nom »

**Voyage en Sonocène — Épisode 2 (Corse, secteur Boziu)**

Décomposition du signal du chant de la **grenouille peinte de Corse**
(*Discoglossus montalentii*) et modèle probabiliste pour détecter, dans un
panel d'archives de Jean-Claude Roché, si ce chant a **déjà été enregistré sans
avoir jamais été identifié**. Les instances dont la probabilité dépasse **90 %**
sont extraites en clips audio pour être écoutées.

> Enregistrement de référence (prise de terrain de Thibault) :
> https://www.instagram.com/p/Dah3CFAFYwZ/

---

## L'enjeu narratif : un chant enregistré avant d'avoir un nom

*Discoglossus montalentii* n'a été **décrite scientifiquement qu'en 1984**
(Lanza, Nascetti, Capula & Bullini). Espèce endémique de Corse, montagnarde
(300–2000 m), au chant **nocturne** et **harmonique** — un trait qui la distingue
des autres discoglosses, au chant inharmonique, et de sa très proche cousine
sarde *Discoglossus sardus*.

Or Jean Roché enregistrait déjà la Corse dans les années 1960–1970. **Si le
modèle retrouve ce chant dans une bande antérieure à 1984, Thibault aura mis au
jour une occurrence captée avant que la science ne nomme l'espèce** : une
archive qui « savait » avant de savoir. C'est le cœur de l'épisode, et la
démarche ci-dessous en est la méthode.

---

## La démarche, étape par étape

### 1. Décomposition du signal (l'empreinte)

À partir de l'enregistrement de référence, on isole les cris (détection
d'onsets avec période réfractaire) et on en extrait une **empreinte sonore** à
deux composantes :

- **un filtre adapté** : le spectrogramme mel moyen d'un cri, normalisé, qui
  sert de gabarit de *forme spectrale* ;
- **des descripteurs acoustiques** : fréquence dominante, centroïde et largeur
  de bande, cadence des pulses, MFCC, et surtout la **tonalité de pic**
  (`1 − platitude spectrale`), qui capture le trait diagnostique de l'espèce :
  son chant est **tonal/harmonique**, là où le bruit de ruisseau et les chants
  inharmoniques ne le sont pas.

L'analyse est bornée en fréquence (200–4000 Hz) pour rester robuste au
grondement de l'eau (basses) et aux stridulations d'orthoptères (hautes).

### 2. Modèle probabiliste

Chaque fenêtre candidate reçoit **deux scores calibrés dans [0, 1]** :

| Évidence | Ce qu'elle mesure | Comment |
|---|---|---|
| Filtre adapté | la fenêtre a-t-elle la *forme spectrale* du cri ? | corrélation croisée normalisée fenêtre ↔ gabarit |
| Tonalité | la fenêtre est-elle *harmonique* comme l'espèce ? | `1 − platitude spectrale` de la trame la plus tonale |

Les deux sont fusionnés par **moyenne géométrique** — un choix volontairement
sévère : les deux évidences doivent concorder pour approcher 1. Un ruisseau qui
« ressemble » spectralement mais sans tonalité est rejeté ; un son tonal de
mauvaise forme (un oiseau) l'est aussi. Le calibrage (point de bascule à 50 %,
raideur) est **appris sur la seule référence** : on ne dispose que d'exemples
positifs, situation réaliste d'une détection *cible connue, archive inconnue*.

### 3. Balayage des archives Roché

Fenêtre glissante sur chaque enregistrement du panel, calcul de la probabilité,
puis **suppression des non-maxima** pour ne garder qu'un pic par cri.

### 4. Instances > 90 % → écoute

Toute détection de probabilité **≥ 0,90** est exportée en clip `.wav`
(avec marge de contexte) et consignée dans un rapport `detections.json`
(fichier source, horodatage, probabilité). L'oreille humaine — Thibault, les
éco-acousticiens — tranche en dernier ressort : le modèle **oriente l'écoute**,
il ne la remplace pas.

---

## Utilisation

```bash
pip install -r requirements.txt

# 1. Construire l'empreinte depuis l'enregistrement de référence de Thibault
python detect_grenouille_corse.py fit \
    --reference refs/thibault_boziu.wav \
    --model empreinte_montalentii.npz

# 2. Balayer le panel d'archives Roché, exporter les instances > 90 %
python detect_grenouille_corse.py scan \
    --model empreinte_montalentii.npz \
    --archive archives_roche/ \
    --out detections/ \
    --threshold 0.90
```

Sortie : les clips `.wav` des détections + `detections/detections.json`, triés
par probabilité décroissante, prêts à écouter.

## Vérification

Le pipeline est validé de bout en bout, sans données réelles, par un test qui
synthétise un chant harmonique de référence, une archive contenant des
occurrences noyées dans du bruit de ruisseau, et un **leurre inharmonique** :

```bash
python selftest.py
# → détecte les occurrences (>90 %), rejette le leurre, vérifie la sérialisation
```

## Limites et honnêteté scientifique

- Le modèle **ne prouve pas** une identification : il classe des candidats par
  vraisemblance acoustique. La confirmation reste humaine (écoute) et, idéalement,
  croisée avec les métadonnées de terrain (lieu, altitude, date, saison de chant).
- *D. montalentii* et *D. sardus* ont des chants proches ; la distinction fine
  passe par les **cris d'alerte** et par le contexte écologique (altitude, habitat).
  Le seuil et le gabarit doivent être affinés avec les éco-acousticiens de l'épisode.
- Les archives anciennes (bandes 1/4 de pouce, DAT) ont des réponses en fréquence
  et des bruits de fond variables : prévoir une normalisation par support avant
  balayage à grande échelle.

## Sources

- INPN — *Discoglossus montalentii* : https://inpn.mnhn.fr/espece/cd_nom/223
- Différenciation bioacoustique des *Discoglossus* (Amphibia-Reptilia, 1991) :
  https://doi.org/10.1163/156853891X00031
- Fonds Jean Roché, Muséum national d'Histoire naturelle :
  https://sonotheque.mnhn.fr/articles/59
- Association Jean Roché — la sonothèque : https://www.jeanroche.fr/la-sonotheque/
