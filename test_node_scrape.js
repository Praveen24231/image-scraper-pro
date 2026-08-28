const https = require('https');

function scrapeYandexNode(query) {
    return new Promise((resolve, reject) => {
        const url = `https://yandex.com/images/search?text=${encodeURIComponent(query)}&p=0`;
        const req = https.get(url, {
            headers: {
                'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/125.0.0.0 Safari/537.36',
                'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8',
                'Accept-Language': 'en-US,en;q=0.9'
            }
        }, (res) => {
            let data = '';
            res.on('data', chunk => data += chunk);
            res.on('end', () => {
                const origUrlRegex = /"origUrl"\s*:\s*"(https?[^"]+)"/g;
                const matches = [];
                let match;
                while ((match = origUrlRegex.exec(data)) !== null) {
                    matches.push(match[1].replace(/\\/g, ''));
                }
                resolve({ count: matches.length, samples: matches.slice(0, 5) });
            });
        });
        req.on('error', reject);
    });
}

scrapeYandexNode('bmw m4').then(console.log).catch(console.error);
