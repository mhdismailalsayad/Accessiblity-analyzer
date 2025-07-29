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
from typing import List, Dict, Tuple

"""
This module provides a set of functions to automatically crawl a website,
run several accessibility testing tools (Pa11y, Axe and Lighthouse) against
the collected pages, unify their findings and compute accessibility scores.

It also contains utilities to visualise the results both globally and on
a per‑page basis.  In particular, it avoids generating a separate
``score.json`` file and instead relies solely on ``scores_per_url.json``
for page specific scores and diagrams.

The original implementation wrote a ``score.json`` file via the
``_write_score_json`` helper.  Because the per‑page scores are now
persisted in ``scores_per_url.json``, the generation of ``score.json``
has been removed and the visualisation functions work directly from
``scores_per_url.json``.
"""

if os.name == "nt":
    NPX = "npx.cmd"
else:
    NPX = "npx"

# ------------------------------------------------------------------------------
# Definition of canonical issue messages and weighting factors used for
# calculating accessibility scores.  See the documentation for each entry in
# ``ISSUE_CATEGORIES`` for details.

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

DEFAULT_SEVERITY = 1
DEFAULT_TYPE_FACTOR = 1.0

ISSUE_CATEGORIES: Dict[str, Dict[str, object]] = {
    msg: {"severity": DEFAULT_SEVERITY, "type_factor": DEFAULT_TYPE_FACTOR, "label": msg}
    for msg in CANONICAL_MESSAGES
}

ISSUE_CATEGORIES.update(
    {
        "images must have alternative text": {
            "severity": 4,
            "type_factor": 1.5,
            "label": "Fehlender Alternativtext",
        },
        "elements must meet minimum color contrast ratio thresholds": {
            "severity": 3,
            "type_factor": 1.3,
            "label": "Geringer Farbkontrast",
        },
        "form elements must have labels": {
            "severity": 4,
            "type_factor": 1.5,
            "label": "Unbeschriftetes Formularfeld",
        },
        "links must have discernible text": {
            "severity": 4,
            "type_factor": 1.3,
            "label": "Nicht erkennbare Linktexte",
        },
        "element requires an accessible name": {
            "severity": 4,
            "type_factor": 1.3,
            "label": "Fehlender Accessible Name",
        },
        "document should have one main landmark": {
            "severity": 3,
            "type_factor": 1.2,
            "label": "Fehlende Haupt‑Landmarke",
        },
        "all page content should be contained by landmarks": {
            "severity": 3,
            "type_factor": 1.2,
            "label": "Inhalt außerhalb von Landmarken",
        },
        "document must have a title element": {
            "severity": 3,
            "type_factor": 1.1,
            "label": "Fehlender Seitentitel",
        },
        "document must have a language attribute": {
            "severity": 2,
            "type_factor": 1.0,
            "label": "Fehlendes Sprachattribut",
        },
        "aria-hidden element must not be focusable": {
            "severity": 3,
            "type_factor": 1.2,
            "label": "ARIA‑hidden ist fokussierbar",
        },
        "avoid positive tabindex values": {
            "severity": 3,
            "type_factor": 1.1,
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
            "type_factor": 1.3,
            "label": "Kleine interaktive Elemente",
        },
        "fieldsets must contain a legend element": {
            "severity": 2,
            "type_factor": 1.0,
            "label": "Fieldset ohne Legende",
        },
        "autocomplete attribute must be valid": {
            "severity": 2,
            "type_factor": 0.9,
            "label": "Ungültiges Autocomplete‑Attribut",
        },
        "lists must only contain allowed children": {
            "severity": 2,
            "type_factor": 1.0,
            "label": "Liste enthält ungültige Kinder",
        },
        "scrollable region must be focusable": {
            "severity": 3,
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
            "type_factor": 1.3,
            "label": "Kein Skip‑Link vorhanden",
        },
        "table cells must have headers": {
            "severity": 4,
            "type_factor": 1.2,
            "label": "Tabellenzellen ohne Header",
        },
        "elements must have unique ids": {
            "severity": 3,
            "type_factor": 1.1,
            "label": "Nicht eindeutige IDs",
        },
        "page must not use timed refresh": {
            "severity": 3,
            "type_factor": 1.2,
            "label": "Zeitgesteuertes Refresh",
        },
        "page must allow zooming": {
            "severity": 3,
            "type_factor": 1.1,
            "label": "Zoom‑Funktion deaktiviert",
        },
        "element has an invalid aria role": {
            "severity": 2,
            "type_factor": 1.2,
            "label": "Ungültige ARIA‑Rolle",
        },
    }
)


