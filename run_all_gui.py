#!/usr/bin/env python3
"""
run_all_gui.py - Lanceur graphique du POC GreenMove Edge Telematics.

Ouvre une fenetre facon macOS (trois boutons rouge, jaune, vert) et execute
le script existant run_all.py EN DIRECT, en affichant sa vraie sortie colorisee.
Aucune valeur n'est recopiee : tout provient de l'execution reelle du POC.

Ce fichier n'enveloppe que les scripts existants (run_all.py -> main.py + run_tests.py).
Il ne modifie aucune logique metier.

Dependance : PySide6 (pip install PySide6).
Lancement : python3 run_all_gui.py
Repli terminal si PySide6 est absent : python3 run_all.py
"""

import os
import re
import sys
import time

BASE = os.path.dirname(os.path.abspath(__file__))

# Temporisation entre chaque ligne affichee, en secondes.
# Donne un effet "live" lisible pour la captation video (au lieu d'un affichage
# instantane). Mettre 0.0 pour desactiver, 0.12 pour un rythme lent et demonstratif.
LINE_DELAY_S = 0.06

try:
    from PySide6.QtCore import QObject, QPoint, Qt, QThread, Signal
    from PySide6.QtGui import QFont, QTextCursor
    from PySide6.QtWidgets import (
        QApplication, QFrame, QHBoxLayout, QLabel, QMainWindow,
        QPushButton, QTextEdit, QVBoxLayout, QWidget,
    )
except ImportError:
    print("PySide6 n'est pas installe. Repli sur le terminal :\n")
    import subprocess
    sys.exit(subprocess.run([sys.executable, os.path.join(BASE, "run_all.py")]).returncode)


# --- Traduction des couleurs ANSI (colorama) du POC en HTML pour l'affichage ---
ANSI_TO_HTML = {
    "30": "#89929E", "31": "#FF4D4D", "32": "#35D04F", "33": "#F4C430",
    "34": "#65BDF7", "35": "#C98BDB", "36": "#5BC8C8", "37": "#D5D9DE",
    "90": "#89929E", "91": "#FF6B6B", "92": "#5BE585", "93": "#FFD966",
    "94": "#7FC9FF", "95": "#D6A2E8", "96": "#7FE0E0", "97": "#FFFFFF",
}
ANSI_RE = re.compile(r"\x1b\[([0-9;]*)m")


