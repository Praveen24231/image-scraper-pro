// api/scrape.js — 100% Vercel Serverless Yandex Scraper (Zero Sleep, 24/7 Live)
export default async function handler(req, res) {
  res.setHeader('Access-Control-Allow-Credentials', 'true');
  res.setHeader('Access-Control-Allow-Origin', '*');
  res.setHeader('Access-Control-Allow-Methods', 'GET,POST,OPTIONS');
  res.setHeader('Access-Control-Allow-Headers', 'Content-Type');

  if (req.method === 'OPTIONS') return res.status(200).end();

  try {
    const { url, autoscroll } = req.body || req.query || {};
    if (!url) return res.status(400).json({ error: 'URL is required' });

    let decodedUrl = decodeURIComponent(url);
    if (!decodedUrl.startsWith('http://') && !decodedUrl.startsWith('https://')) {
      decodedUrl = 'https://' + decodedUrl;
    }

    const u = new URL(decodedUrl);
    const params = new URLSearchParams(u.search);
    const text = params.get('text') || params.get('query') || params.get('q') || 'wallpaper';

    const pagesToScrape = autoscroll ? 5 : 1; // 5 pages = ~150-200 images in < 3 seconds on Vercel
    const allUrls = [];
    const seen = new Set();

    const fetchPage = async (pageIdx) => {
      const pageUrl = `https://${u.hostname}/images/search?text=${encodeURIComponent(text)}&p=${pageIdx}`;
      try {
        const response = await fetch(pageUrl, {
          headers: {
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/125.0.0.0 Safari/537.36',
            'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,*/*;q=0.8',
            'Accept-Language': 'en-US,en;q=0.9',
            'Referer': 'https://yandex.com/'
          },
          signal: AbortSignal.timeout(5000)
        });
        const html = await response.text();

        // 1. Extract origUrl matches
        const origRegex = /"origUrl"\s*:\s*"(https?[^"]+)"/g;
        let match;
        while ((match = origRegex.exec(html)) !== null) {
          const imgUrl = match[1].replace(/\\/g, '');
          if (!seen.has(imgUrl) && imgUrl.startsWith('http')) {
            seen.add(imgUrl);
            allUrls.push(imgUrl);
          }
        }

        // 2. Extract img_url parameter matches
        const imgUrlRegex = /img_url=([^&"'\s<>]+)/g;
        while ((match = imgUrlRegex.exec(html)) !== null) {
          try {
            const imgUrl = decodeURIComponent(match[1]).replace(/\\/g, '');
            if (!seen.has(imgUrl) && imgUrl.startsWith('http')) {
              seen.add(imgUrl);
              allUrls.push(imgUrl);
            }
          } catch (e) {}
        }
      } catch (e) {}
    };

    const promises = [];
    for (let p = 0; p < pagesToScrape; p++) {
      promises.push(fetchPage(p));
    }
    await Promise.all(promises);

    const images = allUrls.map(imgUrl => ({
      url: imgUrl,
      thumb: imgUrl,
      alt: text,
      width: 'Original',
      height: 'Original'
    }));

    return res.status(200).json({ images, count: images.length, source: 'vercel-serverless' });
  } catch (err) {
    return res.status(500).json({ error: err.message });
  }
}
