# 07 — La vue stratégique : une plateforme, pas un plugin

## Le constat

L'écosystème AAX dans Media Composer est **entièrement mono-piste** : EQ III,
Dynamics III, RX Connect, ERA, CrumplePop… Personne ne fait de traitement
**inter-pistes**, non par manque d'idées mais faute de **routing** — MC n'offre
ni sidechain, ni ARA, ni AudioSuite multi-entrée (doc 01).

La connexion du doc 02 lève exactement ce verrou. Une fois le pont
insert ↔ registre ↔ AudioSuite validé (doc 03/04), **le décalage boom/lav n'est
qu'un des modules DSP** qu'on peut brancher dessus.

## L'infra est le produit

```
        ┌──────────────────────────────────────────────┐
        │   Pont Hal (transport + registre partagé)      │  ← doc 02
        └──────────────────────────────────────────────┘
              │        │         │          │        │
              ▼        ▼         ▼          ▼        ▼
          Align    Auto-    Sélecteur   EQ       Room tone
          boom/    ducking  boom/lav    matching fill
          lav      musique/                       (comblement)
          (v1)     dialogue
                                    │
                                    ▼
                              QC loudness
                              (timeline)
```

Chaque module réutilise **le même pont**. Ce ne sont que des DSP différents sur
la même information inter-pistes :

| Module | Ce qu'il lit sur le pont | Ce qu'il rend |
|--------|--------------------------|----------------|
| **Align boom/lav** (v1) | capture de l'autre piste | δ + polarité appliqués |
| **Auto-ducking** musique/dialogue | enveloppe de la piste dialogue | gain musique modulé |
| **Sélecteur boom/lav** | les deux captures + confiance | la meilleure prise par segment |
| **EQ matching** | spectre de la piste cible | courbe d'égalisation appliquée |
| **Room tone fill** | ton de salle capturé ailleurs | comblement des trous |
| **QC loudness** timeline | niveaux de toutes les pistes | rapport / marqueurs de conformité |

## Pourquoi ça compte

- **Barrière à l'entrée** : personne d'autre n'a le routing inter-pistes dans
  MC. Le premier à valider le pont a une longueur d'avance structurelle.
- **Coût marginal décroissant** : le gros du risque et de l'effort est dans le
  pont (doc 02) et sa validation (doc 03/04). Chaque module suivant est
  « juste » du DSP sur une infra déjà éprouvée.
- **Une seule surface à maintenir** : format de capture versionné,
  discipline thread audio, gestion multi-projet — résolus une fois, réutilisés
  partout.

## Séquencement

1. **Valider le pont** (test transport, doc 04). Rien avant.
2. **v1 = Align boom/lav** — le module qui justifie le pont et le rentabilise.
3. **Modules suivants** au fil de la demande, sans retoucher l'infra.

C'est ça, la vraie valeur du projet : pas un aligneur, **une plateforme de
traitement inter-pistes pour Media Composer**.
