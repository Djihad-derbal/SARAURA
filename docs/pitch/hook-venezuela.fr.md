# Hook Venezuela (remplace les sections 1 et 2 de pitch-script.fr.md, et la slide 12)

Le reste du script (NISAR, ressource brute, mécanisme, IA hybride, six phénomènes, open source, produit) ne bouge pas.
Un séisme ne se prévient pas : l'angle « la donnée était là » porte sur **les 72 premières heures** (où chercher) et sur **l'après** (où reconstruire, le sol bouge-t-il encore). C'est exactement ce que répondent les questions E1 à E4.

Faits du projet utilisables (vérifiés dans le dépôt) :
- Deux séismes, M7.2 puis M7.5, le 24 juin 2026, côte nord du Venezuela, Caracas et Caraballeda.
- NISAR, track 126 descendant, a survolé la zone le **22 juin** (2 jours avant) et le **4 juillet** (10 jours après). La paire interférométrique 22 juin → 4 juillet contient le séisme.
- Les dommages ont été cartographiés par Copernicus EMS (activation EMSR884) depuis l'optique : environ 3 000 bâtiments touchés selon Copernicus/ESA, au moins 855 selon l'OCHA. Les sources ne s'accordent pas.
- Sur 13 zones d'intérêt demandées à Copernicus, **8 n'ont pas pu être cartographiées** (limites de la télédétection optique).
- Notre modèle, entraîné sur ces relevés réels, classe les blocs de 250 m par probabilité de dommage : précision moyenne 0,73 contre 0,61 pour la perte de cohérence seule (Yun 2015), et 0,13 au hasard.
- Questions construites : E1 où inspecter d'abord, E2 où reconstruire, E3 le sol bouge-t-il encore, E4 quelles routes et réseaux ont traversé un sol qui a bougé.

À compléter avec des sources officielles : `[heure locale]`, `[victimes]`, `[déplacés]`, `[quartiers les plus touchés]`.

---

## SLIDE 1 : plein écran, pas de titre

**Visuel :** photo ou vidéo d'un immeuble effondré à Caracas ou Caraballeda, de nuit, équipes de secours à la lampe. Une seule ligne en bas : **24 juin 2026 · M7.5**.

> Le 24 juin 2026, à `[heure]`, la terre tremble au nord du Venezuela. Magnitude 7.2. Puis, quelques heures plus tard, 7.5. À Caracas et sur la côte de Caraballeda, des immeubles tombent. `[X morts, Y déplacés]`.
>
> Dans un séisme, la première question n'est pas « pourquoi ». C'est « où ». Où sont les gens sous les décombres ? Dans quelle rue envoyer la première équipe ? Les secouristes ont 72 heures. Après, les chances de retrouver quelqu'un vivant s'effondrent.
>
> Et pendant ces 72 heures, ils ont cherché comme on cherche depuis toujours : à pied, à l'oreille, avec ce que les habitants leur disaient.

---

## SLIDE 2 : « Deux échos »

**Visuel :** deux dates côte à côte sur une carte de Caracas : **22 juin** et **4 juillet**. Entre les deux, un trait rouge : **24 juin**. En dessous, notre carte de perte de cohérence : les blocs rouges là où les bâtiments ont bougé. Titre : **Deux échos. Dix jours.**

> Deux jours avant le séisme, un satellite est passé au-dessus de Caracas. Il a envoyé une onde radar de 24 centimètres sur chaque bâtiment, chaque colline, et il a enregistré l'écho. Dix jours après, il est repassé sur la même orbite, au mètre près, et il a écouté encore.
>
> Là où rien n'a bougé, les deux échos sont identiques. Là où un immeuble s'est fissuré, s'est affaissé, s'est effondré, l'écho a changé. On appelle ça la **perte de cohérence interférométrique**. C'est, depuis le Népal en 2015, le proxy de dommage le plus fiable que la télédétection connaisse. Et le radar le voit de nuit, sous les nuages, sous la poussière.
>
> Ce satellite, c'est NISAR. La mission NASA-ISRO. La carte que vous voyez, c'est la sienne, lue par notre outil. Sur les quartiers où l'Europe a pu relever les dommages depuis l'optique, elle les retrouve avec une précision moyenne de 0,73 là où la méthode classique fait 0,61.

