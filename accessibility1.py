import requests
from bs4 import BeautifulSoup
from urllib.parse import urljoin, urlparse
import subprocess
import json
import os
import tempfile
from pathlib import Path
from collections import Counter
import matplotlib.pyplot as plt

""" Pfad zu "npx" plattformunabhängig bestimmen. Unter Windows wird "npx.cmd" verwendet,
auf anderen Systemen reicht "npx"."""
if os.name == "nt":
    NPX = "npx.cmd"
else:
    NPX = "npx"

# ------------------------------------------------------------------------------
# Definition von Meldungskategorien und Gewichtungen für die Berechnung des
# Barrierefreiheits‑Scores.  Jede Meldung aus den verschiedenen Tools wird auf
# eine kanonische Form abgebildet (siehe `_canonicalize_message`) und erhält
# einen Schweregrad sowie einen Typ‑Faktor.  Diese Werte bestimmen, wie stark
# sich ein bestimmter Fehler auf den Gesamtpunktestand auswirkt.  Für viele
# Meldungen werden die Standardwerte unten überschrieben, um eine feinere
# Priorisierung zu ermöglichen.

# Liste der möglichen kanonischen Meldungen.  Diese wird verwendet, um das
# `ISSUE_CATEGORIES`‑Dictionary mit Standardwerten zu befüllen.  Wird eine
# Meldung durch `_canonicalize_message` nicht zugeordnet, bleibt der
# Schweregrad auf dem Standardwert `DEFAULT_SEVERITY` und der Typ‑Faktor auf
# `DEFAULT_TYPE_FACTOR`.
CANONICAL_MESSAGES = [
    "images must have alternative text",
    "document should have one main landmark",
    "all page content should be contained by landmarks",
    "document must have a title element",
    "document must have a language attribute",
    "links must have discernible text",
    "form elements must have labels",
    "element requires an accessible name",
    "aria-hidden element must not be focusable",
    "avoid positive tabindex values",
    "frames must not remove focusable content",
    "elements must meet minimum color contrast ratio thresholds",
    "links must be distinguishable without relying on color",
    "interactive elements must have sufficient size",
    "fieldsets must contain a legend element",
    "autocomplete attribute must be valid",
    "lists must only contain allowed children",
    "scrollable region must be focusable",
    "page should contain a level-one heading",
    "aria attributes must be valid",
    "interactive controls must not be nested",
    "page must have a skip link or landmark",
    "table cells must have headers",
    "elements must have unique ids",
    "page must not use timed refresh",
    "page must allow zooming",
    "element has an invalid aria role",
]

# Standardgewichtungen für alle Fehlertypen.  Einzelne Kategorien können diese
# Werte überschreiben.
DEFAULT_SEVERITY = 2
DEFAULT_TYPE_FACTOR = 1.0

# Das Dictionary `ISSUE_CATEGORIES` enthält für jede kanonische Meldung den
# Schweregrad, den Typ‑Faktor und eine kurze, deutschsprachige Bezeichnung.
# Diese Werte werden verwendet, um Punktabzüge zu berechnen.  Für Meldungen
# ohne spezifischen Eintrag gelten die oben definierten Standardwerte.
ISSUE_CATEGORIES = {
    msg: {"severity": DEFAULT_SEVERITY, "type_factor": DEFAULT_TYPE_FACTOR, "label": msg}
    for msg in CANONICAL_MESSAGES
}

