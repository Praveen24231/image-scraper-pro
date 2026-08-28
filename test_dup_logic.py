import html
import json
import re

def extract_best_dups(content):
    results = []
    # Find patterns like &quot;dups&quot;:[{...}]
    # We use a non-greedy match for the content between brackets
    matches = re.finditer(r'&quot;dups&quot;:\s*\[(.*?)]', content)
    
    for match in matches:
        try:
            # Unescape everything
            json_str = html.unescape(match.group(0))
            # Wrap in braces to make it a valid object
            parsed = json.loads("{" + json_str + "}")
            dups = parsed.get('dups', [])
            if dups:
                # Find the one with the largest area
                best = max(dups, key=lambda x: x.get('w', 0) * x.get('h', 0))
                results.append({
                    'url': best.get('url'),
                    'w': best.get('w'),
                    'h': best.get('h'),
                    'alt': 'Best Quality (from metadata)'
                })
        except Exception as e:
            # print(f"Error: {e}")
            continue
    return results

# Sample content from the diagnostic run
sample = """39065,&quot;w&quot;:714,&quot;h&quot;:400}],&quot;dups&quot;:[{&quot;url&quot;:&quot;https://static.vecteezy.com/system/resources/previews/049/855/274/large_2x/nature-background-high-resolution-wallpaper-for-a-serene-and-stunning-view-photo.jpg&quot;,&quot;fileSizeInBytes&quot;:571369,&quot;w&quot;:3497,&quot;h&quot;:1960},{&quot;url&quot;:&quot;https://i.pinimg.com/originals/1e/4c/f1/1e4cf186a1f408183cf757b192be5b5f.jpg&quot;,&quot;fileSizeInBytes&quot;:180126,&quot;w&quot;:1749,&quot;h&quot;:980}]"""

best_urls = extract_best_dups(sample)
for u in best_urls:
    print(f"Found: {u['w']}x{u['h']} -> {u['url']}")
