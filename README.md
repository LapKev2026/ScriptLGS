# P.R.I.S.M

**PowerShell Remote Initialization & System Management**

Outil de provisionnement automatisé des postes de travail pour les déploiements Groupe LGS — une société IBM.

> Version applicative : **3.8.1** — Itération livrée : **PRISM 12** (Python / PyQt6)
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
7. [Validations obligatoires du CISO IBM](#6-obtention-des-validations-obligatoires-du-ciso-ibm)
8. [Installation et utilisation](#installation-et-utilisation)
9. [Historique des versions](#historique-des-versions)

---

## Aperçu

P.R.I.S.M automatise la préparation complète d'un poste de travail Windows dans le cadre des déploiements LGS, depuis un poste fraîchement imagé jusqu'à un poste prêt à remettre à l'utilisateur. L'outil regroupe en une seule interface les étapes habituellement manuelles et sujettes à erreur : renommage machine, configuration régionale, jonction Entra ID, installation des applications standard, chiffrement BitLocker avec sauvegarde de la clé, et vérifications post-installation.

Deux implémentations fonctionnellement équivalentes sont maintenues en parallèle :

| Implémentation | Interface | Fichier | Usage |
|---|---|---|---|
| Python 3.10+ / PyQt6 | GUI thème sombre | `LGS_Install_Script_PRISM_12_.py` | Itération courante |
| PowerShell / WinForms | GUI thème sombre | `LGS_Install_Script 3.4 (P.R.I.S.M).ps1` | Version historique / environnements sans Python |

**Caractéristiques principales**

- Provisionnement en 10 étapes séquentielles (grille de progression sur 11 jalons) avec log temps réel
- Élévation UAC automatique et exécution en contexte administrateur
- Jonction Entra ID couvrant les scénarios Autopilot, PPKG et manuel
- Chiffrement BitLocker (XTS-AES-256) avec sauvegarde de la clé de récupération vers Entra ID
- Déploiement applicatif via winget avec repli sur téléchargement direct, plus paquets de déploiement compagnons pour Microsoft 365 Apps (ODT) et Lenovo Commercial Vantage
- **Vérification de la signature Authenticode des installeurs téléchargés** (`Get-AuthenticodeSignature`) avant toute exécution en administrateur ; un binaire non signé, altéré ou non fiable est rejeté
- Assets embarqués en Base64 (aucune dépendance réseau vers SharePoint / OneDrive)
- Détection de langue ; détection matérielle robuste des GPU NVIDIA (par ID fabricant PCI `VEN_10DE`) avec installation du pilote et de NVIDIA App (Entreprise) ; automatisation Windows Update
- Journal détaillé écrit dans `%PROGRAMDATA%\LGS\Logs` (ACL restreintes Administrateurs + SYSTEM) avec raccourci d'accès sur le bureau
- Journalisation incrémentale et journal de crash automatique

---

## 1. Conception

La conception de PRISM répond à un besoin opérationnel précis : réduire le temps et la variabilité du provisionnement des postes tout en garantissant un résultat conforme aux standards LGS/IBM.

**Objectifs de conception**

- **Reproductibilité** — un poste provisionné par PRISM est identique à tout autre, quel que soit le technicien.
- **Autonomie réseau** — les fichiers requis (raccourcis, PDF de procédures, favoris) sont embarqués dans le script en Base64, éliminant les échecs liés à l'authentification SharePoint/OneDrive et à l'encodage des URL rencontrés dans les versions antérieures.
- **Robustesse** — chaque étape est isolée (try/except par étape) pour qu'un échec ponctuel n'interrompe pas l'ensemble du provisionnement.
- **Traçabilité** — journalisation au fil de l'eau et journal de crash automatique.

**Décisions d'architecture**

- **GUI + worker thread** — l'interface (PyQt6 / WinForms) reste réactive pendant les opérations longues grâce à un thread de travail dédié (`QThread` côté Python), la communication vers l'UI se faisant par signaux thread-safe (`pyqtSignal`).
- **Renommage machine sans `Rename-Computer`** — le renommage évite la cmdlet `Rename-Computer`, qui peut émettre `WM_ENDSESSION` / `InitiateSystemShutdown` et fermer prématurément la GUI. Il est réalisé via PowerShell par écriture registre (`Set-ItemProperty` sur `ComputerName` / `Hostname`) puis `Win32_ComputerSystem.Rename()` (WMI), sans aucun signal de redémarrage — le changement est effectif au prochain démarrage. Le nouveau nom est transmis par variable d'environnement (`$env:PRISM_NEW_NAME`), jamais interpolé dans le corps du script (anti-injection).
- **Appels système centralisés** — les commandes externes passent par un helper unique `run_cmd` (forçage UTF-8, `CREATE_NO_WINDOW`, timeout paramétrable, injection de variables d'environnement via `env_extra`). Les scripts PowerShell complexes (détection GPU) sont transmis en Base64 UTF-16LE via `-EncodedCommand` (helper `_ps_encoded`) pour éviter toute mauvaise interprétation des `$` et caractères spéciaux. PowerShell reste l'outil retenu là où il est le plus fiable (raccourci COM `WScript.Shell`, renommage, BitLocker, PSWindowsUpdate, signature Authenticode, requêtes CIM/WMI).
- **Politique d'exécution `RemoteSigned`** — les appels PowerShell utilisent `-ExecutionPolicy RemoteSigned` (au lieu de `Bypass`) : les scripts système sollicités (PSGallery/WUA, cmdlets BitLocker) sont signés par Microsoft et s'exécutent sans abaisser la politique.
- **Vérification des binaires avant exécution** — tout installeur téléchargé (repli hors winget : Firefox/Chrome, Adobe, Intel DSA, NVIDIA Driver, NVIDIA App) est contrôlé avant d'être lancé en administrateur : taille minimale et signature Authenticode de l'éditeur via la fonction `verify_authenticode` (`Get-AuthenticodeSignature`). Un fichier non signé, altéré ou non fiable est rejeté (fail-safe).
- **Encodage UTF-8 forcé** — encodage UTF-8 (avec BOM) de bout en bout, incluant l'injection d'un préfixe console pour les appels PowerShell, afin d'éviter la corruption des accents et caractères spéciaux sur un Windows en français.
- **Installation applicative pilotée par les données** — le catalogue logiciel (`LOGICIELS`) décrit chaque application (chemins de détection, identifiant winget, URL et méthode de repli) ; l'étape 6 l'exploite pour uniformiser détection et installation. Les paquets nécessitant un déploiement entreprise (Microsoft 365 Apps via l'ODT, Lenovo Commercial Vantage) sont installés depuis un dossier compagnon `C:\LGS_Deploy` (`LGS_DEPLOY_DIR`, sous-dossiers `ODT\` et `CommercialVantage\`).
- **Journal à emplacement protégé** — le journal détaillé est écrit dans `%PROGRAMDATA%\LGS\Logs` avec des ACL restreintes (Administrateurs + SYSTEM via `icacls`) plutôt que sur le bureau public ; un raccourci est déposé sur le bureau pour l'accès de l'opérateur, avec repli silencieux vers le bureau si l'emplacement protégé est inaccessible.
- **Configuration externalisée** — paramètres structurés en JSON, séparés de la logique, pour faciliter la maintenance sans toucher au code.

---

## 2. Développement

**Pile technique**

- Python 3.10+ (garde de version au démarrage avec message d'erreur explicite)
- PyQt6 (`QtWidgets`, `QtCore`, `QtGui`) — installé automatiquement via `pip` s'il est absent
- API Windows via `ctypes` (élévation UAC, résolution du bureau `SHGetFolderPathW`, MessageBox)
- `winreg`, `subprocess`, `base64`, `urllib`, `shutil`, `re`
- PowerShell (via `run_cmd` / `_ps_encoded`) pour raccourci COM `WScript.Shell`, renommage machine, requêtes CIM/WMI, `Get-AuthenticodeSignature`, BitLocker et PSWindowsUpdate

**Étapes du flux de provisionnement (implémentation Python)**

*Actions préliminaires* (au démarrage du thread de travail) : protection anti-veille (`powercfg`, restaurée à l'étape 8) et test de disponibilité de winget avec mise à jour des sources.

1. **Création du dossier CAT** sur le bureau.
2. **Extraction des fichiers embarqués** (Base64) dans le dossier CAT (PDF de procédures, raccourcis `.url`, etc.).
3. **Raccourci bureau** `CAT.lnk` — créé via PowerShell COM `WScript.Shell` (aucune dépendance externe, disponible sur tout Windows).
4. **Renommage machine** — `Set-ItemProperty` (registre) + `Win32_ComputerSystem.Rename()` (WMI), sans `Rename-Computer` ni signal de redémarrage, effectif au prochain démarrage. Nom passé via `$env:PRISM_NEW_NAME` (anti-injection), après validation NetBIOS.
   - *4b — Nouvelle embauche (conditionnel)* : ouverture de Box IBM et attente de l'acceptation du User Agreement, uniquement si l'option « Nouvelle embauche » est cochée dans l'écran de configuration.
5. **Microsoft 365 Apps** — via l'Office Deployment Tool (ODT, `setup.exe` compagnon dans `C:\LGS_Deploy\ODT\`), ignoré si Office déjà présent.
6. **Applications standard** — Firefox, Google Chrome, page d'accueil www.lgs.com (stratégies Chrome / Edge / Firefox), Slack, Box for Office, Box Tools, Adobe Acrobat Reader, Intel Driver & Support Assistant, **pilote NVIDIA + NVIDIA App (Entreprise)** si GPU NVIDIA détecté, **Lenovo Commercial Vantage** sur matériel Lenovo (winget + repli sur téléchargement vérifié / paquets compagnons).
7. **Favoris Microsoft Edge** — écriture des favoris dans les profils + activation de la barre des favoris.
8. **Configuration Windows** — écran de veille (Ribbons.scr, 10 min, verrouillage), désactivation du démarrage rapide, restauration des paramètres de veille sauvegardés.
9. **Windows Update** — PSWindowsUpdate avec repli sur l'agent COM natif (WUA), après détection d'un éventuel redémarrage en attente.
10. **BitLocker → Entra ID** (`dsregcmd`, `Get-Tpm`, `Enable-BitLocker` XTS-AES-256, `BackupToAAD-BitLockerKeyProtector`, confirmation via event 845 ; **la clé de récupération n'est jamais journalisée**).

*En clôture* : récapitulatif des actions, détection d'un redémarrage requis, puis écriture du journal dans `%PROGRAMDATA%\LGS\Logs` avec dépôt d'un raccourci d'accès sur le bureau.

> La barre de progression de la GUI est graduée sur 11 jalons (les 10 étapes numérotées ci-dessus + l'état « Installation terminée »). L'étape 4b n'occupe pas de rang numéroté distinct.

**Points techniques notables**

- **Élévation UAC durcie** — relance avec chemin absolu et arguments entre guillemets (résistant aux chemins contenant des espaces), relance via `pythonw.exe` pour un fonctionnement sans console, et MessageBox en cas d'échec d'élévation plutôt qu'une sortie silencieuse.
- **Suppression des fenêtres console enfants** — les appels `subprocess` utilisent `CREATE_NO_WINDOW` pour éviter tout flash de console pendant les étapes winget / PowerShell.
- **Table complète des codes de sortie winget** (37 codes) avec conversion int32 signé.
- **Vérification d'intégrité des téléchargements** — fonction `verify_authenticode` (`Get-AuthenticodeSignature`, disponible sur toutes les versions de Windows) appelée avant exécution sur chaque installeur en repli (Firefox/Chrome, Adobe, Intel DSA, NVIDIA Driver, NVIDIA App), en plus d'un contrôle de taille minimale. Le binaire est rejeté avant exécution si la signature est absente ou non valide ; en cas d'échec sur Intel DSA, seule cette application est ignorée sans interrompre le reste de l'étape 6.
- **Détection GPU NVIDIA robuste** — la détection s'appuie sur l'ID fabricant PCI `VEN_10DE` (présent dès l'image, avant même l'installation du pilote, là où un filtre sur le nom échouerait car la carte apparaît en « 3D Video Controller »). La version du pilote installé est lue via `nvidia-smi` (repli CIM), et une table `NVIDIA_DEV_NAMES` fournit le nom commercial des GPU Ada laptop quand CIM renvoie un nom générique. Un log de diagnostic liste les périphériques `VEN_10DE` présents.
- **Renommage & raccourci via PowerShell** — le renommage machine (`Set-ItemProperty` + WMI `Rename()`, nom via `$env:PRISM_NEW_NAME`) et la création de raccourci (`WScript.Shell`) passent par PowerShell ; `Rename-Computer` est explicitement évité pour ne pas fermer la GUI.
- **Appels centralisés** — helper unique `run_cmd` (forçage UTF-8, `CREATE_NO_WINDOW`, `env_extra`) et `_ps_encoded` (scripts PowerShell en Base64 UTF-16LE via `-EncodedCommand`, avec `$ProgressPreference='SilentlyContinue'` pour ne pas polluer la sortie des cmdlets CIM).
- **Validation du nom d'ordinateur** par expression régulière conforme NetBIOS (`[A-Za-z0-9-]{1,15}`), dupliquée volontairement entre la validation GUI (`SetupDialog._launch`) et le thread d'exécution (`step4_computer_name`) — les deux doivent rester identiques — comme garde anti-injection avant le renommage.
- **Journal protégé** — écrit dans `%PROGRAMDATA%\LGS\Logs` avec ACL restreintes (`icacls` : Administrateurs + SYSTEM), raccourci d'accès déposé sur le bureau, repli silencieux vers le bureau si l'emplacement est inaccessible. La clé de récupération BitLocker n'est jamais journalisée.
- **Timeouts adaptatifs** par commande (30 min par défaut, 2 h pour Windows Update).
- **Protection anti-veille** pendant le provisionnement et **mécanisme de pause** thread-safe.
- **Assets Base64** — fichiers embarqués (PDF de procédures, DOCX, raccourcis `.url`). Un chantier d'optimisation du bloc d'assets (~66 000 lignes) est en cours : externalisation vers un dossier compagnon ou consolidation en archive unique.

**Outil compagnon**

- **PRISM Asset Updater** (PS1 + EXE via ps2exe) — interface glisser-déposer permettant à du personnel non technique de remplacer les fichiers Base64 embarqués sans connaissances en développement.

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

PRISM effectue des opérations à privilèges élevés (exécution en administrateur, écriture registre, chiffrement BitLocker, jonction d'identité, installation logicielle). À ce titre, l'engagement avec l'équipe de sécurité IBM fait partie intégrante du cycle de vie et non d'une étape finale.

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
- Confidentialité du journal détaillé (emplacement `%PROGRAMDATA%` à ACL restreintes)
- Intégrité des assets embarqués et absence de dépendances réseau non maîtrisées
- Journalisation (garantie de non-fuite de secrets dans les logs)
- Signature numérique du livrable

> **À compléter** — registre des interactions avec l'équipe de sécurité IBM.

| Date | Sujet / domaine | Interlocuteur(s) | Recommandation | Suite donnée | Statut |
|---|---|---|---|---|---|
| | | | | | |
| | | | | | |

---

## 6. Obtention des validations obligatoires du CISO IBM

La mise en production de PRISM est conditionnée à l'obtention des validations obligatoires côté CISO IBM. Cette section suit l'état de ces validations dans le cadre du plan de validation formelle en 10 phases demandé par la hiérarchie.

**Plan de validation formelle en 10 phases**

| Phase | Domaine | Livrable | Statut |
|---|---|---|---|
| 1 | Fondation / journalisation | PS1 dédié | Construit |
| 2 | Renommage machine / config régionale (fr-CA, ISO, 24 h) | PS1 dédié | Construit |
| 3 | Jonction Entra ID (Autopilot / PPKG / manuel) | PS1 dédié | Construit |
| 4 | Installation des applications standard (8 apps winget + repli local) | PS1 dédié | Construit |
| 5 | Agents AV / EDR / RMM / MDM | | À faire |
| 6 | BitLocker + sauvegarde de la clé | | À faire |
| 7 | Réseau / proxy / certificats / VPN | | À faire |
| 8 | Tests post-installation | | À faire |
| 9 | Gestion d'erreurs robuste | | À faire |
| 10 | Signature numérique conforme IBM | | À faire |

**Validations obligatoires du CISO — suivi**

> **À compléter** — ne renseigner « Obtenue » qu'après réception de l'approbation formelle et signée du CISO. Ce tableau constitue la trace de conformité.

| Validation requise | Prérequis | Statut | Date | Référence / approbateur |
|---|---|---|---|---|
| Revue d'architecture de sécurité | Phases 1–4 documentées | En attente | | |
| Revue de la gestion des secrets (clé BitLocker) | Phase 6 complétée | En attente | | |
| Revue du mécanisme d'élévation | Documentation technique | En attente | | |
| Signature numérique conforme IBM | Phase 10 | En attente | | |
| **Approbation finale CISO pour mise en production** | Toutes les validations ci-dessus | **En attente** | | |

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
  python "C:\chemin\complet\LGS_Install_Script_PRISM_12_.py"
  ```

**Dépannage**

- Si rien ne s'affiche après le UAC : vérifier que PyQt6 est installé pour le bon interpréteur (`py -0p`, `assoc .py`, `ftype Python.File`).
- Journal de crash automatique : `%TEMP%\PRISM_crash.log` (ouvert automatiquement en cas d'erreur).
- Journal détaillé d'installation : `%PROGRAMDATA%\LGS\Logs\LGS_Log_Detaile_<nom>_<horodatage>.txt` (accès Administrateurs + SYSTEM ; un raccourci est déposé sur le bureau). Repli sur le bureau si l'emplacement est inaccessible.
- Paquets compagnons attendus dans `C:\LGS_Deploy` : `ODT\setup.exe` (Microsoft 365 Apps) et `CommercialVantage\` (Lenovo Vantage). Leur absence n'interrompt pas le provisionnement mais l'application concernée est ignorée.
- Attention : si l'élévation utilise un compte administrateur différent, le journal de crash est écrit dans le `%TEMP%` de ce compte.

---

## Historique des versions

- **Lignée v3.x → PRISM 7/8** (PowerShell / WinForms) — sourcing SharePoint/OneDrive, puis bascule vers l'embarquement Base64, GUI thème sombre + branding LGS, détection GPU NVIDIA, Adobe Reader dynamique, import des favoris Edge, automatisation Windows Update, détection langue française, flux « Nouvelle embauche ».
- **v3.4 (PowerShell)** — dernière version WinForms d'origine (~2 553 lignes) avant conversion Python.
- **PRISM 8** — ajout de l'étape 10 (BitLocker → Entra ID), grille GUI à 6 rangées, correctif de l'icône (LOGO_B64), validation du nom NetBIOS, timeouts adaptatifs, log incrémental.
- **PRISM 12** (courant, Python / PyQt6, version applicative 3.8.x) — déploiement winget, sauvegarde BitLocker/Entra ID, correctifs UTF-8, élévation UAC durcie (chemin absolu + arguments quotés), relance via `pythonw.exe`, suppression des fenêtres console enfants (`CREATE_NO_WINDOW`).
  - **v3.8** — première itération du durcissement : vérification Authenticode des installeurs en repli, installation applicative pilotée par le catalogue `LOGICIELS`.
  - **v3.8.1 (courant)** — durcissement sécurité et robustesse matérielle :
    - **Sécurité** — `verify_authenticode` bascule sur `Get-AuthenticodeSignature` (au lieu de `WinVerifyTrust`/ctypes), appliquée avant exécution à Firefox/Chrome, Adobe, Intel DSA, NVIDIA Driver et NVIDIA App (contrôle de taille + signature ; l'empreinte SHA-256 est retirée). Politique PowerShell passée de `Bypass` à `RemoteSigned`. Renommage machine sécurisé par variable d'environnement `$env:PRISM_NEW_NAME` (anti-injection). Journal déplacé dans `%PROGRAMDATA%\LGS\Logs` avec ACL restreintes (`icacls`) et raccourci bureau.
    - **Détection GPU NVIDIA réécrite** — clé sur l'ID PCI `VEN_10DE` (fonctionne sur image fraîche sans pilote), version pilote via `nvidia-smi`, table `NVIDIA_DEV_NAMES` pour les GPU Ada laptop, commandes PowerShell en Base64 (`_ps_encoded` / `-EncodedCommand`), logs de diagnostic.
    - **Nouvelles installations** — pilote NVIDIA + NVIDIA App (Entreprise), Lenovo Commercial Vantage, et Microsoft 365 Apps via l'Office Deployment Tool (dossier compagnon `C:\LGS_Deploy`).
    - **Revirement d'architecture** — le raccourci `CAT.lnk` (COM `WScript.Shell`) et le renommage machine (`Set-ItemProperty` + WMI `Rename()`) sont désormais réalisés via PowerShell plutôt qu'en API natives ctypes ; `Rename-Computer` reste évité. Helper d'appels unifié `run_cmd`.
    - **Qualité** — `urlretrieve` (dépréciée) remplacée par `urlopen` + `copyfileobj` (Adobe).