ISSUE_CATEGORIES.update(
    {
        "images must have alternative text": {
            "severity": 4,
            "type_factor": 1.0,
            "label": "Fehlender Alternativtext",
        },
        "elements must meet minimum color contrast ratio thresholds": {
            "severity": 2,
            "type_factor": 1.2,
            "label": "Geringer Farbkontrast",
        },
        "form elements must have labels": {
            "severity": 4,
            "type_factor": 1.5,
            "label": "Unbeschriftetes Formularfeld",
        },
        "links must have discernible text": {
            "severity": 4,
            "type_factor": 1.0,
            "label": "Nicht erkennbare Linktexte",
        },
        "element requires an accessible name": {
            "severity": 4,
            "type_factor": 1.0,
            "label": "Fehlender Accessible Name",
        },
        "document should have one main landmark": {
            "severity": 2,
            "type_factor": 1.2,
            "label": "Fehlende Haupt‑Landmarke",
        },
        "all page content should be contained by landmarks": {
            "severity": 2,
            "type_factor": 1.2,
            "label": "Inhalt außerhalb von Landmarken",
        },
        "document must have a title element": {
            "severity": 2,
            "type_factor": 1.0,
            "label": "Fehlender Seitentitel",
        },
        "document must have a language attribute": {
            "severity": 1,
            "type_factor": 0.8,
            "label": "Fehlendes Sprachattribut",
        },
        "aria-hidden element must not be focusable": {
            "severity": 3,
            "type_factor": 1.2,
            "label": "ARIA‑hidden ist fokussierbar",
        },
        "avoid positive tabindex values": {
            "severity": 2,
            "type_factor": 1.0,
            "label": "Tabindex positiv gesetzt",
        },
        "frames must not remove focusable content": {
            "severity": 4,
            "type_factor": 1.3,
            "label": "Frames entfernen fokussierbare Inhalte",
        },
        "links must be distinguishable without relying on color": {
            "severity": 3,
            "type_factor": 1.2,
            "label": "Links nur durch Farbe unterscheidbar",
        },
        "interactive elements must have sufficient size": {
            "severity": 3,
            "type_factor": 1.5,
            "label": "Kleine interaktive Elemente",
        },
        "fieldsets must contain a legend element": {
            "severity": 2,
            "type_factor": 1.0,
            "label": "Fieldset ohne Legende",
        },
        "autocomplete attribute must be valid": {
            "severity": 1,
            "type_factor": 1.0,
            "label": "Ungültiges Autocomplete‑Attribut",
        },
        "lists must only contain allowed children": {
            "severity": 2,
            "type_factor": 1.0,
            "label": "Liste enthält ungültige Kinder",
        },
        "scrollable region must be focusable": {
            "severity": 2,
            "type_factor": 1.2,
            "label": "Nicht fokussierbarer Scrollbereich",
        },
        "page should contain a level-one heading": {
            "severity": 2,
            "type_factor": 1.0,
            "label": "Kein H1‑Element vorhanden",
        },
        "aria attributes must be valid": {
            "severity": 2,
            "type_factor": 1.1,
            "label": "Ungültiges ARIA‑Attribut",
        },
        "interactive controls must not be nested": {
            "severity": 3,
            "type_factor": 1.2,
            "label": "Verschachtelte interaktive Elemente",
        },
        "page must have a skip link or landmark": {
            "severity": 3,
            "type_factor": 1.0,
            "label": "Kein Skip‑Link vorhanden",
        },
        "table cells must have headers": {
            "severity": 4,
            "type_factor": 1.1,
            "label": "Tabellenzellen ohne Header",
        },
        "elements must have unique ids": {
            "severity": 3,
            "type_factor": 1.2,
            "label": "Nicht eindeutige IDs",
        },
        "page must not use timed refresh": {
            "severity": 3,
            "type_factor": 1.1,
            "label": "Zeitgesteuertes Refresh",
        },
        "page must allow zooming": {
            "severity": 3,
            "type_factor": 1.0,
            "label": "Zoom‑Funktion deaktiviert",
        },
        "element has an invalid aria role": {
            "severity": 2,
            "type_factor": 1.2,
            "label": "Ungültige ARIA‑Rolle",
        },
    }
)

def _check_node_version(min_major=20):
    """Gibt True zurück, wenn die installierte Node.js-Version die Mindestanforderung erfüllt."""
    try:
        result = subprocess.run(["node", "-v"], capture_output=True, text=True)
        if result.returncode != 0:
            print("Node.js konnte nicht gefunden werden. Bitte installieren Sie Node.js.")
            return False
        version = result.stdout.strip().lstrip("v")
        major = int(version.split(".")[0])
        if major < min_major:
            print(
                f"Gefundene Node.js Version {version}."
                f" Bitte aktualisieren Sie Node.js auf Version {min_major} oder neuer."
            )
            return False
    except Exception as exc:
        print(f"Konnte Node.js Version nicht bestimmen: {exc}")
        return False
    return True

def ist_internal_link(base_url, link):
    """Prüft, ob link zur selben Domain gehört wie base_url."""
    base_domain = urlparse(base_url).netloc
    target_domain = urlparse(link).netloc
    return (target_domain == "" or target_domain == base_domain)

def finde_interne_links(start_url):
    """Findet alle internen Links auf der Startseite und gibt sie als Liste zurück."""
    visited = set()
    try:
        response = requests.get(start_url)
        soup = BeautifulSoup(response.text, 'html.parser')
        for a_tag in soup.find_all('a', href=True):
            raw_link = a_tag['href']
            full_url = urljoin(start_url, raw_link)
            if ist_internal_link(start_url, full_url):
                visited.add(full_url)
        with open("gefundene_urls.txt", "w", encoding="utf-8") as f:
            for url in sorted(visited):
                f.write(url + "\n")
        print(f"\n Alle internen Links in 'gefundene_urls.txt' gespeichert.")  
    except requests.RequestException as e:
        print(f"Fehler beim Abrufen der Seite {start_url}: {e}")
        return []
    return list(visited)