# ------------------------------------------------------------------------------
# Utility functions

def _check_node_version() -> bool:
    """Return True if the installed Node.js version meets the minimum requirement."""
    try:
        result = subprocess.run(["node", "-v"], capture_output=True, text=True)
        if result.returncode != 0:
            print("Node.js konnte nicht gefunden werden. Bitte installieren Sie Node.js.")
            return False
        version = result.stdout.strip().lstrip("v")
        major = int(version.split(".")[0])
        if major < 20:
            print(
                f"Gefundene Node.js Version {version}. Bitte aktualisieren Sie Node.js auf Version 20 oder neuer."
            )
            return False
    except Exception as exc:
        print(f"Konnte Node.js Version nicht bestimmen: {exc}")
        return False
    return True


def ist_internal_link(base_url: str, link: str) -> bool:
    """Check whether ``link`` belongs to the same domain as ``base_url``."""
    base_domain = urlparse(base_url).netloc
    target_domain = urlparse(link).netloc
    return target_domain == "" or target_domain == base_domain


def finde_interne_links(start_url: str) -> List[str]:
    """Find all internal links on the starting page and return them as a list."""
    visited: set = set()
    try:
        response = requests.get(start_url)
        soup = BeautifulSoup(response.text, "html.parser")
        for a_tag in soup.find_all("a", href=True):
            raw_link = a_tag["href"]
            full_url = urljoin(start_url, raw_link)
            if ist_internal_link(start_url, full_url):
                visited.add(full_url)
        with open("gefundene_urls.txt", "w", encoding="utf-8") as f:
            for url in sorted(visited):
                f.write(url + "\n")
        print("\n Alle internen Links in 'gefundene_urls.txt' gespeichert.")
    except requests.RequestException as e:
        print(f"Fehler beim Abrufen der Seite {start_url}: {e}")
        return []
    return list(visited)


def run_pa11y(url: str, filename: str = "pa11y_result.json") -> None:
    """Run Pa11y and store the result in a JSON file."""
    print(f"Pa11y: {url}")
    result = subprocess.run([NPX, "pa11y", "--reporter", "json", "--include-warnings", url], capture_output=True, text=True)
    try:
        results_json = json.loads(result.stdout)
    except json.JSONDecodeError as e:
        print(f"Fehler beim Parsen der pa11y Ausgabe für {url}: {e}")
        results_json = []
    entry = {
        "url": url,
        "results": results_json,
    }
    try:
        with open(filename, "r", encoding="utf-8") as f:
            data = json.load(f)
    except (FileNotFoundError, json.JSONDecodeError):
        data = []
    data.append(entry)
    with open(filename, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2, ensure_ascii=False)


def run_axe(url: str, filename: str = "axe_result.json") -> None:
    """Run axe-core and append the result to a JSON file."""
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
    entry = {"url": url, "axe_result": data}
    try:
        with open(filename, "r", encoding="utf-8") as f:
            all_data = json.load(f)
    except (FileNotFoundError, json.JSONDecodeError):
        all_data = []
    all_data.append(entry)
    with open(filename, "w", encoding="utf-8") as f:
        json.dump(all_data, f, indent=2, ensure_ascii=False)


def run_lighthouse(url: str, filename: str = "lighthouse_results.json") -> None:
    """Run Lighthouse for the given URL and append the JSON result to ``filename``."""
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


def accessibility_checks(urls: List[str]) -> None:
    """Run Pa11y, Axe and Lighthouse on each URL in ``urls``."""
    for url in urls:
        print(f"\n=== Teste Seite: {url} ===")
        run_pa11y(url)
        run_axe(url)
        run_lighthouse(url)


