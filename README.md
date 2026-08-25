# LGS InstalleX

**Provisionnement automatisé des postes de travail LGS**

Outil de provisionnement automatisé des postes de travail pour les déploiements Groupe LGS — une société IBM.

> Version applicative : **1.2** (Python / PyQt6) — versionnage repris à 1.0 lors du passage de P.R.I.S.M à LGS InstalleX ; la lignée technique précédente s'arrêtait à 3.8.1
> Version parallèle maintenue : **PowerShell / WinForms** (lignée v3.x)
> © Copyright Groupe LGS — une société IBM

---

## Table des matières

1. [Aperçu](#aperçu)
2. [Conception](#1-conception)
3. [Développement](#2-développement)
4. [Tests internes](#3-tests-internes)
5. [Documentation](#4-documentation)
6. [Interaction avec l'équipe de sécurité IBM](#5-interaction-proactive-et-continue-avec-léquipe-de-sécurité-ibm)
7. [Installation et utilisation](#installation-et-utilisation)
8. [**Correctifs**](#correctifs)
9. [Historique des versions](#historique-des-versions)

---

## Aperçu

LGS InstalleX automatise la préparation complète d'un poste de travail Windows dans le cadre des déploiements LGS, depuis un poste fraîchement imagé jusqu'à un poste prêt à remettre à l'utilisateur. L'outil regroupe en une seule interface les étapes habituellement manuelles et sujettes à erreur : renommage machine, configuration régionale, jonction Entra ID, installation des applications standard, et vérifications post-installation. Le chiffrement BitLocker relève des stratégies du parc et n'est plus piloté par l'outil ; la vérification finale se contente d'en **constater** l'état.

Deux implémentations fonctionnellement équivalentes sont maintenues en parallèle :

| Implémentation | Interface | Fichier | Usage |
|---|---|---|---|
| Python 3.10+ / PyQt6 | GUI thème sombre | `LGS_InstalleX.py` | Itération courante |
| PowerShell / WinForms | GUI thème sombre | `LGS_Install_Script 3.4 (P.R.I.S.M).ps1` | Version historique, conservée sous son nom d'origine |

**Caractéristiques principales**

- Provisionnement en 9 étapes séquentielles (grille de progression sur 10 jalons) avec log temps réel
- Élévation UAC automatique et exécution en contexte administrateur
- Jonction Entra ID couvrant les scénarios Autopilot, PPKG et manuel
- Déploiement applicatif via winget avec repli sur téléchargement direct ; Microsoft 365 Apps installé par winget avec configuration maîtrisée (repli sur l'ODT local) et Lenovo Commercial Vantage via paquet de déploiement compagnon
- **Vérification de la signature Authenticode des installeurs téléchargés** (`Get-AuthenticodeSignature`) avant toute exécution en administrateur ; un binaire non signé, altéré ou non fiable est rejeté
- Assets embarqués en Base64 (aucune dépendance réseau vers SharePoint / OneDrive)
- Détection de langue ; détection matérielle robuste des GPU NVIDIA (par ID fabricant PCI `VEN_10DE`) avec installation du pilote et de NVIDIA App (Entreprise)
- **Inventaire matériel** du poste collecté et journalisé au démarrage (sans effet sur le provisionnement), puis réutilisé dans la fiche de remise
- **Configuration régionale** fr-CA : date ISO `yyyy-MM-dd`, horloge 24 h, fuseau Eastern Standard Time, position géographique Canada
- **Vérification finale** en 15 points qui remesure le poste réellement livré, et **fiche de remise HTML** déposée sur le bureau (identification, contrôles, inventaire)
- Téléchargements résilients : contexte TLS enrichi des magasins de certificats Windows, avec repli sur `curl.exe` (Schannel)
- Journal détaillé écrit directement sur le bureau, à l'endroit où le technicien le cherche
- Nettoyage automatique du dossier de déploiement compagnon en fin d'exécution
- **Signal sonore de fin personnalisable** — un `.mp3` ou `.wav` peut remplacer les bips, via la configuration externe ou en l'embarquant en Base64
- Journalisation incrémentale et journal de crash automatique

---

## 1. Conception

La conception de LGS InstalleX répond à un besoin opérationnel précis : réduire le temps et la variabilité du provisionnement des postes tout en garantissant un résultat conforme aux standards LGS/IBM.

**Objectifs de conception**

- **Reproductibilité** — un poste provisionné par LGS InstalleX est identique à tout autre, quel que soit le technicien.
- **Autonomie réseau** — les fichiers requis (raccourcis, PDF de procédures, favoris) sont embarqués dans le script en Base64, éliminant les échecs liés à l'authentification SharePoint/OneDrive et à l'encodage des URL rencontrés dans les versions antérieures.
- **Robustesse** — chaque étape est isolée (try/except par étape) pour qu'un échec ponctuel n'interrompe pas l'ensemble du provisionnement.
- **Traçabilité** — journalisation au fil de l'eau et journal de crash automatique.

**Décisions d'architecture**

- **GUI + worker thread** — l'interface (PyQt6 / WinForms) reste réactive pendant les opérations longues grâce à un thread de travail dédié (`QThread` côté Python), la communication vers l'UI se faisant par signaux thread-safe (`pyqtSignal`).
- **Renommage machine sans `Rename-Computer`** — le renommage évite la cmdlet `Rename-Computer`, qui peut émettre `WM_ENDSESSION` / `InitiateSystemShutdown` et fermer prématurément la GUI. Il est réalisé via PowerShell par écriture registre (`Set-ItemProperty` sur `ComputerName` / `Hostname`) puis `Win32_ComputerSystem.Rename()` (WMI), sans aucun signal de redémarrage — le changement est effectif au prochain démarrage. Le nouveau nom est transmis par variable d'environnement (`$env:INSTALLEX_NEW_NAME`), jamais interpolé dans le corps du script (anti-injection).
- **Appels système centralisés** — les commandes externes passent par un helper unique `run_cmd` (forçage UTF-8, `CREATE_NO_WINDOW`, timeout paramétrable, injection de variables d'environnement via `env_extra`). Les scripts PowerShell complexes (détection GPU) sont transmis en Base64 UTF-16LE via `-EncodedCommand` (helper `_ps_encoded`) pour éviter toute mauvaise interprétation des `$` et caractères spéciaux. PowerShell reste l'outil retenu là où il est le plus fiable (raccourci COM `WScript.Shell`, renommage, signature Authenticode, requêtes CIM/WMI, lecture de l'état BitLocker).
- **Politique d'exécution `RemoteSigned`** — les appels PowerShell utilisent `-ExecutionPolicy RemoteSigned` (au lieu de `Bypass`) : les scripts système sollicités sont signés par Microsoft et s'exécutent sans abaisser la politique.
- **Vérification des binaires avant exécution** — tout installeur téléchargé (repli hors winget : Firefox/Chrome, Adobe, Intel DSA, NVIDIA Driver, NVIDIA App) est contrôlé avant d'être lancé en administrateur : taille minimale et signature Authenticode de l'éditeur via la fonction `verify_authenticode` (`Get-AuthenticodeSignature`). Un fichier non signé, altéré ou non fiable est rejeté (fail-safe).
- **Encodage UTF-8 forcé** — encodage UTF-8 (avec BOM) de bout en bout, incluant l'injection d'un préfixe console pour les appels PowerShell, afin d'éviter la corruption des accents et caractères spéciaux sur un Windows en français.
- **Détection et confirmation uniformes** — le helper `_soft_present()` combine chemins de fichiers **et** clés Uninstall du registre (HKLM 64/32 bits + HKCU) pour toutes les applications ; la détection par chemin seule ratait les installations dans un dossier renommé d'une version à l'autre. Le même contrôle est rejoué **après** chaque installation : un `0` retourné par winget ne prouve pas que le logiciel est présent (cas constaté sur Office).
- **Mise à jour d'Office après installation** — l'ODT comme winget posent la version présente sur le CDN au moment du déploiement ; sans passe de mise à jour, un poste neuf peut être livré avec plusieurs correctifs de retard. `_update_office()` appelle donc `OfficeC2RClient.exe /update` — winget n'ayant aucune prise sur un Office installé en Click-to-Run — après une installation **et** lorsque Office était déjà présent. `forceappshutdown=false` est volontaire : le script pouvant être relancé sur un poste en service, forcer la fermeture d'Office y ferait perdre le travail en cours ; la mise à jour s'applique alors à la prochaine fermeture.
- **Windows Update : ne pas doubler une session en cours** — l'étape vérifie d'abord `IUpdateInstaller.IsBusy` et la présence de `MoUsoCoreWorker.exe` ayant réellement consommé du CPU. Deux signaux ont été écartés après mesure : `wuauserv`, qui tourne en permanence, et `TiWorker.exe`, qui démarre pour n'importe quelle opération de servicing — y compris une simple requête Appx sans rapport avec Windows Update. En cas de doute, l'étape s'exécute : relancer une recherche est sans conséquence, la sauter à tort priverait le poste de ses mises à jour.
- **Saut de Commercial Vantage sous conditions strictes** — l'étape n'est ignorée que si le paquet est trouvé, que son `Status` vaut `Ok` et que son dossier d'installation existe réellement. L'asymétrie est assumée : un faux positif laisserait un poste sans Vantage, alors qu'un faux négatif se contente de réinstaller ce qui est déjà là.
- **Support MSI et téléchargements résilients** — `_install_from_url()` télécharge via `download_file()` (contexte TLS + repli `curl.exe`/Schannel) et lance automatiquement les `.msi` par `msiexec /i /qn /norestart`, les `.exe` recevant leurs arguments propres. Le code de sortie de l'installeur est lu et journalisé.
- **Installation applicative pilotée par les données** — le catalogue logiciel (`LOGICIELS`) décrit chaque application (chemins de détection, motifs registre, identifiant winget, URL et méthode de repli) ; l'étape 6 l'exploite pour uniformiser détection et installation. Un dossier compagnon `C:\LGS_Deploy` (`LGS_DEPLOY_DIR`, sous-dossiers `ODT\` et `CommercialVantage\`) héberge les paquets de déploiement entreprise : il est requis pour Lenovo Commercial Vantage, et sert de repli pour Microsoft 365 Apps.
- **Microsoft 365 Apps — winget d'abord, ODT en repli** — le paquet winget `Microsoft.Office` est le *même* `setup.exe` Click-to-Run que l'ODT, simplement téléchargé depuis le CDN Microsoft. LGS InstalleX l'installe donc via winget en lui passant **son propre `configuration.xml`** (`--custom "/configure <xml>"`), ce qui conserve la maîtrise totale du déploiement (fr-CA, canal, RemoveMSI) tout en évitant d'avoir à pré-déposer `setup.exe` sur chaque poste. En cas d'échec (winget absent, CDN inaccessible, « installer hash mismatch » du manifeste), l'ODT prend le relais — et si `setup.exe` n'a pas été pré-déposé dans `C:\LGS_Deploy\ODT`, il est **téléchargé automatiquement depuis le CDN Microsoft** (`_download_odt_setup`). Le succès est vérifié par la présence réelle des binaires Office, car winget peut retourner `0` alors que Click-to-Run a échoué.
- **Téléchargements résilients** — le helper `download_file` tente d'abord `urlopen` avec un contexte TLS construit à partir des magasins de certificats Windows (`ROOT` et `CA`, via `ssl.enum_certificates`), puis se replie sur `curl.exe` (intégré depuis Windows 10 1803), qui s'appuie sur Schannel. Ce double chemin évite les échecs de validation de certificat derrière un proxy d'inspection TLS d'entreprise.
- **Inventaire matériel informatif** — `collect_inventory` / `log_inventory` interrogent CIM au démarrage et consignent la configuration du poste dans le journal. La collecte est volontairement non bloquante : elle ne lève jamais, et aucune décision d'installation n'en dépend. Le résultat alimente ensuite la fiche de remise.
- **Écriture multi-ruches factorisée** — `_loaded_user_sids()` et `_write_all_user_hives()` sont partagés par l'écran de veille et la configuration régionale : la règle de sélection des ruches (dont les SID Entra ID) vit à un seul endroit, au lieu d'être dupliquée dans chaque fonctionnalité où elle pourrait diverger.
- **Vérification finale par remesure** — `_final_verification()` ne se fie pas au déroulé du script : chaque point est relu sur la machine. C'est indispensable puisqu'une étape peut se dérouler sans erreur sans que le résultat soit là — winget retourne `0` alors que rien n'est installé. Les contrôles d'écran de veille et de configuration régionale lisent une **ruche utilisateur réelle**, jamais celle du compte élevé.
- **Nettoyage en fin de course** — `_cleanup_deploy_folder` supprime `C:\LGS_Deploy` une fois le provisionnement terminé (best-effort : les fichiers verrouillés sont ignorés, l'attribut lecture seule est levé si besoin, et une erreur n'interrompt jamais le script).
- **Journal sur le bureau** — le journal détaillé est écrit directement sur le bureau de l'opérateur. Une itération intermédiaire l'avait déplacé dans `%PROGRAMDATA%\LGS\Logs` avec des ACL restreintes ; en pratique cela imposait de passer par un raccourci pour le consulter, pour un gain opérationnel nul — le choix a donc été annulé.
- **Signal sonore de fin** — la lecture passe par **MCI** (`winmm.dll`, pilote `mpegvideo`) et non par `winsound`, qui ne sait lire que le WAV : MCI gère le **MP3** nativement, sans dépendance tierce — ce qui compte pour un script qui n'en a qu'une seule (PyQt6). Deux sources, dans l'ordre : la clé `sound_file` de la configuration externe, puis le son embarqué en Base64 (`SON_FIN_B64`), extrait dans `%TEMP%` puis nettoyé en fin d'exécution. Le son livré est **program-complete.mp3** (5,3 Ko, 1,35 s), embarqué par défaut : les bips ne sont plus joués que si sa lecture échoue. Si aucune n'aboutit, les bips d'origine sont joués : le poste ne termine jamais en silence.
- **Configuration externalisée** — fichier **facultatif** `LGS_InstalleX.config.json`, cherché à côté du script puis dans `C:\LGS_Deploy`. Il permet de pré-remplir le nom du poste et l'option « nouvelle embauche », et de surcharger la page d'accueil, le délai d'écran de veille, le fuseau, la locale et le format de date. Format JSON et non YAML : `json` est dans la bibliothèque standard, là où PyYAML ajouterait une dépendance tierce à auditer. Tolérant par construction — fichier absent, partiel, corrompu ou contenant des clés inconnues : les valeurs par défaut s'appliquent et le provisionnement se déroule normalement. L'origine de la configuration est inscrite en tête du journal. *Reste dans le code : le catalogue `LOGICIELS` et le `configuration.xml` d'Office.*

---

## 2. Développement

**Pile technique**

- Python 3.10+ (garde de version au démarrage avec message d'erreur explicite)
- PyQt6 (`QtWidgets`, `QtCore`, `QtGui`) — installé automatiquement via `pip` s'il est absent
- API Windows via `ctypes` (élévation UAC, résolution du bureau `SHGetFolderPathW`, MessageBox)
- `winreg`, `subprocess`, `base64`, `urllib`, `shutil`, `re`
- PowerShell (via `run_cmd` / `_ps_encoded`) pour raccourci COM `WScript.Shell`, renommage machine, requêtes CIM/WMI, `Get-AuthenticodeSignature`, BitLocker et PSWindowsUpdate

**Étapes du flux de provisionnement (implémentation Python)**

*Actions préliminaires* (au démarrage du thread de travail) : protection anti-veille (`powercfg`, restaurée à l'étape 8), test de disponibilité de winget avec mise à jour des sources, et collecte de l'**inventaire matériel** consigné au journal.

1. **Création du dossier CAT** sur le bureau.
2. **Extraction des fichiers embarqués** (Base64) dans le dossier CAT (PDF de procédures, raccourcis `.url`, etc.).
3. **Bureau utilisateur** — le dossier `CAT` étant créé directement sur le bureau à l'étape 2, aucun raccourci n'est posé : il ne ferait que dupliquer l'icône. L'étape **supprime** au contraire le `CAT.lnk` laissé par les versions antérieures, pour que les postes déjà provisionnés se nettoient d'eux-mêmes.
4. **Renommage machine** — `Set-ItemProperty` (registre) + `Win32_ComputerSystem.Rename()` (WMI), sans `Rename-Computer` ni signal de redémarrage, effectif au prochain démarrage. Nom passé via `$env:INSTALLEX_NEW_NAME` (anti-injection), après validation NetBIOS.
   - *4b — Nouvelle embauche (conditionnel)* : ouverture de Box IBM et attente de l'acceptation du User Agreement, uniquement si l'option « Nouvelle embauche » est cochée dans l'écran de configuration.
5. **Microsoft 365 Apps** — via winget (`Microsoft.Office` + `configuration.xml` maison passé en `--custom /configure`), avec repli automatique sur l'Office Deployment Tool local (`setup.exe` dans `C:\LGS_Deploy\ODT\`) ; l'installation est ignorée si Office est déjà présent. Dans **tous les cas**, une passe de mise à jour Click-to-Run suit.
6. **Applications standard** — Firefox, Google Chrome, page d'accueil www.lgs.com (stratégies Chrome / Edge / Firefox), Slack, Box for Office, Box Tools, Adobe Acrobat Reader, Intel Driver & Support Assistant, **pilote NVIDIA + NVIDIA App (Entreprise)** si GPU NVIDIA détecté, **Lenovo Commercial Vantage** sur matériel Lenovo. Chaque application suit une chaîne de replis (voir ci-dessous) et son installation est confirmée avant de passer à la suivante.

**Stratégie d'installation par application**

| Application | Méthode primaire | Replis |
|---|---|---|
| Microsoft 365 Apps | winget + `configuration.xml` LGS, puis mise à jour C2R | ODT local, puis ODT téléchargé du CDN |
| Slack | winget **sans `--scope`** — winget choisit l'installeur exploitable | — (le MSI `slack.com/ssb` redirige vers un fichier absent du CDN) |
| Google Chrome | winget | MSI Chrome Enterprise, puis installeur `.exe` |
| Firefox | winget **`Mozilla.Firefox.fr`** (paquet français) | MSI `lang=fr`, puis installeur `.exe` `lang=fr` |
| Intel DSA | winget `Intel.IntelDriverAndSupportAssistant` | téléchargement direct `dsadata.intel.com` |
| Box for Office | winget | message d'installation manuelle |
| Box Tools | winget **sans `--scope`** | message d'installation manuelle |
| Adobe Acrobat Reader | winget | API Adobe (endpoint non documenté) |
| Pilote NVIDIA / NVIDIA App | CDN NVIDIA (lookup de version) | URL de repli figée |
| Lenovo Commercial Vantage | `VantageInstaller.exe` du paquet de déploiement (App + SU Helper) | Microsoft Store `9NR5B8GVVM13` — **application seule**, sans System Update Helper |

> **Commercial Vantage et le Microsoft Store** — le paquet de déploiement Lenovo reste la méthode de référence : il installe l'application **et** le System Update Helper (`VantageInstaller Install -Vantage -SuHelper`). Le repli Store (`9NR5B8GVVM13`) n'installe que l'application ; il évite de ne rien installer du tout quand le paquet est absent du poste, mais l'installation reste incomplète et le journal le signale. Attention à ne pas confondre avec `9WZDNCRFJ4MV`, la version **grand public** de Vantage, qui embarque des fonctions promotionnelles et de surveillance dark web sans place sur un poste d'entreprise.
>
> **Firefox et la langue** — Mozilla publie **un paquet winget par langue**. L'identifiant générique `Mozilla.Firefox` correspond au paquet **en-US** : il installait donc un Firefox en anglais. Le catalogue cible désormais `Mozilla.Firefox.fr`. À noter : Mozilla ne publie pas de locale `fr-CA` pour Firefox — la locale française est `fr`, y compris pour les postes canadiens.

> **Slack et le Microsoft Store** — inutile d'y recourir : la source `winget` publie déjà les deux variantes du paquet (MSIX en portée machine, `SlackSetup.exe` en portée utilisateur). Le Store ne proposerait que le MSIX, précisément ce que refusent les images où le déploiement AppX est restreint.

> **Slack et la portée d'installation** — en portée machine, winget sert le paquet **MSIX** de Slack, provisionné pour tous les profils : c'est le comportement attendu en provisionnement, et la raison pour laquelle `--scope machine` est conservé. En portée utilisateur, Slack n'atterrirait que dans le profil du technicien. Conséquence importante pour la détection : un Slack installé en MSIX réside dans `C:\Program Files\WindowsApps` et n'expose **aucun** des chemins classiques — d'où la détection par registre et par nom de paquet Appx (`appx_name`).
7. **Favoris Microsoft Edge** — écriture des favoris dans les profils + activation de la barre des favoris.
8. **Configuration Windows** — écran de veille (Ribbons.scr, 10 min, verrouillage) écrit dans le profil par défaut et dans chaque ruche utilisateur chargée, **puis appliqué à la session en cours** via `SystemParametersInfoW` ; **configuration régionale** (fr-CA, date `yyyy-MM-dd`, horloge 24 h, fuseau Eastern Standard Time, position Canada) ; désactivation du démarrage rapide ; restauration des paramètres de veille sauvegardés.
9. **Windows Update** — PSWindowsUpdate avec repli sur l'agent COM natif (WUA). L'étape commence par vérifier qu'**aucune session Windows Update n'est déjà en cours** : si c'est le cas, elle laisse la session existante travailler plutôt que d'en lancer une seconde en parallèle. Le service **Microsoft Update** est enregistré pour couvrir les correctifs Office et les pilotes, jusqu'à **3 passes** s'enchaînent, et l'étape dispose d'un **budget de 10 minutes** au-delà duquel le provisionnement continue.

*En clôture* : **vérification finale** (15 points remesurés sur le poste) et génération de la **fiche de remise HTML** sur le bureau — les deux avant le nettoyage, pour que la fiche reflète le poste tel qu'il est livré — puis suppression du dossier de déploiement `C:\LGS_Deploy`, récapitulatif des actions, détection d'un redémarrage requis et sauvegarde du journal sur le bureau.

**Vérification finale — points contrôlés**

| Domaine | Contrôle |
|---|---|
| Identité | Nom d'ordinateur conforme à la demande |
| Documentation | Dossier `CAT` présent sur le bureau |
| Logiciels | Les 8 applications du catalogue, détectées par chemin + registre + MSIX |
| Matériel Lenovo | Commercial Vantage (ignoré sur poste non-Lenovo) |
| Chiffrement | BitLocker : état de protection et pourcentage chiffré |
| Identité cloud | `dsregcmd` → `AzureAdJoined : YES` |
| Poste | Écran de veille et configuration régionale, lus dans une ruche utilisateur réelle |

Le résultat est journalisé point par point, puis résumé en trois issues : conforme, avertissements à vérifier, ou échecs à traiter avant remise.

**Fiche de remise**

Fichier `Fiche_Remise_<poste>_<horodatage>.html` déposé sur le bureau. Trois sections : identification (poste, date, technicien, durée, version de l'outil), résultats de la vérification avec pastilles de couleur, et inventaire matériel complet. Autonome (CSS embarqué, aucune dépendance réseau) et mis en page pour l'impression.

> La barre de progression de la GUI est graduée sur 10 jalons (le diagnostic initial, les 9 étapes numérotées ci-dessus, puis l'état « Terminé »). L'étape 4b n'occupe pas de rang numéroté distinct.

**Points techniques notables**

- **Élévation UAC durcie** — relance avec chemin absolu et arguments entre guillemets (résistant aux chemins contenant des espaces), relance via `pythonw.exe` pour un fonctionnement sans console, et MessageBox en cas d'échec d'élévation plutôt qu'une sortie silencieuse.
- **Suppression des fenêtres console enfants** — les appels `subprocess` utilisent `CREATE_NO_WINDOW` pour éviter tout flash de console pendant les étapes winget / PowerShell.
- **Table complète des codes de sortie winget** (36 codes) avec conversion int32 signé.
- **Portée d'installation adaptée au paquet** — `_winget_install` accepte un paramètre `scope` (« machine » par défaut). Slack, publié uniquement en portée utilisateur, est installé avec `scope=None` ; sans cela winget répond `-1978335216` (« aucun installeur applicable »), un code ni valide ni transitoire qui interrompait la boucle dès le premier essai. En garde-fou, un `-1978335216` obtenu malgré une portée imposée déclenche un nouvel essai sans `--scope`.
- **Vérification d'intégrité des téléchargements** — fonction `verify_authenticode` (`Get-AuthenticodeSignature`, disponible sur toutes les versions de Windows) appelée avant exécution sur chaque installeur en repli (Firefox/Chrome, Adobe, Intel DSA, NVIDIA Driver, NVIDIA App), en plus d'un contrôle de taille minimale. Le binaire est rejeté avant exécution si la signature est absente ou non valide ; en cas d'échec sur Intel DSA, seule cette application est ignorée sans interrompre le reste de l'étape 6.
- **Détection GPU NVIDIA robuste** — la détection s'appuie sur l'ID fabricant PCI `VEN_10DE` (présent dès l'image, avant même l'installation du pilote, là où un filtre sur le nom échouerait car la carte apparaît en « 3D Video Controller »). La version du pilote installé est lue via `nvidia-smi` (repli CIM), et une table `NVIDIA_DEV_NAMES` fournit le nom commercial des GPU Ada laptop quand CIM renvoie un nom générique. Un log de diagnostic liste les périphériques `VEN_10DE` présents.
- **Renommage & raccourci via PowerShell** — le renommage machine (`Set-ItemProperty` + WMI `Rename()`, nom via `$env:INSTALLEX_NEW_NAME`) et la création de raccourci (`WScript.Shell`) passent par PowerShell ; `Rename-Computer` est explicitement évité pour ne pas fermer la GUI.
- **Appels centralisés** — helper unique `run_cmd` (forçage UTF-8, `CREATE_NO_WINDOW`, `env_extra`) et `_ps_encoded` (scripts PowerShell en Base64 UTF-16LE via `-EncodedCommand`, avec `$ProgressPreference='SilentlyContinue'` pour ne pas polluer la sortie des cmdlets CIM).
- **Validation du nom d'ordinateur** par expression régulière conforme NetBIOS (`[A-Za-z0-9-]{1,15}`), dupliquée volontairement entre la validation GUI (`SetupDialog._launch`) et le thread d'exécution (`step4_computer_name`) — les deux doivent rester identiques — comme garde anti-injection avant le renommage.
- **Journal sur le bureau** — écrit au fil de l'eau sur le bureau sous `LGS_Log_Detaile_<nom>_<horodatage>.txt`, consultable immédiatement sans raccourci ni élévation. La clé de récupération BitLocker n'est jamais journalisée.
- **Écran de veille — ruches Entra ID incluses** — les valeurs sont écrites dans `Control Panel\Desktop` du profil par défaut **et** de chaque ruche utilisateur chargée. Le filtre accepte les SID en `S-1-5-21-…` (comptes locaux et Active Directory) **et en `S-1-12-1-…` (comptes Entra ID)** : ne retenir que le premier préfixe revenait à ignorer l'utilisateur final sur tout poste joint à Entra ID — c'est-à-dire sur la cible même de cet outil. Les SID de service (`S-1-5-18/19/20`, `S-1-5-80-…`) et `.DEFAULT` restent exclus.
- **Écran de veille appliqué immédiatement** — l'écriture registre couvre les ouvertures de session futures. Mais Windows garde ces paramètres en cache pour la session déjà ouverte : sans notification, l'écran de veille ne s'armait qu'après un redémarrage. `SystemParametersInfoW` (`SPI_SETSCREENSAVETIMEOUT` + `SPI_SETSCREENSAVEACTIVE`, avec `SPIF_SENDCHANGE`) diffuse le changement à la session courante. À noter : cet appel porte sur la session du compte qui exécute le script — si l'élévation UAC utilise un compte administrateur distinct, l'utilisateur final reçoit le réglage par le registre à sa prochaine ouverture de session.
- **Timeouts adaptatifs** par commande (30 min par défaut).
- **Protection anti-veille** pendant le provisionnement et **mécanisme de pause** thread-safe.
- **Assets Base64** — fichiers embarqués (PDF de procédures, DOCX, raccourcis `.url`). Un chantier d'optimisation du bloc d'assets (~66 000 lignes) est en cours : externalisation vers un dossier compagnon ou consolidation en archive unique.

**Outil compagnon**

- **LGS InstalleX Asset Updater** (`LGS_InstalleX_Updater.py`, Python / PyQt6) — interface glisser-déposer permettant à du personnel non technique de gérer les fichiers Base64 embarqués sans connaissances en développement. Au chargement d'un script, l'outil **liste les fichiers embarqués avec leur taille** et permet de **marquer ceux à supprimer** — le marquage reste réversible jusqu'à l'application, les suppressions sont confirmées nommément, et elles sont traitées avant les ajouts pour qu'un fichier redéposé sous le même nom l'emporte. L'outil cible **le script Python** (`LGS_InstalleX.py`) : il localise le bloc `FICHIERS_EMBARQUES`, ré-encode les fichiers déposés en Base64 (lignes de 64 caractères) et réécrit le bloc en UTF-8 avec BOM, après création automatique d'une sauvegarde horodatée du script d'origine.

---

## 3. Tests internes

Les tests sont menés de façon itérative, sur postes réels, selon un cycle « exécuter → observer le symptôme → diagnostic ciblé → correctif ».

**Portée des tests internes**

- Exécution sur postes fraîchement imagés, dans les conditions réelles de déploiement.
- Validation du lancement (double-clic, console admin, association `.py`/`.pyw`) et du comportement d'élévation UAC.
- Vérification de chaque étape du flux : renommage, jonction Entra ID, installation applicative, etc.
- Contrôle de l'encodage (accents, émojis) sur Windows en français.
- Tests de robustesse : coupure réseau, échec d'une étape, chemins avec espaces, session non-admin.

Depuis l'ajout de la **vérification finale**, chaque exécution produit sa propre preuve : la fiche de remise HTML consigne l'état réel du poste en 15 points. Conserver ces fiches constitue le relevé de tests le plus fidèle, poste par poste.

> **À compléter** — matrice de tests, environnements couverts (versions Windows, builds), et résultats détaillés à consigner ici au fur et à mesure.

| Domaine testé | Environnement | Statut | Date | Notes |
|---|---|---|---|---|
| Lancement / élévation UAC | | | | |
| Renommage + régional | | | | |
| Jonction Entra ID | | | | |
| Installation applicative | | | | |
| Vérifications post-install | | | | |

---

## 4. Documentation

L'ensemble de la documentation est destiné à la fois à l'usage opérationnel et à l'approbation par le comité de projet LGS.

**Documents produits**

- **Portée fonctionnelle** (DOCX) — description du périmètre et des étapes.
- **Exigences techniques** (DOCX) — prérequis, dépendances, contraintes d'exécution.
- **Fichiers de configuration** (JSON / CSV) et **chargeur de configuration** PowerShell.
- **Présentation** (PPTX) pour le comité d'approbation du projet.
- **Ce README** — vue d'ensemble du cycle de vie et point d'entrée de la documentation.

> **À compléter** — liens vers l'emplacement de référence (SharePoint interne), numéros de version des documents et responsables.

---

## 5. Interaction proactive et continue avec l'équipe de sécurité IBM

LGS InstalleX effectue des opérations à privilèges élevés (exécution en administrateur, écriture registre, jonction d'identité, installation logicielle). À ce titre, l'engagement avec l'équipe de sécurité IBM fait partie intégrante du cycle de vie et non d'une étape finale.

**Principes d'engagement**

- **Proactivité** — l'équipe de sécurité est sollicitée dès la conception des fonctionnalités sensibles (élévation, jonction d'identité, exécution de binaires téléchargés), et non uniquement au moment de la mise en production.
- **Continuité** — chaque évolution touchant à un domaine sensible (nouvelle étape, changement de comportement d'élévation, gestion des secrets) déclenche une revue.
- **Traçabilité** — les échanges, recommandations et suites données sont consignés dans le registre ci-dessous.

**Domaines soumis à revue de sécurité**

- Mécanisme d'élévation UAC et surface d'exécution en administrateur
- État du chiffrement BitLocker — **constaté uniquement**, l'outil n'agit plus dessus et ne manipule aucune clé
- Manipulation des identités (jonction Entra ID)
- Intégrité des installeurs téléchargés (signature Authenticode via `Get-AuthenticodeSignature` + contrôle de taille) avant exécution en administrateur
- Politique d'exécution PowerShell (`RemoteSigned`) et prévention de l'injection lors du renommage (nom via variable d'environnement, validation NetBIOS)
- Contenu du journal détaillé (garantie qu'aucun secret n'y figure, le fichier résidant sur le bureau)
- Intégrité des assets embarqués et absence de dépendances réseau non maîtrisées
- Journalisation (garantie de non-fuite de secrets dans les logs)
- Signature numérique du livrable

> **À compléter** — registre des interactions avec l'équipe de sécurité IBM.

| Date | Sujet / domaine | Interlocuteur(s) | Recommandation | Suite donnée | Statut |
|---|---|---|---|---|---|
| | | | | | |
| | | | | | |

---

## Installation et utilisation

**Prérequis**

- Windows (poste imagé LGS)
- Python 3.10 ou plus récent
- PyQt6 (`pip install PyQt6`) — installé pour l'interpréteur associé aux fichiers `.py`/`.pyw`
- Droits permettant l'élévation UAC

**Lancement**

- **Recommandé** : renommer le script en `.pyw` et double-cliquer → exécution sans aucune fenêtre console, du début à la fin.
- **Alternative** : lancer depuis une console administrateur :
  ```
  python "C:\chemin\complet\LGS_InstalleX.py"
  ```

**Dépannage**

- Si rien ne s'affiche après le UAC : vérifier que PyQt6 est installé pour le bon interpréteur (`py -0p`, `assoc .py`, `ftype Python.File`).
- Journal de crash automatique : `%TEMP%\InstalleX_crash.log` (ouvert automatiquement en cas d'erreur).
- Journal détaillé d'installation : `LGS_Log_Detaile_<nom>_<horodatage>.txt`, sur le bureau. Attention : si l'élévation UAC utilise un compte administrateur différent, le fichier atterrit sur le bureau de ce compte.
- Paquets compagnons dans `C:\LGS_Deploy` : `CommercialVantage\VantageInstaller.exe` (Lenovo Vantage — requis, sinon l'application est ignorée) et `ODT\setup.exe` (facultatif : téléchargé automatiquement depuis le CDN Microsoft s'il est absent). Le dossier est supprimé automatiquement en fin de provisionnement.
- Échec de téléchargement derrière un proxy d'entreprise : `download_file` bascule seul sur `curl.exe`. Si les deux chemins échouent, vérifier que le certificat d'inspection TLS est bien présent dans le magasin Windows (`ROOT` / `CA`).
- Office installé mais en mauvaise langue / mauvais canal : vérifier que `--custom "/configure <xml>"` est bien transmis à winget — sans lui, winget appliquerait la configuration par défaut du manifeste au lieu de celle de LGS.
- Attention : si l'élévation utilise un compte administrateur différent, le journal de crash est écrit dans le `%TEMP%` de ce compte.

---

## Correctifs

> **Tenue de cette section** — tout défaut corrigé y est consigné, du plus récent au plus ancien : ce qui n'allait pas, ce qui a été fait, et le commit correspondant. L'objectif est qu'un correctif se retrouve en quelques secondes sans parcourir l'historique Git. **Chaque correction apportée au script doit donner lieu à une entrée ici.**

### 2026-08-25

| Défaut | Correction | Commit |
|---|---|---|
| Edge ne s'ouvrait pas sur `www.lgs.com`. Seuls `HomepageLocation` et `HomepageIsNewTabPage` lui étaient posés — or `HomepageLocation` ne pilote que le **bouton Accueil**, pas la page d'ouverture. Chrome recevait bien les quatre clés nécessaires, Edge seulement deux | Ajout de `RestoreOnStartup` à `4` (« ouvrir des pages précises ») et de `RestoreOnStartupURLs\1` pour Edge, à l'identique de Chrome | `—` |

### 2026-08-24

| Défaut | Correction | Commit |
|---|---|---|
| Commercial Vantage déclaré **ABSENT** par la vérification finale alors qu'il venait d'être installé avec succès. Les deux contrôles divergeaient : l'installation cherchait `-AllUsers *LenovoSettingsforEnterprise*`, la vérification `-Name '*Vantage*'` — or le paquet s'appelle `E046963F.LenovoSettingsforEnterprise` et **ne contient pas « Vantage »**. Il manquait aussi `-AllUsers`, indispensable puisque le script tourne élevé | Détection extraite dans `VANTAGE_CHECK_PS`, une définition **unique** partagée par les deux appels. Rendue robuste au passage : `-AllUsers` exige l'élévation et renvoyait une sortie **vide** — ni `YES` ni `NO` — en cas de refus ; un `try/catch` et un repli sur la requête utilisateur courant garantissent désormais une réponse | `fef9cda` |

### 2026-08-21

| Défaut | Correction | Commit |
|---|---|---|
| Installeurs abandonnés dans `%TEMP%` : chaque étape nettoie bien le sien dans un `finally`, mais la suppression échoue tant que l'installeur tient le fichier verrouillé, et l'échec était **avalé silencieusement**. Constat sur un poste : **374 Mo** de pilote NVIDIA restés en place | `_cleanup_temp_files()` repasse en fin d'exécution, une fois les verrous relâchés, sur une **liste explicite et fermée** d'artefacts — jamais de balayage générique de `%TEMP%`. Ce qui reste verrouillé est désormais **nommé dans le journal** au lieu d'être ignoré. Le journal de crash est volontairement conservé | `691b69c` |
| `%TEMP%\INSTALLEX_ODT` (setup.exe de l'ODT + `configuration.xml`) et `%TEMP%\LGS_Office` n'étaient jamais supprimés | Les deux dossiers rejoignent la liste nettoyée en fin d'exécution | `691b69c` |
| Adobe : le `unlink` était dans le corps du `try`, donc sauté dès qu'une exception survenait pendant le téléchargement ou l'installation | Déplacé dans un `finally`, avec `tmp` initialisé avant le `try` pour couvrir un échec antérieur au calcul du chemin | `691b69c` |
| Repli Microsoft Store abandonné dès le premier `0x8A15005E` (source injoignable — épinglage de certificat cassé par le proxy). Sur un poste fraîchement imagé, la configuration proxy et les services Store ne sont pas encore stabilisés à l'étape 6 : l'échec n'est pas forcément définitif, et winget suggère lui-même « try the source reset command » | Les sources winget sont réinitialisées (`winget source reset --force`, forme globale car seule elle réajoute les sources par défaut) puis msstore rafraîchie, avant une seconde tentative. Vérifié : `winget source update --name msstore` réussit sur un poste déjà provisionné, ce qui confirme que le blocage n'est pas permanent | `e4be79f` |
| Case « Nouvelle embauche » **invisible** dans l'écran de configuration : `QCheckBox` ne définissait que la couleur du texte, l'indicateur héritait donc du fond de `QWidget` et se confondait avec lui sur le thème sombre | Indicateur dessiné explicitement : bordure claire sur fond contrasté quand décoché, remplissage accent quand coché, bordure accent au survol. Pas de glyphe de coche — Qt ne charge pas les data URI depuis une feuille de style (vérifié par analyse de pixels : aucun rendu), et embarquer un fichier image irait contre l'autonomie du script | `6bc0186` |

### 2026-08-20

| Défaut | Correction | Commit |
|---|---|---|
| Deux versions de la procédure de mot de passe embarquées simultanément — chaque poste recevait la v3.10.1 **et** une version périmée de dix mois, sans moyen de les distinguer | Retrait de `Win_Procedure_de_changement_des_mots_de_passe.docx` du bloc Base64 ; les 8 assets restants vérifiés identiques au bit près. Script réduit de 12,15 à 7,67 Mo | `ca575e3` |

### 2026-08-19

| Défaut | Correction | Commit |
|---|---|---|
| Windows Update annonçait **75 mises à jour** là où le poste en recevait 23 : `Get-WindowsUpdate -Install` émet un objet par mise à jour **et par étape**, et une même mise à jour peut venir de plusieurs services | Comptage par **titres distincts** (`Select-Object -Unique` côté PSWindowsUpdate, table de titres vus côté WUA, ensemble de secours côté Python). `AcceptEula` continue de s'appliquer à chaque objet | `db47de4` |
| `0x8A15005E` s'affichait comme « Code HRESULT inconnu », masquant une cause pourtant documentée dans le code | Code nommé dans la table winget : « Source injoignable — épinglage de certificat (proxy à inspection SSL) » | `f2d92f2` |
| `Raccourci CAT.lnk — FAIL` à chaque exécution : la vérification finale cherchait un raccourci que `step3_shortcuts` **supprime** volontairement | Contrôle retiré. La vérification compte **15 points** — le chiffre de 14 annoncé jusqu'ici était erroné, vérifié par comptage sur un journal d'exécution réel | `f2d92f2` |
| BitLocker signalé en **échec** pendant le chiffrement : `ProtectionStatus` reste `Off` tant qu'il tourne, donc un poste à 98 % avec clé déjà sauvegardée était marqué en erreur | `VolumeStatus` et le pourcentage distinguent « chiffrement en cours » (avertissement) de « non protégé » (échec) | `f2d92f2` |
| Slack déclaré introuvable 5 s après winget, alors qu'il l'était bien | Attente jusqu'à 30 s avant de conclure | `f2d92f2` |
| `_msstore_install` imposait `--scope machine` alors que les paquets Store sont des MSIX qui gèrent leur propre portée | `--scope` retiré. Cause probable de l'échec de Commercial Vantage constaté sur poste | `b7c6f33` |
| Windows Update pouvait immobiliser le technicien 2 h par méthode | Budget `WU_BUDGET_S` de **10 minutes** couvrant l'étape entière — le repli WUA n'obtient que le temps restant | `b7c6f33` |

### 2026-08-14

| Défaut | Correction | Commit |
|---|---|---|
| Windows Update **abandonné** dès qu'un redémarrage était en attente — condition auto-infligée par les installations des étapes 5 à 8, donc l'étape ne tournait quasiment jamais (3 des 4 indicateurs présents sur un poste mesuré) | L'état est journalisé et reporté au bilan, mais la mise à jour est **tentée**. Le traitement d'erreur existant intercepte un blocage réel | `23fa5d3` |

### 2026-08-11

| Défaut | Correction | Commit |
|---|---|---|
| Firefox installé **en anglais** : l'identifiant `Mozilla.Firefox` est le paquet en-US, Mozilla publiant un paquet par langue | Bascule sur `Mozilla.Firefox.fr`. Au passage, deux URL de repli cassées corrigées : `os=win64-msi` renvoyait 404, et `lang=fr-CA` n'existe pas chez Mozilla | `c0fa643` |
| Écran de veille jamais appliqué à l'utilisateur final sur poste Entra ID : le filtre ne retenait que les SID `S-1-5-21-`, alors que les comptes Entra ID sont en `S-1-12-1-` | Les deux préfixes sont acceptés ; SID de service toujours exclus. Mesuré : 0 ruche retenue avant, 1 après | `94dc4c6` |
| Les deux regex NetBIOS, que le code exige identiques, avaient divergé (`[A-Za-z0-9\-]` / `[A-Za-z0-9-]`) | Alignées. Comportement vérifié identique sur 10 entrées — l'écart était typographique, mais invitait une vraie divergence | `d32cd5b` |

### 2026-08-05

| Défaut | Correction | Commit |
|---|---|---|
| Numéro de série disque affiché sous forme d'**EUI-64 du contrôleur** (`0025_38A9_41BF_6A6F`) au lieu du numéro d'étiquette. Les trois classes WMI interrogées renvoyaient toutes la même valeur | Lecture de `FruId` puis `AdapterSerialNumber` de `MSFT_PhysicalDisk`, seules propriétés portant le vrai numéro. Vérifié : `S7G8NF1X923400` | `3893faf` |

### 2026-08-04

| Défaut | Correction | Commit |
|---|---|---|
| Écran de veille configuré mais **jamais armé** : Windows garde ces paramètres en cache pour la session ouverte, et `SystemParametersInfo` n'était jamais appelé (0 occurrence) | Appel de `SystemParametersInfoW` avec `SPIF_SENDCHANGE` : la session recharge le réglage immédiatement, sans redémarrage | `6928799` |
| Slack échouait avec `-1978334957` (« paquet non supporté par ce système ») sans qu'aucune des 3 tentatives ne puisse aboutir | Ce code déclenche désormais un réessai **sans `--scope`**, comme `-1978335216` : les deux signifient « pas d'installeur pour cette portée » | `a8e5afa` |

### 2026-07-31

| Défaut | Correction | Commit |
|---|---|---|
| Codes de résultat Windows Update mal interprétés : `4` (Échec) et `5` (Abandonné) journalisés comme un simple « redémarrage requis », `3` passant pour un succès complet | Table `OperationResultCode` correcte et lecture de `RebootRequired` | `1610743` |
| Le repli WUA n'appelait jamais `AcceptEula()` : toute mise à jour exigeant un CLUF échouait **silencieusement**, précisément dans le chemin utilisé quand PSGallery est bloqué par le proxy | `AcceptEula` appliqué à chaque mise à jour | `1610743` |
| Deux balayages complets de Windows Update enchaînés (`Get` puis `Install`) | Une seule commande `Get-WindowsUpdate -Install` | `1610743` |
| `PSGallery` laissé durablement en « Trusted » sur le poste livré | Politique d'origine restaurée dans un `finally` | `1610743` |
| Intel DSA : code de retour de l'installeur **ignoré**, et fenêtre de détection de 30 s alors que l'étape annonce 1 à 2 min | Code lu et journalisé, fenêtre portée à 2 min, trois issues distinctes au lieu d'un message unique | `772446e` |
| Le code de verrou MSI retenu pour les réessais était le mauvais : `-1978334957` (condition permanente) y figurait, tandis que `0x8A150102` (installation en cours) en était absent | Liste `WINGET_TRANSIENT` corrigée | `b84cc39` |
| Doublon `-1978335215` dans la table des codes winget — Python conservait la dernière entrée, rendant la première morte | Doublon retiré | `772446e` |
| Journal déplacé dans `%PROGRAMDATA%` avec ACL restreintes, imposant un raccourci pour le consulter | Retour à une écriture directe sur le bureau | `dc5249a` |

---

## Historique des versions

> L'outil s'est appelé **P.R.I.S.M** jusqu'à la version 3.8.1 incluse. Les entrées ci-dessous conservent le nom porté à l'époque : le renommage en **LGS InstalleX** s'accompagne d'une remise à zéro du versionnage à **1.0**, et n'efface pas la lignée technique qui l'a précédé.

### LGS InstalleX

- **v1.0** *(2026-08-05)* — première version sous le nom LGS InstalleX. Reprend l'intégralité des fonctionnalités et correctifs de P.R.I.S.M 3.8.1 ; seuls le nom et le versionnage changent. Identifiants internes alignés (`INSTALLEX_VERSION`, `$env:INSTALLEX_NEW_NAME`, `InstalleX_crash.log`).
- **Depuis la v1.2** *(le numéro de version n'a pas encore été incrémenté)* :
  - **Windows Update rétabli, avec garde-fou** — l'étape est de retour (le provisionnement repasse à **9 étapes / 10 jalons**), mais elle commence par vérifier qu'aucune session Windows Update n'est déjà active : dans ce cas elle laisse la session existante travailler au lieu d'en lancer une seconde, qui ne l'accélérerait pas et risquerait d'échouer sur un verrou. BitLocker, lui, reste hors du script.
- **v1.2** *(2026-08-25)* :
  - **Mise à jour d'Office après installation** — une passe `OfficeC2RClient.exe /update` suit l'installation (et s'exécute aussi quand Office était déjà présent), pour ne pas livrer un poste en retard de plusieurs correctifs. `forceappshutdown=false` volontairement : le script pouvant être relancé sur un poste en service, forcer la fermeture d'Office y ferait perdre le travail en cours. Les versions avant/après sont journalisées.
  - **Commercial Vantage : saut fiabilisé** — l'étape n'est ignorée que si **trois conditions cumulatives** sont réunies : paquet trouvé, `Status` à `Ok`, et dossier d'installation réellement présent sur le disque. Le faux positif est l'erreur coûteuse ici — il ferait sauter l'installation sur un poste qui en a besoin. La version détectée est journalisée.
  - **Windows Update et BitLocker retirés du script** — ces deux domaines relèvent des stratégies du parc (Intune, GPO), et le chiffrement était déjà actif avant l'intervention de l'outil sur les postes observés. Le provisionnement passe de **10 à 8 étapes** et la grille de **11 à 9 jalons**. La vérification finale continue de **constater** l'état de BitLocker, en lecture seule : la fiche de remise reste une preuve de conformité, mais l'outil n'agit plus sur le chiffrement. Windows Update figure désormais dans les actions manuelles recommandées.
- **v1.1** *(2026-08-21)* — sept ajouts fonctionnels, sans changement de comportement pour les étapes existantes :
  - **Configuration régionale** — fr-CA, date ISO `yyyy-MM-dd`, horloge 24 h, fuseau Eastern Standard Time et position Canada, intégrés à l'étape 8 sans nouvelle étape numérotée.
  - **Vérification finale** — 15 points remesurés sur le poste en fin de provisionnement, plutôt que déduits du déroulé du script.
  - **Fiche de remise HTML** — déposée sur le bureau : identification, résultats des contrôles, inventaire matériel. Autonome et mise en page pour l'impression.
  - **Configuration externe** — `LGS_InstalleX.config.json`, facultatif, pour ajuster un déploiement sans toucher au script.
  - **Nettoyage de `%TEMP%`** — les installeurs déposés par le script sont supprimés en fin d'exécution, sur liste explicite.
  - **Signal sonore de fin** — `program-complete.mp3` (5,3 Ko, 1,35 s) embarqué en Base64 et joué via MCI, en remplacement des bips.
  - **Updater étendu** — `LGS_InstalleX_Updater.py` liste désormais les fichiers embarqués avec leur taille et permet de les supprimer, pas seulement de les remplacer.

### P.R.I.S.M (lignée précédente)

- **Lignée v3.x → PRISM 7/8** (PowerShell / WinForms) — sourcing SharePoint/OneDrive, puis bascule vers l'embarquement Base64, GUI thème sombre + branding LGS, détection GPU NVIDIA, Adobe Reader dynamique, import des favoris Edge, automatisation Windows Update, détection langue française, flux « Nouvelle embauche ».
- **v3.4 (PowerShell)** — dernière version WinForms d'origine (~2 553 lignes) avant conversion Python.
- **PRISM 8** — ajout de l'étape 10 (BitLocker → Entra ID), grille GUI à 6 rangées, correctif de l'icône (LOGO_B64), validation du nom NetBIOS, timeouts adaptatifs, log incrémental.
- **PRISM 12** (Python / PyQt6, version applicative 3.8.x) — déploiement winget, sauvegarde BitLocker/Entra ID, correctifs UTF-8, élévation UAC durcie (chemin absolu + arguments quotés), relance via `pythonw.exe`, suppression des fenêtres console enfants (`CREATE_NO_WINDOW`).
  - **v3.8** — première itération du durcissement : vérification Authenticode des installeurs en repli, installation applicative pilotée par le catalogue `LOGICIELS`.
  - **v3.8.1** — durcissement sécurité et robustesse matérielle (dernière version sous le nom P.R.I.S.M) :
    - **Sécurité** — `verify_authenticode` bascule sur `Get-AuthenticodeSignature` (au lieu de `WinVerifyTrust`/ctypes), appliquée avant exécution à Firefox/Chrome, Adobe, Intel DSA, NVIDIA Driver et NVIDIA App (contrôle de taille + signature ; l'empreinte SHA-256 est retirée). Politique PowerShell passée de `Bypass` à `RemoteSigned`. Renommage machine sécurisé par variable d'environnement `$env:INSTALLEX_NEW_NAME` (anti-injection). Journal temporairement déplacé dans `%PROGRAMDATA%\LGS\Logs` avec ACL restreintes (`icacls`) — **choix annulé depuis**, le journal est de nouveau écrit sur le bureau.
    - **Détection GPU NVIDIA réécrite** — clé sur l'ID PCI `VEN_10DE` (fonctionne sur image fraîche sans pilote), version pilote via `nvidia-smi`, table `NVIDIA_DEV_NAMES` pour les GPU Ada laptop, commandes PowerShell en Base64 (`_ps_encoded` / `-EncodedCommand`), logs de diagnostic.
    - **Nouvelles installations** — pilote NVIDIA + NVIDIA App (Entreprise), Lenovo Commercial Vantage, et Microsoft 365 Apps via l'Office Deployment Tool (dossier compagnon `C:\LGS_Deploy`).
    - **Office : winget prioritaire, ODT en repli** — ajout de `_install_office_winget()` : installation par `winget install --id Microsoft.Office` avec le `configuration.xml` LGS transmis en `--custom "/configure"`, ce qui supprime l'obligation de pré-déposer `setup.exe` sur le poste. Repli automatique sur l'ODT local en cas d'échec (winget indisponible, CDN inaccessible, hash de manifeste obsolète) et vérification effective de la présence d'Office après installation.
    - **Résilience réseau & inventaire** — helper `download_file` (contexte TLS enrichi des magasins Windows via `ssl.enum_certificates`, repli `curl.exe`/Schannel) appliqué aux téléchargements ; `_download_odt_setup()` récupère `setup.exe` depuis le CDN Microsoft quand l'ODT n'est pas pré-déposé ; ajout d'un **inventaire matériel** non bloquant (`collect_inventory` / `log_inventory`) consigné au journal ; nettoyage automatique de `C:\LGS_Deploy` en fin d'exécution (`_cleanup_deploy_folder`).
    - **Revirement d'architecture** — le raccourci `CAT.lnk` (COM `WScript.Shell`) et le renommage machine (`Set-ItemProperty` + WMI `Rename()`) sont désormais réalisés via PowerShell plutôt qu'en API natives ctypes ; `Rename-Computer` reste évité. Helper d'appels unifié `run_cmd`.
    - **Qualité** — `urlretrieve` (dépréciée) remplacée par `urlopen` + `copyfileobj` (Adobe).
