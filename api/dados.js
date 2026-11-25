const crypto = require('crypto');

const owner = process.env.GITHUB_OWNER || 'benitesedu';
const repo = process.env.GITHUB_REPO || 'modo-cumplices';
const branch = process.env.GITHUB_BRANCH || 'main';
const githubPath = 'dados.json';
const supabaseUrl = process.env.SUPABASE_URL?.replace(/\/$/, '');
const supabaseKey = process.env.SUPABASE_SERVICE_ROLE_KEY;

function githubUrl() {
  return `https://api.github.com/repos/${owner}/${repo}/contents/${githubPath}`;
}

function githubHeaders() {
  const result = { Accept: 'application/vnd.github+json', 'X-GitHub-Api-Version': '2022-11-28' };
  if (process.env.GITHUB_TOKEN) result.Authorization = `Bearer ${process.env.GITHUB_TOKEN}`;
  return result;
}

async function getGithubData() {
  const response = await fetch(`${githubUrl()}?ref=${encodeURIComponent(branch)}`, { headers: githubHeaders() });
  if (!response.ok) throw new Error(`GitHub GET ${response.status}`);
  const file = await response.json();
  return { data: JSON.parse(Buffer.from(file.content, 'base64').toString('utf8')), revision: file.sha };
}

function supabaseHeaders(prefer) {
  return { apikey: supabaseKey, Authorization: `Bearer ${supabaseKey}`, ...(prefer ? { Prefer: prefer } : {}) };
}

async function supabaseRequest(path, options = {}) {
  const result = await fetch(`${supabaseUrl}/rest/v1/${path}`, { ...options, headers: { ...supabaseHeaders(options.prefer), ...options.headers } });
  if (!result.ok) throw new Error(`Supabase ${result.status}: ${await result.text()}`);
  return result.status === 204 ? null : result.json();
}

function revision(data) {
  return crypto.createHash('sha256').update(JSON.stringify(data)).digest('hex');
}

async function getSupabaseData() {
  const [days, votes] = await Promise.all([
    supabaseRequest('dias?select=dia,marcacoes,envolvidos_na_briga,observacao&order=dia.asc'),
    supabaseRequest('votos?select=dia,participante,estrelas,comentario&order=dia.asc')
  ]);
  const records = Object.fromEntries(days.map(day => [day.dia, {
    marcacoes: day.marcacoes,
    envolvidosNaBriga: day.envolvidos_na_briga,
    observacao: day.observacao,
    votos: { eduardo: null, jessica: null }
  }]));
  for (const vote of votes) {
    if (records[vote.dia]) records[vote.dia].votos[vote.participante] = { estrelas: vote.estrelas, comentario: vote.comentario };
  }
  return { data: { versao: 1, jogo: 'Modo Cúmplice', tiposDeDia: { briga: 'Teve briga', feliz: 'Dia feliz', quente: 'Dia quente' }, participantes: { eduardo: { nome: 'Eduardo' }, jessica: { nome: 'Jéssica' } }, registros: records } };
}

async function updateSupabase(change) {
  const current = await getSupabaseData();
  current.data.registros[change.data] = change.registro;
  const record = change.registro;
  await supabaseRequest('dias?on_conflict=dia', {
    method: 'POST',
    prefer: 'resolution=merge-duplicates,return=minimal',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify([{ dia: change.data, marcacoes: record.marcacoes, envolvidos_na_briga: record.envolvidosNaBriga, observacao: record.observacao }])
  });
  await supabaseRequest(`votos?dia=eq.${encodeURIComponent(change.data)}`, { method: 'DELETE', prefer: 'return=minimal' });
  const votes = Object.entries(record.votos).filter(([, vote]) => vote).map(([participant, vote]) => ({ dia: change.data, participante: participant, estrelas: vote.estrelas, comentario: vote.comentario }));
  if (votes.length) await supabaseRequest('votos', { method: 'POST', prefer: 'return=minimal', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(votes) });
  return current.data;
}

module.exports = async function handler(request, response) {
  try {
    if (supabaseUrl && supabaseKey) {
      const current = await getSupabaseData();
      const currentRevision = revision(current.data);
      response.setHeader('ETag', `"${currentRevision}"`);
      if (request.method === 'GET') return response.status(200).json(current.data);
      if (request.method !== 'PUT') return response.status(405).json({ error: 'Método não permitido' });
      const expected = (request.headers['if-match'] || '').replaceAll('"', '');
      if (expected && expected !== currentRevision) return response.status(412).json({ error: 'Arquivo alterado' });
      const change = typeof request.body === 'string' ? JSON.parse(request.body) : request.body;
      if (!change?.data || !change.registro) return response.status(400).json({ error: 'Registro inválido' });
      const updated = await updateSupabase(change);
      response.setHeader('ETag', `"${revision(updated)}"`);
      return response.status(200).json({ ok: true });
    }

    const current = await getGithubData();
    if (request.method === 'GET') {
      response.setHeader('ETag', `"${current.revision}"`);
      return response.status(200).json(current.data);
    }
    if (request.method !== 'PUT' || !process.env.GITHUB_TOKEN) return response.status(503).json({ error: 'Banco não configurado' });
    const change = typeof request.body === 'string' ? JSON.parse(request.body) : request.body;
    if (!change?.data || !change.registro) return response.status(400).json({ error: 'Registro inválido' });
    const expected = (request.headers['if-match'] || '').replaceAll('"', '');
    if (expected && expected !== current.revision) return response.status(412).json({ error: 'Arquivo alterado' });
    current.data.registros[change.data] = change.registro;
    const content = Buffer.from(`${JSON.stringify(current.data, null, 2)}\n`).toString('base64');
    const commit = await fetch(githubUrl(), { method: 'PUT', headers: { ...githubHeaders(), 'Content-Type': 'application/json' }, body: JSON.stringify({ message: `Atualiza registro de ${change.data}`, content, sha: current.revision, branch }) });
    if (!commit.ok) throw new Error(`GitHub PUT ${commit.status}`);
    const result = await commit.json();
    response.setHeader('ETag', `"${result.content.sha}"`);
    return response.status(200).json({ ok: true });
  } catch (error) {
    console.error(error);
    return response.status(500).json({ error: 'Não foi possível atualizar a base de dados' });
  }
};
