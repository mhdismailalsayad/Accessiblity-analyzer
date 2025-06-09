import json
from collections import Counter
from pathlib import Path


DEF_PATH = Path(__file__).with_name("bewertung.json")


def load_bewertung(path: Path = DEF_PATH):
    """Load rating data from JSON file."""
    with path.open("r", encoding="utf-8") as f:
        return json.load(f)


def count_issues(entries):
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


def count_common_errors(entries):
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


def write_summary_text(counts, counter, output: Path = Path("visualization_summary.txt")):
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


def plot_tool_comparison(counts, output: Path = Path("tool_comparison.png")):
    """Create a bar chart comparing issue counts per tool."""
    try:
        import matplotlib.pyplot as plt
    except ModuleNotFoundError:
        print("matplotlib is not installed; skipping tool comparison plot.")
        return

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


def plot_common_errors(counter: Counter, output: Path = Path("common_errors.png"), top_n: int = 10):
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


def main():
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
    main()