# ------------------------------------------------------------------------------
# Helper functions to extract and canonicalise issues from the various tools

def _extract_pa11y_errors(data: List[dict]) -> List[Dict[str, str]]:
    """Return a list of error messages and contexts from Pa11y results."""
    errors: List[Dict[str, str]] = []
    seen: set = set()
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


def _extract_axe_errors(data: List[dict]) -> List[Dict[str, str]]:
    """Return a list of error messages and contexts from Axe results."""
    errors: List[Dict[str, str]] = []
    seen: set = set()
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


def _extract_lighthouse_errors(data: List[dict]) -> List[Dict[str, str]]:
    """Return a list of error messages and contexts from Lighthouse results."""
    errors: List[Dict[str, str]] = []
    seen: set = set()
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
    """Simplify the given message to a canonical form for deduplication."""
    msg_l = msg.lower()
    if "alt attribute" in msg_l or "alternative text" in msg_l or "missing alt" in msg_l:
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
    if ("aria hidden" in msg_l and "focusable" in msg_l) or "focusable content should have tabindex" in msg_l:
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


# ------------------------------------------------------------------------------
# Data combination and serialisation

def combine_errors(
    pa11y_file: str = "pa11y_result.json",
    axe_file: str = "axe_result.json",
    lighthouse_file: str = "lighthouse_results.json",
    output: str = "bewertung.json",
) -> None:
    """Combine errors from all tools and write the unified list to ``output``.

    The resulting JSON is a list of objects where each entry contains the URL
    along with the issues found by each individual tool and a merged list
    under the key ``All tools``.
    """
    pa11y_data = _load_json(pa11y_file)
    axe_data = _load_json(axe_file)
    lighthouse_data = _load_json(lighthouse_file)
    grouped: Dict[str, Dict[str, List[Dict[str, str]]]] = {}
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
        url = entry.get("url") or entry.get("lighthouse_result", {}).get("finalUrl") or entry.get("lighthouse_result", {}).get("requestedUrl")
        if not url:
            continue
        grouped.setdefault(url, {"pa11y": [], "axe": [], "lighthouse": []})
        grouped[url]["lighthouse"].extend(_extract_lighthouse_errors([entry]))
    result_list = []
    for url, data in grouped.items():
        seen: set = set()
        all_tools: List[Dict[str, str]] = []
        for tool_name in ("pa11y", "axe", "lighthouse"):
            for err in data[tool_name]:
                msg = err.get("message", "")
                ctx = err.get("context", "")
                key = (_canonicalize_message(msg), ctx)
                if key not in seen:
                    seen.add(key)
                    all_tools.append({"message": key[0], "context": ctx})
        result_list.append(
            {
                "URL": url,
                "All tools": all_tools,
                "pa11y": data["pa11y"],
                "axe": data["axe"],
                "lighthouse": data["lighthouse"],
            }
        )
    try:
        with open(output, "w", encoding="utf-8") as f:
            json.dump(result_list, f, indent=2, ensure_ascii=False)
        print(f"Kombinierte Fehler in '{output}' gespeichert.")
    except Exception as exc:
        print(f"Fehler beim Speichern der kombinierten Fehler: {exc}")


def _load_json(path: str) -> List[dict]:
    """Load a JSON file and return its contents or an empty list."""
    try:
        with open(path, "r", encoding="utf-8") as f:
            data = json.load(f)
            if isinstance(data, dict):
                return [data]
            return data
    except (FileNotFoundError, json.JSONDecodeError):
        return []


def delete_old_results() -> None:
    """Remove existing result files if they exist."""
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
        "score.json",
        "scores_per_url.json",
        "scores_visualization_summary.txt",
        "scores_per_url_chart.png",
        "total_deduction_chart.png",
        # legacy score_chart files for individual URLs; they will be removed below
        # by pattern matching in the code that follows
    ]
    for file in temp_files:
        if os.path.exists(file):
            os.remove(file)
    print(" Alte Ergebnisdateien gelöscht.")

    # Remove any per‑URL score charts from previous runs
    try:
        for fname in os.listdir('.'):
            if fname.startswith('score_chart_') and fname.endswith('.png'):
                os.remove(fname)
    except Exception:
        # silently ignore any errors here
        pass