def run_pa11y(url, filename="pa11y_result.json"):
    """Führt Pa11y aus und speichert das Ergebnis in einer JSON-Datei."""
    print(f"Pa11y: {url}")
    result = subprocess.run([NPX, "pa11y", "--reporter", "json", "--include-warnings", url], capture_output=True, text=True)

    try:
        results_json = json.loads(result.stdout)
    except json.JSONDecodeError as e:
        print(f"Fehler beim Parsen der pa11y Ausgabe für {url}: {e}")
        results_json = []

    entry = {
        "url": url,
        "results": results_json
    }

    try:
        with open(filename, "r", encoding="utf-8") as f:
            data = json.load(f)
    except (FileNotFoundError, json.JSONDecodeError):
        data = []

    data.append(entry)

    with open(filename, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2, ensure_ascii=False)

def run_axe(url, filename="axe_result.json"):
    """Führt axe-core aus und speichert das Ergebnis als JSON-Datei."""
    print(f"axe-core: {url}")
    result = subprocess.run(
        [NPX, "@axe-core/cli", url, "--save", "axe_tmp.json"],
        capture_output=True,
        text=True,
    )

    if result.returncode != 0:
        print("Fehler bei axe-core:", result.stderr)

    try:
        with open("axe_tmp.json", "r", encoding="utf-8") as tmp:
            data = json.load(tmp)
        os.remove("axe_tmp.json")
    except Exception as e:
        print(f"Fehler beim Lesen der axe-core Ausgabe: {e}")
        data = {}

    entry = {
        "url": url,
        "axe_result": data,
    }

    try:
        with open(filename, "r", encoding="utf-8") as f:
            all_data = json.load(f)
    except (FileNotFoundError, json.JSONDecodeError):
        all_data = []

    all_data.append(entry)

    with open(filename, "w", encoding="utf-8") as f:
        json.dump(all_data, f, indent=2, ensure_ascii=False)

def run_lighthouse(url, filename="lighthouse_results.json"):
    """Führt Lighthouse für die angegebene URL aus und hängt das JSON-Ergebnis an die angegebene Datei an."""
    print(f"Lighthouse: {url}")
    fd, tmp_path = tempfile.mkstemp(suffix=".json")
    os.close(fd)

    result = subprocess.run(
        [
            NPX,
            "lighthouse",
            url,
            "--only-categories=accessibility",
            "--output=json",
            "--chrome-flags=--headless",
            f"--output-path={tmp_path}",
        ],
        capture_output=True,
        text=True,
    )

    if result.returncode != 0:
        print("Fehler bei Lighthouse:", result.stderr)

    try:
        with open(tmp_path, "r", encoding="utf-8") as tmp_file:
            data = json.load(tmp_file)
        entry = {"url": url, "lighthouse_result": data}
        
        try:
            with open(filename, "r", encoding="utf-8") as f:
                all_data = json.load(f)
        except (FileNotFoundError, json.JSONDecodeError):
            all_data = []

        all_data.append(entry)

        with open(filename, "w", encoding="utf-8") as out_file:
            json.dump(all_data, out_file, indent=2, ensure_ascii=False)
    except Exception as exc:
        print(f"Fehler beim Lesen/Speichern von Lighthouse-Ergebnissen: {exc}")
    finally:
        try:
            os.remove(tmp_path)
        except OSError:
            pass

def accessibility_checks(urls):
    """Führt alle Tests für jede URL in urls aus."""
    """Die Ergebnisse werden in den Dateien pa11y_result.json, axe_result.json und lighthouse_results.json gespeichert."""
    for url in urls:
        print(f"\n=== Teste Seite: {url} ===")
        run_pa11y(url)
        run_axe(url)
        run_lighthouse(url)

def _extract_pa11y_errors(data):
    """Gibt eine Liste mit Fehlern aus den Pa11y-Ergebnissen zurück,
    jeweils bestehend aus einer Nachricht (message) und dem Kontext (context)."""    
    errors = []
    seen = set()
    for entry in data:
        for res in entry.get("results", []):
            if res.get("type") == "error":
                msg = res.get("message", "")
                ctx = res.get("context", "")
                key = (_canonicalize_message(msg), ctx)
                if key in seen:
                    continue
                seen.add(key)
                errors.append({"message": msg, "context": ctx})
    return errors

def _extract_axe_errors(data):
    """Gibt eine Liste mit Fehlernachrichten und HTML-Kontext aus den Axe-Ergebnissen zurück."""
    errors = []
    seen = set()
    for entry in data:
        axe_result = entry.get("axe_result", {})
        results = axe_result if isinstance(axe_result, list) else [axe_result]
        for result in results:
            for viol in result.get("violations", []):
                msg = viol.get("help", viol.get("description", ""))
                for node in viol.get("nodes", []):
                    ctx = node.get("html", "")
                    key = (_canonicalize_message(msg), ctx)
                    if key in seen:
                        continue
                    seen.add(key)
                    errors.append({"message": msg, "context": ctx})
    return errors