---

## SLIDE 3 : « La donnée était là »

**Visuel :** la liste des 13 zones demandées à Copernicus. 5 cochées, **8 barrées : « non cartographiée »**. À droite, la même zone vue par NISAR, entièrement couverte. Titre : **13 zones demandées. 8 jamais cartographiées.**

> Après le séisme, le Venezuela a activé le service européen de cartographie d'urgence. Treize zones demandées. Huit n'ont jamais été cartographiées : l'optique ne pouvait pas voir. Les comptes de bâtiments touchés vont de 855 à 3 000 selon la source. Cinq mois plus tard, on ne sait toujours pas exactement.
>
> Pendant ce temps, l'écho radar du 4 juillet couvrait **cent pour cent** de la zone. Il était enregistré. Il est aujourd'hui en accès libre.
>
> Personne ne l'a lu. Pas par négligence : parce que personne ne pouvait le lire. Un fichier de plusieurs gigaoctets, de la phase radar, du bruit ionosphérique de dix-sept centimètres. Du minerai.
>
> C'est ça, le problème qu'on a attaqué.

*(Enchaîner directement sur la section 3 du script principal : « NISAR : ce que c'est ». La slide 5 « ressource brute » reste, mais tu l'as déjà amorcée ici : raccourcis-la de moitié.)*

---

## Ce qui change dans la suite du script

- **Section 7, six phénomènes :** mettre le séisme en **premier**, puis l'incendie, puis la subsidence. Ajouter la phrase humaine de l'après : « Trois semaines plus tard, une famille veut rentrer chez elle. Le sol bouge-t-il encore ? Peut-on reconstruire ici ? Nos questions E2 et E3 répondent, et se renouvellent à chaque passage, tous les 12 jours. »
- **Section 9, produit :** l'exemple à l'écran devient Caracas : « Protection civile et secours » → liste des quartiers à inspecter d'abord, classés ; « Famille » → reconstruire ici ?
- **Slide 12, clôture :** retour sur Caracas, avec notre carte dessus. Titre : **« Deux échos. Et une réponse en 12 jours. »**

> Je reviens au 24 juin. Au prochain séisme, où que ce soit sur Terre, NISAR sera repassé dans les 12 jours. L'écho sera là. La question est de savoir si quelqu'un pourra le lire dans la nuit même, pour dire aux secouristes : commencez par cette rue.
>
> On n'est pas sismologues. On a construit ça en deux jours avec vos méthodes et vos papiers. Imaginez ce que vous en ferez.
>
> NISAR regarde la Terre entière tous les 12 jours. SARAURA, c'est l'outil qui la fait parler. Merci.

---

## Garde-fous spécifiques au Venezuela

- Ne jamais dire « on aurait sauvé des vies ». Dire : « on aurait su où chercher d'abord ». La carte classe des blocs de 250 m, elle ne voit pas à l'intérieur d'un bâtiment.
- Le délai honnête est **jusqu'à 12 jours** (le passage du 4 juillet), pas 72 heures. La phrase forte est : « au prochain séisme, l'écho sera là en 12 jours au plus ; aujourd'hui personne ne l'exploite ». Si un juré pousse : la revisite de 12 jours est la limite de la mission, pas de l'outil ; avec les deux orbites (montante et descendante) on tombe à 6.
- La perte de cohérence tombe aussi avec la végétation, la pluie et les chantiers : certains blocs rouges sont des faux positifs. Le dire si on le demande, c'est un point de crédibilité.
- Nos labels couvrent seulement la côte de Caraballeda et une partie de Caracas. Ailleurs, le modèle extrapole, et la carte le dit.
- Les produits NISAR utilisés sont PROVISIONAL ; le décompte des dommages varie selon la source, cite les deux chiffres.
- Pourquoi « 8 non cartographiées » : le dépôt note « limites de la télédétection », sans préciser la cause (nuages, angle, résolution). Dire « l'optique ne pouvait pas voir », pas « à cause des nuages », sauf si l'équipe le vérifie sur le portail EMSR884.