def delete_results() -> None:
    """Delete tool result files (Pa11y, Axe, Lighthouse)."""
    temp_files = ["axe_result.json", "lighthouse_results.json", "pa11y_result.json"]
    for path in temp_files:
        if os.path.exists(path):
            try:
                os.remove(path)
            except Exception as e:
                print(f"Fehler beim Löschen von {path}: {e}")
        else:
            print(f"Nicht gefunden (oder schon gelöscht): {path}")


# ------------------------------------------------------------------------------
# Counting and summary helpers

def _load_bewertung(path: Path = Path("bewertung.json")) -> List[dict]:
    """Load evaluation data from the specified JSON file."""
    return _load_json(str(path))


def _count_issues(entries: List[dict]) -> List[Dict[str, object]]:
    """Return a list with the number of issues per tool for each URL."""
    counts: List[Dict[str, object]] = []
    for entry in entries:
        counts.append(
            {
                "url": entry.get("URL", "unknown"),
                "pa11y": len(entry.get("pa11y", [])),
                "axe": len(entry.get("axe", [])),
                "lighthouse": len(entry.get("lighthouse", [])),
                "all": len(entry.get("All tools", [])),
            }
        )
    return counts


def _count_common_errors(entries: List[dict]) -> Counter:
    """Return a Counter with the frequency of each error message across all tools and URLs."""
    counter: Counter = Counter()
    tools = ("pa11y", "axe", "lighthouse")
    for entry in entries:
        for tool in tools:
            for issue in entry.get(tool, []):
                msg = issue.get("message", "")
                if msg:
                    counter[msg] += 1
    return counter


def _write_summary_text(counts: List[Dict[str, object]], counter: Counter, output: Path = Path("visualization_summary.txt")) -> None:
    """Write a textual summary of the visualisation data for screen readers."""
    with output.open("w", encoding="utf-8") as f:
        f.write("Probleme pro Tool und Seite:\n")
        for c in counts:
            f.write(
                f"{c['url']}: pa11y={c['pa11y']}, axe={c['axe']}, lighthouse={c['lighthouse']}, alle={c['all']}\n"
            )
        f.write("\nHäufigste Probleme:\n")
        for msg, num in counter.most_common(10):
            f.write(f"{num}× {msg}\n")


def _plot_tool_comparison(counts: List[Dict[str, object]], output: Path = Path("tool_comparison.png")) -> None:
    """Create a bar chart comparing the number of issues per tool per page."""
    labels = [c["url"] for c in counts]
    pa11y = [c["pa11y"] for c in counts]
    axe = [c["axe"] for c in counts]
    lighthouse = [c["lighthouse"] for c in counts]
    all_tools = [c["all"] for c in counts]
    colors = plt.get_cmap("tab10").colors
    x = range(len(labels))
    width = 0.2
    numbers = list(range(1, len(labels) + 1))
    fig, ax = plt.subplots(figsize=(10, 6))
    ax.bar([p - 1.5 * width for p in x], pa11y, width, label="pa11y", color=colors[0])
    ax.bar([p - 0.5 * width for p in x], axe, width, label="axe", color=colors[1])
    ax.bar([p + 0.5 * width for p in x], lighthouse, width, label="lighthouse", color=colors[2])
    ax.bar([p + 1.5 * width for p in x], all_tools, width, label="alle Tools", color=colors[3])
    ax.set_xticks(list(x))
    ax.set_xticklabels(numbers)
    ax.set_ylabel("Anzahl der Probleme")
    ax.set_title("Barrierefreiheitsprobleme pro Seite")
    ax.legend()
    for i, value in enumerate(all_tools):
        ax.text(i + 1.5 * width, value + 0.5, str(value), ha="center", va="bottom", fontsize=10)
    mapping = "\n".join([f"{num}: {url}" for num, url in zip(numbers, labels)])
    fig.text(0.5, -0.15, mapping, ha="center", va="top", fontsize=9, wrap=True)
    fig.tight_layout()
    fig.savefig(output, bbox_inches="tight")
    print(f"Diagramm zum Tool‑Vergleich wurde in {output} gespeichert.")


