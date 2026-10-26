// 방명록 API. 플랫폼이 /students/{링크이름}/api 접두사를 떼고 넘겨주므로 루트 기준 경로로 받는다.
const http = require('http');
const { Pool } = require('pg');
const { createClient } = require('redis');

const db = new Pool({ connectionString: process.env.DATABASE_URL, max: 3 });
const redis = createClient({ url: process.env.REDIS_URL });
const PREFIX = process.env.REDIS_KEY_PREFIX || '';  // 모든 키 앞에 반드시 붙인다
redis.on('error', (e) => console.error('redis', e.message));

async function init() {
  for (let i = 0; i < 20; i++) {
    try {
      await db.query(`CREATE TABLE IF NOT EXISTS messages (
        id serial PRIMARY KEY, name text NOT NULL, text text NOT NULL, created_at timestamptz DEFAULT now())`);
      break;
    } catch (e) {
      console.error('db 대기 중', e.message);
      await new Promise((r) => setTimeout(r, 1500));
    }
  }
  await redis.connect().catch((e) => console.error('redis 연결 실패', e.message));
}

const json = (res, code, body) => { res.writeHead(code, { 'Content-Type': 'application/json' }); res.end(JSON.stringify(body)); };
const readBody = (req) => new Promise((ok) => { let s = ''; req.on('data', (c) => (s += c).length > 10000 && req.destroy()); req.on('end', () => ok(s)); });

http.createServer(async (req, res) => {
  const path = req.url.split('?')[0];
  try {
    if (path === '/health') {
      const dbOk = await db.query('SELECT 1').then(() => 'ok', () => 'error');
      const redisOk = await redis.ping().then(() => 'ok', () => 'error');
      return json(res, 200, { ok: dbOk === 'ok' && redisOk === 'ok', db: dbOk, redis: redisOk, base: process.env.BASE_PATH });
    }
    if (path === '/messages' && req.method === 'GET') {
      const { rows } = await db.query('SELECT name, text, created_at FROM messages ORDER BY id DESC LIMIT 50');
      return json(res, 200, rows);
    }
    if (path === '/messages' && req.method === 'POST') {
      const { name, text } = JSON.parse((await readBody(req)) || '{}');
      if (!name || !text) return json(res, 400, { error: '이름과 내용이 필요해요' });
      await db.query('INSERT INTO messages (name, text) VALUES ($1, $2)', [String(name).slice(0, 30), String(text).slice(0, 300)]);
      return json(res, 201, { ok: true });
    }
    if (path === '/visits' && req.method === 'POST') {
      return json(res, 200, { visits: await redis.incr(PREFIX + 'visits') });
    }
    json(res, 404, { error: 'not found', path });
  } catch (e) {
    console.error(e);
    json(res, 500, { error: e.message });
  }
}).listen(3000, '0.0.0.0', () => console.log('api on :3000'));

init();
