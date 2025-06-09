
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


# Pfad zu "npx" plattformunabhängig bestimmen. Unter Windows wird "npx.cmd"
# verwendet, auf anderen Systemen reicht "npx".
if os.name == "nt":
    NPX = "npx.cmd"
else:
    NPX = "npx"

def _check_node_version(min_major=20):
    """Return True if the installed Node.js version meets the requirement."""
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
    base_domain = urlparse(base_url).netloc
    target_domain = urlparse(link).netloc
    return (target_domain == "" or target_domain == base_domain)

def finde_interne_links(start_url):
    visited = set()
    try:
        response = requests.get(start_url)
        soup = BeautifulSoup(response.text, 'html.parser')
        for a_tag in soup.find_all('a', href=True):
            raw_link = a_tag['href']
            full_url = urljoin(start_url, raw_link)
            if ist_internal_link(start_url, full_url):
                visited.add(full_url)
    except requests.RequestException as e:
        print(f"Fehler beim Abrufen der Seite {start_url}: {e}")
        return []
    return list(visited)


def run_pa11y(url, filename="pa11y_result.json"):
    print(f" Pa11y: {url}")
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
    """Führt axe-core aus und speichert das Ergebnis als JSON."""
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
    print(" axe-core-Ergebnisse gespeichert.")







def run_lighthouse(url, filename="lighthouse_results.json"):
    """Run Lighthouse for ``url`` and append the JSON result to ``filename``."""
    print(f"Lighthouse: {url}")

    # Use a temporary file for the Lighthouse output to avoid permission issues
    # on some platforms (e.g. Windows). The file is removed afterwards.
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
    for url in urls:
        print(f"\n=== Teste Seite: {url} ===")
        run_pa11y(url)
        run_axe(url)
        run_lighthouse(url)


def _extract_pa11y_errors(data):
    """Return a list of dicts with message and context from Pa11y results."""
    errors = []
    for entry in data:
        for res in entry.get("results", []):
            if res.get("type") == "error":
                errors.append({
                    "message": res.get("message", ""),
                    "context": res.get("context", ""),
                })
    return errors


def _extract_axe_errors(data):
    """Return a list of dicts with message and context from Axe results."""
    errors = []
    for entry in data:
        axe_result = entry.get("axe_result", {})
        results = axe_result if isinstance(axe_result, list) else [axe_result]
        for result in results:
            for viol in result.get("violations", []):
                msg = viol.get("help", viol.get("description", ""))
                for node in viol.get("nodes", []):
                    errors.append({
                        "message": msg,
                        "context": node.get("html", ""),
                    })
    return errors


def _extract_lighthouse_errors(data):
    """Return a list of dicts with message and context from Lighthouse results."""
    errors = []
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
                        context = node.get("snippet", "")
                        msg = node.get("explanation", title)
                        errors.append({"message": msg, "context": context})
                else:
                    errors.append({"message": title, "context": ""})
    return errors