def _plot_common_errors(counter: Counter, output: Path = Path("common_errors.png"), top_n: int = 10) -> None:
    """Plot the most frequent accessibility issues across all tools and pages."""
    most_common = counter.most_common(top_n)
    labels = [m[0][:50] + ("..." if len(m[0]) > 50 else "") for m in most_common]
    values = [m[1] for m in most_common]
    colors = plt.get_cmap("tab10").colors
    fig, ax = plt.subplots(figsize=(10, 6))
    ax.barh(labels, values, color=colors[4])
    ax.set_xlabel("Häufigkeit")
    ax.set_title(f"Top {top_n} häufigste Probleme")
    fig.tight_layout()
    fig.savefig(output)
    print(f"Diagramm der häufigsten Probleme wurde in {output} gespeichert.")


def visualisation() -> None:
    """Generate visualisations for the combined error data and per‑URL scores."""
    entries = _load_bewertung()
    counts = _count_issues(entries)
    counter = _count_common_errors(entries)
    _plot_tool_comparison(counts)
    _plot_common_errors(counter)
    _write_summary_text(counts, counter)
    # Visualise per‑URL scores using the scores_per_url.json file if present
    _visualise_scores_per_url()


# ------------------------------------------------------------------------------
# Scoring functions

def calculate_score(issues: List[Dict[str, object]], max_score: int = 100) -> int:
    """Simple scoring function summing severity, frequency and type factor products."""
    total_penalty = 0
    for issue in issues:
        s = issue.get("S", issue.get("severity", 1))
        h = issue.get("H", issue.get("frequency", 1))
        t = issue.get("T", issue.get("type_factor", 1))
        total_penalty += s * h * t
    return max(0, max_score - total_penalty)


def _count_all_tool_messages(entries: List[dict]) -> Counter:
    """Count how often each canonical message occurs across all pages."""
    counter: Counter = Counter()
    for entry in entries:
        for issue in entry.get("All tools", []):
            msg = issue.get("message", "")
            if msg:
                counter[_canonicalize_message(msg)] += 1
    return counter


def accessibility_score(entries: List[dict]) -> Tuple[float, float, List[Dict[str, object]]]:
    """Compute a normalised accessibility score across all pages."""
    counts = _count_all_tool_messages(entries)
    total_issues = sum(counts.values())
    if total_issues == 0:
        return 100.0, 0.0, []
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
    details: List[Dict[str, object]] = []
    total_penalty = 0.0
    for key, freq in counts.items():
        if freq == 0:
            continue
        info = ISSUE_CATEGORIES.get(
            key, {"severity": DEFAULT_SEVERITY, "type_factor": DEFAULT_TYPE_FACTOR, "label": key}
        )
        severity = info.get("severity", DEFAULT_SEVERITY)
        type_factor = info.get("type_factor", DEFAULT_TYPE_FACTOR)
        label = info.get("label", key)
        ratio = freq / total_issues
        deduction = severity * type_factor * ratio * scaling_factor
        total_penalty += deduction
        details.append(
            {
                "label": label,
                "severity": severity,
                "frequency": freq,
                "type_factor": type_factor,
                "ratio": ratio,
                "deduction": deduction,
            }
        )
    details.sort(key=lambda d: d["deduction"], reverse=True)
    score = max(0.0, 100.0 - total_penalty)
    return round(score, 1), round(total_penalty, 1), details


