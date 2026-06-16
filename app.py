import os
import time
import requests
import xml.etree.ElementTree as ET
from bs4 import BeautifulSoup
from flask import Flask, jsonify, render_template, request

app = Flask(__name__)

# Cache structure: { "data": list, "timestamp": float }
FEED_CACHE = {
    "data": None,
    "timestamp": 0
}
CACHE_DURATION_SECS = 300  # 5 minutes cache

FEED_URL = "https://docs.cloud.google.com/feeds/bigquery-release-notes.xml"
HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
}

def parse_html_content(html_content):
    """Parses BigQuery HTML release content into structured updates."""
    if not html_content:
        return []
    
    soup = BeautifulSoup(html_content, "html.parser")
    items = []
    
    current_type = None
    current_elements = []
    
    for child in soup.contents:
        if child.name == 'h3':
            # Save previous item
            if current_type and current_elements:
                html_str = "".join(str(el) for el in current_elements).strip()
                text_str = BeautifulSoup(html_str, "html.parser").get_text().strip()
                items.append({
                    "type": current_type,
                    "html": html_str,
                    "text": text_str
                })
            current_type = child.get_text().strip()
            current_elements = []
        elif child.name is not None:
            current_elements.append(child)
            
    # Save the last item
    if current_type and current_elements:
        html_str = "".join(str(el) for el in current_elements).strip()
        text_str = BeautifulSoup(html_str, "html.parser").get_text().strip()
        items.append({
            "type": current_type,
            "html": html_str,
            "text": text_str
        })
        
    # If no <h3> was found, treat the whole content as a single update
    if not items and soup.get_text().strip():
        items.append({
            "type": "Update",
            "html": str(soup),
            "text": soup.get_text().strip()
        })
        
    return items

def fetch_feed():
    """Fetches the Atom feed and parses it into JSON-serializable list."""
    try:
        response = requests.get(FEED_URL, headers=HEADERS, timeout=15)
        response.raise_for_status()
        
        root = ET.fromstring(response.content)
        ns = {"atom": "http://www.w3.org/2005/Atom"}
        
        entries = []
        for entry in root.findall("atom:entry", ns):
            title_el = entry.find("atom:title", ns)
            date_str = title_el.text if title_el is not None else "Unknown Date"
            
            updated_el = entry.find("atom:updated", ns)
            updated_str = updated_el.text if updated_el is not None else ""
            
            id_el = entry.find("atom:id", ns)
            entry_id = id_el.text if id_el is not None else ""
            
            link_el = entry.find("atom:link[@rel='alternate']", ns)
            if link_el is None:
                link_el = entry.find("atom:link", ns)
            link_href = link_el.attrib.get("href", "") if link_el is not None else ""
            
            content_el = entry.find("atom:content", ns)
            content_html = content_el.text if content_el is not None else ""
            
            # Parse individual updates within this release entry
            updates = parse_html_content(content_html)
            
            entries.append({
                "id": entry_id,
                "date": date_str,
                "updated": updated_str,
                "link": link_href,
                "updates": updates
            })
            
        return entries, None
    except Exception as e:
        return None, str(e)

@app.route("/")
def index():
    return render_template("index.html")

@app.route("/api/releases")
def get_releases():
    force_refresh = request.args.get("force", "false").lower() == "true"
    current_time = time.time()
    
    if force_refresh or not FEED_CACHE["data"] or (current_time - FEED_CACHE["timestamp"] > CACHE_DURATION_SECS):
        data, error = fetch_feed()
        if error:
            # If fetch fails but we have stale cache, return stale cache with warning
            if FEED_CACHE["data"]:
                return jsonify({
                    "releases": FEED_CACHE["data"],
                    "warning": f"Could not refresh: {error}. Displaying cached data.",
                    "cached_at": FEED_CACHE["timestamp"]
                })
            return jsonify({"error": f"Failed to fetch release notes: {error}"}), 500
        
        FEED_CACHE["data"] = data
        FEED_CACHE["timestamp"] = current_time
        
    return jsonify({
        "releases": FEED_CACHE["data"],
        "cached_at": FEED_CACHE["timestamp"]
    })

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5000, debug=True)
