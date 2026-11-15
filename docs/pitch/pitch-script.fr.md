# SARAURA, script de pitch (Space Apps 2026, jury géologie)

Public : jury à fond géologie / sciences de la Terre, peu IT. Ton : confiant, précis, émotionnel aux bons endroits.
Règle d'or : on explique l'IA « juste assez » pour qu'ils posent la question en Q&A. On explique la géologie et le radar « très bien », avec leurs mots.
Les crochets `[ ]` sont des trous à remplir avec le rapport d'expertise et les personas finaux. Les chiffres sans crochet viennent du projet tel qu'il tourne aujourd'hui.

Durée cible : 6 min (les coupes possibles sont marquées ✂️ pour tenir 4 min).

---

## 0. Quelle catastrophe pour le hook, et pourquoi

| Candidat | Force du hook | Problème |
|---|---|---|
| **Jijel, incendies du 26–30 août 2026** (recommandé) | Le feu éclate **7 jours** après la première diffusion publique des données NISAR (19 août 2026, à vérifier). Dans nos propres données, le satellite regardait déjà Jijel depuis le 17 juin 2026. Catastrophe algérienne, donc la nôtre. Et surtout : la **deuxième catastrophe** (boue, érosion, routes coupées aux pluies d'hiver) est exactement celle que la donnée permet d'anticiper. Le pitch a lieu le 15 novembre : **les pluies d'hiver commencent maintenant**. | On ne peut pas dire « le feu aurait pu être évité ». On dit : « ce qui vient après le feu aurait pu être anticipé ». C'est plus honnête et plus fort devant des géologues (coulées de débris post-incendie, Staley 2017). |
| Mexico, effondrement du métro ligne 12 (3 mai 2021, 26 morts) | L'histoire parfaite du « la donnée existait » : la subsidence différentielle de la zone lacustre est documentée depuis des années. Notre question M4 classe aujourd'hui les lignes A et 12 parmi les pires. | NISAR n'existait pas en 2021 (c'était Sentinel-1). Le rapport officiel pointe d'abord des défauts de construction, l'affaissement est un facteur aggravant. À manier avec prudence devant des experts. Bon **deuxième exemple**, pas un hook. |
| Venezuela, séismes M7.2 + M7.5 du 24 juin 2026 | Le plus émotionnel (bâtiments effondrés, recherche de survivants). Nos seuls labels réels (Copernicus EMS). | Un séisme ne se prévient pas, et l'événement précède la diffusion publique de NISAR. Le hook « on aurait pu » ne tient pas. Garder pour la partie phénomènes. |

**Décision : Jijel.** Le pitch est modulable, la slide 1 et la slide 2 changent, le reste ne bouge pas.

