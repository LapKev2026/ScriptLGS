# LGS Install Script v3.4 — P.R.I.S.M

> **PowerShell Remote Initialization & System Management**

Application développée pour automatiser la préparation et la configuration d'un poste Windows.

---

# Fonctionnalités

- Interface graphique développée avec **PyQt6**
- Vérification automatique des privilèges administrateur
- Relance automatique avec élévation (UAC)
- Détection de la version de Windows
- Interface de configuration avant l'exécution
- Déploiement de fichiers embarqués
- Journalisation des opérations
- Automatisation de différentes tâches d'installation et de configuration

---

# Prérequis

- Windows 10 ou Windows 11
- Python 3.11 ou supérieur recommandé
- Compte Administrateur

---

# Installation des dépendances

Ouvrir **PowerShell** ou **Invite de commandes** puis exécuter :

```powershell
pip install PyQt6
```

Si plusieurs versions de Python sont installées :

```powershell
py -m pip install PyQt6
```

---

# Vérifier l'installation

```powershell
python --version
```

ou

```powershell
py --version
```

Vous devriez obtenir une version semblable à :

```
Python 3.11.x
```

---

# Exécution du script

Depuis le dossier contenant le script :

```powershell
python LGS_Install_Script_PRISM_8_.py
```

ou

```powershell
py LGS_Install_Script_PRISM_8_.py
```

---

# Exécution en tant qu'administrateur

Le script vérifie automatiquement s'il possède les privilèges administrateur.

Si ce n'est pas le cas :

- une fenêtre UAC (Contrôle de compte utilisateur) apparaît;
- le script se relance automatiquement avec les droits Administrateur.

Aucune manipulation supplémentaire n'est nécessaire.

---

# Déroulement

Au lancement :

1. Vérification des droits administrateur
2. Détection de la version de Windows
3. Ouverture de la fenêtre de configuration
4. Validation des informations
5. Ouverture de l'interface principale
6. Exécution automatique des différentes tâches

---

# Structure du projet

```text
LGS_Install_Script_PRISM_8_.py
README.md
```

Le script contient également des ressources embarquées (Base64) qui sont extraites automatiquement pendant l'exécution.

---

# Compilation en exécutable (optionnel)

Installer PyInstaller :

```powershell
pip install pyinstaller
```

Créer un exécutable :

```powershell
pyinstaller ^
    --onefile ^
    --windowed ^
    --uac-admin ^
    LGS_Install_Script_PRISM_8_.py
```

Le fichier compilé sera créé dans :

```text
dist\
```

---

# Dépannage

## Module PyQt6 introuvable

```text
ModuleNotFoundError: No module named 'PyQt6'
```

Solution :

```powershell
pip install PyQt6
```

---

## Python n'est pas reconnu

```text
python n'est pas reconnu...
```

Utiliser :

```powershell
py LGS_Install_Script_PRISM_8_.py
```

ou ajouter Python au PATH.

---

## Fenêtre UAC n'apparaît pas

Vérifier que :

- le contrôle de compte utilisateur (UAC) est activé;
- le compte possède les permissions Administrateur.

---

# Auteur

**LGS Install Script v3.4 — P.R.I.S.M**

PowerShell Remote Initialization & System Management

© Groupe LGS — Une société IBM

---

# Licence

Usage interne uniquement.
