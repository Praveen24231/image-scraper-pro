import requests, json

url = "https://mfw-scrapper-praveen-daniel.vercel.app/api/proxy?url=https%3A%2F%2Fyandex.com%2Fimages%2Fsearch%3Ftext%3Dbmw%2Bm4"
r = requests.get(url, timeout=10)
data = r.json()
raw_html = data.get('contents', '')
print("HTML SNIPPET (first 1000 chars):")
print(raw_html[:1000])
