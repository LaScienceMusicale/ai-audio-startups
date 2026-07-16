# 08 — Compendium AAX × Media Composer

> Le grand vrac organisé : tout ce qu'il faut savoir, vérifier ou envisager pour
> développer des plugins AAX dans Media Composer, plus les améliorations
> possibles de Hal Align. Marquage :
> **✔** établi · **⚠️** à vérifier dans ta version de MC · **💡** idée/amélioration.
>
> Contexte version : MC 2025.12.x est la branche courante ; le Panel SDK
> s'appelle désormais officiellement **Media Composer Extensions** avec un menu
> déroulant dédié depuis 2025.12.

---

## A. L'écosystème AAX — fondamentaux

1. ✔ AAX est le seul format plugin audio de MC moderne — RTAS est abandonné, pas de VST/AU.
2. ✔ Trois déclinaisons AAX : **Native** (temps réel CPU), **AudioSuite** (offline), **DSP** (HDX). MC n'héberge que Native et AudioSuite — jamais DSP.
3. ✔ Le SDK se télécharge sur developer.avid.com/aax après licence click-through ; questions à audiosdk@avid.com.
4. ✔ Un même binaire AAX peut se décrire à la fois en Native et en AudioSuite (deux effect descriptions dans le même Describe) — c'est exactement ce que fait Hal Align (insert + AudioSuite dans une image unique, condition du partage de statics, doc 02).
5. ✔ Tout AAX distribué doit être **signé PACE** (wraptool/Eden) — même gratuit. Compte PACE développeur requis (gratuit pour la signature AAX). Un AAX non signé ne charge pas dans les builds shipping.
6. ✔ Bundle `.aaxplugin` (dossier), installé dans `C:\Program Files\Common Files\Avid\Audio\Plug-Ins` (Win) / `/Library/Application Support/Avid/Audio/Plug-Ins` (Mac). Partagé entre Pro Tools et MC sur la même machine.
7. ✔ Le SDK fournit **DSH/dish** (shell de test hôte) et des outils de validation. Il n'existe **aucun harnais de test MC** : on valide la conformité AAX dans dish/Pro Tools, puis on teste le comportement hôte dans MC lui-même.
8. ⚠️ Les versions min/max du SDK AAX supportées par MC 2025.x — à confirmer dans la doc développeur de ta version (la matrice hôte/SDK n'est pas publique).
9. ✔ JUCE exporte en AAX (chemin SDK à fournir) — chemin le plus courant si l'AAX existant est JUCE ; sinon SDK natif direct.
10. ✔ Architecture : ACF (Avid Component Framework), interfaces COM-like versionnées (`AAX_IACF*`). Ne jamais caster à travers les versions — passer par les proxys `AAX_C*` du SDK.
11. ✔ Classes clés : `AAX_CEffectParameters` (état/params), `AAX_IEffectGUI` (UI), `AAX_ITransport` (transport), `AAX_IController` (hôte), ProcessProc (rendu temps réel), RenderAudio (AudioSuite).
12. ✔ La description d'effet (Describe) fige : stem formats, latence, catégorie, IDs (ManufacturerID/ProductID/TypeIDs quadruplets), propriétés AudioSuite. Les TypeIDs doivent être **uniques et stables** — les changer casse les sessions existantes.
13. ✔ Chunks d'état : la sauvegarde de session passe par les chunks (`GetChunk`/`SetChunk`). Versionner le chunk dès le v1 (même logique que le format de capture, doc 02).
14. ✔ Page tables (`.xml`) pour surfaces de contrôle — optionnel, mais leur absence fait des warnings de validation.

## B. Hébergement AAX côté Media Composer — spécificités et pièges

15. ✔ **5 inserts max par piste audio** — l'insert Hal doit cohabiter ; viser une seule slot consommée.
16. ✔ Les inserts MC sont des **track effects** temps réel ; AudioSuite est un **clip effect** qui rend un precompute, master clip préservé (doc 01).
17. ✔ Sample rate = celui du projet (44.1/48/96 kHz typiques). Le lire à l'exécution, jamais le supposer (checklist doc 06).
18. ⚠️ Taille et stabilité des buffers de rendu MC (fixes ? variables selon la charge ?) — mesurer dans le test transport (V3, doc 04).
19. ⚠️ La PDC de MC pour les inserts : réputée fragile, historiquement partielle. D'où la règle absolue latence constante déclarée (doc 05). Mesurer la compensation réelle dans ta version : même clip, deux pistes, un insert à latence connue sur une seule → l'écart résiduel EST la qualité de la PDC.
20. ⚠️ MC honore-t-il `SetSignalLatency` en cours de vie du plugin ? Ne pas s'y fier : latence figée au Describe.
21. ⚠️ Comportement de MC pendant le **scrub/jog** : les inserts reçoivent-ils de l'audio avec un transport cohérent ? Probablement à exclure de la capture (garde `IsTransportPlaying`).
22. ⚠️ Pendant un **render vidéo / mixdown audio**, MC repasse-t-il l'audio dans les inserts ? Si oui, avec quel transport ? Risque de pollution du registre → l'`epochId` protège, mais vérifier.
23. ⚠️ MC instancie-t-il les plugins d'insert une fois par piste ou les recycle-t-il (bypass, réouverture de projet) ? Impacte le cycle open/close des ports du registre.
24. ⚠️ L'AudioSuite MC en **Preview** : boucle-t-il la sélection ? Le fallback passe 1 (doc 04) suppose une lecture simple — si preview boucle, la détection de discontinuité doit clore proprement les segments.
25. ⚠️ Les **handles AudioSuite** (audio au-delà de la sélection) : Pro Tools les offre ; MC ? Si oui, δ appliqué peut puiser dans le handle au lieu de zéro-padder les bords — gros gain de qualité aux bornes du clip.
26. ⚠️ AudioSuite MC et **clips groupés/multicam** : sur quoi porte le render ? À tester avant de promettre le support.
27. ⚠️ AudioSuite MC sur une **sélection multi-clips** : un render par clip ou un render global ? Impacte le chemin fingerprint (une corrélation par clip).
28. ⚠️ Mono vs stéréo : le lav est mono, le boom parfois stéréo (MS décodé ?). Déclarer les stem formats couverts, refuser proprement le reste.
29. ✔ Pas de sidechain, pas d'ARA, pas d'AudioSuite multi-entrée — le verrou fondateur du projet (doc 01). Aucun signe que MC 2025.x change ça.
30. ⚠️ MC charge-t-il les AAX dans le processus principal ou un process audio séparé ? L'hypothèse in-process fonde le chemin statics (a) — c'est le test §3 (doc 03). Un MC futur qui sandboxerait l'audio tuerait (a) mais pas (b) mmap.
31. ⚠️ Deux projets MC ouverts (ou MC + Pro Tools ouverts !) : PT et MC partagent le dossier de plugins — le fichier mmap doit être **namespacé par process et par session** pour qu'un Pro Tools ouvert à côté ne lise pas le registre MC.
32. ⚠️ Comportement à la **fermeture de projet sans fermer MC** : les inserts sont-ils détruits ? Les ports doivent se fermer proprement (close sous verrou) sinon fuite de ports.
33. ⚠️ **Undo après render AudioSuite** : MC restaure le clip — le marqueur « aligné » posé par l'extension devient mensonger. L'extension devrait vérifier l'état réel au lieu de faire confiance à son historique.
34. ⚠️ **Trim après render** : le precompute suit-il ou MC re-rend-il silencieusement ? (piège tueur n°3, doc 06) — test dédié obligatoire.
35. ⚠️ Consolidate/transcode/media management sur un clip rendu : le precompute survit-il ? L'AAF l'emporte-t-il ?
36. ⚠️ **AAF vers Pro Tools** : l'effet AudioSuite rendu voyage comme média rendu ou comme référence au master ? Les deux sont acceptables (le mixeur veut le rendu OU le brut + marqueur δ) mais il faut savoir lequel et le documenter pour les mixeurs.
37. ⚠️ Projets 23.976/24/25 fps : le TC change mais les samples non — tout le raisonnement Hal est en samples, garder le TC uniquement pour l'affichage et `sourceHash`.
38. ⚠️ MC et les fichiers source **48 kHz dans un projet 44.1** (SRC à la volée) : l'audio capté par l'insert est post-SRC — le δ reste valide (les deux pistes subissent le même SRC) mais le fingerprint contre le fichier source ne matcherait pas. On ne corrèle QUE capture contre capture (déjà le design, doc 02) — ne jamais corréler contre le fichier source.

## C. Transport & timing — au-delà du doc 02

39. ✔ `GetCurrentNativeSampleLocation` = position échantillon native ; `GetCurrentTickPosition` = ticks musicaux (inutile ici) ; `IsTransportPlaying` = garde de capture.
40. ⚠️ Y a-t-il un décalage fixe entre la position transport lue et le buffer réellement fourni (pré-roll interne MC) ? La Manip B (doc 04) le révèle ; s'il est constant, on le calibre une fois et on le soustrait.
41. ⚠️ Loop play MC : la position saute-t-elle proprement (discontinuité franche) ou glisse-t-elle ? La détection de segment (doc 02) doit être testée en boucle.
42. ⚠️ Lecture inverse / shuttle arrière : positions décroissantes — exclure de la capture (la monotonie V3 devient un garde d'exécution, pas juste un test).
43. ⚠️ `GetCurrentLoopPosition` / autres accesseurs transport AAX : lesquels MC implémente-t-il réellement ? Beaucoup d'hôtes ne remplissent qu'une partie de `AAX_ITransport` — sonde exhaustive à logger une fois dans l'insert instrumenté.
44. 💡 Ajouter au doc 04 une **Manip D — stress** : lecture avec charge CPU artificielle (beaucoup de pistes + effets) pour vérifier que les estampilles restent justes quand MC souffre. C'est là que les hôtes trichent.
45. 💡 Calibration automatique au premier lancement : l'insert joue le test offset-zéro tout seul (l'utilisateur pose le même clip sur 2 pistes, clique « calibrer ») et stocke le biais mesuré par version de MC.
46. 💡 Journal de santé transport permanent (compteur de discontinuités, sauts, buffers hors-ordre) exposé dans l'UI de l'insert — diagnostic à distance quand un utilisateur signale un désalignement.

## D. Threading, mémoire, temps réel — discipline

47. ✔ ProcessProc/RenderAudio : jamais d'allocation, de verrou, de syscall, d'I/O fichier, de logging synchrone (doc 02 §Lien 2).
48. ✔ Logging temps réel → ring buffer lock-free vidé par un thread de service (le log du test transport doit suivre cette règle sinon il fausse la mesure).
49. ✔ Un producteur/un consommateur par port, index atomiques, publication release/acquire — pas de mutex sur le chemin chaud.
50. ⚠️ Sur quel thread MC appelle-t-il `GetChunk`/`SetChunk`, les notifications de paramètres, la GUI ? Supposer « pas le thread audio » mais vérifier — certains hôtes surprennent.
51. ✔ Dimensionner le ring : scène max visée × sample rate max × canaux × 4 octets. 20 min @ 96 kHz stéréo ≈ 920 Mo → confirme mmap paginé (doc 02) et suggère 💡 une option « fenêtre glissante » (ne garder que les N dernières minutes) pour les inserts laissés en permanence.
52. 💡 Compression légère de la capture (float32 → float16, voire 24 dB de headroom en int16 + gain) : ÷2 à ÷4 sur l'empreinte, largement suffisant pour la corrélation (pas pour le rendu — le rendu lit le vrai signal d'entrée AudioSuite, jamais la capture).
53. 💡 Décimation pour la recherche grossière : corrélation d'abord à 8 kHz (rapide, large), raffinage à pleine résolution sur ±2 ms — accélère GCC-PHAT d'un ordre de grandeur sur les longues scènes.
54. ✔ Alignement mémoire/SIMD : FFT et corrélation en blocs alignés 32/64 octets ; sur Mac ARM, Accelerate/vDSP ; sur Win, IPP ou FFT maison AVX2.
55. ⚠️ MC sur Apple Silicon : l'AAX doit être universel (arm64 + x86_64) signé — vérifier que la build existante l'est, sinon Rosetta fausse les perfs de corrélation.