Chiffres Jijel disponibles dans le projet (à l'écran, pas à réciter) :
- 11 passages NISAR entre juin et octobre 2026 sur ~3 500 km² de côte de Petite Kabylie
- 30 843 ha de pentes brûlées raides (≥ 23°) identifiées comme sources de boue
- 12 villages à moins de 250 m d'un chenal de boue principal, 18 à côté d'un secondaire
- 104 tronçons de route à fermer en cas de forte pluie, 179 à surveiller
- 6 réservoirs et embouchures sur 26 classés « lourds » (El Agrem 24 % de bassin brûlé et raide, Tabellout 1 621 ha en amont)
- 119 ha de parcelles agricoles brûlées, dont la moitié en vergers
- Récupération médiane de la végétation : 0,02 (presque rien n'est revenu)

Chiffres officiels à ajouter : `[hectares brûlés officiels]`, `[victimes / évacués]`, `[communes touchées]` (Protection civile, DGF).

---

## 1. LE HOOK : la catastrophe (45 s)

**SLIDE 1** : plein écran, photo ou vidéo de Jijel pendant le feu. Pas de texte. Juste la date : **26 août 2026**.

> Le 26 août 2026, la forêt de Jijel prend feu. En quatre jours, `[X hectares]` de chêne-liège et de pin partent en fumée. `[Y familles]` sont évacuées. Vous connaissez ces images. Nous aussi, c'est chez nous.
>
> Et puis le feu s'éteint. Les caméras partent. Et tout le monde pense que la catastrophe est finie.
>
> Elle ne l'est pas. Elle commence.

**SLIDE 2** : la même colline, en coupe. Pente brûlée, sol nu, un village en bas, un nuage de pluie en haut. Un seul mot : **« Novembre »**.

> Un sol brûlé devient hydrophobe. Il ne boit plus l'eau. À la première grosse pluie d'automne, sur une pente de plus de 23 degrés, l'eau ne s'infiltre pas : elle emporte la cendre, la terre, les troncs, et ça descend en coulée de débris sur le premier village en dessous. Ça, c'est de la géologie connue. Shakesby 2011 : l'essentiel du sol d'un bassin brûlé part dans les premières tempêtes de l'hiver.
>
> On est le 15 novembre. Il pleut sur Jijel cette semaine.

---

## 2. LA DONNÉE ÉTAIT LÀ (40 s)

**SLIDE 3** : une frise. À gauche « 19 août 2026 : première diffusion publique des données NISAR ». Sept jours plus loin : « 26 août : Jijel brûle ». Puis, tous les 12 jours, un trait : les passages du satellite.

> Sept jours avant le feu, la NASA et l'ISRO ouvrent au public les données de NISAR, le radar d'observation de la Terre le plus ambitieux jamais lancé. Et pendant que Jijel brûlait, sous la fumée, de nuit, NISAR passait au-dessus tous les 12 jours et enregistrait chaque pente, chaque hectare, chaque chenal.
>
> La donnée pour savoir quel village était en dessous de quelle pente brûlée existait. Elle existe encore. Elle est en accès libre.
>
> Personne ne l'a lue. Pas par négligence : parce que personne ne *pouvait* la lire.

---

## 3. NISAR : ce que c'est, et ce que ça change (50 s)

**SLIDE 4** : le satellite, et trois lignes :
- NASA + ISRO (Inde) · lancé le 30 juillet 2025
- Radar en bande L (24 cm) + bande S · antenne de 12 m · fauchée de 240 km
- Revisite tous les **12 jours**, jour et nuit, à travers nuages et fumée

> NISAR, c'est une mission conjointe NASA-ISRO. Ce n'est pas un appareil photo. C'est un radar à synthèse d'ouverture : un capteur **actif**. Il éclaire lui-même le sol avec une onde de 24 centimètres, la bande L, et il écoute l'écho.
>
> Pour vous, trois conséquences. Un : la bande L **traverse** les nuages, la fumée, la nuit, et même la canopée. Elle voit le sol sous la forêt. Deux : à chaque passage, il mesure la **rétrodiffusion** de chaque pixel de 20 mètres sur 20, en deux polarisations, HH et HV. La HV, c'est la signature du volume végétal : quand la forêt brûle, la HV s'effondre. Trois : en comparant la **phase** de deux passages, l'interférométrie radar, l'InSAR, mesure un déplacement du sol de l'ordre du centimètre. Subsidence, glissement, déformation co-sismique, gonflement d'un volcan.
>
> Un instrument géodésique global, gratuit, qui repasse tous les 12 jours. Pour la géologie appliquée, c'est une rupture.

---

## 4. LE PROBLÈME : une ressource brute (35 s)

**SLIDE 5** : une capture d'écran brute d'un fichier HDF5 (arborescence illisible). En dessous : **« 1,9 à 5,3 Go par fichier · phase enroulée · bruit ionosphérique ±17 cm »**.

> Voilà à quoi ressemble la donnée. Un fichier HDF5 de 2 à 5 gigaoctets par passage. De la phase radar enroulée entre −π et +π. Une couche ionosphérique qui, si on ne la corrige pas, fabrique 17 centimètres de faux mouvement du sol tous les 12 jours. On l'a mesuré sur Mexico.
>
> Ce n'est pas une carte. C'est du minerai. Une ressource brute, nouvelle, extraordinairement riche, et inexploitable par un ingénieur de la Protection civile, un forestier, un maire, ou un acheteur de terrain.
>
> Notre travail, pendant ces deux jours : transformer ce minerai en réponses.

---

## 5. LE MÉCANISME DE BASE : apprendre à lire l'écho (70 s)

C'est ici qu'on explique l'IA « juste assez ». Une image mentale, pas d'équations. Le détail (U-Net, attention temporelle, LightGBM, validation croisée spatiale) reste pour la Q&A.

**SLIDE 6** : schéma en deux colonnes.
- À gauche, **X** : la pile des passages NISAR (HH, HV), grille 20 × 20 m.
- À droite, **Y** : une carte optique par ciel clair (Sentinel-2) ou une carte officielle (USDA, Copernicus EMS).
- Une flèche au milieu : **« la machine apprend X → Y »**.
- En bas : **« Ensuite : Y à partir de X seul. Nuit, nuages, fumée. »**

> Le principe tient en une phrase : **un humain ne sait pas lire un écho radar, mais une machine peut apprendre à le faire si on lui montre la réponse.**
>
> Concrètement. Pour chaque pixel de 20 m sur 20, on a d'un côté ce que NISAR a entendu : l'écho en HH et en HV, passage après passage. C'est notre X. De l'autre côté, pour la phase d'apprentissage uniquement, on prend une image optique par ciel clair, Sentinel-2, et on en tire automatiquement un masque de vérité terrain : brûlé, pas brûlé. Eau, pas eau. Maïs, soja. C'est notre Y.
>
> On entraîne un modèle de **segmentation sémantique** : il attribue à chaque pixel une catégorie, à partir de l'écho seul. Une fois entraîné, l'optique n'est plus nécessaire. Le modèle lit NISAR directement, de nuit, sous la fumée, et produit une nouvelle carte tous les 12 jours.
>
> Résultat sur Jijel : notre modèle cartographie le brûlé avec un recouvrement de 86 % par rapport à la vérité optique, là où la méthode classique, un simple seuil de chute en HV, plafonne à 21 %.
>
> Ça, c'est la fondation. Rendre **visible** ce que NISAR mesure. Tout le reste de SARAURA est construit dessus.

✂️ Pour tenir 4 min : couper le paragraphe « Concrètement » et garder la phrase en gras + le résultat 86 % / 21 %.

---

## 6. LE PATTERN DE NOS MODÈLES : IA hybride, en deux étages (40 s)

**SLIDE 7** : un schéma en pyramide.
- Étage 1 (commun) : **Segmentation / changement sur l'écho NISAR** (le modèle appris).
- Étage 2 (par phénomène) : **Expertise du domaine, en règles publiées** (géotechnique, hydrologie, sismologie…).
- Sommet : **Risque = Aléa × Exposition × Vulnérabilité**.

> On n'a pas fait une IA qui décide toute seule. On a fait une **IA hybride**. Deux étages.
>
> L'étage du bas est le même partout : le modèle qui lit l'écho et détecte le changement. L'étage du haut, c'est votre science : des règles explicites, publiées, citées. Le seuil de 23 degrés de Staley pour les coulées de débris post-incendie. La limite de tassement différentiel de 1/500 de Bjerrum pour la fissuration des murs. Le routage hydrologique par priority-flood sur le MNT Copernicus. La perte de cohérence interférométrique comme proxy de dommage, Yun 2015.
>
> Et une seule formule qui tient tout : **Risque = Aléa × Exposition × Vulnérabilité.** Le radar donne l'aléa. OpenStreetMap donne l'exposition, villages, routes, lignes de métro, champs. Vos seuils donnent la vulnérabilité.
>
> Pourquoi ce choix ? Parce que les modèles ne voyagent pas et les règles voyagent. Notre modèle incendie entraîné à Jijel tombe à 36 % sur un feu dans l'État de Washington. Les règles de pentes brûlées, elles, ont tourné sur Washington **sans une ligne de code en plus**. Et chaque réponse reste explicable : « rouge parce que la pente brûlée fait 27 degrés et que le village est à 180 mètres en aval ». Un géologue peut la contester. C'est voulu.

---

## 7. SIX PHÉNOMÈNES, SIX EXPERTISES, DES GENS (90 s)

Un phénomène par ligne, trois temps chacun : la dimension humaine, ce qu'on mesure, ce qu'on a adapté. Les trous `[ ]` attendent le rapport d'expertise et les personas.

**SLIDE 8** : six vignettes avec un pictogramme, un lieu et une phrase humaine. Le présentateur en lit trois en détail (feu, subsidence, séisme : ceux qui ont des questions construites) et survole les trois autres.

> La même architecture, adaptée six fois. Parce que chaque phénomène touche des gens différents, à des moments différents.

**1. Incendie — Jijel (Algérie) et Sinlahekin (Washington, États-Unis)**
> Après le feu, il y a un forestier qui doit choisir où replanter en premier, un maire qui doit décider quelle route fermer quand la météo annonce 40 mm, une agence des barrages qui va recevoir la cendre dans son réservoir, un agriculteur dont le verger a brûlé et qui attend une liste d'indemnisation.
> On mesure : la carte du brûlé à travers la fumée, le routage de l'eau sur le MNT, les pentes brûlées raides en amont de chaque chenal, la récupération du signal végétal HV passage après passage.
> On a adapté pour : `[personas finaux]` — aujourd'hui Protection civile, forestiers, conseil communal, travaux publics, agence des barrages, agriculteurs, parc national.

**2. Subsidence — Mexico**
> Mexico s'enfonce. Jusqu'à 30 centimètres par an à Nezahualcóyotl, sur l'argile de l'ancien lac. Ce n'est pas l'enfoncement qui tue les bâtiments, c'est l'enfoncement **inégal** : le tassement différentiel qui ouvre les murs et déforme les rails.
> On mesure : la vitesse verticale par InSAR sur 28 passages, l'accélération, et le nombre d'années avant que le tilt atteigne 1/500.
> On a adapté pour : une famille qui achète un terrain, un promoteur, l'exploitant du métro — 37 km de lignes atteignent la limite en moins de 15 ans, lignes A et 12 en tête. `[compléter]`

**3. Séisme — Venezuela, 24 juin 2026, M7.2 et M7.5**
> Dans les 72 premières heures, la seule question qui compte : où chercher d'abord ? Où sont les immeubles qui ont bougé ?
> On mesure : la perte de cohérence interférométrique entre le passage d'avant et celui d'après, le déplacement co-sismique, et un modèle entraîné sur les vrais relevés de dommages de Copernicus EMS : il atteint une précision moyenne de 0,73 contre 0,61 pour la méthode de référence.
> On a adapté pour : les équipes de secours (inspecter d'abord), les urbanistes (reconstruire où ?), les réseaux (quelles conduites ont traversé un sol qui a bougé). `[compléter]`

**4. Volcan — Krasheninnikov, Kamchatka**
> `[dimension humaine : observatoire KVERT, aviation, camps dans les vallées de lahars]`
> On mesure : l'arrivée de lave nouvelle sous les nuages et dans la nuit polaire, le gonflement de l'édifice par InSAR. Honnêteté : ici le modèle appris est faible (le signal est rare), on s'appuie sur la physique.
> On a adapté pour : `[ ]`

**5. Zone humide / inondation — Delta de l'Okavango**
> `[dimension humaine : éleveurs, campements, pistes coupées par la crue annuelle]`
> On mesure : l'eau libre et, grâce à la double réflexion en bande L, **l'eau cachée sous les roseaux et le papyrus**, que l'optique ne voit jamais. Fréquence d'inondation, hydropériode, date d'arrivée de l'eau.
> On a adapté pour : `[ ]`

**6. Agriculture — Iowa, Midwest américain**
> `[dimension humaine : rendement, assurance récolte, sécurité alimentaire]`
> On mesure : le type de culture, maïs ou soja, avant la récolte, à partir de la série temporelle HV, avec un F1 de 0,86, des mois avant la carte officielle de l'USDA.
> On a adapté pour : `[ ]`

✂️ Pour tenir 4 min : lire 1, 2, 3 en entier, puis une phrase pour 4-5-6 : « Et la même mécanique tourne déjà sur un volcan au Kamchatka, sur la crue de l'Okavango, et sur les champs de l'Iowa. »

---

## 8. OPEN SOURCE : la philosophie (45 s)

**SLIDE 9** : fond noir, une citation : **« Talk is cheap. Show me the code. » — Linus Torvalds**. En dessous, l'URL du dépôt GitHub et trois mots : **Questions = fichiers. Pas du code.**

> Maintenant, pourquoi c'est open source, et pourquoi ça compte plus que tout le reste.
>
> Linus Torvalds a écrit un noyau avec le monde entier parce qu'il a compris une chose : un bon outil devient grand quand ce sont les autres qui le font grandir. Dans la communauté, on appelle ça la loi de Linus : avec assez de regards, chaque erreur devient évidente.
>
> On a construit SARAURA pour ça. Chaque question qu'un expert veut poser à NISAR, « est-ce que ce versant bouge après la pluie ? », « quel puits doit pomper moins ? », c'est **un fichier texte**, pas du code : les seuils, les classes, les couleurs, les sources, les limites. Un hydrologue à Béjaïa, un géotechnicien à Jakarta, une étudiante à Alger peuvent ajouter leur question, avec leurs seuils, pour leur zone, et la publier. Les modèles se branchent par fichiers. Les sources sont citées à chaque réponse.
>
> On ne vend pas une boîte noire. On donne une fondation. Et on a déjà la preuve que ça voyage : nos questions écrites pour Jijel ont tourné sur un feu américain à 10 000 km, sans une ligne de code en plus.
>
> NISAR est gratuit pour la Terre entière. Il fallait que l'outil qui le rend lisible le soit aussi.

---

## 9. LE PRODUIT : des personas, un écran chacun, un rapport pour les scientifiques (40 s)

**SLIDE 10** : capture de la page d'accueil (la Terre 3D, « Earth, through NISAR's eye ») puis la page lieu avec « Qui êtes-vous ? ».

> Et on ne s'est pas arrêtés à la fondation. On a designé un produit par usage.
>
> On arrive sur un lieu, on dit qui on est, et on ne voit que ses questions. Un acheteur de terrain à Mexico tape sur sa parcelle : feu rouge, orange ou vert, la raison, trois options de fondation avec leur coût et leur source, et ce qu'il faut vérifier au sol. Un chef de la Protection civile à Jijel voit la liste des villages classés par chenal de boue, et les 104 tronçons de route à fermer. Pour chaque phénomène, un affichage différent, parce que la décision est différente :
> - phénomène 1 `[incendie]` → `[listes classées : villages, routes, parcelles, réservoirs ; carte de replantation]`
> - phénomène 2 `[subsidence]` → `[feu tricolore par parcelle, types de fondation, segments de ligne]`
> - phénomène 3 `[séisme]` → `[ordre d'inspection par quartier, reconstruire ici ?, réseaux traversés]`
> - phénomène 4 `[volcan]` → `[ ]`
> - phénomène 5 `[zone humide]` → `[ ]`
> - phénomène 6 `[agriculture]` → `[ ]`
>
> Et chaque réponse se renouvelle tous les 12 jours, à chaque passage du satellite. « Qu'est-ce qui a changé depuis le dernier passage ? » est une question comme les autres.

**SLIDE 11** : une page du rapport PDF.

> Pour les scientifiques, un rapport PDF complet : les couches physiques, la série temporelle, le modèle contre sa méthode de référence avec le score, la liste des passages NISAR avec leur identifiant et le lien vers ASF Vertex, les méthodes et les sources. `[contenu final du rapport]`. Tout est traçable jusqu'au granule.

---

## 10. CLÔTURE (30 s)

**SLIDE 12** : retour sur la colline de Jijel. Cette fois avec notre carte dessus : les chenaux de boue, les 12 villages, les routes en rouge. Un titre : **« La donnée était là. Maintenant elle parle. »**

> Je reviens à Jijel. La donnée qui dit quels villages sont sous une pente brûlée existait avant la première pluie. Aujourd'hui, elle dit : 12 villages, 104 tronçons de route, 6 réservoirs. Avec une raison, une source, et quoi faire.
>
> On n'est pas géologues. On a construit ça en deux jours avec vos règles, vos seuils, vos papiers. Imaginez ce que vous en ferez.
>
> NISAR regarde la Terre entière tous les 12 jours. SARAURA, c'est l'outil qui la fait parler. Merci.

---

## Ce qu'il faut mettre EXACTEMENT sur les slides

| # | Titre à l'écran | Contenu visible | Ce que le jury doit retenir |
|---|---|---|---|
| 1 | *(aucun)* | Photo/vidéo du feu, « 26 août 2026 » | L'émotion, le lieu |
| 2 | **Novembre** | Coupe de versant brûlé + village + pluie ; « sol hydrophobe · pente > 23° · coulée de débris » | La deuxième catastrophe |
| 3 | **La donnée était là** | Frise : 19 août (NISAR public) → 26 août (feu) → traits tous les 12 jours | Le décalage de 7 jours |
| 4 | **NISAR** | NASA + ISRO · 30 juil. 2025 · bande L 24 cm + bande S · antenne 12 m · fauchée 240 km · 12 jours · jour/nuit/nuages/fumée | Capteur actif, traverse tout, répète |
| 5 | **Une ressource brute** | Capture HDF5 ; « 1,9–5,3 Go / fichier · phase enroulée · ionosphère ±17 cm » | Inexploitable sans outil |
| 6 | **Apprendre à lire l'écho** | X (NISAR HH/HV, 20 m) → machine → Y (Sentinel-2 / USDA / Copernicus) ; « ensuite : Y depuis X seul » ; « 86 % vs 21 % » | Segmentation sémantique, vérité terrain auto |
| 7 | **IA hybride** | Pyramide : modèle appris / règles publiées (Staley 23°, Bjerrum 1/500, Yun 2015) / Risque = Aléa × Exposition × Vulnérabilité | Explicable, transportable |
| 8 | **Six phénomènes** | 6 vignettes : Jijel+Washington, Mexico, Venezuela, Kamchatka, Okavango, Iowa ; une phrase humaine chacune | Même base, expertise différente |
| 9 | **Open source** | Citation Torvalds · URL GitHub · « Questions = fichiers, pas du code » · « Jijel → Washington : 0 ligne de code » | Fondation ouverte, ça voyage |
| 10 | **Qui êtes-vous ?** | Capture page d'accueil + page lieu ; 6 lignes « phénomène → affichage » | Un produit par usage |
| 11 | **Le rapport** | Une page du PDF : couches, Modèle vs Référence, liste des passages avec lien ASF Vertex | Traçable jusqu'au granule |
| 12 | **La donnée était là. Maintenant elle parle.** | La colline de Jijel avec notre carte : chenaux, 12 villages, routes rouges | Boucle fermée |

---

## Garde-fous : le degré de « maxing » devant des géologues

À dire sans hésiter (vrai et vérifiable dans le projet) :
- bande L 24 cm, pénétration de la canopée, polarisations HH/HV, rétrodiffusion, interférométrie, cohérence, phase déroulée, correction ionosphérique, ligne de visée, tassement différentiel, limite 1/500, pente critique 23°, routage priority-flood, MNT Copernicus 60 m, dNBR, double réflexion (double bounce) sous végétation inondée, validation croisée spatiale par blocs.

À ne PAS dire :
- « on prédit les catastrophes » → on **dépiste** et on **priorise**. Chaque réponse est un screening, pas une certification.
- « on aurait évité l'incendie » → on aurait anticipé **ce qui suit** l'incendie.
- « notre IA détecte la lave » → le modèle volcan est faible, on s'appuie sur la physique. Si un juré demande, le dire franchement : c'est un point de crédibilité.
- « précision de 86 % » pour l'incendie → c'est un **IoU de 0,86 contre des labels optiques**, pas contre le terrain. Dire « recouvrement de 86 % avec la vérité optique ».
- « temps réel » → tous les 12 jours, et PROVISIONAL en attendant les produits VALIDATED.
- Des pixels de 20 à 80 m jugent un quartier ou une grande parcelle, jamais une maison.

Questions à provoquer pour la Q&A (c'est là que l'équipe brille) :
- « Comment le modèle apprend sans vérité terrain ? » → labels proxy auto-générés depuis Sentinel-2, et labels réels Copernicus pour le séisme.
- « Comment vous gérez le bruit ionosphérique ? » → écran ionosphérique du produit GUNW, de ±17 cm à ±2–3 cm.
- « Pourquoi des règles et pas des modèles pour les questions ? » → Jijel 0,86 → Washington 0,36 ; les règles ont tourné sans code.
- « Ça marche ailleurs ? » → oui, physique-based sur n'importe quelle zone dessinée ; les modèles restent sur les sites vitrine.

## À vérifier avant la scène
- La date du 19 août 2026 comme première diffusion publique NISAR (nos données calibrées sur Jijel commencent le 17 juin 2026 : si c'est plus juste, dire « le satellite regardait déjà Jijel deux mois avant le feu »).
- Les chiffres officiels de l'incendie de Jijel (hectares, évacués) auprès de la Protection civile / DGF.
- La pluie réelle sur Jijel la semaine du pitch (Office National de la Météorologie) : si elle est annoncée, c'est la phrase la plus forte du pitch.
