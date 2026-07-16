# Hal Align — Media Composer

Aligner un clip (lav) sur un autre (boom) dans Avid Media Composer, façon
Auto-Align Post, **sans sidechain, sans ARA, sans AudioSuite multi-entrée** —
les trois raisons pour lesquelles Auto-Align Post ne supporte pas MC.

Ce dossier ne contient **pas** le code AAX (il existe déjà côté Hal Audio). Il
fige l'**architecture**, le **protocole de test**, et surtout **la connexion
exacte** entre les trois briques — le câblage transport ↔ mémoire partagée ↔
AudioSuite qui n'était pas encore spécifié.

## Statut

| Brique | État | Ce qui manque |
|--------|------|----------------|
| Insert AAX bit-transparent | Code existant | Le câblage transport → registre (voir doc 02) |
| AudioSuite lav | Code existant | La lecture du registre + repli fingerprint (doc 02, doc 05) |
| Extension MC | À écrire | Orchestration (doc 01) — hors périmètre v0 |

**Contrainte produit : tout dans Media Composer.** Pas de « load reference »,
pas d'audio chargé hors de l'app, pas d'export/réimport. La référence boom est
capturée pendant que MC la lit (insert, ou AudioSuite Preview en fallback) ; le
transit entre instances est de la plomberie interne invisible (doc 02).

**v0 = maquette.** L'objectif de la maquette n'est pas d'aligner quoi que ce
soit : c'est de **valider les 4 hypothèses bloquantes** (doc 03) avant de
construire. Tant que le test transport (doc 04) n'est pas vert, rien d'autre ne
compte.

## Index

| # | Document | Rôle |
|---|----------|------|
| 01 | [architecture.md](docs/01-architecture.md) | Le trio, le flux, le workflow utilisateur |
| 02 | [connexion-exacte.md](docs/02-connexion-exacte.md) | **La connexion** : transport, statics/mmap, format de capture, handshake |
| 03 | [validations-bloquantes.md](docs/03-validations-bloquantes.md) | Les 4 tests go/no-go |
| 04 | [protocole-test-transport.md](docs/04-protocole-test-transport.md) | Le premier test, pas à pas |
| 05 | [dsp.md](docs/05-dsp.md) | GCC-PHAT, délai fractionnaire, lissage, confiance |
| 06 | [checklist.md](docs/06-checklist.md) | Les pièges par catégorie |
| 07 | [roadmap-plateforme.md](docs/07-roadmap-plateforme.md) | Pourquoi l'infra est une plateforme |
| 08 | [compendium-aax-mc.md](docs/08-compendium-aax-mc.md) | Le grand vrac : 122 points AAX × MC (établi / à vérifier / améliorations) |

## Par où commencer

Le test transport (doc 04). C'est lui qui décide de tout le reste : si le
transport de MC n'est pas sample-accurate et cohérent entre pistes, l'approche
δ(t) sur base timeline commune ne tient pas et il faut basculer sur le
fingerprint pur (doc 05).