def accessibility_score_per_url(entries: List[dict]) -> List[Dict[str, object]]:
    """Compute the score and details for each individual URL."""
    results: List[Dict[str, object]] = []
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
    for entry in entries:
        url = entry.get("URL") or entry.get("url")
        issues = entry.get("All tools", [])
        counts: Counter = Counter()
        for issue in issues:
            msg = issue.get("message", "")
            if msg:
                key = _canonicalize_message(msg)
                counts[key] += 1
        total_issues = sum(counts.values())
        if total_issues == 0:
            results.append({"url": url, "score": 100.0, "total_deduction": 0.0, "issues": []})
            continue
        total_penalty = 0.0
        details: List[Dict[str, object]] = []
        for key, freq in counts.items():
            info = ISSUE_CATEGORIES.get(
                key, {"severity": DEFAULT_SEVERITY, "type_factor": DEFAULT_TYPE_FACTOR, "label": key}
            )
            severity = info.get("severity", DEFAULT_SEVERITY)
            type_factor = info.get("type_factor", DEFAULT_TYPE_FACTOR)
            label = info.get("label", key)
            ratio = freq / total_issues
            deduction = severity * type_factor * ratio * scaling_factor
            total_penalty += deduction
            details.append(
                {
                    "label": label,
                    "severity": severity,
                    "frequency": freq,
                    "type_factor": type_factor,
                    "deduction": round(deduction, 1),
                }
            )
        details.sort(key=lambda d: d["deduction"], reverse=True)
        score = max(0.0, 100.0 - total_penalty)
        results.append(
            {
                "url": url,
                "score": round(score, 1),
                "total_deduction": round(total_penalty, 1),
                "issues": details,
            }
        )
    return results


def print_scores_per_url() -> None:
    """Print the accessibility scores for all stored URLs and write to JSON."""
    entries = _load_bewertung()
    results = accessibility_score_per_url(entries)
    print("\nScores pro URL:")
    for res in results:
        print(f"{res['url']}: Score = {res['score']:.1f}, Gesamtabzug = {res['total_deduction']:.1f}")
        for d in res["issues"]:
            print(
                f"  - {d['label']}: Schweregrad {d['severity']} , Häufigkeit {d['frequency']} , "
                f"Typ‑Faktor {d['type_factor']} = {d['deduction']:.1f}"
            )
    with open("scores_per_url.json", "w", encoding="utf-8") as f:
        json.dump(results, f, indent=2, ensure_ascii=False)

    # Generate a score chart for each URL
    for idx, res in enumerate(results, start=1):
        url = res.get('url', '')
        issues = res.get('issues', [])
        _plot_url_issue_details(url, issues, idx)


def print_score_and_prioritization() -> None:
    """Print a prioritised list of issues and the overall score."""
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
    # Do not write score.json; only plot the top deductions diagram for visualisation


def _plot_url_issue_details(url: str, issues: List[Dict[str, object]], index: int, top_n: int = 10) -> None:
    """Plot a horizontal bar chart of the largest issue deductions for a single URL.

    Parameters
    ----------
    url: str
        The URL for which the issues are plotted (used only for labelling in logs).
    issues: List[Dict[str, object]]
        List of issue dictionaries for the page as returned by
        ``accessibility_score_per_url``.  Each dictionary should have
        keys ``label`` and ``deduction``.
    index: int
        A running index used to generate the file name of the chart.  The
        resulting file will be named ``score_chart_<index>.png``.
    top_n: int, optional
        The number of top issues to display in the chart (default: 10).

    This helper builds a horizontal bar chart similar to the global
    ``_plot_score_details`` but on a per‑page basis.  The file is saved
    directly into the current working directory.
    """
    if not issues:
        return
    # Take the top_n issues by deduction
    subset = sorted(issues, key=lambda d: d.get('deduction', 0), reverse=True)[:top_n]
    labels = [d.get('label', '') for d in subset]
    values = [d.get('deduction', 0) for d in subset]
    colors = plt.get_cmap('tab10').colors
    # Use a wider figure to accommodate long labels
    fig, ax = plt.subplots(figsize=(12, 7))
    ax.barh(labels, values, color=colors[5])
    ax.invert_yaxis()
    ax.set_xlabel("Punktabzug")
    ax.set_title(f"Top Barrierefreiheitsprobleme für Seite {index}")
    # Adjust layout and save with bbox_inches='tight' to prevent truncation of long labels
    fig.tight_layout()
    filename = f"score_chart_{index}.png"
    fig.savefig(filename, bbox_inches='tight')
    print(f"Per‑URL Score‑Diagramm wurde für {url} in {filename} gespeichert.")


