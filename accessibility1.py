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
        f.write("Issues per tool and page:\n")
        for c in counts:
            f.write(
                f"{c['url']}: pa11y={c['pa11y']}, axe={c['axe']}, lighthouse={c['lighthouse']}, all={c['all']}\n"
            )
        f.write("\nMost common issues:\n")
        for msg, num in counter.most_common(10):
            f.write(f"{num}x {msg}\n")

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

    fig, ax = plt.subplots(figsize=(10, 6))
    ax.bar([p - 1.5 * width for p in x], pa11y, width, label="pa11y", color=colors[0])
    ax.bar([p - 0.5 * width for p in x], axe, width, label="axe", color=colors[1])
    ax.bar([p + 0.5 * width for p in x], lighthouse, width, label="lighthouse", color=colors[2])
    ax.bar([p + 1.5 * width for p in x], all_tools, width, label="all tools", color=colors[3])

    ax.set_xticks(list(x))
    ax.set_xticklabels(numbers)
    ax.set_ylabel("Number of issues")
    ax.set_title("Accessibility issues per page")
    ax.legend()

    # Gesamtzahl über die "all tools"-Balken schreiben
    for i, value in enumerate(all_tools):
        ax.text(i + 1.5 * width, value + 0.5, str(value), ha='center', va='bottom', fontsize=10)

    # Mapping unten unter das Diagramm schreiben
    mapping = "\n".join([f"{num}: {url}" for num, url in zip(numbers, labels)])
    fig.text(0.5, -0.15, mapping, ha="center", va="top", fontsize=9, wrap=True)

    fig.tight_layout()
    fig.savefig(output, bbox_inches='tight')
    print(f"Tool comparison saved to {output}")


def _plot_common_errors(counter: Counter, output: Path = Path("common_errors.png"), top_n: int = 10):
    """Zeigt die häufigsten Accessibility-Probleme als Diagramm an."""
    try:
        import matplotlib.pyplot as plt
    except ModuleNotFoundError:
        print("matplotlib is not installed; skipping common errors plot.")
        return

    most_common = counter.most_common(top_n)
    labels = [m[0][:50] + ("..." if len(m[0]) > 50 else "") for m in most_common]
    values = [m[1] for m in most_common]

    colors = plt.get_cmap("tab10").colors

    fig, ax = plt.subplots(figsize=(10, 6))
    ax.barh(labels, values, color=colors[4])
    ax.set_xlabel("Occurrences")
    ax.set_title(f"Top {top_n} frequent issues")
    fig.tight_layout()
    fig.savefig(output)
    print(f"Common errors plot saved to {output}")

def visualisation():
    entries = _load_bewertung()
    counts = _count_issues(entries)
    counter = _count_common_errors(entries)

    _plot_tool_comparison(counts)
    _plot_common_errors(counter)
    _write_summary_text(counts, counter)


if __name__ == "__main__":
        if not _check_node_version():
            exit(1)
        delete_old_results()
        user_url = input(" Gib eine URL ein (inkl. https://) : ").strip()
        if not user_url.startswith("http"):
            print(" Bitte mit http:// oder https:// beginnen.")
        else:
            seiten = [user_url] + finde_interne_links(user_url)
            print(f"\n Gefundene Seiten:{len(seiten)}")
            anzahl_seiten = int(input(" Wie viele Seiten sollen getestet werden? (0 für alle): ").strip())
            if anzahl_seiten == 0:
                print(f" Starte Accessibility-Checks für alle Seiten ....")
                accessibility_checks(seiten)
            else:
                print(f" Starte Accessibility-Checks für {anzahl_seiten} Seite(n) ....")
                accessibility_checks(seiten[:anzahl_seiten])
            combine_errors()
            delete_results()
            visualisation()