def _extract_lighthouse_errors(data):
    """Gibt eine Liste von Fehlern aus den Lighthouse-Ergebnissen zurück,""" 
    """jeweils mit Nachricht (message) und HTML-Kontext (Context)."""
    errors = []
    seen = set()
    for entry in data:
        lh = entry.get("lighthouse_result", entry)
        audits = lh.get("audits", {})
        for audit in audits.values():
            score = audit.get("score")
            if score is not None and score < 1:
                title = audit.get("title", "")
                details = audit.get("details", {})
                items = details.get("items", [])
                if items:
                    for it in items:
                        node = it.get("node", {})
                        ctx = node.get("snippet", "")
                        msg = node.get("explanation", title)
                        key = (_canonicalize_message(msg), ctx)
                        if key in seen:
                            continue
                        seen.add(key)
                        errors.append({"message": msg, "context": ctx})
                else:
                    key = (_canonicalize_message(title), "")
                    if key in seen:
                        continue
                    seen.add(key)
                    errors.append({"message": title, "context": ""})
    return errors

def _canonicalize_message(msg: str) -> str:
    """Vereinfachte Darstellung zum Vergleich verschiedener Tools zurückgegeben."""
    msg_l = msg.lower()
    if ("alt attribute" in msg_l or "alternative text" in msg_l or "missing alt" in msg_l):
        return "images must have alternative text"

    if "one main landmark" in msg_l:
        return "document should have one main landmark"

    if "landmark" in msg_l:
        return "all page content should be contained by landmarks"

    if "page title" in msg_l or "title element" in msg_l:
        return "document must have a title element"

    if "lang attribute" in msg_l or "document language" in msg_l:
        return "document must have a language attribute"

    if (
        "no link content" in msg_l
        or "discernible text" in msg_l
        or "anchor element found with a valid href" in msg_l
    ):
        return "links must have discernible text"

    if "form" in msg_l and "label" in msg_l:
        return "form elements must have labels"

    if "<label>" in msg_l and ("implicit" in msg_l or "explicit" in msg_l):
        return "form elements must have labels"

    if (
        "accessible name" in msg_l
        or "name available to an accessibility api" in msg_l
        or "does not have accessible text" in msg_l
    ):
        return "element requires an accessible name"

    if (
        "aria hidden" in msg_l and "focusable" in msg_l
    ) or "focusable content should have tabindex" in msg_l:
        return "aria-hidden element must not be focusable"

    if "tabindex" in msg_l and "+" in msg_l:
        return "avoid positive tabindex values"

    if "frame" in msg_l and "tabindex" in msg_l:
        return "frames must not remove focusable content"

    if "color contrast" in msg_l:
        return "elements must meet minimum color contrast ratio thresholds"

    if "link has no styling" in msg_l or "relying on color" in msg_l:
        return "links must be distinguishable without relying on color"

    if "insufficient size" in msg_l or "tap target" in msg_l:
        return "interactive elements must have sufficient size"

    if "fieldset" in msg_l and "legend" in msg_l:
        return "fieldsets must contain a legend element"

    if "invalid autocomplete" in msg_l:
        return "autocomplete attribute must be valid"

    if "list element has direct children" in msg_l or "<ul> and <ol> must only directly contain" in msg_l:
        return "lists must only contain allowed children"

    if "scrollable" in msg_l and "focusable" in msg_l:
        return "scrollable region must be focusable"

    if "level-one heading" in msg_l:
        return "page should contain a level-one heading"

    if "aria" in msg_l and "attribute" in msg_l and "valid" in msg_l:
        return "aria attributes must be valid"

    if "interactive controls" in msg_l and "nested" in msg_l:
        return "interactive controls must not be nested"

    if "bypass" in msg_l and "repeated blocks" in msg_l:
        return "page must have a skip link or landmark"

    if "data cells" in msg_l and "table headers" in msg_l:
        return "table cells must have headers"

    if "duplicate id" in msg_l:
        return "elements must have unique ids"

    if "meta http-equiv\"refresh" in msg_l or "timed refresh" in msg_l:
        return "page must not use timed refresh"

    if "user-scalable\"=" in msg_l or "maximum-scale" in msg_l:
        return "page must allow zooming"

    if "aria role" in msg_l and (
        "not allowed" in msg_l or "appropriate" in msg_l or "invalid" in msg_l
    ):
        return "element has an invalid aria role"

    return msg_l.strip()

