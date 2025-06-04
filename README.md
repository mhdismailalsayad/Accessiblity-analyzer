# Website Accessibility Analyzer

A simple Python-based **Accessibility Analyzer** that crawls a website, collects internal links, and runs automated accessibility checks using:

- [Pa11y](https://github.com/pa11y/pa11y)
- [axe-core/cli](https://github.com/dequelabs/axe-core-npm)
- [Lighthouse](https://github.com/GoogleChrome/lighthouse)

Results are saved in an easy-to-read CSV file for further analysis.

---

## Features

- Crawl a given URL and extract internal links  
- Run multiple accessibility tools: Pa11y, Axe, Lighthouse  
- Save results as:
  - `gefundene_urls.txt` → list of internal URLs
  - `ergebnisse.csv` → accessibility results per page

---

## Requirements

- Python 3.x
- `requests`
- `beautifulsoup4`
- Node.js with global installs of:
  - `pa11y`
  - `@axe-core/cli`
  - `lighthouse`

---

## Installation

1. Clone the repository:

```
git clone https://github.com/mhdismailalsayad/Accessiblity-analyzer.git
cd Accessiblity-analyzer

```
2. Install Python dependencies:
   ```bash
   pip install requests beautifulsoup4
   ```
3. Install Node.js CLI tools globally:
   ```bash
   npm install -g pa11y @axe-core/cli lighthouse
   ```

## Usage
- Run the script: python accessibility.py
- You will be prompted to enter a URL:
- The script will:
    - Crawl the page
    - Extract internal links
    - Run accessibility tests
    - Save the results
