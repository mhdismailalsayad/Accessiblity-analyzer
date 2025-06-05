import json
import os


def load_json(path):
    """Load JSON from ``path`` or return an empty list."""
    try:
        with open(path, "r", encoding="utf-8") as fh:
            data = json.load(fh)
            # Some result files may contain a single object instead of a list.
            # Normalise to a list so downstream code can iterate safely.
            if isinstance(data, dict):
                return [data]
            return data
    except (FileNotFoundError, json.JSONDecodeError):
        return []


def combine_tool_results(pa11y_data, lighthouse_data, axe_data):
    """Combine results from Pa11y, Lighthouse and Axe and remove duplicates."""
    combined = {}

    for entry in pa11y_data:
        url = entry.get("url")
        if not url:
            continue
        combined.setdefault(url, {"pa11y": [], "lighthouse": [], "axe": [], "lh_score": 1})
        for res in entry.get("results", []):
            msg = res.get("message", "")
            sev = res.get("typeCode", 3)
            combined[url]["pa11y"].append((msg, sev))

    for entry in lighthouse_data:
        url = entry.get("url")
        if not url:
            continue
        combined.setdefault(url, {"pa11y": [], "lighthouse": [], "axe": [], "lh_score": 1})
        lh_result = entry.get("lighthouse_result", {})
        audits = lh_result.get("audits", {})
        msgs = []
        for audit in audits.values():
            if audit.get("score") is not None and audit.get("score") < 1:
                msgs.append(audit.get("title", ""))
        combined[url]["lighthouse"] = msgs
        acc_cat = lh_result.get("categories", {}).get("accessibility", {})
        combined[url]["lh_score"] = acc_cat.get("score", 1)

    for entry in axe_data:
        url = entry.get("url")
        if not url:
            continue
        combined.setdefault(url, {"pa11y": [], "lighthouse": [], "axe": [], "lh_score": 1})

        axe_result = entry.get("axe_result", {})

        # ``axe_result`` can be either a single result object or a list of such
        # objects depending on the axe-core CLI version. Normalize to a list for
        # consistent processing.
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


def calculate_scores(combined):
    """Calculate a score per page based on severity of issues."""
    scores = {}
    for url, data in combined.items():
        seen = set()
        penalty = 0
        for msg, sev in data.get("pa11y", []):
            if msg in seen:
                continue
            seen.add(msg)
            if sev == 1:
                penalty += 5
            elif sev == 2:
                penalty += 3
            else:
                penalty += 1

        for msg, sev in data.get("axe", []):
            if msg in seen:
                continue
            seen.add(msg)
            penalty += sev

        for msg in data.get("lighthouse", []):
            if msg not in seen:
                seen.add(msg)
                penalty += 2

        base = data.get("lh_score", 1) * 100
        scores[url] = max(0, round(base - penalty, 2))
    return scores


def create_rating(pa11y_file="pa11y_result.json", lighthouse_file="lighthouse_results.json", axe_file="axe_result.json", output="bewertung.json"):
    """Load tool results, combine them and store a rating per page."""
    pa11y_data = load_json(pa11y_file)
    lighthouse_data = load_json(lighthouse_file)
    axe_data = load_json(axe_file)

    if not pa11y_data and not lighthouse_data and not axe_data:
        print("Keine Ergebnisdaten für die Bewertung gefunden.")
        return

    combined = combine_tool_results(pa11y_data, lighthouse_data, axe_data)
    scores = calculate_scores(combined)

    rating = {
        "info": "Tools kombiniert, Duplikate entfernt",
        "scores": scores,
    }

    try:
        with open(output, "w", encoding="utf-8") as fh:
            json.dump(rating, fh, indent=2, ensure_ascii=False)
        print(f"Bewertung in '{output}' gespeichert.")
    except Exception as exc:
        print(f"Fehler beim Speichern der Bewertung: {exc}")


if __name__ == "__main__":
    create_rating()
