import subprocess

def run_pa11y(url):
    print(f"\n🔍 Pa11y scan für {url}")
    result = subprocess.run(
        [r"C:\Users\memom\AppData\Roaming\npm\npx.cmd", "pa11y", "--reporter", "json", url],
        capture_output=True,
        text=True
    )
    print(result.stdout)


def run_axe(url):
    print(f"\n🧪 axe-core scan für {url}")
    result = subprocess.run(["npx", "@axe-core/cli", "-q", url], capture_output=True, text=True)
    print(result.stdout)

def run_lighthouse(url):
    print(f"\n💡 Lighthouse scan für {url}")
    result = subprocess.run([
        "npx", "lighthouse", url,
        "--only-categories=accessibility",
        "--chrome-flags=--headless",
        "--output=json",
        "--output-path=./lighthouse_report.json"
    ], capture_output=True, text=True)
    print(result.stdout)

def run_all_tools_for(url):
    run_pa11y(url)
    run_axe(url)
    run_lighthouse(url)

# Beispiel: URLs testen
if __name__ == "__main__":
    urls = [
        "https://zeit.de",
        "https://example.com"
    ]
    for url in urls:
        run_all_tools_for(url)