def combine_errors(pa11y_file="pa11y_result.json", axe_file="axe_result.json", lighthouse_file="lighthouse_results.json", output="bewertung.json",):
    """Fehler aus allen Tools kombinieren und in „output“ schreiben."""
    """Die resultierende JSON-Datei ist eine Liste von Objekten, die jeweils die URL und eine"""
    """Meldungs-/Kontextliste für jedes Tool enthalten. Eine einheitliche Liste „All tools“ führt"""
    """die Meldungen aus Pa11y, Axe und Lighthouse zusammen und entfernt Duplikate."""
    pa11y_data = _load_json(pa11y_file)
    axe_data = _load_json(axe_file)
    lighthouse_data = _load_json(lighthouse_file)

    grouped = {}

    for entry in pa11y_data:
        url = entry.get("url")
        if not url:
            continue
        grouped.setdefault(url, {"pa11y": [], "axe": [], "lighthouse": []})
        grouped[url]["pa11y"].extend(_extract_pa11y_errors([entry]))

    for entry in axe_data:
        url = entry.get("url")
        if not url:
            continue
        grouped.setdefault(url, {"pa11y": [], "axe": [], "lighthouse": []})
        grouped[url]["axe"].extend(_extract_axe_errors([entry]))

    for entry in lighthouse_data:
        url = entry.get("url")
        if not url:
            lh = entry.get("lighthouse_result", {})
            url = lh.get("finalUrl") or lh.get("requestedUrl")
        if not url:
            continue
        grouped.setdefault(url, {"pa11y": [], "axe": [], "lighthouse": []})
        grouped[url]["lighthouse"].extend(_extract_lighthouse_errors([entry]))

    result_list = []
    for url, data in grouped.items():
        seen = set()
        all_tools = []
        for tool_name in ("pa11y", "axe", "lighthouse"):
            for err in data[tool_name]:
                msg = err.get("message", "")
                ctx = err.get("context", "")
                key = (_canonicalize_message(msg), ctx)
                if key not in seen:
                    seen.add(key)
                    all_tools.append({"message": key[0], "context": ctx})

        result_list.append({
            "URL": url,
            "All tools": all_tools,
            "pa11y": data["pa11y"],
            "axe": data["axe"],
            "lighthouse": data["lighthouse"],
        })

    try:
        with open(output, "w", encoding="utf-8") as f:
            json.dump(result_list, f, indent=2, ensure_ascii=False)
        print(f"Kombinierte Fehler in '{output}' gespeichert.")
    except Exception as exc:
        print(f"Fehler beim Speichern der kombinierten Fehler: {exc}")

def _load_json(path):
    """Lädt eine JSON-Datei oder gibt eine leere Liste zurück."""
    try:
        with open(path, "r", encoding="utf-8") as f:
            data = json.load(f)
            if isinstance(data, dict):
                return [data]
            return data
    except (FileNotFoundError, json.JSONDecodeError):
        return []

def delete_old_results():
    """Löscht vorhandene Ergebnisdateien, falls sie existieren."""
    temp_files = [
        "axe_result.json",
        "lighthouse_results.json",
        "pa11y_result.json",
        "bewertung.json",
        "gefundene_urls.txt",
        "lh_tmp.json",
        "visualization_summary.txt",
        "tool_comparison.png",
        "common_errors.png",
    ]

    for file in temp_files:
        if os.path.exists(file):
            os.remove(file)
    print(" Alte Ergebnisdateien gelöscht.")

def delete_results():
    """Tool-Ergebnisdateien löschen."""
    temp_files = [
        "axe_result.json",
        "lighthouse_results.json",
        "pa11y_result.json"
    ]

    for path in temp_files:
        if os.path.exists(path):
            try:
                os.remove(path)
            except Exception as e:
                print(f"Fehler beim Löschen von {path}: {e}")
        else:
            print(f"Nicht gefunden (oder schon gelöscht): {path}")

def _load_bewertung(path: Path = Path(__file__).with_name("bewertung.json")):
    """Lädt Bewertungsdaten aus einer JSON-Datei."""
    with path.open("r", encoding="utf-8") as f:
        return json.load(f)

def _count_issues(entries):
    """Gibt eine Liste mit der Anzahl der Probleme pro Tool für jede URL zurück."""
    counts = []
    for entry in entries:
        counts.append({
            "url": entry.get("URL", "unknown"),
            "pa11y": len(entry.get("pa11y", [])),
            "axe": len(entry.get("axe", [])),
            "lighthouse": len(entry.get("lighthouse", [])),
            "all": len(entry.get("All tools", [])),
        })
    return counts

def _count_common_errors(entries):
    """Gibt einen Counter mit der Häufigkeit jeder Fehlermeldung über alle Tools und URLs zurück."""
    counter = Counter()
    tools = ("pa11y", "axe", "lighthouse")
    for entry in entries:
        for tool in tools:
            for issue in entry.get(tool, []):
                msg = issue.get("message", "")
                if msg:
                    counter[msg] += 1
    return counter

