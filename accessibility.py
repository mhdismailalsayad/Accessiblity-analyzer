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
