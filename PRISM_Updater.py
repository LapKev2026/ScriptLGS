#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
PRISM Updater — Outil de mise à jour des fichiers embarqués
Glissez-déposez vos nouveaux fichiers et cliquez sur Appliquer.
© Groupe LGS — une Société IBM
"""

import sys
import os
import re
import base64
import shutil
from pathlib import Path
from datetime import datetime

from PyQt6.QtWidgets import (
    QApplication, QMainWindow, QWidget, QVBoxLayout, QHBoxLayout,
    QLabel, QPushButton, QFrame, QScrollArea, QFileDialog,
    QMessageBox, QProgressBar, QTextEdit
)
from PyQt6.QtCore import Qt, QThread, pyqtSignal, QMimeData
from PyQt6.QtGui import QFont, QColor, QPalette, QDragEnterEvent, QDropEvent


# ─── Palette LGS ─────────────────────────────────────────────────────────────
DARK_BG    = "#1e1e2e"
CARD_BG    = "#2a2a3e"
ACCENT     = "#0066cc"
ACCENT_HOV = "#0055aa"
GREEN      = "#22c55e"
ORANGE     = "#f59e0b"
RED        = "#ef4444"
TEXT       = "#e2e8f0"
MUTED      = "#94a3b8"
BORDER     = "#3f3f5a"


# ─── Constante : marqueur de début/fin du bloc FICHIERS_EMBARQUES ─────────────
MARKER_START = "FICHIERS_EMBARQUES = {"
MARKER_END   = "}\n\n# ─── BASE64 DU LOGO LGS"


# ─── Widget Drop Zone ─────────────────────────────────────────────────────────
class DropZone(QFrame):
    """Zone de glisser-déposer pour les fichiers à intégrer."""
    files_dropped = pyqtSignal(list)

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setAcceptDrops(True)
        self.setMinimumHeight(130)
        self._build_ui()
        self._set_style(active=False)

    def _build_ui(self):
        layout = QVBoxLayout(self)
        layout.setAlignment(Qt.AlignmentFlag.AlignCenter)

        icon = QLabel("📂")
        icon.setAlignment(Qt.AlignmentFlag.AlignCenter)
        icon.setFont(QFont("Segoe UI", 32))

        self.hint = QLabel("Glissez vos fichiers ici\nou cliquez pour parcourir")
        self.hint.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.hint.setFont(QFont("Segoe UI", 11))
        self.hint.setStyleSheet(f"color: {MUTED};")

        layout.addWidget(icon)
        layout.addWidget(self.hint)
        self.setCursor(Qt.CursorShape.PointingHandCursor)

    def _set_style(self, active: bool):
        border_color = ACCENT if active else BORDER
        self.setStyleSheet(f"""
            DropZone {{
                background-color: {CARD_BG};
                border: 2px dashed {border_color};
                border-radius: 10px;
            }}
        """)

    def mousePressEvent(self, event):
        files, _ = QFileDialog.getOpenFileNames(self, "Choisir des fichiers")
        if files:
            self.files_dropped.emit(files)

    def dragEnterEvent(self, event: QDragEnterEvent):
        if event.mimeData().hasUrls():
            event.acceptProposedAction()
            self._set_style(active=True)

    def dragLeaveEvent(self, event):
        self._set_style(active=False)

    def dropEvent(self, event: QDropEvent):
        self._set_style(active=False)
        paths = [u.toLocalFile() for u in event.mimeData().urls() if u.isLocalFile()]
        if paths:
            self.files_dropped.emit(paths)


# ─── Carte fichier ────────────────────────────────────────────────────────────
class FileCard(QFrame):
    removed = pyqtSignal(str)  # émet le chemin du fichier

    def __init__(self, filepath: str, is_known: bool, parent=None):
        super().__init__(parent)
        self.filepath = filepath
        self.filename = Path(filepath).name
        self.is_known = is_known
        self._build_ui()

    def _build_ui(self):
        layout = QHBoxLayout(self)
        layout.setContentsMargins(10, 6, 10, 6)

        # Statut
        if self.is_known:
            status_text = "✔ Fichier reconnu — sera mis à jour"
            status_color = GREEN
        else:
            status_text = "⚠ Fichier non reconnu — sera ajouté"
            status_color = ORANGE

        name_lbl = QLabel(f"<b>{self.filename}</b>")
        name_lbl.setStyleSheet(f"color: {TEXT};")
        name_lbl.setFont(QFont("Segoe UI", 10))

        status_lbl = QLabel(status_text)
        status_lbl.setStyleSheet(f"color: {status_color}; font-size: 9pt;")

        info_col = QVBoxLayout()
        info_col.setSpacing(2)
        info_col.addWidget(name_lbl)
        info_col.addWidget(status_lbl)

        remove_btn = QPushButton("✕")
        remove_btn.setFixedSize(28, 28)
        remove_btn.setStyleSheet(f"""
            QPushButton {{
                background: transparent;
                color: {MUTED};
                border: none;
                font-size: 14px;
                border-radius: 4px;
            }}
            QPushButton:hover {{
                color: {RED};
                background: rgba(239,68,68,0.15);
            }}
        """)
        remove_btn.clicked.connect(lambda: self.removed.emit(self.filepath))

        layout.addLayout(info_col, stretch=1)
        layout.addWidget(remove_btn)

        self.setStyleSheet(f"""
            FileCard {{
                background: {DARK_BG};
                border: 1px solid {BORDER};
                border-radius: 8px;
            }}
        """)


# ─── Thread de mise à jour ────────────────────────────────────────────────────
class UpdateWorker(QThread):
    progress   = pyqtSignal(int, str)   # (pourcentage, message)
    finished   = pyqtSignal(bool, str)  # (succès, message_final)

    def __init__(self, script_path: str, new_files: list[str]):
        super().__init__()
        self.script_path = script_path
        self.new_files   = new_files

    def run(self):
        try:
            self._do_update()
        except Exception as exc:
            self.finished.emit(False, f"Erreur inattendue : {exc}")

    def _do_update(self):
        script_path = Path(self.script_path)

        # 1 — Lire le script source
        self.progress.emit(5, "Lecture du script source…")
        source = script_path.read_text(encoding="utf-8-sig")

        # 2 — Localiser le bloc FICHIERS_EMBARQUES
        self.progress.emit(15, "Analyse du bloc FICHIERS_EMBARQUES…")
        start_idx = source.find(MARKER_START)
        end_idx   = source.find(MARKER_END, start_idx)
        if start_idx == -1 or end_idx == -1:
            self.finished.emit(False, "Impossible de localiser le bloc FICHIERS_EMBARQUES dans le script.")
            return

        # 3 — Parser les clés existantes
        existing_block = source[start_idx:end_idx + 1]
        existing_keys  = set(re.findall(r'"([^"]+)":\s*\(', existing_block))
        self.progress.emit(25, f"{len(existing_keys)} fichier(s) existant(s) détectés.")

        # 4 — Encoder chaque nouveau fichier
        entries = {}
        total = len(self.new_files)
        for i, fp in enumerate(self.new_files):
            pct = 30 + int((i / total) * 40)
            name = Path(fp).name
            self.progress.emit(pct, f"Encodage : {name}")
            raw_b64 = base64.b64encode(Path(fp).read_bytes()).decode("ascii")
            # Découper en lignes de 64 caractères pour la lisibilité
            chunks = [raw_b64[j:j+64] for j in range(0, len(raw_b64), 64)]
            entries[name] = chunks

        # 5 — Reconstruire le bloc
        self.progress.emit(72, "Reconstruction du bloc embarqué…")
        new_block_lines = [MARKER_START + "\n"]

        # Conserver les fichiers existants NON remplacés
        # On reparse le bloc existant pour les conserver
        key_pattern = re.compile(r'    "([^"]+)": \(\n(.*?)\n    \),', re.DOTALL)
        existing_entries: dict[str, str] = {}
        for m in key_pattern.finditer(existing_block):
            existing_entries[m.group(1)] = m.group(2)

        # Mettre à jour / ajouter
        for name, chunks in entries.items():
            existing_entries[name] = "\n".join(f'        "{c}"' for c in chunks)

        # Réécrire toutes les entrées dans l'ordre alphabétique
        for key in sorted(existing_entries.keys()):
            val = existing_entries[key]
            new_block_lines.append(f'    "{key}": (\n{val}\n    ),\n')

        new_block_lines.append("}")
        new_block = "".join(new_block_lines)

        # 6 — Backup du fichier original
        self.progress.emit(80, "Sauvegarde de l'original…")
        ts = datetime.now().strftime("%Y%m%d_%H%M%S")
        backup_path = script_path.with_name(f"{script_path.stem}_backup_{ts}{script_path.suffix}")
        shutil.copy2(script_path, backup_path)

        # 7 — Écrire le nouveau script
        self.progress.emit(90, "Écriture du script mis à jour…")
        new_source = source[:start_idx] + new_block + source[end_idx + 1:]
        script_path.write_text(new_source, encoding="utf-8-sig")

        self.progress.emit(100, "Terminé !")
        updated = [n for n in entries if n in existing_keys]
        added   = [n for n in entries if n not in existing_keys]

        lines = []
        if updated:
            lines.append(f"✔ Mis à jour ({len(updated)}) : " + ", ".join(updated))
        if added:
            lines.append(f"+ Ajoutés   ({len(added)}) : " + ", ".join(added))
        lines.append(f"\nBackup créé : {backup_path.name}")
        self.finished.emit(True, "\n".join(lines))


# ─── Fenêtre principale ───────────────────────────────────────────────────────
class PRISMUpdater(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("PRISM Updater — Mise à jour des fichiers embarqués")
        self.setMinimumSize(720, 660)
        self.pending_files: dict[str, bool] = {}   # chemin → is_known
        self.script_path: str = ""
        self.existing_keys: set[str] = set()
        self._build_ui()
        self._apply_theme()

    # ── Construction UI ───────────────────────────────────────────────────────
    def _build_ui(self):
        central = QWidget()
        self.setCentralWidget(central)
        root = QVBoxLayout(central)
        root.setContentsMargins(24, 24, 24, 24)
        root.setSpacing(16)

        # Titre
        title = QLabel("PRISM Updater")
        title.setFont(QFont("Segoe UI", 18, QFont.Weight.Bold))
        title.setStyleSheet(f"color: {TEXT};")
        sub   = QLabel("Mettez à jour les fichiers embarqués dans le script PRISM sans toucher au code.")
        sub.setStyleSheet(f"color: {MUTED}; font-size: 10pt;")
        root.addWidget(title)
        root.addWidget(sub)

        sep = QFrame(); sep.setFrameShape(QFrame.Shape.HLine)
        sep.setStyleSheet(f"color: {BORDER};")
        root.addWidget(sep)

        # ── Sélection du script source ────────────────────────────────────────
        script_row = QHBoxLayout()
        self.script_lbl = QLabel("Aucun script sélectionné")
        self.script_lbl.setStyleSheet(f"color: {MUTED}; font-size: 9pt;")
        choose_btn = QPushButton("📄  Choisir le script PRISM (.py)")
        choose_btn.setFixedHeight(36)
        choose_btn.clicked.connect(self._pick_script)
        choose_btn.setStyleSheet(self._btn_style(secondary=True))
        script_row.addWidget(self.script_lbl, stretch=1)
        script_row.addWidget(choose_btn)
        root.addLayout(script_row)

        # ── Zone de drop ──────────────────────────────────────────────────────
        drop_lbl = QLabel("Nouveaux fichiers à embarquer")
        drop_lbl.setFont(QFont("Segoe UI", 11, QFont.Weight.Bold))
        drop_lbl.setStyleSheet(f"color: {TEXT};")
        root.addWidget(drop_lbl)

        self.drop_zone = DropZone()
        self.drop_zone.files_dropped.connect(self._add_files)
        root.addWidget(self.drop_zone)

        # ── Liste des fichiers en attente ──────────────────────────────────────
        list_lbl = QLabel("Fichiers en attente")
        list_lbl.setFont(QFont("Segoe UI", 10, QFont.Weight.Bold))
        list_lbl.setStyleSheet(f"color: {MUTED};")
        root.addWidget(list_lbl)

        self.list_scroll = QScrollArea()
        self.list_scroll.setWidgetResizable(True)
        self.list_scroll.setMinimumHeight(140)
        self.list_scroll.setStyleSheet(f"QScrollArea {{ border: none; background: transparent; }}")
        self.list_widget = QWidget()
        self.list_layout = QVBoxLayout(self.list_widget)
        self.list_layout.setContentsMargins(0, 0, 0, 0)
        self.list_layout.setSpacing(6)
        self.list_layout.addStretch()
        self.list_scroll.setWidget(self.list_widget)
        root.addWidget(self.list_scroll)

        self.empty_lbl = QLabel("Aucun fichier ajouté")
        self.empty_lbl.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.empty_lbl.setStyleSheet(f"color: {MUTED}; font-size: 9pt;")
        root.addWidget(self.empty_lbl)

        # ── Barre de progression + log ─────────────────────────────────────────
        self.progress_bar = QProgressBar()
        self.progress_bar.setVisible(False)
        self.progress_bar.setTextVisible(True)
        self.progress_bar.setFixedHeight(20)
        self.progress_bar.setStyleSheet(f"""
            QProgressBar {{
                border: 1px solid {BORDER};
                border-radius: 6px;
                background: {DARK_BG};
                color: {TEXT};
                text-align: center;
                font-size: 9pt;
            }}
            QProgressBar::chunk {{
                background-color: {ACCENT};
                border-radius: 6px;
            }}
        """)
        root.addWidget(self.progress_bar)

        self.log_area = QTextEdit()
        self.log_area.setReadOnly(True)
        self.log_area.setVisible(False)
        self.log_area.setMaximumHeight(100)
        self.log_area.setStyleSheet(f"""
            QTextEdit {{
                background: {DARK_BG};
                color: {MUTED};
                border: 1px solid {BORDER};
                border-radius: 6px;
                font-family: Consolas, monospace;
                font-size: 9pt;
                padding: 6px;
            }}
        """)
        root.addWidget(self.log_area)

        # ── Boutons ───────────────────────────────────────────────────────────
        btn_row = QHBoxLayout()
        self.clear_btn = QPushButton("🗑  Vider la liste")
        self.clear_btn.setFixedHeight(42)
        self.clear_btn.clicked.connect(self._clear_files)
        self.clear_btn.setStyleSheet(self._btn_style(secondary=True))

        self.apply_btn = QPushButton("⚡  Appliquer les mises à jour")
        self.apply_btn.setFixedHeight(42)
        self.apply_btn.setFont(QFont("Segoe UI", 11, QFont.Weight.Bold))
        self.apply_btn.clicked.connect(self._apply)
        self.apply_btn.setStyleSheet(self._btn_style(secondary=False))

        btn_row.addWidget(self.clear_btn)
        btn_row.addStretch()
        btn_row.addWidget(self.apply_btn)
        root.addLayout(btn_row)

    # ── Thème ─────────────────────────────────────────────────────────────────
    def _apply_theme(self):
        self.setStyleSheet(f"""
            QMainWindow, QWidget {{
                background-color: {DARK_BG};
                color: {TEXT};
            }}
            QScrollArea > QWidget > QWidget {{
                background: transparent;
            }}
        """)

    def _btn_style(self, secondary=False) -> str:
        if secondary:
            return f"""
                QPushButton {{
                    background: {CARD_BG};
                    color: {TEXT};
                    border: 1px solid {BORDER};
                    border-radius: 8px;
                    padding: 6px 16px;
                    font-size: 10pt;
                }}
                QPushButton:hover {{
                    background: {BORDER};
                }}
                QPushButton:disabled {{
                    color: {MUTED};
                    background: {DARK_BG};
                }}
            """
        return f"""
            QPushButton {{
                background: {ACCENT};
                color: white;
                border: none;
                border-radius: 8px;
                padding: 6px 24px;
                font-size: 10pt;
            }}
            QPushButton:hover {{
                background: {ACCENT_HOV};
            }}
            QPushButton:disabled {{
                background: {MUTED};
                color: {DARK_BG};
            }}
        """

    # ── Sélection du script ────────────────────────────────────────────────────
    def _pick_script(self):
        path, _ = QFileDialog.getOpenFileName(
            self, "Sélectionner le script PRISM", "", "Python (*.py)"
        )
        if not path:
            return
        # Vérifier que c'est bien un script PRISM
        try:
            content = Path(path).read_text(encoding="utf-8-sig", errors="replace")
        except Exception as e:
            QMessageBox.critical(self, "Erreur", f"Impossible de lire le fichier :\n{e}")
            return
        if MARKER_START not in content:
            QMessageBox.warning(
                self, "Script non reconnu",
                f"Le fichier sélectionné ne contient pas le marqueur :\n{MARKER_START}\n\n"
                "Assurez-vous de choisir le bon script PRISM."
            )
            return
        self.script_path = path
        short = Path(path).name
        self.script_lbl.setText(f"✔  {short}")
        self.script_lbl.setStyleSheet(f"color: {GREEN}; font-size: 9pt;")
        # Parser les clés existantes pour l'indication visuelle
        start = content.find(MARKER_START)
        end   = content.find(MARKER_END, start)
        block = content[start:end + 1]
        self.existing_keys = set(re.findall(r'"([^"]+)":\s*\(', block))
        # Rafraîchir les cartes déjà présentes
        self._refresh_cards()

    # ── Gestion des fichiers ──────────────────────────────────────────────────
    def _add_files(self, paths: list[str]):
        for p in paths:
            if os.path.isfile(p):
                name = Path(p).name
                is_known = name in self.existing_keys
                self.pending_files[p] = is_known
        self._refresh_ui()

    def _remove_file(self, path: str):
        self.pending_files.pop(path, None)
        self._refresh_ui()

    def _clear_files(self):
        self.pending_files.clear()
        self._refresh_ui()

    def _refresh_cards(self):
        """Recrée les cartes avec les informations is_known à jour."""
        updated = {}
        for path in list(self.pending_files.keys()):
            name = Path(path).name
            updated[path] = name in self.existing_keys
        self.pending_files = updated
        self._refresh_ui()

    def _refresh_ui(self):
        # Vider la liste
        while self.list_layout.count() > 1:  # garder le stretch
            item = self.list_layout.takeAt(0)
            if item.widget():
                item.widget().deleteLater()

        if not self.pending_files:
            self.empty_lbl.setVisible(True)
        else:
            self.empty_lbl.setVisible(False)
            for path, is_known in sorted(self.pending_files.items(), key=lambda x: Path(x[0]).name):
                card = FileCard(path, is_known)
                card.removed.connect(self._remove_file)
                self.list_layout.insertWidget(self.list_layout.count() - 1, card)

    # ── Appliquer ─────────────────────────────────────────────────────────────
    def _apply(self):
        if not self.script_path:
            QMessageBox.warning(self, "Script manquant", "Veuillez d'abord sélectionner le script PRISM.")
            return
        if not self.pending_files:
            QMessageBox.warning(self, "Aucun fichier", "Ajoutez au moins un fichier à mettre à jour.")
            return

        self.apply_btn.setEnabled(False)
        self.clear_btn.setEnabled(False)
        self.progress_bar.setVisible(True)
        self.progress_bar.setValue(0)
        self.log_area.setVisible(True)
        self.log_area.clear()

        self.worker = UpdateWorker(self.script_path, list(self.pending_files.keys()))
        self.worker.progress.connect(self._on_progress)
        self.worker.finished.connect(self._on_finished)
        self.worker.start()

    def _on_progress(self, pct: int, msg: str):
        self.progress_bar.setValue(pct)
        self.progress_bar.setFormat(f"{pct}%  {msg}")
        self.log_area.append(msg)

    def _on_finished(self, success: bool, message: str):
        self.apply_btn.setEnabled(True)
        self.clear_btn.setEnabled(True)
        if success:
            self.progress_bar.setStyleSheet(self.progress_bar.styleSheet().replace(ACCENT, GREEN))
            QMessageBox.information(self, "Mise à jour réussie ✔", message)
            self.pending_files.clear()
            self._refresh_ui()
        else:
            self.progress_bar.setStyleSheet(self.progress_bar.styleSheet().replace(ACCENT, RED))
            QMessageBox.critical(self, "Erreur", message)
        self.log_area.append("\n" + message)


# ─── Point d'entrée ───────────────────────────────────────────────────────────
if __name__ == "__main__":
    app = QApplication(sys.argv)
    app.setStyle("Fusion")
    window = PRISMUpdater()
    window.show()
    sys.exit(app.exec())
