# 06 — Checklist des pièges

La « checklist des 100 points » condensée en catégories, centrée sur les pièges
majeurs. Cocher au fur et à mesure. Les 5 **pièges tueurs** sont marqués 🔴.

## Timing / transport

- [ ] `GetCurrentNativeSampleLocation` (Native, pas Tick) sur le début de buffer
- [ ] Capture uniquement si `IsTransportPlaying`
- [ ] Détection de discontinuité (locate/boucle) → nouveau segment de capture
- [ ] 🔴 **Varispeed / retime** : si MC lit à vitesse variable, la base timeline
      ment → détecter et refuser (le fingerprint doit rester le juge)
- [ ] Sample rate lu à l'exécution, pas supposé
- [ ] Monotonie et contiguïté des estampilles vérifiées (V3, doc 04)

## Capture

- [ ] Ring-buffer pré-alloué, dimensionné pour la plus longue scène visée
- [ ] Copie de l'entrée **avant** tout traitement (bit-transparence)
- [ ] Longues captures : mmap paginé, pas RAM statique (doc 02 §Lien 2b)
- [ ] Un seul producteur / un seul consommateur par port

## IPC / registre

- [ ] Verrou **uniquement** sur open/close/snapshot, jamais sur `push`
- [ ] `push` sans allocation, sans syscall, sans verrou
- [ ] 🔴 **Versionnage du format de capture dès le v1** : `formatMajor` refuse
      les builds incohérentes (doc 02 §Format)
- [ ] `epochId` régénéré par session de lecture
- [ ] Politique statics (a) vs mmap (b) tranchée par le test §3

## AudioSuite

- [ ] Longueur sortie == longueur entrée (doc 03 §2)
- [ ] 🔴 **Re-render silencieux après trim** : un clip retaillé puis re-rendu ne
      doit pas réutiliser une capture périmée → contrôle `epochId` + Source/TC
- [ ] Mode Preview = capture only (fallback passe 1)
- [ ] Chemin métadonnées ET chemin fingerprint tous deux implémentés

## Extension MC

- [ ] Lecture bornée In/Out pilotable (test §4)
- [ ] Lecture des segments : Start TC, Source File, nom
- [ ] Pose de marqueurs de résultat
- [ ] Fonctionne aussi en absence d'extension (fallback 2 passes)

## Métadonnées / conform

- [ ] Le render reste un effet de clip (precompute), master clip préservé
- [ ] 🔴 **Jamais** d'export/réimport WAV ni de nouveau master clip
- [ ] Start TC / Source File / nom intacts après render (test AAF aller-retour)

## DSP

- [ ] GCC-PHAT, fenêtre ±45 ms
- [ ] Délai fractionnaire interpolé (parabolique + filtre)
- [ ] Latence **constante** déclarée, jamais dynamique (PDC MC fragile)
- [ ] Lissage / slew de δ(t) contre le warble
- [ ] Test de polarité
- [ ] Seuil de confiance → bypass par défaut si faible

## Déploiement / multi-projet

- [ ] 🔴 **Multi-projet** : deux sessions MC ouvertes ne doivent pas partager un
      registre par erreur → `epochId` + isolation du fichier mmap par session
- [ ] Nettoyage des captures mmap orphelines (crash, session fermée)
- [ ] Chemin du fichier de capture configurable et sûr en écriture
- [ ] Comportement défini si le registre est absent/corrompu (refus propre)

---

## Les 5 pièges tueurs, résumés

1. **Varispeed / retime** MC → base timeline mensongère.
2. **Versionner le format de capture** dès le v1.
3. **Re-render silencieux après trim** → capture périmée appliquée.
4. **Multi-projet** → registres croisés entre sessions.
5. **Latence dynamique** → PDC de MC désynchronisée, mix décalé en silence.