def combine_errors(
    pa11y_file="pa11y_result.json",
    axe_file="axe_result.json",
    lighthouse_file="lighthouse_results.json",
    output="bewertung.json",
):
    """Combine errors from all tools and write them to ``output``.

    The resulting JSON is a list of objects, each containing the URL and a
    message/context list for every tool. A unified list ``All tools`` merges and
    deduplicates messages across Pa11y, Axe and Lighthouse.
    """

    pa11y_data = _load_json(pa11y_file)
    axe_data = _load_json(axe_file)
    lighthouse_data = _load_json(lighthouse_file)

    grouped = {}

    # Collect Pa11y errors
    for entry in pa11y_data:
        url = entry.get("url")
        if not url:
            continue
        grouped.setdefault(url, {"pa11y": [], "axe": [], "lighthouse": []})
        grouped[url]["pa11y"].extend(_extract_pa11y_errors([entry]))

    # Collect Axe errors
    for entry in axe_data:
        url = entry.get("url")
        if not url:
            continue
        grouped.setdefault(url, {"pa11y": [], "axe": [], "lighthouse": []})
        grouped[url]["axe"].extend(_extract_axe_errors([entry]))

    # Collect Lighthouse errors
    for entry in lighthouse_data:
        url = entry.get("url")
        if not url:
            lh = entry.get("lighthouse_result", {})
            url = lh.get("finalUrl") or lh.get("requestedUrl")
        if not url:
            continue
        grouped.setdefault(url, {"pa11y": [], "axe": [], "lighthouse": []})
        grouped[url]["lighthouse"].extend(_extract_lighthouse_errors([entry]))

    # Build final list in requested format
    result_list = []
    for url, data in grouped.items():
        seen = set()
        all_tools = []
        for tool_name in ("pa11y", "axe", "lighthouse"):
            for err in data[tool_name]:
                key = (err.get("message", ""), err.get("context", ""))
                if key not in seen:
                    seen.add(key)
                    all_tools.append(err)

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
            # Einige Ergebnisdateien enthalten nur ein einzelnes
            # Objekt. Um die Verarbeitung zu vereinfachen, wird ein
            # solches Objekt in eine Liste gepackt.
            if isinstance(data, dict):
                return [data]
            return data
    except (FileNotFoundError, json.JSONDecodeError):
        return []


def _combine_tool_results(pa11y_data, lighthouse_data, axe_data):
    """Kombiniert Ergebnisse der drei Tools und vermeidet Duplikate."""
    combined = {}

    for entry in pa11y_data:
        url = entry.get("url")
        if not url:
            continue
        combined.setdefault(url, {"pa11y": [], "lighthouse": [], "axe": [], "lh_score": 1})
        for res in entry.get("results", []):
            msg = res.get("message", "")
            severity = res.get("typeCode", 3)
            combined[url]["pa11y"].append((msg, severity))

    for entry in lighthouse_data:
        url = entry.get("url")
        if not url:
            continue
        combined.setdefault(url, {"pa11y": [], "lighthouse": [], "axe": [], "lh_score": 1})
        lh_result = entry.get("lighthouse_result", {})
        audits = lh_result.get("audits", {})
        fail_msgs = []
        for audit in audits.values():
            if audit.get("score") is not None and audit.get("score") < 1:
                fail_msgs.append(audit.get("title", ""))
        combined[url]["lighthouse"] = fail_msgs
        acc_cat = lh_result.get("categories", {}).get("accessibility", {})
        combined[url]["lh_score"] = acc_cat.get("score", 1)

    for entry in axe_data:
        url = entry.get("url")
        if not url:
            continue
        combined.setdefault(url, {"pa11y": [], "lighthouse": [], "axe": [], "lh_score": 1})

        axe_result = entry.get("axe_result", {})

        # ``axe_result`` may be a single object or a list of objects.
        if isinstance(axe_result, list):
            results = axe_result
        else:
            results = [axe_result]

        for result in results:
            violations = result.get("violations", [])
            for viol in violations:
                msg = viol.get("help", viol.get("description", ""))
                impact = viol.get("impact", "minor")
                severity = {"minor": 1, "moderate": 3, "serious": 5, "critical": 7}.get(impact, 1)
                combined[url]["axe"].append((msg, severity))
    return combined


def _extract_messages(combined):
    """Gibt alle Meldungen pro URL gruppiert nach Tool zurück."""
    results = {}
    for url, data in combined.items():
        pa11y_msgs = [msg for msg, _ in data.get("pa11y", [])]
        axe_msgs = [msg for msg, _ in data.get("axe", [])]
        lighthouse_msgs = data.get("lighthouse", [])

        all_msgs = []
        seen = set()
        for m in pa11y_msgs + axe_msgs + lighthouse_msgs:
            if m not in seen:
                seen.add(m)
                all_msgs.append(m)

        results[url] = {
            "all_tools": all_msgs,
            "pa11y": pa11y_msgs,
            "axe": axe_msgs,
            "lighthouse": lighthouse_msgs,
        }
    return results


