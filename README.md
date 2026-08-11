# LGS InstalleX

**Provisionnement automatisé des postes de travail LGS**

Outil de provisionnement automatisé des postes de travail pour les déploiements Groupe LGS — une société IBM.

> Version applicative : **1.0** (Python / PyQt6) — versionnage repris à 1.0 lors du passage de P.R.I.S.M à LGS InstalleX ; la lignée technique précédente s'arrêtait à 3.8.1
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
8. [Historique des versions](#historique-des-versions)

---

## Aperçu

LGS InstalleX automatise la préparation complète d'un poste de travail Windows dans le cadre des déploiements LGS, depuis un poste fraîchement imagé jusqu'à un poste prêt à remettre à l'utilisateur. L'outil regroupe en une seule interface les étapes habituellement manuelles et sujettes à erreur : renommage machine, configuration régionale, jonction Entra ID, installation des applications standard, chiffrement BitLocker avec sauvegarde de la clé, et vérifications post-installation.

Deux implémentations fonctionnellement équivalentes sont maintenues en parallèle :

| Implémentation | Interface | Fichier | Usage |
|---|---|---|---|
| Python 3.10+ / PyQt6 | GUI thème sombre | `LGS_InstalleX.py` | Itération courante |
| PowerShell / WinForms | GUI thème sombre | `LGS_Install_Script 3.4 (P.R.I.S.M).ps1` | Version historique, conservée sous son nom d'origine |

**Caractéristiques principales**

- Provisionnement en 10 étapes séquentielles (grille de progression sur 11 jalons) avec log temps réel
- Élévation UAC automatique et exécution en contexte administrateur
- Jonction Entra ID couvrant les scénarios Autopilot, PPKG et manuel
- Chiffrement BitLocker (XTS-AES-256) avec sauvegarde de la clé de récupération vers Entra ID
- Déploiement applicatif via winget avec repli sur téléchargement direct ; Microsoft 365 Apps installé par winget avec configuration maîtrisée (repli sur l'ODT local) et Lenovo Commercial Vantage via paquet de déploiement compagnon
- **Vérification de la signature Authenticode des installeurs téléchargés** (`Get-AuthenticodeSignature`) avant toute exécution en administrateur ; un binaire non signé, altéré ou non fiable est rejeté
- Assets embarqués en Base64 (aucune dépendance réseau vers SharePoint / OneDrive)
- Détection de langue ; détection matérielle robuste des GPU NVIDIA (par ID fabricant PCI `VEN_10DE`) avec installation du pilote et de NVIDIA App (Entreprise) ; automatisation Windows Update
- **Inventaire matériel** du poste collecté et journalisé au démarrage (sans effet sur le provisionnement), puis réutilisé dans la fiche de remise
- **Configuration régionale** fr-CA : date ISO `yyyy-MM-dd`, horloge 24 h, fuseau Eastern Standard Time, position géographique Canada
- **Vérification finale** en 14 points qui remesure le poste réellement livré, et **fiche de remise HTML** déposée sur le bureau (identification, contrôles, inventaire)
- Téléchargements résilients : contexte TLS enrichi des magasins de certificats Windows, avec repli sur `curl.exe` (Schannel)
- Journal détaillé écrit directement sur le bureau, à l'endroit où le technicien le cherche
- Nettoyage automatique du dossier de déploiement compagnon en fin d'exécution
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
- **Appels système centralisés** — les commandes externes passent par un helper unique `run_cmd` (forçage UTF-8, `CREATE_NO_WINDOW`, timeout paramétrable, injection de variables d'environnement via `env_extra`). Les scripts PowerShell complexes (détection GPU) sont transmis en Base64 UTF-16LE via `-EncodedCommand` (helper `_ps_encoded`) pour éviter toute mauvaise interprétation des `$` et caractères spéciaux. PowerShell reste l'outil retenu là où il est le plus fiable (raccourci COM `WScript.Shell`, renommage, BitLocker, PSWindowsUpdate, signature Authenticode, requêtes CIM/WMI).
- **Politique d'exécution `RemoteSigned`** — les appels PowerShell utilisent `-ExecutionPolicy RemoteSigned` (au lieu de `Bypass`) : les scripts système sollicités (PSGallery/WUA, cmdlets BitLocker) sont signés par Microsoft et s'exécutent sans abaisser la politique.
- **Vérification des binaires avant exécution** — tout installeur téléchargé (repli hors winget : Firefox/Chrome, Adobe, Intel DSA, NVIDIA Driver, NVIDIA App) est contrôlé avant d'être lancé en administrateur : taille minimale et signature Authenticode de l'éditeur via la fonction `verify_authenticode` (`Get-AuthenticodeSignature`). Un fichier non signé, altéré ou non fiable est rejeté (fail-safe).
- **Encodage UTF-8 forcé** — encodage UTF-8 (avec BOM) de bout en bout, incluant l'injection d'un préfixe console pour les appels PowerShell, afin d'éviter la corruption des accents et caractères spéciaux sur un Windows en français.
- **Détection et confirmation uniformes** — le helper `_soft_present()` combine chemins de fichiers **et** clés Uninstall du registre (HKLM 64/32 bits + HKCU) pour toutes les applications ; la détection par chemin seule ratait les installations dans un dossier renommé d'une version à l'autre. Le même contrôle est rejoué **après** chaque installation : un `0` retourné par winget ne prouve pas que le logiciel est présent (cas constaté sur Office).
- **Support MSI et téléchargements résilients** — `_install_from_url()` télécharge via `download_file()` (contexte TLS + repli `curl.exe`/Schannel) et lance automatiquement les `.msi` par `msiexec /i /qn /norestart`, les `.exe` recevant leurs arguments propres. Le code de sortie de l'installeur est lu et journalisé.
- **Installation applicative pilotée par les données** — le catalogue logiciel (`LOGICIELS`) décrit chaque application (chemins de détection, motifs registre, identifiant winget, URL et méthode de repli) ; l'étape 6 l'exploite pour uniformiser détection et installation. Un dossier compagnon `C:\LGS_Deploy` (`LGS_DEPLOY_DIR`, sous-dossiers `ODT\` et `CommercialVantage\`) héberge les paquets de déploiement entreprise : il est requis pour Lenovo Commercial Vantage, et sert de repli pour Microsoft 365 Apps.
- **Microsoft 365 Apps — winget d'abord, ODT en repli** — le paquet winget `Microsoft.Office` est le *même* `setup.exe` Click-to-Run que l'ODT, simplement téléchargé depuis le CDN Microsoft. LGS InstalleX l'installe donc via winget en lui passant **son propre `configuration.xml`** (`--custom "/configure <xml>"`), ce qui conserve la maîtrise totale du déploiement (fr-CA, canal, RemoveMSI) tout en évitant d'avoir à pré-déposer `setup.exe` sur chaque poste. En cas d'échec (winget absent, CDN inaccessible, « installer hash mismatch » du manifeste), l'ODT prend le relais — et si `setup.exe` n'a pas été pré-déposé dans `C:\LGS_Deploy\ODT`, il est **téléchargé automatiquement depuis le CDN Microsoft** (`_download_odt_setup`). Le succès est vérifié par la présence réelle des binaires Office, car winget peut retourner `0` alors que Click-to-Run a échoué.
- **Téléchargements résilients** — le helper `download_file` tente d'abord `urlopen` avec un contexte TLS construit à partir des magasins de certificats Windows (`ROOT` et `CA`, via `ssl.enum_certificates`), puis se replie sur `curl.exe` (intégré depuis Windows 10 1803), qui s'appuie sur Schannel. Ce double chemin évite les échecs de validation de certificat derrière un proxy d'inspection TLS d'entreprise.
- **Inventaire matériel informatif** — `collect_inventory` / `log_inventory` interrogent CIM au démarrage et consignent la configuration du poste dans le journal. La collecte est volontairement non bloquante : elle ne lève jamais, et aucune décision d'installation n'en dépend. Le résultat alimente ensuite la fiche de remise.
- **Écriture multi-ruches factorisée** — `_loaded_user_sids()` et `_write_all_user_hives()` sont partagés par l'écran de veille et la configuration régionale : la règle de sélection des ruches (dont les SID Entra ID) vit à un seul endroit, au lieu d'être dupliquée dans chaque fonctionnalité où elle pourrait diverger.
- **Vérification finale par remesure** — `_final_verification()` ne se fie pas au déroulé du script : chaque point est relu sur la machine. C'est indispensable puisqu'une étape peut se dérouler sans erreur sans que le résultat soit là — winget retourne `0` alors que rien n'est installé. Les contrôles d'écran de veille et de configuration régionale lisent une **ruche utilisateur réelle**, jamais celle du compte élevé.
- **Nettoyage en fin de course** — `_cleanup_deploy_folder` supprime `C:\LGS_Deploy` une fois le provisionnement terminé (best-effort : les fichiers verrouillés sont ignorés, l'attribut lecture seule est levé si besoin, et une erreur n'interrompt jamais le script).
- **Journal sur le bureau** — le journal détaillé est écrit directement sur le bureau de l'opérateur. Une itération intermédiaire l'avait déplacé dans `%PROGRAMDATA%\LGS\Logs` avec des ACL restreintes ; en pratique cela imposait de passer par un raccourci pour le consulter, pour un gain opérationnel nul — le choix a donc été annulé.
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
3. **Raccourci bureau** `CAT.lnk` — créé via PowerShell COM `WScript.Shell` (aucune dépendance externe, disponible sur tout Windows).
4. **Renommage machine** — `Set-ItemProperty` (registre) + `Win32_ComputerSystem.Rename()` (WMI), sans `Rename-Computer` ni signal de redémarrage, effectif au prochain démarrage. Nom passé via `$env:INSTALLEX_NEW_NAME` (anti-injection), après validation NetBIOS.
   - *4b — Nouvelle embauche (conditionnel)* : ouverture de Box IBM et attente de l'acceptation du User Agreement, uniquement si l'option « Nouvelle embauche » est cochée dans l'écran de configuration.
5. **Microsoft 365 Apps** — via winget (`Microsoft.Office` + `configuration.xml` maison passé en `--custom /configure`), avec repli automatique sur l'Office Deployment Tool local (`setup.exe` dans `C:\LGS_Deploy\ODT\`) ; ignoré si Office est déjà présent.
6. **Applications standard** — Firefox, Google Chrome, page d'accueil www.lgs.com (stratégies Chrome / Edge / Firefox), Slack, Box for Office, Box Tools, Adobe Acrobat Reader, Intel Driver & Support Assistant, **pilote NVIDIA + NVIDIA App (Entreprise)** si GPU NVIDIA détecté, **Lenovo Commercial Vantage** sur matériel Lenovo. Chaque application suit une chaîne de replis (voir ci-dessous) et son installation est confirmée avant de passer à la suivante.

**Stratégie d'installation par application**

| Application | Méthode primaire | Replis |
|---|---|---|
| Microsoft 365 Apps | winget + `configuration.xml` LGS | ODT local, puis ODT téléchargé du CDN |
| Slack | winget **en portée machine** → paquet MSIX provisionné pour tous les profils | — (le MSI `slack.com/ssb` redirige vers un fichier absent du CDN) |
| Google Chrome | winget | MSI Chrome Enterprise, puis installeur `.exe` |
| Firefox | winget **`Mozilla.Firefox.fr`** (paquet français) | MSI `lang=fr`, puis installeur `.exe` `lang=fr` |
| Intel DSA | winget `Intel.IntelDriverAndSupportAssistant` | téléchargement direct `dsadata.intel.com` |
| Box for Office / Box Tools | winget | message d'installation manuelle |
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
9. **Windows Update** — PSWindowsUpdate avec repli sur l'agent COM natif (WUA), après détection d'un éventuel redémarrage en attente. Le **service Microsoft Update** est enregistré pour couvrir les correctifs Office et les pilotes, et jusqu'à **3 passes** s'enchaînent tant que de nouvelles mises à jour apparaissent (arrêt immédiat si un redémarrage devient nécessaire).
10. **BitLocker → Entra ID** (`dsregcmd`, `Get-Tpm`, `Enable-BitLocker` XTS-AES-256, `BackupToAAD-BitLockerKeyProtector`, confirmation via event 845 ; **la clé de récupération n'est jamais journalisée**).

*En clôture* : **vérification finale** (14 points remesurés sur le poste) et génération de la **fiche de remise HTML** sur le bureau — les deux avant le nettoyage, pour que la fiche reflète le poste tel qu'il est livré — puis suppression du dossier de déploiement `C:\LGS_Deploy`, récapitulatif des actions, détection d'un redémarrage requis et sauvegarde du journal sur le bureau.

**Vérification finale — points contrôlés**

| Domaine | Contrôle |
|---|---|
| Identité | Nom d'ordinateur conforme à la demande |
| Documentation | Dossier `CAT` et raccourci `CAT.lnk` sur le bureau |
| Logiciels | Les 8 applications du catalogue, détectées par chemin + registre + MSIX |
| Matériel Lenovo | Commercial Vantage (ignoré sur poste non-Lenovo) |
| Chiffrement | BitLocker : état de protection et pourcentage chiffré |
| Identité cloud | `dsregcmd` → `AzureAdJoined : YES` |
| Poste | Écran de veille et configuration régionale, lus dans une ruche utilisateur réelle |

Le résultat est journalisé point par point, puis résumé en trois issues : conforme, avertissements à vérifier, ou échecs à traiter avant remise.

**Fiche de remise**

Fichier `Fiche_Remise_<poste>_<horodatage>.html` déposé sur le bureau. Trois sections : identification (poste, date, technicien, durée, version de l'outil), résultats de la vérification avec pastilles de couleur, et inventaire matériel complet. Autonome (CSS embarqué, aucune dépendance réseau) et mis en page pour l'impression.

> La barre de progression de la GUI est graduée sur 11 jalons (les 10 étapes numérotées ci-dessus + l'état « Installation terminée »). L'étape 4b n'occupe pas de rang numéroté distinct.

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
- **Windows Update — portée et fiabilité** — le service **Microsoft Update** est enregistré (correctifs Office et pilotes, absents du service Windows Update seul) et le repli WUA ne filtre plus sur `Type='Software'`, qui excluait tous les pilotes. Les CLUF sont acceptés (`AcceptEula`) : sans cela, toute mise à jour en exigeant un échouait silencieusement dans ce chemin. Les codes `OperationResultCode` sont interprétés correctement — `2` réussi, `3` réussi avec erreurs, **`4` échec**, **`5` abandonné** — au lieu de traiter `4` et `5` comme un simple redémarrage requis. Le besoin de redémarrage est lu sur `RebootRequired` et remonté au bilan final. La recherche et l'installation tiennent en une seule commande (`-Install`), là où l'ancien code enchaînait deux balayages complets, et la politique `PSGallery` est restaurée en fin d'étape pour ne rien laisser de modifié sur le poste livré.
- **Timeouts adaptatifs** par commande (30 min par défaut, 2 h pour Windows Update).
- **Protection anti-veille** pendant le provisionnement et **mécanisme de pause** thread-safe.
- **Assets Base64** — fichiers embarqués (PDF de procédures, DOCX, raccourcis `.url`). Un chantier d'optimisation du bloc d'assets (~66 000 lignes) est en cours : externalisation vers un dossier compagnon ou consolidation en archive unique.

**Outil compagnon**

- **LGS InstalleX Asset Updater** (`LGS_InstalleX_Updater.py`, Python / PyQt6) — interface glisser-déposer permettant à du personnel non technique de remplacer les fichiers Base64 embarqués sans connaissances en développement. L'outil cible **le script Python** (`LGS_InstalleX.py`) : il localise le bloc `FICHIERS_EMBARQUES`, ré-encode les fichiers déposés en Base64 (lignes de 64 caractères) et réécrit le bloc en UTF-8 avec BOM, après création automatique d'une sauvegarde horodatée du script d'origine.

---

## 3. Tests internes

Les tests sont menés de façon itérative, sur postes réels, selon un cycle « exécuter → observer le symptôme → diagnostic ciblé → correctif ».

**Portée des tests internes**

- Exécution sur postes fraîchement imagés, dans les conditions réelles de déploiement.
- Validation du lancement (double-clic, console admin, association `.py`/`.pyw`) et du comportement d'élévation UAC.
- Vérification de chaque étape du flux : renommage, jonction Entra ID, installation applicative, BitLocker, etc.
- Contrôle de l'encodage (accents, émojis) sur Windows en français.
- Vérification de la sauvegarde de la clé BitLocker dans Entra ID (event 845).
- Tests de robustesse : coupure réseau, échec d'une étape, chemins avec espaces, session non-admin.

Depuis l'ajout de la **vérification finale**, chaque exécution produit sa propre preuve : la fiche de remise HTML consigne l'état réel du poste en 14 points. Conserver ces fiches constitue le relevé de tests le plus fidèle, poste par poste.

> **À compléter** — matrice de tests, environnements couverts (versions Windows, builds), et résultats détaillés à consigner ici au fur et à mesure.

| Domaine testé | Environnement | Statut | Date | Notes |
|---|---|---|---|---|
| Lancement / élévation UAC | | | | |
| Renommage + régional | | | | |
| Jonction Entra ID | | | | |
| Installation applicative | | | | |
| BitLocker + sauvegarde clé | | | | |
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

LGS InstalleX effectue des opérations à privilèges élevés (exécution en administrateur, écriture registre, chiffrement BitLocker, jonction d'identité, installation logicielle). À ce titre, l'engagement avec l'équipe de sécurité IBM fait partie intégrante du cycle de vie et non d'une étape finale.

**Principes d'engagement**

- **Proactivité** — l'équipe de sécurité est sollicitée dès la conception des fonctionnalités sensibles (élévation, BitLocker, gestion de la clé de récupération), et non uniquement au moment de la mise en production.
- **Continuité** — chaque évolution touchant à un domaine sensible (nouvelle étape, changement de comportement d'élévation, gestion des secrets) déclenche une revue.
- **Traçabilité** — les échanges, recommandations et suites données sont consignés dans le registre ci-dessous.

**Domaines soumis à revue de sécurité**

- Mécanisme d'élévation UAC et surface d'exécution en administrateur
- Gestion de la clé de récupération BitLocker (jamais journalisée, sauvegarde vers Entra ID)
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

## Historique des versions

> L'outil s'est appelé **P.R.I.S.M** jusqu'à la version 3.8.1 incluse. Les entrées ci-dessous conservent le nom porté à l'époque : le renommage en **LGS InstalleX** s'accompagne d'une remise à zéro du versionnage à **1.0**, et n'efface pas la lignée technique qui l'a précédé.

### LGS InstalleX

- **v1.0 (courant)** — première version sous le nom LGS InstalleX. Reprend l'intégralité des fonctionnalités et correctifs de P.R.I.S.M 3.8.1 ; seuls le nom et le versionnage changent. Identifiants internes alignés (`INSTALLEX_VERSION`, `$env:INSTALLEX_NEW_NAME`, `InstalleX_crash.log`).

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
