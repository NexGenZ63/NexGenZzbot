// PuckScore NHL – serveur sans dépendance (Node 18+)
const http = require('http'), fs = require('fs'), path = require('path');
const API = 'https://api-web.nhle.com/v1', PORT = process.env.PORT || 3000, N = 100000;
const cache = new Map();

async function get(p, ttl = 300000) {
  const c = cache.get(p);
  if (c && Date.now() - c.t < ttl) return c.d;
  const r = await fetch(API + p);
  if (!r.ok) throw new Error(r.status + ' ' + p);
  const d = await r.json();
  cache.set(p, { t: Date.now(), d });
  return d;
}

const pois = l => { const L = Math.exp(-l); let k = 0, p = 1; do { k++; p *= Math.random(); } while (p > L); return k - 1; };
const rate = s => {
  const gp = s.gamesPlayed || 1, l = s.l10GamesPlayed || 1;
  return { gf: .6 * s.goalFor / gp + .4 * s.l10GoalsFor / l, ga: .6 * s.goalAgainst / gp + .4 * s.l10GoalsAgainst / l };
};

function simulate(h, a, lg) {
  const xh = h.gf * a.ga / lg * 1.04, xa = a.gf * h.ga / lg * 0.96;
  let hw = 0, aw = 0, ot = 0, over = 0, hotw = 0; const sc = {};
  for (let i = 0; i < N; i++) {
    let gh = pois(xh), ga = pois(xa);
    if (gh === ga) { ot++; if (Math.random() < xh / (xh + xa)) { gh++; hotw++; } else ga++; }
    gh > ga ? hw++ : aw++;
    if (gh + ga > 5.5) over++;
    const k = gh + '–' + ga; sc[k] = (sc[k] || 0) + 1;
  }
  const top = Object.entries(sc).sort((x, y) => y[1] - x[1]).slice(0, 5).map(([s, n]) => [s, n / N]);
  return { xh, xa, pHome: hw / N, pAway: aw / N, pOT: ot / N, pOver: over / N, top, index: Math.round(100 * xh / (xh + xa)) };
}

async function form(abbr) {
  const d = await get(`/club-schedule-season/${abbr}/now`);
  const done = d.games.filter(g => ['OFF', 'FINAL'].includes(g.gameState));
  const mk = g => {
    const home = g.homeTeam.abbrev === abbr, gf = home ? g.homeTeam.score : g.awayTeam.score, ga = home ? g.awayTeam.score : g.homeTeam.score;
    const ext = g.gameOutcome && g.gameOutcome.lastPeriodType !== 'REG';
    return { date: g.gameDate, opp: home ? g.awayTeam.abbrev : g.homeTeam.abbrev, home, gf, ga, r: gf > ga ? 'V' : ext ? 'DP' : 'D' };
  };
  const all = done.map(mk), last = all.slice(-5);
  return { last, pts: last.reduce((s, g) => s + (g.r === 'V' ? 2 : g.r === 'DP' ? 1 : 0), 0), gf: last.reduce((s, g) => s + g.gf, 0), ga: last.reduce((s, g) => s + g.ga, 0), all };
}

async function players(abbr) {
  const d = await get(`/club-stats/${abbr}/now`, 1800000), n = p => `${p.firstName.default} ${p.lastName.default}`;
  return {
    skaters: d.skaters.sort((a, b) => b.points - a.points).slice(0, 6).map(p => ({ name: n(p), pos: p.positionCode, gp: p.gamesPlayed, g: p.goals, a: p.assists, pts: p.points, img: p.headshot })),
    goalie: d.goalies.sort((a, b) => b.gamesPlayed - a.gamesPlayed).slice(0, 2).map(p => ({ name: n(p), gp: p.gamesPlayed, sv: p.savePercentage, gaa: p.goalsAgainstAverage, img: p.headshot }))
  };
}

const routes = {
  async '/api/games'(q) {
    const date = q.get('date'), d = await get(`/schedule/${date}`, 60000);
    const day = d.gameWeek.find(x => x.date === date) || { games: [] };
    const t = x => ({ abbrev: x.abbrev, name: x.commonName ? x.commonName.default : x.abbrev, logo: x.logo, score: x.score });
    return day.games.map(g => ({ id: g.id, start: g.startTimeUTC, state: g.gameState, home: t(g.homeTeam), away: t(g.awayTeam) }));
  },
  async '/api/match'(q) {
    const H = q.get('home'), A = q.get('away'), st = (await get('/standings/now')).standings;
    const by = ab => st.find(s => s.teamAbbrev.default === ab);
    const lg = st.reduce((s, x) => s + x.goalFor, 0) / st.reduce((s, x) => s + x.gamesPlayed, 0);
    const [fh, fa, ph, pa] = await Promise.all([form(H), form(A), players(H), players(A)]);
    const sh = by(H), sa = by(A), sim = simulate(rate(sh), rate(sa), lg);
    const pick = s => ({ rank: s.leagueSequence, gp: s.gamesPlayed, w: s.wins, l: s.losses, otl: s.otLosses, pts: s.points, pct: s.pointPctg, gfpg: s.goalFor / s.gamesPlayed, gapg: s.goalAgainst / s.gamesPlayed, diff: s.goalDifferential,
      homeGf: s.homeGoalsFor / (s.homeGamesPlayed || 1), homeGa: s.homeGoalsAgainst / (s.homeGamesPlayed || 1), roadGf: s.roadGoalsFor / (s.roadGamesPlayed || 1), roadGa: s.roadGoalsAgainst / (s.roadGamesPlayed || 1),
      l10: `${s.l10Wins}-${s.l10Losses}-${s.l10OtLosses}`, streak: (s.streakCode || '') + (s.streakCount || '') });
    const h2h = fh.all.filter(g => g.opp === A).slice(-5).reverse();
    return { sim, stats: { home: pick(sh), away: pick(sa) }, form: { home: fh.last, away: fa.last, hp: fh.pts, ap: fa.pts, hgf: fh.gf, agf: fa.gf, hga: fh.ga, aga: fa.ga }, h2h, players: { home: ph, away: pa } };
  }
};

http.createServer(async (req, res) => {
  const u = new URL(req.url, 'http://x');
  try {
    if (routes[u.pathname]) {
      const body = await routes[u.pathname](u.searchParams);
      res.writeHead(200, { 'Content-Type': 'application/json' }); return res.end(JSON.stringify(body));
    }
    res.writeHead(200, { 'Content-Type': 'text/html; charset=utf-8' });
    res.end(fs.readFileSync(path.join(__dirname, 'public', 'index.html')));
  } catch (e) { res.writeHead(502, { 'Content-Type': 'application/json' }); res.end(JSON.stringify({ error: String(e.message) })); }
}).listen(PORT, () => console.log('PuckScore sur http://localhost:' + PORT));