## E. AudioSuite — le contrat fin

56. ✔ Longueur sortie == longueur entrée, toujours (validation §2, doc 03).
57. ✔ Le δ appliqué décale le contenu DANS la fenêtre : bord entrant à combler. Options : zéro-pad (v0), handles si MC les donne (⚠️ n°25), 💡 micro-fade 5 ms aux bornes pour éviter le clic.
58. ⚠️ L'AudioSuite MC a-t-il un vrai mode « analyze » séparé du render (deux passes internes) ? Si oui, le fallback passe 1 (capture boom) peut être un analyze officiel au lieu d'un preview détourné — plus propre.
59. ✔ Idempotence : re-rendre un clip déjà aligné doit re-corréler contre l'entrée actuelle (déjà décalée) et trouver δ≈0 → no-op propre, pas un double décalage. Le fingerprint donne ça gratuitement ; le chemin métadonnées doit le vérifier explicitement.
60. 💡 Mode « dry run » : calcule δ et la confiance, pose le marqueur, ne rend RIEN. Le monteur voit ce qui va se passer avant de commettre — confiance produit énorme pour pas cher.
61. 💡 Rapport de passe : après un « Align scene », un résumé (n clips, δ min/max/médian, confiances, refus) déposé en marqueur ou dans le panel — c'est aussi la note de session pour le mixeur (cf. roadmap doc 07).
62. 💡 Préférences par projet stockées dans le chunk : fenêtre de recherche, seuil de confiance, politique polarité — les plateaux ont des habitudes différentes.
63. ⚠️ Nom du precompute / suffixe de clip après render : MC ajoute-t-il un suffixe visible ? Si personnalisable, y encoder « HAL δ=+3.2ms ✓ » — traçabilité dans la timeline sans marqueur.

