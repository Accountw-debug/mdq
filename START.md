# START – vom Zip zum ersten Claude-Code-Prompt (ca. 20 Minuten)

## 1. GitHub (im Browser, 2 Minuten)
- github.com → New repository → Name `mdq` → **Private** → *kein* README, *keine* .gitignore, *keine* Lizenz → Create.
- Die angezeigte URL merken: `https://github.com/<dein-user>/mdq.git` (oder SSH, wenn du das bei Bondio schon nutzt).

## 2. In WSL (Ubuntu-Terminal)
```bash
mkdir -p ~/projects && cd ~/projects
# Zip aus dem Windows-Download-Ordner holen (Benutzername anpassen):
cp /mnt/c/Users/<windows-user>/Downloads/mdq-starter.zip .
unzip mdq-starter.zip && cd mdq

git init -b main
git add .
git commit -m "Starter: Konzept, Schema, Regeln, Mapping, Wörterbücher, Beispiel-Findings"
git remote add origin https://github.com/<dein-user>/mdq.git
git push -u origin main
```
Falls `git push` nach Login fragt und du noch nichts eingerichtet hast: `gh auth login` (GitHub CLI) oder SSH-Key – so wie bei Bondio.

## 3. Werkzeuge (einmalig)
```bash
# uv (falls nicht vorhanden)
curl -LsSf https://astral.sh/uv/install.sh | sh
exec $SHELL
uv --version

# Claude Code: falls noch nicht installiert, Installer aus der Setup-Doku ausführen
claude --version

# Abhängigkeiten
uv sync
```

## 4. Alias (optional, spart jeden Tag 20 Sekunden)
```bash
echo "alias mdq='cd ~/projects/mdq && claude'" >> ~/.bashrc && source ~/.bashrc
```

## 5. Erste Session
```bash
cd ~/projects/mdq
claude
```
Erster Prompt (kopieren):

> Lies CLAUDE.md, docs/CONCEPT.md, docs/GLOSSARY.md, docs/DECISIONS.md und docs/specs/SPRINT-1.md vollständig. Fasse mir in 10 Zeilen zusammen, was das Produkt ist und welche Regeln für dich gelten. Dann schlag mir einen Plan für Aufgabe 1 (Projekt-Bootstrap) aus SPRINT-1.md vor – nur den Plan, noch keine Änderungen. Warte auf meine Freigabe.

Danach: Aufgabe für Aufgabe durch SPRINT-1.md. Nach jeder Aufgabe muss Claude Code
`uv run pytest` zeigen und committen. Am Ende der Session: `docs/SESSION_LOG.md`.

## Was du parallel fachlich machst
- `logic/examples/findings/`: 24 weitere Findings nach dem Muster der sechs vorhandenen (Liste im README dort).
- `logic/rules/CATALOG.md`: offene Fragen unten beantworten, 10 Regeln auf Status `spec` bringen.
- `docs/extraction/SAP-ECC-EXTRACTION.md`: gegenlesen mit deiner SAP-Brille.
