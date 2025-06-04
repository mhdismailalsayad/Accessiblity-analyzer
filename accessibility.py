import requests
from bs4 import BeautifulSoup
from urllib.parse import urljoin, urlparse
import subprocess
import json
import os
# <<< Pfad zu npx anpassen >>>
# Für Windows: NPX = r"C:\Users\memom\AppData\Roaming\npm\npx.cmd"
NPX = r"C:\Users\memom\AppData\Roaming\npm\npx.cmd"

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
        # Alle gefundenen Links speichern
        with open("gefundene_urls.txt", "w", encoding="utf-8") as f:
            for url in sorted(visited):
                f.write(url + "\n")
        print(f"\n Alle {len(visited)} internen Links in 'gefundene_urls.txt' gespeichert.")
    except Exception as e:
        print(f" Fehler beim Crawlen von {start_url}: {e}")
    return list(visited)


def run_pa11y(url, filename="pa11y_result.json"):
    print(f" Pa11y: {url}")
    result = subprocess.run([NPX, "pa11y", "--reporter", "json", url], capture_output=True, text=True)

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


def run_axe(url):
    print(f"axe-core: {url}")
    result = subprocess.run(
        [NPX, "@axe-core/cli", "-q", url],
        capture_output=True,
        text=True
    )
    
    try:
        with open("axe_result.txt", "a", encoding="utf-8") as f:
            f.write(f"\n=== Ergebnisse für: {url} ===\n")
            if result.stdout:
                f.write(result.stdout)
            else:
                f.write(" Keine Ausgabe von axe-core erhalten.\n")
            if result.stderr:
                f.write("\n[Fehlermeldung]\n" + result.stderr)
            f.write("\n\n")
        print(" axe-core-Ergebnisse gespeichert.")
    except Exception as e:
        print(f" Fehler beim Schreiben in die Datei: {e}")







def run_lighthouse(url, filename="lighthouse_results.json"):
    print(f"Lighthouse: {url}")
    result = subprocess.run([
        NPX, "lighthouse", url,
        "--only-categories=accessibility",
        "--output=json",
        "--chrome-flags=--headless",
        "--output-path=./lh_tmp.json"
    ], capture_output=True, text=True)

    if result.returncode != 0:
        print("Fehler bei Lighthouse:", result.stderr)
        return

    try:
        with open("lh_tmp.json", "r", encoding="utf-8") as tmp_file:
            data = json.load(tmp_file)

        entry = {
            "url": url,
            "lighthouse_result": data
        }

        try:
            with open(filename, "r", encoding="utf-8") as f:
                all_data = json.load(f)
        except (FileNotFoundError, json.JSONDecodeError):
            all_data = []

        all_data.append(entry)

        with open(filename, "w", encoding="utf-8") as out_file:
            json.dump(all_data, out_file, indent=2, ensure_ascii=False)

        os.remove("lh_tmp.json")

    except Exception as e:
        print(f"Fehler beim Lesen/Speichern von Lighthouse-Ergebnissen: {e}")

def accessibility_checks(urls):
    for url in urls:
        print(f"\n=== Teste Seite: {url} ===")
        run_pa11y(url)
        run_axe(url)
        run_lighthouse(url)




def convert_pa11y_to_custom_format():
    input_file = "pa11y_result.json"
    output_file = "end_ergebnis.json"

    try:
        with open(input_file, "r", encoding="utf-8") as f:
            data = json.load(f)

        # Wir erwarten eine Liste von Einträgen, jeder mit "url" und "results"
        output_list = []

        for entry in data:
            url_obj = {"url": entry.get("url", "")}
            output_list.append(url_obj)

            for result in entry.get("results", []):
                filtered_result = {
                    "message": result.get("message", ""),
                    "context": result.get("context", "")
                }
                output_list.append(filtered_result)

        with open(output_file, "w", encoding="utf-8") as out:
            json.dump(output_list, out, indent=2, ensure_ascii=False)

        print(f"Ergebnis gespeichert in '{output_file}'.")

    except Exception as e:
        print(f"Fehler beim Verarbeiten der Datei: {e}")


def _load_json(path):
    """Lädt eine JSON-Datei oder gibt eine leere Liste zurück."""
    try:
        with open(path, "r", encoding="utf-8") as f:
            return json.load(f)
    except (FileNotFoundError, json.JSONDecodeError):
        return []


def _combine_tool_results(pa11y_data, lighthouse_data):
    """Kombiniert Ergebnisse verschiedener Tools und vermeidet Duplikate."""
    combined = {}

    for entry in pa11y_data:
        url = entry.get("url")
        if not url:
            continue
        combined.setdefault(url, {"pa11y": [], "lighthouse": [], "lh_score": 1})
        for res in entry.get("results", []):
            msg = res.get("message", "")
            severity = res.get("typeCode", 3)
            combined[url]["pa11y"].append((msg, severity))

    for entry in lighthouse_data:
        url = entry.get("url")
        if not url:
            continue
        combined.setdefault(url, {"pa11y": [], "lighthouse": [], "lh_score": 1})
        lh_result = entry.get("lighthouse_result", {})
        audits = lh_result.get("audits", {})
        fail_msgs = []
        for audit in audits.values():
            if audit.get("score") is not None and audit.get("score") < 1:
                fail_msgs.append(audit.get("title", ""))
        combined[url]["lighthouse"] = fail_msgs
        acc_cat = lh_result.get("categories", {}).get("accessibility", {})
        combined[url]["lh_score"] = acc_cat.get("score", 1)
    return combined


def _calculate_scores(combined):
    """Berechnet eine Bewertung pro Seite basierend auf Schwere der Probleme."""
    scores = {}
    for url, data in combined.items():
        seen = set()
        penalty = 0
        for msg, sev in data.get("pa11y", []):
            if msg in seen:
                continue
            seen.add(msg)
            if sev == 1:
                penalty += 5  # Fehler
            elif sev == 2:
                penalty += 3  # Warnung
            else:
                penalty += 1  # Hinweis
        for msg in data.get("lighthouse", []):
            if msg not in seen:
                seen.add(msg)
                penalty += 2
        base = data.get("lh_score", 1) * 100
        scores[url] = max(0, round(base - penalty, 2))
    return scores


def create_rating(pa11y_file="pa11y_result.json", lighthouse_file="lighthouse_results.json", output="bewertung.json"):
    """Erstellt eine Bewertung pro Seite und speichert sie als JSON."""
    pa11y_data = _load_json(pa11y_file)
    lighthouse_data = _load_json(lighthouse_file)

    if not pa11y_data and not lighthouse_data:
        print("Keine Ergebnisdaten für die Bewertung gefunden.")
        return

    combined = _combine_tool_results(pa11y_data, lighthouse_data)
    scores = _calculate_scores(combined)

    rating = {
        "info": "Tools kombinieren",
        "scores": scores,
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
        "axe_result.txt",
        "lighthouse_results.json",
        "pa11y_result.json"
    ]

    for file in temp_files:
        if os.path.exists(file):
            os.remove(file)




if __name__ == "__main__":

        delete_old_results()
        user_url = input(" Gib eine URL ein (inkl. https://) : ").strip()
        if not user_url.startswith("http"):
            print(" Bitte mit http:// oder https:// beginnen.")
        else:
            seiten = [user_url] + finde_interne_links(user_url)
            print(f"\n Starte Accessibility-Checks für {len(seiten)} Seiten...")
            accessibility_checks(seiten[:1])
            convert_pa11y_to_custom_format()
            create_rating()
