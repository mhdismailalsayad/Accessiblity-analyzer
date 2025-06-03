import requests
from bs4 import BeautifulSoup
from urllib.parse import urljoin, urlparse
import subprocess

# <<< Pfad zu npx.cmd anpassen >>>
NPX = r"C:\Users\memom\AppData\Roaming\npm\npx.cmd"

def ist_internal_link(base_url, link):
    base_domain = urlparse(base_url).netloc
    target_domain = urlparse(link).netloc
    return (target_domain == "" or target_domain == base_domain)

def finde_interne_links(start_url):
    visited = set()
    try:
        response = requests.get(start_url, timeout=10, headers={"User-Agent": "Mozilla/5.0"})
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
        print(f"\n✅ Alle {len(visited)} internen Links in 'gefundene_urls.txt' gespeichert.")
    except Exception as e:
        print(f"❌ Fehler beim Crawlen von {start_url}: {e}")
    return list(visited)

def run_pa11y(url):
    print(f"🔍 Pa11y: {url}")
    result = subprocess.run([NPX, "pa11y", "--reporter", "json", url], capture_output=True, text=True)
    print(result.stdout[:300])  # gekürzt

def run_axe(url):
    print(f"🧪 axe-core: {url}")
    result = subprocess.run([NPX, "@axe-core/cli", "-q", url], capture_output=True, text=True)
    print(result.stdout[:300])  # gekürzt

def run_lighthouse(url):
    print(f"💡 Lighthouse: {url}")
    result = subprocess.run([
        NPX, "lighthouse", url,
        "--only-categories=accessibility",
        "--output=json",
        "--chrome-flags=--headless",
        "--output-path=./lh_tmp.json"
    ], capture_output=True, text=True)
    print("Lighthouse fertig (Ausgabe in lh_tmp.json)")

def accessibility_checks(urls):
    for url in urls:
        print(f"\n=== 📄 Teste Seite: {url} ===")
        run_pa11y(url)
        run_axe(url)
        run_lighthouse(url)

if __name__ == "__main__":
    user_url = input("🔗 Gib eine URL ein (inkl. https://): ").strip()
    if not user_url.startswith("http"):
        print("❗ Bitte mit http:// oder https:// beginnen.")
    else:
        seiten = [user_url] + finde_interne_links(user_url)
        print(f"\n🚀 Starte Accessibility-Checks für {len(seiten)} Seiten...")
        accessibility_checks(seiten[:5])