def _visualise_scores_per_url(file_path: str = "scores_per_url.json") -> None:
    """Visualise per‑URL scores and total deductions in separate diagrams.

    This helper reads the ``scores_per_url.json`` file, which is created by
    ``print_scores_per_url``, and generates two bar charts: one for the
    accessibility score of each URL and one for the total deduction.  It
    additionally writes a summary text for screen readers.
    """
    if not os.path.exists(file_path):
        return
    try:
        with open(file_path, "r", encoding="utf-8") as f:
            data = json.load(f)
    except Exception as exc:
        print(f"Fehler beim Laden von {file_path}: {exc}")
        return
    if not isinstance(data, list) or not data:
        return
    urls = [entry.get("url", "unknown") for entry in data]
    scores = [entry.get("score", 0) for entry in data]
    deductions = [entry.get("total_deduction", 0) for entry in data]
    # Plot scores per URL
    numbers = list(range(1, len(urls) + 1))
    x = range(len(urls))
    fig, ax = plt.subplots(figsize=(10, 6))
    ax.bar(x, scores, color=plt.get_cmap("tab10").colors[6])
    ax.set_xticks(x)
    ax.set_xticklabels(numbers)
    ax.set_ylabel("Score")
    ax.set_title("Barrierefreiheits‑Score pro Seite")
    for i, value in enumerate(scores):
        ax.text(i, value + 0.5, f"{value:.1f}", ha="center", va="bottom", fontsize=10)
    mapping = "\n".join([f"{num}: {url}" for num, url in zip(numbers, urls)])
    fig.text(0.5, -0.15, mapping, ha="center", va="top", fontsize=9, wrap=True)
    fig.tight_layout()
    fig.savefig("scores_per_url_chart.png", bbox_inches="tight")
    print("Diagramm der Barrierefreiheits‑Scores pro Seite wurde in scores_per_url_chart.png gespeichert.")
    # Plot total deductions per URL
    fig2, ax2 = plt.subplots(figsize=(10, 6))
    ax2.bar(x, deductions, color=plt.get_cmap("tab10").colors[7])
    ax2.set_xticks(x)
    ax2.set_xticklabels(numbers)
    ax2.set_ylabel("Gesamtabzug")
    ax2.set_title("Gesamter Punktabzug pro Seite")
    for i, value in enumerate(deductions):
        ax2.text(i, value + 0.5, f"{value:.1f}", ha="center", va="bottom", fontsize=10)
    mapping2 = "\n".join([f"{num}: {url}" for num, url in zip(numbers, urls)])
    fig2.text(0.5, -0.15, mapping2, ha="center", va="top", fontsize=9, wrap=True)
    fig2.tight_layout()
    fig2.savefig("total_deduction_chart.png", bbox_inches="tight")
    print("Diagramm der Gesamtabzüge pro Seite wurde in total_deduction_chart.png gespeichert.")
    # Write a summary text for screen readers
    with open("scores_visualization_summary.txt", "w", encoding="utf-8") as f:
        f.write("Barrierefreiheits‑Scores und Gesamtabzüge pro Seite:\n")
        for num, url, score, ded in zip(numbers, urls, scores, deductions):
            f.write(f"{num}: {url} – Score: {score:.1f}, Gesamtabzug: {ded:.1f}\n")


if __name__ == "__main__":
    # Ensure Node.js meets the minimum version before starting tests
    if not _check_node_version():
        exit(1)
    delete_old_results()
    user_url = input("Gib eine URL ein (inkl. https://): ").strip()
    if not user_url.startswith("http"):
        print("Bitte mit http:// oder https:// beginnen.")
    else:
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
        combine_errors()
        delete_results()
        visualisation()
        print_score_and_prioritization()
        print_scores_per_url()