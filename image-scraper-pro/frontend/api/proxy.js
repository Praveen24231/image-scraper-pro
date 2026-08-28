// api/proxy.js
// Proxy that forwards the real user IP to Yandex so it looks like a residential request.

export default async function handler(req, res) {
  // CORS headers — allow our frontend to call this
  res.setHeader('Access-Control-Allow-Credentials', 'true');
  res.setHeader('Access-Control-Allow-Origin', '*');
  res.setHeader('Access-Control-Allow-Methods', 'GET,OPTIONS');
  res.setHeader('Access-Control-Allow-Headers', 'Accept, Accept-Version, Content-Type, Date');

  if (req.method === 'OPTIONS') {
    res.status(200).end();
    return;
  }

  const { url } = req.query;
  if (!url) return res.status(400).json({ error: 'Missing url' });

  let decodedUrl;
  try {
    decodedUrl = decodeURIComponent(url);
    if (!decodedUrl.startsWith('http://') && !decodedUrl.startsWith('https://'))
      throw new Error('bad protocol');
  } catch {
    return res.status(400).json({ error: 'Invalid URL' });
  }

  // Get the real user IP from Vercel's forwarding chain
  const userIp = (req.headers['x-forwarded-for'] || '').split(',')[0].trim()
              || req.headers['x-real-ip']
              || '1.1.1.1';

  // Forward the user's Cookie header if present (helps with Yandex session)
  const userCookie = req.headers['cookie'] || '';
  // Also accept a forwarded cookie from custom header
  const fwdCookie = req.headers['x-yandex-cookie'] || '';
  const cookieVal = fwdCookie || userCookie;

  const controller = new AbortController();
  const timeoutId = setTimeout(() => controller.abort(), 12000);

  try {
    const fetchHeaders = {
      'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/125.0.0.0 Safari/537.36',
      'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,*/*;q=0.8',
      'Accept-Language': 'en-US,en;q=0.9',
      'Cache-Control': 'no-cache',
      'Pragma': 'no-cache',
      'Sec-Ch-Ua': '"Chromium";v="125", "Not=A?Brand";v="8"',
      'Sec-Ch-Ua-Mobile': '?0',
      'Sec-Ch-Ua-Platform': '"Windows"',
      'Sec-Fetch-Dest': 'document',
      'Sec-Fetch-Mode': 'navigate',
      'Sec-Fetch-Site': 'same-origin',
      'Sec-Fetch-User': '?1',
      'Upgrade-Insecure-Requests': '1',
      // Forward the real user IP so Yandex sees a residential address
      'X-Forwarded-For': userIp,
      'X-Real-IP': userIp,
      // Referrer so it looks like a normal Yandex navigation
      'Referer': 'https://yandex.com/',
    };

    // Forward cookies if available
    if (cookieVal) fetchHeaders['Cookie'] = cookieVal;

    const response = await fetch(decodedUrl, {
      headers: fetchHeaders,
      redirect: 'follow',
      signal: controller.signal,
    });

    clearTimeout(timeoutId);

    const contentType = response.headers.get('content-type') || '';

    // Binary assets (images) — stream directly
    if (contentType.includes('image/') || contentType.includes('application/octet-stream')) {
      const buffer = await response.arrayBuffer();
      res.setHeader('Content-Type', contentType);
      res.setHeader('Cache-Control', 'public, max-age=86400');
      return res.status(200).send(Buffer.from(buffer));
    }

    // Text / HTML — check for captcha, then return
    const text = await response.text();
    const isCaptcha = text.includes('"type":"captcha"') || text.includes('showcaptcha') ||
                      (text.length < 15000 && text.includes('captcha'));

    return res.status(200).json({
      contents: text,
      contentType,
      statusCode: response.status,
      isCaptcha,
      userIp, // useful for debugging
    });

  } catch (error) {
    clearTimeout(timeoutId);
    return res.status(500).json({
      error: error.name === 'AbortError' ? 'Timeout (12s)' : error.message
    });
  }
}