def create_rating(pa11y_file="pa11y_result.json", lighthouse_file="lighthouse_results.json", axe_file="axe_result.json", output="bewertung.json"):
    """Erstellt eine Bewertung pro Seite und speichert sie als JSON."""
    """Kombiniert Ergebnisse der Tools und speichert sie in einer JSON-Datei."""
    pa11y_data = _load_json(pa11y_file)
    lighthouse_data = _load_json(lighthouse_file)
    axe_data = _load_json(axe_file)

    if not pa11y_data and not lighthouse_data and not axe_data:
        print("Keine Ergebnisdaten für die Bewertung gefunden.")
        return

    combined = _combine_tool_results(pa11y_data, lighthouse_data, axe_data)
    messages = _extract_messages(combined)

    rating = {
        "info": "Tools kombinieren",
        "scores": messages,
    }

    try:
        with open(output, "w", encoding="utf-8") as f:
            json.dump(rating, f, indent=2, ensure_ascii=False)
        print(f"Bewertung in '{output}' gespeichert.")
    except Exception as e:
        print(f"Fehler beim Speichern der Bewertung: {e}")



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



DEF_PATH = Path(__file__).with_name("bewertung.json")


def _load_bewertung(path: Path = DEF_PATH):
    """Load rating data from JSON file."""
    with path.open("r", encoding="utf-8") as f:
        return json.load(f)


def _count_issues(entries):
    """Return list of issue counts per tool for every URL."""
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
    """Return Counter of issue messages across all tools and URLs."""
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
    """Write a textual summary of the visualization data for screen readers."""
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
    """Create a bar chart comparing issue counts per tool."""
    labels = [c["url"] for c in counts]
    pa11y = [c["pa11y"] for c in counts]
    axe = [c["axe"] for c in counts]
    lighthouse = [c["lighthouse"] for c in counts]
    all_tools = [c["all"] for c in counts]
    colors = plt.get_cmap("tab10").colors

    x = range(len(labels))
    width = 0.2
    fig, ax = plt.subplots(figsize=(10, 6))
    ax.bar([p - 1.5 * width for p in x], pa11y, width, label="pa11y", color=colors[0])
    ax.bar([p - 0.5 * width for p in x], axe, width, label="axe", color=colors[1])
    ax.bar([p + 0.5 * width for p in x], lighthouse, width, label="lighthouse", color=colors[2])
    ax.bar([p + 1.5 * width for p in x], all_tools, width, label="all tools", color=colors[3])
    ax.set_xticks(list(x))
    ax.set_xticklabels(labels, rotation=45, ha="right")
    ax.set_ylabel("Number of issues")
    ax.set_title("Accessibility issues per page")
    ax.legend()
    fig.tight_layout()
    fig.savefig(output)
    print(f"Tool comparison saved to {output}")


def _plot_common_errors(counter: Counter, output: Path = Path("common_errors.png"), top_n: int = 10):
    """Plot the most frequent accessibility issues."""
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
    entries = load_bewertung()
    counts = count_issues(entries)
    counter = count_common_errors(entries)

    print("Issues per tool and page:")
    for c in counts:
        print(c)
    print()
    print("Most common issues:")
    for msg, num in counter.most_common(5):
        print(f"{num}x {msg}")

    plot_tool_comparison(counts)
    plot_common_errors(counter)
    write_summary_text(counts, counter)



if __name__ == "__main__":
        if not _check_node_version():
            exit(1)
        delete_old_results()
        user_url = input(" Gib eine URL ein (inkl. https://) : ").strip()
        if not user_url.startswith("http"):
            print(" Bitte mit http:// oder https:// beginnen.")
        else:
            seiten = [user_url] + finde_interne_links(user_url)
            print(f"\n Starte Accessibility-Checks für {len(seiten)} Seiten...")
            anzahl_seiten = int(input(" Wie viele Seiten sollen getestet werden? (0 für alle): ").strip())
            if anzahl_seiten == 0:
                print(" Keine internen Links gefunden.")
            else:
                print(f" Gefundene Seiten: {anzahl_seiten}")
                print(" Starte Accessibility-Checks...")
            accessibility_checks(seiten[:anzahl_seiten])
            combine_errors()
            visualisation()
