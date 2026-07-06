 # LGS Install Script v3.4 — P.R.I.S.M

> **PowerShell Remote Initialization & System Management**

Script PowerShell permettant d'automatiser la préparation, la configuration et l'installation d'un poste Windows.

---

# Fonctionnalités

- Vérification automatique des privilèges Administrateur
- Interface graphique Windows Forms
- Configuration guidée de l'utilisateur
- Installation automatique de logiciels
- Configuration de Windows
- Déploiement de raccourcis et fichiers
- Journalisation complète des opérations
- Barre de progression
- Gestion des erreurs

---

# Prérequis

- Windows 10 ou Windows 11
- PowerShell 5.1 ou supérieur
- Compte Administrateur

---

# Vérifier la version de PowerShell

Ouvrir PowerShell :

```powershell
$PSVersionTable.PSVersion
```

Résultat attendu :

```text
Major Minor Build Revision
----- ----- ----- --------
5     1
```

---

# Autoriser temporairement l'exécution des scripts

Si PowerShell bloque l'exécution :

```powershell
Set-ExecutionPolicy -Scope Process Bypass
```

ou

```powershell
Set-ExecutionPolicy RemoteSigned -Scope CurrentUser
```

> L'option **Process** ne modifie pas la configuration permanente du système.

---

# Exécution

Ouvrir PowerShell dans le dossier contenant le script.

Exécuter :

```powershell
.\LGS_Install_Script 3.4 (P.R.I.S.M).ps1
```

ou

```powershell
powershell.exe -ExecutionPolicy Bypass -File ".\LGS_Install_Script 3.4 (P.R.I.S.M).ps1"
```

---

# Exécution avec privilèges Administrateur

Le script détecte automatiquement si PowerShell est exécuté en mode Administrateur.

Si ce n'est pas le cas :

- une fenêtre UAC s'ouvre;
- PowerShell est relancé automatiquement avec les droits Administrateur.

---

# Déroulement

Lors de l'exécution :

1. Vérification des privilèges Administrateur
2. Vérification de l'environnement Windows
3. Chargement de l'interface graphique
4. Saisie des informations nécessaires
5. Début de l'installation
6. Configuration automatique du poste
7. Création des raccourcis
8. Nettoyage final
9. Fin de l'installation

---

# Structure du projet

```text
LGS_Install_Script 3.4 (P.R.I.S.M).ps1
README.md
```

---

# Paramètres PowerShell utiles

Afficher la politique d'exécution :

```powershell
Get-ExecutionPolicy
```

Afficher toutes les politiques :

```powershell
Get-ExecutionPolicy -List
```

Modifier temporairement la politique :

```powershell
Set-ExecutionPolicy Bypass -Scope Process
```

---

# Dépannage

## Les scripts sont désactivés

Message :

```text
running scripts is disabled on this system
```

Solution :

```powershell
Set-ExecutionPolicy Bypass -Scope Process
```

ou

```powershell
Set-ExecutionPolicy RemoteSigned -Scope CurrentUser
```

---

## Accès refusé

Exécuter PowerShell en tant qu'Administrateur.

---

## Le script ne démarre pas

Vérifier :

- que le fichier n'est pas bloqué par Windows :

```powershell
Unblock-File ".\LGS_Install_Script 3.4 (P.R.I.S.M).ps1"
```

- que PowerShell est bien en version 5.1 minimum.

---

# Journalisation

Si le script génère un fichier journal, celui-ci permet de :

- suivre toutes les étapes d'installation;
- identifier les erreurs;
- faciliter le dépannage.

---

# Auteur

**LGS Install Script v3.4 — P.R.I.S.M**

PowerShell Remote Initialization & System Management

© Groupe LGS — Une société IBM

---

# Licence

Usage interne uniquement.

Ne pas redistribuer sans autorisation.