## F. DSP — au-delà du doc 05

64. ✔ GCC-PHAT : β réglable (PHAT-β, 0.5–1.0) — β<1 réintroduit un peu d'amplitude, utile quand le lav est très bruité (vent) et que la phase seule devient instable.
65. 💡 Pré-filtre passe-bande 200 Hz–4 kHz avant corrélation : la parole y vit, les LF de perche et les HF de frottements polluent — améliore le pic sans toucher au rendu.
66. 💡 VAD (détection d'activité vocale) simple avant corrélation : ne corréler que les fenêtres où ça parle — le silence de plateau ne vote pas.
67. 💡 δ(t) par morceaux : une estimation par fenêtre de 2–5 s, puis régression robuste (RANSAC/médiane glissante) → détecte la dérive d'horloge (pente) ET les sauts (changement de prise) au lieu d'un δ unique.
68. ✔ La pente de δ(t) EST le ratio d'horloges : si l'enregistreur lav dérive de 20 ppm, resampler d'un facteur constant vaut mieux que rattraper par à-coups (le lissage doc 05 gère le résiduel).
69. 💡 Score de confiance composite : hauteur du pic PHAT + ratio pic/2e pic + cohérence inter-fenêtres + énergie vocale — plus robuste que le pic seul, et exposable en UI (vert/orange/rouge).
70. 💡 Polarité par bande (le grave peut être inversé et pas le médium avec certains couples capsule/HPF) — v2, rare mais réel.
71. 💡 Après alignement : vérification par **somme test** — RMS(boom+lav aligné) vs RMS(boom+lav brut) ; si la somme alignée n'est pas plus « pleine », alerte (probable faux pic).
72. ✔ Interpolation d'application : Lagrange 3e ordre suffit pour la parole ; sinc fenêtré 32 taps si on vise le « bit-perfect marketing ». Coût négligeable en offline.
73. 💡 Fenêtre de recherche adaptative : partir à ±45 ms ; si le pic est au bord, élargir automatiquement une fois (×2) avec pénalité de confiance — évite l'échec silencieux sur les plateaux exotiques (retards > 45 ms).
74. 💡 Multi-lav : N lavs contre un boom en une passe de lecture (un port par piste, le registre est déjà multi-ports) — c'est le vrai cas série télé.
75. 💡 Export du profil de dérive (δ(t) complet) en sidecar JSON à côté du rapport : le mixeur Pro Tools peut le rejouer si besoin.

## G. Extension MC (Media Composer Extensions, ex-Panel SDK)

76. ✔ Renommé **Media Composer Extensions** ; menu déroulant dédié dans MC depuis 2025.12 ; distribution via le programme partenaire/marketplace Avid.
77. ✔ Modèle : panels web (HTML/JS) intégrés dans MC, API JS vers projets, bins, séquences, clips, **marqueurs** et métadonnées.
78. ⚠️ **Contrôle transport** : la capacité exacte (lancer lecture bornée In/Out, savoir quand elle finit) est LE point du test §4 (doc 03) — la doc marketing parle d'interaction timeline, pas de piloter Play. À vérifier dans la doc développeur du SDK Extensions (accès partenaire).
79. ⚠️ L'extension peut-elle lire **Start TC / Source File par segment** de la timeline (pas juste par bin) ? Nécessaire pour `sourceHash` (doc 02) — sinon fingerprint pur.
80. ⚠️ L'extension peut-elle **déclencher un render AudioSuite** ou seulement guider l'utilisateur ? Si non scriptable, le workflow 1-clic devient « 1 clic + 1 raccourci » — acceptable mais à savoir tôt.
81. ⚠️ Communication extension ↔ plugins : le panel JS ne partage pas les statics C++. Le pont naturel : **le même fichier mmap** (l'extension lit/écrit l'en-tête — epochId, commandes, résultats) ou un socket localhost. Le mmap gagne : déjà là, pas de firewall.
82. 💡 Protocole de commande minimal dans l'en-tête mmap : `commandSeq` (uint64 croissant) + `commandCode` + payload — l'extension écrit, les inserts lisent au prochain buffer (lecture atomique, jamais de verrou côté audio).
83. ⚠️ Cycle de vie du panel (fermé/rouvert, MC minimisé) vs captures en cours — l'état de vérité doit vivre dans le mmap, le panel n'est qu'une vue.
84. 💡 UI panel : liste des scènes détectées (par In/Out ou par sélection), état par clip (aligné ✓ / δ / confiance / refusé), bouton par ligne + « Align all », log repliable.
85. 💡 Les marqueurs posés portent un schéma stable (`HAL|v1|δ=+3.2ms|conf=0.94|epoch=...`) → parsables par d'autres outils (et par l'extension elle-même pour l'idempotence n°59).
86. 💡 Mode « QC seul » de l'extension : scanner la séquence et marquer les couples boom/lav suspects (offset détecté > seuil) SANS rien rendre — produit d'appel gratuit qui vend l'alignement.

## H. Signature, distribution, install

87. ✔ Chaîne : build → signature PACE (wraptool) → notarisation Apple (Mac) / signature Authenticode (Win) → installeur. Les trois manquent souvent un des trois et l'AAX ne charge pas en silence.
88. ✔ MC log de chargement plugins : vérifier où MC journalise les AAX refusés (console/logs MC) — premier réflexe support.
89. 💡 Installeur unique posant l'AAX (dossier commun Avid) ET l'extension (dossier Extensions), avec vérification de version croisée (le `formatMajor` du doc 02 s'applique aussi au couple AAX/extension).
90. ⚠️ Politique marketplace Avid pour les extensions (validation, signature, délais) — à intégrer au planning si distribution large.
91. 💡 Canal bêta : licence à durée (iLok time-limited) + format de capture en `formatMajor` distinct pour que les bêtas ne polluent jamais une prod.
92. ✔ iLok : PACE impose la signature, pas la protection — on peut signer sans DRM (activation machine). Décision business, pas technique.

## I. Test & CI

93. ✔ Étage 1 (sans MC, CI-able) : le cœur DSP + registre compilés en lib native → tests unitaires (corrélation sur fixtures synthétiques : bruit + délais connus, dérives, polarités, SNR décroissants) — la courbe δ_estimé vs δ_vrai est le contrat de non-régression.
94. ✔ Étage 2 : dish/validator du SDK AAX pour la conformité plugin (chargement, describe, chunks).
95. ⚠️ Étage 3 : MC lui-même — pas d'automatisation officielle ; 💡 l'extension peut servir de harnais (scripter les scénarios de test qu'elle sait piloter) — l'outil de test devient un sous-produit du produit.
96. 💡 Corpus de test réel : demander à 2–3 monteurs des rushes boom/lav anonymisés (plateau réel, vent, HF) — les fixtures synthétiques ne suffisent jamais.
97. 💡 Golden files : captures mmap enregistrées de vraies sessions MC, rejouées en CI contre le registre — teste le parseur de format sans MC.
98. ✔ Matrice de test MC : au minimum {version MC courante, N-1} × {Mac ARM, Win} × {44.1, 48, 96 kHz} × {mono, stéréo}.

## J. Améliorations produit Hal Align (v1.x)

99. 💡 Raccourci clavier MC mappable pour « align selection » (via l'extension si elle expose des commandes).
100. 💡 Tri-état par clip dans le panel : auto (seuil) / forcer / jamais — le monteur garde la main.
101. 💡 Tolérance d'affichage en ms ET en frames (les monteurs pensent en frames).
102. 💡 Préréglage « documentaire » (fenêtre large, VAD agressif) vs « fiction plateau » (fenêtre serrée, seuil haut).
103. 💡 Undo-safe : ne jamais stocker d'état qui mente après un undo MC (cf. n°33) — re-scanner plutôt que mémoriser.
104. 💡 Détection de clips DÉJÀ alignés ailleurs (Auto-Align Post en amont, marqueur d'un autre outil) → proposer skip.
105. 💡 Localisation FR/EN dès le v1 (marché : fiction FR + doc US) — les chaînes dans un catalogue, pas dans le code.
106. 💡 Telémétrie opt-in minimale : version MC, sample rate, taux de refus par confiance — pour savoir où ça casse en vrai.
107. 💡 Page de diagnostic dans le panel : version AAX vs version extension vs `formatMajor` mmap vs version MC — la capture d'écran de support universelle.
108. 💡 Mode dégradé explicite : si l'extension est absente, l'AudioSuite affiche le mode 2-passes avec un mini-tuto intégré (le fallback doc 04 devient une feature documentée, pas un secret).

## K. Modules plateforme (rappel doc 07, enrichi)

109. 💡 Auto-ducking musique/dialogue : enveloppe dialogue capturée → gain musique rendu en AudioSuite (le graal doc/reality — impossible aujourd'hui dans MC).
110. 💡 Sélecteur boom/lav par ligne (SNR + proximité + confiance d'alignement déjà calculée — l'alignement v1 produit déjà la moitié des features).
111. 💡 EQ matching lav→boom (spectres moyens des captures, courbe de correction en AudioSuite).
112. 💡 Anti-masquage : creuser la musique dans les bandes du dialogue capturé.
113. 💡 Room tone fill : capture du tone de scène → comblement des trous entre segments.
114. 💡 QC loudness timeline entière + marqueurs R128/-24 LKFS (extension seule, sans capture).
115. 💡 Détecteur de problèmes : clipping, dropouts, hum, désynchro labiale suspecte — marqueurs colorés par gravité.
116. 💡 Comparateur de versions de séquence (diff audio V12 vs V13 pour le conform).
117. 💡 Pré-mix d'export AAF : nivelage dialogue + marqueurs + note de session mixeur générée.
118. ✔ Tous partagent le même pont (transport + registre + AudioSuite) : chaque module = un DSP + une vue panel. Le coût marginal décroît à chaque module (doc 07).

## L. Veille & signaux à surveiller

119. ⚠️ Les notes de version MC (2025.12 → 2026.x) à chaque sortie : tout changement au moteur audio, à la PDC, au sandboxing plugins ou aux Extensions peut invalider un ⚠️ ci-dessus — relire cette liste à chaque upgrade MC.
120. ⚠️ Avid pousse l'IA dans les Extensions (démos IBC 2025) — le canal Extensions va gagner des capacités ; re-tester §4 à chaque version majeure, le « 1-clic » peut devenir plus simple.
121. ⚠️ Si Avid ajoutait un jour le sidechain ou l'ARA à MC : le pont Hal reste utile (captures timestampées, orchestration, QC) mais re-prioriser les modules.
122. ✔ Le vide concurrentiel (aucun AAX inter-pistes dans MC : EQ III, Dynamics III, BF76, D-Verb, Mod Delay III, Channel Strip, RX, ERA, CrumplePop, Waves, NUGEN — tous mono-piste) reste la fenêtre stratégique. Premier arrivé sur le pont = avantage structurel (doc 07).

---

## Récapitulatif des ⚠️ prioritaires (à résoudre pendant la maquette)

| ⚠️ | Sujet | Où c'est testé |
|----|-------|----------------|
| 18, 40–43 | Buffers & transport réels de MC | doc 04, Manips A/B + D (n°44) |
| 19–20 | PDC réelle de MC | test dédié n°19 |
| 24–25, 58 | Preview/handles/analyze AudioSuite | fallback doc 04 |
| 30 | In-process ou pas | doc 03 §3 / Manip C |
| 33–35 | Undo/trim/consolidate vs precompute | tests dédiés (piège n°3) |
| 78–80 | Vraies capacités du SDK Extensions | doc 03 §4 |
| 8, 55, 90 | SDK/plateformes/marketplace | doc développeur Avid |