def ansi_to_html(text: str) -> str:
    """Convertit une ligne colorisee ANSI en span HTML, sans perte de contenu."""
    text = (text.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;"))
    out, open_span, i = [], False, 0
    for m in ANSI_RE.finditer(text):
        out.append(text[i:m.start()])
        i = m.end()
        codes = [c for c in m.group(1).split(";") if c]
        if not codes or "0" in codes:
            if open_span:
                out.append("</span>"); open_span = False
            continue
        color = next((ANSI_TO_HTML[c] for c in codes if c in ANSI_TO_HTML), None)
        bold = "1" in codes
        if color or bold:
            if open_span:
                out.append("</span>")
            style = (f"color:{color};" if color else "") + ("font-weight:bold;" if bold else "")
            out.append(f'<span style="{style}">'); open_span = True
    out.append(text[i:])
    if open_span:
        out.append("</span>")
    return "".join(out)


class Worker(QObject):
    """Execute run_all.py dans un thread et emet chaque ligne de sortie."""
    line = Signal(str)
    done = Signal(int)

    def run(self) -> None:
        import subprocess
        env = dict(os.environ)
        env["PYTHONUNBUFFERED"] = "1"
        env["PYTHONIOENCODING"] = "utf-8"
        env["FORCE_COLOR"] = "1"  # pousse colorama a coloriser meme hors TTY
        proc = subprocess.Popen(
            [sys.executable, os.path.join(BASE, "run_all.py")],
            cwd=BASE, stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
            text=True, encoding="utf-8", errors="replace", env=env, bufsize=1,
        )
        for raw in proc.stdout:
            self.line.emit(raw.rstrip("\n"))
            if LINE_DELAY_S > 0:
                time.sleep(LINE_DELAY_S)  # rythme "live" pour la captation video
        proc.wait()
        self.done.emit(proc.returncode)


class TitleBar(QFrame):
    def __init__(self, window: QMainWindow, on_rerun) -> None:
        super().__init__()
        self.window = window
        self.on_rerun = on_rerun
        self.drag_position = QPoint()
        self.setFixedHeight(42)
        self.setObjectName("titleBar")

        layout = QHBoxLayout(self)
        layout.setContentsMargins(14, 0, 12, 0)
        layout.setSpacing(8)

        # Trois boutons macOS : fermer / reduire / agrandir
        self.close_button = self._button("#FF5F57")
        self.minimize_button = self._button("#FEBC2E")
        self.maximize_button = self._button("#28C840")
        self.close_button.clicked.connect(window.close)
        self.minimize_button.clicked.connect(window.showMinimized)
        self.maximize_button.clicked.connect(self._toggle_max)

        title = QLabel("greenmove-edge-poc — python3 run_all.py")
        title.setObjectName("windowTitle")

        # Petit bouton rejouer, discret, a droite
        self.rerun = QPushButton("Rejouer")
        self.rerun.setObjectName("rerun")
        self.rerun.setCursor(Qt.CursorShape.PointingHandCursor)
        self.rerun.clicked.connect(self.on_rerun)

        layout.addWidget(self.close_button)
        layout.addWidget(self.minimize_button)
        layout.addWidget(self.maximize_button)
        layout.addSpacing(14)
        layout.addStretch()
        layout.addWidget(title)
        layout.addStretch()
        layout.addWidget(self.rerun)

    def _button(self, color: str) -> QPushButton:
        b = QPushButton()
        b.setFixedSize(14, 14)
        b.setCursor(Qt.CursorShape.PointingHandCursor)
        b.setStyleSheet(
            f"QPushButton {{ background-color:{color}; border:none; border-radius:7px; }}"
            f"QPushButton:hover {{ border:1px solid rgba(0,0,0,90); }}"
        )
        return b

    def _toggle_max(self) -> None:
        self.window.showNormal() if self.window.isMaximized() else self.window.showMaximized()

    def mousePressEvent(self, e) -> None:
        if e.button() == Qt.MouseButton.LeftButton:
            self.drag_position = e.globalPosition().toPoint() - self.window.frameGeometry().topLeft()
            e.accept()

    def mouseMoveEvent(self, e) -> None:
        if e.buttons() & Qt.MouseButton.LeftButton and not self.window.isMaximized():
            self.window.move(e.globalPosition().toPoint() - self.drag_position)
            e.accept()

    def mouseDoubleClickEvent(self, e) -> None:
        if e.button() == Qt.MouseButton.LeftButton:
            self._toggle_max()


class TerminalWindow(QMainWindow):
    def __init__(self) -> None:
        super().__init__()
        self.setWindowFlags(Qt.WindowType.FramelessWindowHint)
        self.setWindowTitle("GML Edge Telematics")
        self.resize(1250, 760)

        container = QWidget(); container.setObjectName("container")
        layout = QVBoxLayout(container)
        layout.setContentsMargins(1, 1, 1, 1); layout.setSpacing(0)

        self.title_bar = TitleBar(self, self.start_run)
        self.terminal = QTextEdit()
        self.terminal.setReadOnly(True)
        self.terminal.setObjectName("terminal")
        self.terminal.setFont(QFont("Cascadia Mono", 12))

        layout.addWidget(self.title_bar)
        layout.addWidget(self.terminal)
        self.setCentralWidget(container)
        self._apply_style()

        self._thread = None
        self._worker = None
        self.start_run()

    def _apply_style(self) -> None:
        self.setStyleSheet(
            """
            QWidget#container { background-color:#080D12; border:1px solid #274766; border-radius:8px; }
            QFrame#titleBar { background-color:#17202A; border-top-left-radius:8px; border-top-right-radius:8px; }
            QLabel#windowTitle { color:#9CA3AF; font-family:"Cascadia Mono"; font-size:13px; }
            QPushButton#rerun { color:#9CA3AF; background:#22303C; border:none; border-radius:6px;
                                padding:4px 12px; font-size:12px; }
            QPushButton#rerun:hover { color:#FFFFFF; background:#2C3E4C; }
            QTextEdit#terminal { background-color:#080D12; color:#D5D9DE; border:none;
                                 padding:16px; selection-background-color:#264F78; }
            """
        )

    def start_run(self) -> None:
        if self._thread and self._thread.isRunning():
            return
        self.terminal.clear()
        self._append_html('<span style="color:#65BDF7;">PS C:\\greenmove-edge-poc&gt; python3 run_all.py</span>')
        self._thread = QThread()
        self._worker = Worker()
        self._worker.moveToThread(self._thread)
        self._thread.started.connect(self._worker.run)
        self._worker.line.connect(self._on_line)
        self._worker.done.connect(self._on_done)
        self._worker.done.connect(self._thread.quit)
        self._thread.start()

    @staticmethod
    def _line_color(text: str) -> str | None:
        """Couleur de repli basee sur le prefixe, si colorama n'a pas emis d'ANSI.

        colorama retire les codes ANSI quand la sortie est un pipe (cas ici,
        car on capture stdout). On recolorise donc a partir du contenu, ce qui
        reste fidele a la semantique du POC (vert=ok, jaune=prealerte, rouge=alerte).
        """
        t = text.strip()
        if t.startswith("[ALERT") or t.startswith("[HARSH") or "ERREUR" in t or "a echoue" in t or "a échoué" in t:
            return "#FF4D4D"
        if t.startswith("[PRE-ALERT") or t.startswith("[PREALERT") or t.startswith("[BOUNDARY"):
            return "#F4C430"
        if t.startswith("[ZFE]") or t.startswith("[OK]") or t.startswith("[PASS]") or "tests passes" in t or "termine (code 0)" in t or "score =" in t:
            return "#35D04F"
        if t.startswith("[SAFETY]") or t.startswith("ZFE") or t.startswith("Safety") or t.startswith("Fichiers"):
            return "#D5D9DE"
        if set(t) <= set("= ") and t:      # lignes de separateurs ====
            return "#65BDF7"
        if t.startswith("---") or t.startswith("point ") or "attendu=" in t or "rejet O(1)" in t:
            return "#89929E"
        return None

    def _on_line(self, text: str) -> None:
        html = ansi_to_html(text)
        # Si aucun span couleur n'a ete produit (ANSI absent), on recolorise par prefixe.
        if "<span" not in html:
            color = self._line_color(text)
            if color:
                safe = text.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")
                bold = text.strip().startswith(("[ALERT", "[HARSH", "[PRE-ALERT", "[OK]")) or "tests passes" in text
                style = f"color:{color};" + ("font-weight:bold;" if bold else "")
                html = f'<span style="{style}">{safe}</span>'
        self._append_html(html or "&nbsp;")

    def _on_done(self, code: int) -> None:
        color = "#35D04F" if code == 0 else "#FF4D4D"
        msg = "run_all.py termine (code 0)" if code == 0 else f"run_all.py a echoue (code {code})"
        self._append_html(f'<span style="color:{color};font-weight:bold;">{msg}</span>')

    def _append_html(self, html: str) -> None:
        cursor = self.terminal.textCursor()
        cursor.movePosition(QTextCursor.MoveOperation.End)
        # Ouvrir un nouveau bloc (= nouveau paragraphe) sauf pour la toute
        # premiere ligne, afin que chaque ligne reste sur sa propre ligne.
        if not self.terminal.document().isEmpty():
            cursor.insertBlock()
        cursor.insertHtml(
            f'<span style="font-family:Cascadia Mono; font-size:13px; white-space:pre;">{html}</span>'
        )
        self.terminal.setTextCursor(cursor)
        self.terminal.ensureCursorVisible()


if __name__ == "__main__":
    app = QApplication(sys.argv)
    window = TerminalWindow()
    window.show()
    sys.exit(app.exec())