def _write_summary_text(counts, counter, output: Path = Path("visualization_summary.txt")):
    """Schreibt eine textuelle Zusammenfassung der Visualisierungsdaten für Screenreader."""
    with output.open("w", encoding="utf-8") as f:
        # Kopfzeile für die Übersicht in deutscher Sprache
        f.write("Probleme pro Tool und Seite:\n")
        for c in counts:
            # Beschriftung der Summen: das Feld "all" repräsentiert alle Tools und wird
            # als "alle" ausgegeben, damit deutschsprachige Leser:innen den Wert
            # besser einordnen können.
            f.write(
                f"{c['url']}: pa11y={c['pa11y']}, axe={c['axe']}, lighthouse={c['lighthouse']}, alle={c['all']}\n"
            )
        f.write("\nHäufigste Probleme:\n")
        for msg, num in counter.most_common(10):
            f.write(f"{num}× {msg}\n")

def _plot_tool_comparison(counts, output: Path = Path("tool_comparison.png")):
    """Erstellt ein Balkendiagramm zum Vergleich der Anzahl der Probleme pro Tool."""
    import matplotlib.pyplot as plt

    labels = [c["url"] for c in counts]
    pa11y = [c["pa11y"] for c in counts]
    axe = [c["axe"] for c in counts]
    lighthouse = [c["lighthouse"] for c in counts]
    all_tools = [c["all"] for c in counts]
    colors = plt.get_cmap("tab10").colors

    x = range(len(labels))
    width = 0.2
    numbers = list(range(1, len(labels)+1))

    # Verwende "constrained"‑Layout, damit Matplotlib automatisch genügend Platz
    # für Achsenbeschriftungen und Legenden reserviert. Dies verhindert die
    # Warnung, dass tight_layout nicht angewendet werden konnte.
    fig, ax = plt.subplots(figsize=(10, 6), layout="constrained")
    ax.bar([p - 1.5 * width for p in x], pa11y, width, label="pa11y", color=colors[0])
    ax.bar([p - 0.5 * width for p in x], axe, width, label="axe", color=colors[1])
    ax.bar([p + 0.5 * width for p in x], lighthouse, width, label="lighthouse", color=colors[2])
    # Der vierte Balken aggregiert alle Tools; die Legende wird ins Deutsche übersetzt
    ax.bar([p + 1.5 * width for p in x], all_tools, width, label="alle Tools", color=colors[3])

    ax.set_xticks(list(x))
    ax.set_xticklabels(numbers)
    ax.set_ylabel("Anzahl der Probleme")
    ax.set_title("Barrierefreiheitsprobleme pro Seite")
    ax.legend()

    # Gesamtzahl über die "all tools"-Balken schreiben
    for i, value in enumerate(all_tools):
        ax.text(i + 1.5 * width, value + 0.5, str(value), ha='center', va='bottom', fontsize=10)

    # Mapping unten unter das Diagramm schreiben
    mapping = "\n".join([f"{num}: {url}" for num, url in zip(numbers, labels)])
    fig.text(0.5, -0.15, mapping, ha="center", va="top", fontsize=9, wrap=True)

    # Speichere die Abbildung ohne tight_layout, da das "constrained"‑Layout
    # automatisch Platz reserviert.
    fig.savefig(output)
    print(f"Diagramm zum Tool‑Vergleich wurde in {output} gespeichert.")


def _plot_common_errors(counter: Counter, output: Path = Path("common_errors.png"), top_n: int = 10):
    """Zeigt die häufigsten Accessibility-Probleme als Diagramm an."""
    try:
        import matplotlib.pyplot as plt
    except ModuleNotFoundError:
        print("matplotlib ist nicht installiert; überspringe Diagramm der häufigsten Probleme.")
        return

    most_common = counter.most_common(top_n)
    labels = [m[0][:50] + ("..." if len(m[0]) > 50 else "") for m in most_common]
    values = [m[1] for m in most_common]

    colors = plt.get_cmap("tab10").colors

    # Verwende das "constrained"‑Layout, um genügend Platz für Achsenbeschriftungen
    # und Legenden zu reservieren und Warnungen von tight_layout zu vermeiden.
    fig, ax = plt.subplots(figsize=(10, 6), layout="constrained")
    ax.barh(labels, values, color=colors[4])
    ax.set_xlabel("Häufigkeit")
    ax.set_title(f"Top {top_n} häufigste Probleme")
    # Das "constrained"‑Layout macht einen expliziten Aufruf von tight_layout überflüssig.
    fig.savefig(output)
    print(f"Diagramm der häufigsten Probleme wurde in {output} gespeichert.")

