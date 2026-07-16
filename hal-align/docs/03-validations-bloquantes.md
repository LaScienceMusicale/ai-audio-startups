# 03 — Les 4 validations bloquantes

Ces quatre tests sont **go/no-go**. Tant qu'ils ne sont pas verts, on ne
construit rien. Chacun peut invalider une hypothèse et forcer un changement
d'architecture — c'est pour ça qu'ils passent avant le code.

Ordre imposé : **1 d'abord** (il décide de tout le reste), protocole détaillé
dans le doc 04.

## §1 — Transport sample-accurate et cohérent entre pistes

**Hypothèse.** `GetCurrentNativeSampleLocation` renvoie une position exacte,
monotone pendant la lecture, et **identique pour deux pistes lues ensemble**.

**Test.** Même clip sur deux pistes, un insert sur chacune, lecture. Les deux
inserts doivent capturer `timelineSampleStart` **identiques** et un décalage
mesuré de **zéro** (protocole doc 04).

**Si échec.** Pas de base timeline commune fiable → on abandonne le δ(t) sur
timeline et on bascule sur le **fingerprint pur** (corrélation directe
capture-à-capture, sans se fier aux estampilles). L'architecture survit mais la
fenêtre de recherche s'élargit et la robustesse au bruit baisse.

## §2 — Entrée AudioSuite = segment sample pour sample, sortie = entrée

**Hypothèse.** Ce que l'AudioSuite reçoit en entrée est **exactement** le
segment du clip (mêmes samples, même longueur), et ce qu'il rend a la **même
longueur** que l'entrée.

**Test.** AudioSuite identité (passthrough) sur un segment connu → diff binaire
entrée/sortie = 0, longueurs égales.

**Si échec — longueurs différentes.** Un délai qui change la longueur casse le
conform. Il faut alors compenser (padding/troncature) pour garder
`len(out) == len(in)` — mais si MC lui-même resample ou retime l'entrée, le
fingerprint devient non fiable → drapeau rouge.

## §3 — Statics visibles entre insert et AudioSuite dans ta version de MC

**Hypothèse.** Un `static` du binaire est partagé entre une instance insert et
une instance AudioSuite (in-process, même image).

**Test.** L'insert incrémente un compteur statique pendant la lecture ;
l'AudioSuite lit ce compteur au render et le reporte (marqueur / log). S'il voit
la valeur écrite par l'insert → statics partagés.

**Si échec.** On **ne** compte **pas** sur les statics → chemin (b) obligatoire :
**fichier mappé mémoire** (doc 02 §Lien 2b). Ce n'est pas bloquant pour
l'architecture (le mmap est de toute façon préféré), mais ça tranche la
politique de compilation.

## §4 — Granularité et contrôle transport réels du SDK Extensions

**Hypothèse.** Le SDK Extensions permet de **lancer une lecture bornée**
(In/Out) et d'en connaître les bornes assez finement pour orchestrer la capture.

**Test.** Depuis l'extension : poser In/Out sur une plage connue, déclencher la
lecture, vérifier que la lecture démarre/s'arrête aux bornes attendues et que
l'extension sait quand c'est fini.

**Si échec.** L'orchestration automatique (le « Align scene » en un clic) n'est
pas possible → on reste sur le **fallback deux passes AudioSuite** (doc 04),
piloté à la main. La maquette et même une v1 utilisable **tiennent sans
l'extension** ; §4 conditionne seulement le confort du workflow final, pas la
faisabilité.

---

## Tableau de décision

| Test | Vert | Rouge → conséquence |
|------|------|----------------------|
| §1 Transport | δ(t) sur timeline commune | Fingerprint pur, fenêtre élargie |
| §2 AudioSuite I/O | render direct | Compensation longueur, ou abandon si retime MC |
| §3 Statics | chemin (a) possible | mmap obligatoire (chemin (b)) |
| §4 Extension | « Align scene » 1 clic | Fallback 2 passes manuel |

**Seul §1 peut tuer le projet.** §2 le fragilise. §3 et §4 ne font que choisir
entre variantes déjà prévues. D'où : **commencer par §1.**
