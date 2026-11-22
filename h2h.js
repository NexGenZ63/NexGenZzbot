const fs = require('fs'), path = require('path');
const seasons = () => { const d = new Date(), y = d.getMonth() >= 8 ? d.getFullYear() : d.getFullYear() - 1; return [y - 2, y - 1, y].map(s => `${s}${s + 1}`); };
const MK = ['points', 'goals', 'assists', 'shots'];
const ab = x => (x && x.default) || x;
const st = v => { v = v.filter(x => x != null); if (!v.length) return null; const s = v.filter(x => x >= 1).length; return { n: v.length, s, hit: s / v.length, avg: v.reduce((a, b) => a + b, 0) / v.length }; };
const sm = x => x ? (x.s + 1) / (x.n + 2) : null;

async function pool(items, fn, k = 12) {
  let i = 0;
  await Promise.all(Array.from({ length: k }, async () => {
    while (i < items.length) { const j = i++; try { await fn(items[j]); } catch (e) {} }
  }));
}

async function h2hGames(get, a, h) {
  const rs = await Promise.all(seasons().flatMap(s => [a, h].map(t => get(`/club-schedule-season/${t}/${s}`, 3600000).catch(() => null))));
  const m = {};
  for (const d of rs) if (d) for (const g of d.games) {
    const aa = g.awayTeam.abbrev, hh = g.homeTeam.abbrev;
    if (g.gameType === 2 && ['OFF', 'FINAL'].includes(g.gameState) && ((aa === a && hh === h) || (aa === h && hh === a)))
      m[g.id] = { id: g.id, date: g.gameDate, away: aa, home: hh, as: g.awayTeam.score, hs: g.homeTeam.score };
  }
  return Object.values(m).sort((x, y) => y.date.localeCompare(x.date));
}

async function load(get, team, opp, ids) {
  const r = await get(`/roster/${team}/current`, 1800000);
  const pl = [...r.forwards, ...r.defensemen].map(p => ({ id: p.id, name: p.firstName.default + ' ' + p.lastName.default, team, img: p.headshot }));
  await pool(pl, async p => {
    const ls = await Promise.all(seasons().map(s => get(`/player/${p.id}/game-log/${s}/2`, 3600000).catch(() => null)));
    const m = {};
    ls.forEach(l => l && l.gameLog.forEach(g => m[g.gameId] = g));
    p.log = Object.values(m).sort((a, b) => b.gameDate.localeCompare(a.gameDate));
    p.vs = p.log.filter(g => ab(g.opponentAbbrev) === opp && ids.has(g.gameId));
  });
  return pl.filter(p => p.log);
}

module.exports = async (u, res, get) => {
  if (u.pathname === '/h2h') {
    res.writeHead(200, { 'Content-Type': 'text/html; charset=utf-8' });
    res.end(fs.readFileSync(path.join(__dirname, 'public', 'h2h.html')));
    return true;
  }
  if (u.pathname !== '/api/h2h') return false;
  try {
    const q = u.searchParams, A = q.get('away'), H = q.get('home');
    const mk = MK.includes(q.get('market')) ? q.get('market') : 'points', algo = q.get('algo') === 'form' ? 'form' : 'h2h';
    const games = await h2hGames(get, A, H), ids = new Set(games.map(g => g.id));
    const [pa, ph] = await Promise.all([load(get, A, H, ids), load(get, H, A, ids)]);
    const sc = x => .6 * x.r10.hit + .4 * (x.r20 || x.r10).hit;
    const rows = [...pa, ...ph].map(p => {
      const c = n => p.log.slice(0, n).map(g => g[mk]);
      return { p, h: st(p.vs.map(g => g[mk])), r5: st(c(5)), r10: st(c(10)), r20: st(c(20)) };
    }).filter(x => algo === 'h2h' ? x.h : x.r10 && x.r10.n >= 5);
    rows.sort(algo === 'h2h' ? (a, b) => b.h.avg - a.h.avg || b.h.hit - a.h.hit || b.h.n - a.h.n : (a, b) => sc(b) - sc(a) || b.r10.avg - a.r10.avg);
    const top = rows.slice(0, 5).map(x => {
      let prob = null, conf = null;
      if (mk !== 'shots') {
        const a = sm(x.r10), o = algo === 'form' ? x.r20 : x.h, b = sm(o), w = algo === 'form' ? .6 : .7;
        prob = a != null && b != null ? w * a + (1 - w) * b : (a ?? b);
        conf = Math.max(0, Math.min(100, Math.round(25 + Math.min(x.r10 ? x.r10.n : 0, 10) * 3 + Math.min(o ? o.n : 0, 5) * 4 + (a != null && b != null ? 25 * (1 - Math.abs(a - b)) : 0))));
      }
      return { name: x.p.name, team: x.p.team, img: x.p.img, h: x.h, r5: x.r5, r10: x.r10, r20: x.r20, prob, conf,
        hist: x.p.vs.slice(0, 8).map(g => ({ d: g.gameDate, home: g.homeRoadFlag === 'H', v: g[mk] })) };
    });
    res.writeHead(200, { 'Content-Type': 'application/json' });
    res.end(JSON.stringify({ scores: games.slice(0, 5), top }));
  } catch (e) {
    res.writeHead(502, { 'Content-Type': 'application/json' });
    res.end(JSON.stringify({ error: String(e.message) }));
  }
  return true;
};