def visualisation():
    entries = _load_bewertung()
    counts = _count_issues(entries)
    counter = _count_common_errors(entries)

    _plot_tool_comparison(counts)
    _plot_common_errors(counter)
    _write_summary_text(counts, counter)

# ------------------------------------------------------------------------------
# Funktionen zur Berechnung und Darstellung eines Barrierefreiheits‑Scores.
# Diese Funktionen werten die gespeicherten Fehlermeldungen aus, normieren
# Häufigkeit und Schweregrad und ermitteln daraus einen Punktabzug.  Der
# resultierende Score liegt zwischen 0 und 100, wobei 100 keine festgestellten
# Probleme bedeutet.

from typing import List, Dict

def calculate_score(issues: List[Dict], max_score: int = 100) -> int:
    """Berechnet einen einfachen Score basierend auf den übergebenen Issues.

    Diese Funktion summiert die Produkte aus Schweregrad (S), Häufigkeit (H)
    und Typ‑Faktor (T) für jede Meldung und zieht diese Summe vom
    Maximalwert ab.  Sie liefert einen integerischen Score zwischen 0 und
    ``max_score`` zurück.  Wird ``max_score`` unterschritten, wird der Score
    auf 0 begrenzt.

    Parameters
    ----------
    issues : List[Dict]
        Eine Liste mit Dictionaries, die die Schlüssel ``severity``,
        ``frequency`` und ``type_factor`` enthalten.
    max_score : int, optional
        Der maximal erreichbare Score (Standard: 100).

    Returns
    -------
    int
        Der berechnete Score.
    """
    total_penalty = 0
    for issue in issues:
        s = issue.get("S", issue.get("severity", 1))
        h = issue.get("H", issue.get("frequency", 1))
        t = issue.get("T", issue.get("type_factor", 1))
        total_penalty += s * h * t
    return max(0, max_score - total_penalty)


def _count_all_tool_messages(entries):
    """Zählt, wie oft jede kanonische Meldung über alle Seiten hinweg vorkommt.

    Das Ergebnis ist ein ``Counter``‑Objekt, dessen Schlüssel die
    kanonischen Meldungen (siehe ``_canonicalize_message``) sind und dessen
    Werte die Anzahl der Vorkommen über alle geprüften Seiten darstellen.
    """
    counter = Counter()
    for entry in entries:
        for issue in entry.get("All tools", []):
            msg = issue.get("message", "")
            if msg:
                counter[_canonicalize_message(msg)] += 1
    return counter


def accessibility_score(entries):
    """Berechnet einen normalisierten Barrierefreiheits‑Score basierend auf den
    gespeicherten Fehlermeldungen.

    Die Methode gewichtet jede Meldung mit den Werten aus
    ``ISSUE_CATEGORIES`` (Schweregrad und Typ‑Faktor) und skaliert die
    Ergebnisse so, dass der Punktabzug bei der schwersten einzelnen Meldung
    maximal 100 beträgt.  Der Rückgabewert ist ein Tupel aus Score,
    Gesamtabzug und einer Liste detaillierter Informationen.

    Parameters
    ----------
    entries : List[Dict]
        Die geladenen Bewertungseinträge aus ``bewertung.json``.

    Returns
    -------
    Tuple[float, float, List[Dict]]
        Ein Tupel mit (Score, Gesamtabzug, Details pro Fehlertyp).
    """
    counts = _count_all_tool_messages(entries)
    total_issues = sum(counts.values())
    if total_issues == 0:
        return 100.0, 0.0, []
    # Bestimme den maximalen Abzug je Meldungskategorie
    if ISSUE_CATEGORIES:
        max_weight = max(
            info.get("severity", DEFAULT_SEVERITY) * info.get("type_factor", DEFAULT_TYPE_FACTOR)
            for info in ISSUE_CATEGORIES.values()
        )
    else:
        max_weight = DEFAULT_SEVERITY * DEFAULT_TYPE_FACTOR
    if max_weight <= 0:
        max_weight = 1.0
    scaling_factor = 100.0 / max_weight
    details = []
    total_penalty = 0.0
    for key, freq in counts.items():
        if freq == 0:
            continue
        info = ISSUE_CATEGORIES.get(
            key,
            {"severity": DEFAULT_SEVERITY, "type_factor": DEFAULT_TYPE_FACTOR, "label": key},
        )
        severity = info.get("severity", DEFAULT_SEVERITY)
        type_factor = info.get("type_factor", DEFAULT_TYPE_FACTOR)
        label = info.get("label", key)
        ratio = freq / total_issues
        deduction = severity * type_factor * ratio * scaling_factor
        total_penalty += deduction
        details.append({
            "label": label,
            "severity": severity,
            "frequency": freq,
            "type_factor": type_factor,
            "ratio": ratio,
            "deduction": deduction,
        })
    details.sort(key=lambda d: d["deduction"], reverse=True)
    score = max(0.0, 100.0 - total_penalty)
    return round(score, 1), round(total_penalty, 1), details


def print_score_and_prioritization():
    """Gibt eine priorisierte Liste der wichtigsten Probleme und den Gesamt‑Score aus.

    Diese Funktion lädt die Daten aus ``bewertung.json``, berechnet den
    Barrierefreiheits‑Score und gibt die Probleme sortiert nach ihrem
    Punktabzug aus.  Zusätzlich wird eine JSON‑Datei mit den Detailwerten
    geschrieben und ein Diagramm der größten Abzüge erstellt.
    """
    entries = _load_bewertung()
    score, total, details = accessibility_score(entries)
    print("Priorisierte Probleme:")
    for d in details:
        print(
            f"{d['label']}: Schweregrad {d['severity']} , Häufigkeit {d['frequency']} ,"
            f"Typ‑Faktor {d['type_factor']} = {d['deduction']:.1f}"
        )
    print(f"Gesamtabzug = {total:.1f}")
    print(f"Barrierefreiheits‑Score = {score:.1f}")
    _write_score_json(details, total, score)
    _plot_score_details(details)


def _write_score_json(details, total, score, output: Path = Path("score.json")):
    """Speichert den berechneten Score und die Detailinformationen als JSON.

    Die Datei enthält den gesamten Punktabzug, den Score und eine Liste der
    einzelnen Probleme mit ihren abgeleiteten Werten.  Dies erleichtert die
    weitere maschinelle Auswertung der Ergebnisse.
    """
    data = {
        "total_deduction": round(total, 1),
        "score": round(score, 1),
        "issues": [
            {
                "label": d["label"],
                "severity": d["severity"],
                "frequency": d["frequency"],
                "type_factor": d["type_factor"],
                "deduction": round(d["deduction"], 1),
            }
            for d in details
        ],
    }
    with output.open("w", encoding="utf-8") as f:
        json.dump(data, f, indent=2, ensure_ascii=False)


def _plot_score_details(details, output: Path = Path("score_chart.png"), top_n: int = 10):
    """Zeichnet ein horizontales Balkendiagramm für die größten Punktabzüge.

    Es werden die ``top_n`` größten Punktabzüge dargestellt.  Die Beschriftungen
    sind deutschsprachig, um die Lesbarkeit zu verbessern.
    """
    try:
        import matplotlib.pyplot as plt
    except ModuleNotFoundError:
        print("matplotlib ist nicht installiert; überspringe Score‑Diagramm.")
        return
    subset = details[:top_n]
    labels = [d["label"] for d in subset]
    values = [d["deduction"] for d in subset]
    colors = plt.get_cmap("tab10").colors
    # Nutze das "constrained"‑Layout, das automatisch ausreichend Platz für die
    # Beschriftungen reserviert und die Warnung von tight_layout verhindert.
    fig, ax = plt.subplots(figsize=(10, 6), layout="constrained")
    ax.barh(labels, values, color=colors[5])
    ax.invert_yaxis()
    ax.set_xlabel("Punktabzug")
    ax.set_title("Top Barrierefreiheitsprobleme")
    # Beim "constrained"‑Layout ist kein expliziter Aufruf von tight_layout nötig.
    fig.savefig(output)
    print(f"Score‑Diagramm wurde in {output} gespeichert.")


if __name__ == "__main__":
        # Prüfen Sie die Node.js‑Version, bevor Sie mit den Tests beginnen
        if not _check_node_version():
            exit(1)
        # Alte Ergebnisdateien entfernen
        delete_old_results()
        # URL vom Benutzer abfragen
        user_url = input("Gib eine URL ein (inkl. https://): ").strip()
        if not user_url.startswith("http"):
            print("Bitte mit http:// oder https:// beginnen.")
        else:
            # interne Links sammeln
            seiten = [user_url] + finde_interne_links(user_url)
            print(f"\nGefundene Seiten: {len(seiten)}")
            try:
                anzahl_seiten = int(input("Wie viele Seiten sollen getestet werden? (0 für alle): ").strip())
            except ValueError:
                print("Ungültige Zahl. Es werden alle Seiten getestet.")
                anzahl_seiten = 0
            if anzahl_seiten == 0:
                print("Starte Barrierefreiheits‑Checks für alle Seiten …")
                accessibility_checks(seiten)
            else:
                print(f"Starte Barrierefreiheits‑Checks für {anzahl_seiten} Seite(n) …")
                accessibility_checks(seiten[:anzahl_seiten])
            # Ergebnisse kombinieren und Einzelresultate löschen
            combine_errors()
            delete_results()
            # Visualisierung und Score‑Berechnung
            visualisation()
            print_score_and_prioritization()
