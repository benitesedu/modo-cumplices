const crypto = require('crypto');

const supabaseUrl = process.env.SUPABASE_URL?.replace(/\/$/, '');
const supabaseKey = process.env.SUPABASE_SERVICE_ROLE_KEY;

function supabaseHeaders(prefer) {
  return { apikey: supabaseKey, Authorization: `Bearer ${supabaseKey}`, ...(prefer ? { Prefer: prefer } : {}) };
}

async function supabaseRequest(path, options = {}) {
  const result = await fetch(`${supabaseUrl}/rest/v1/${path}`, {
    ...options,
    headers: { ...supabaseHeaders(options.prefer), ...options.headers }
  });
  const body = await result.text();
  if (!result.ok) throw new Error(`Supabase ${result.status}: ${body}`);
  return body ? JSON.parse(body) : null;
}

function revision(data) {
  return crypto.createHash('sha256').update(JSON.stringify(data)).digest('hex');
}

async function getDatabase() {
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
    if (records[vote.dia]) records[vote.dia].votos[vote.participante] = {
      estrelas: vote.estrelas,
      comentario: vote.comentario
    };
  }
  return { versao: 1, jogo: 'Modo Cúmplice', tiposDeDia: { briga: 'Teve briga', feliz: 'Dia feliz', quente: 'Dia quente' }, registros: records };
}

async function saveRecord(key, record) {
  await supabaseRequest('dias?on_conflict=dia', {
    method: 'POST',
    prefer: 'resolution=merge-duplicates,return=minimal',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify([{ dia: key, marcacoes: record.marcacoes, envolvidos_na_briga: record.envolvidosNaBriga, observacao: record.observacao }])
  });
  await supabaseRequest(`votos?dia=eq.${encodeURIComponent(key)}`, { method: 'DELETE', prefer: 'return=minimal' });
  const votes = Object.entries(record.votos).filter(([, vote]) => vote).map(([participant, vote]) => ({ dia: key, participante: participant, estrelas: vote.estrelas, comentario: vote.comentario }));
  if (votes.length) await supabaseRequest('votos', { method: 'POST', prefer: 'return=minimal', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(votes) });
}

module.exports = async function handler(request, response) {
  if (!supabaseUrl || !supabaseKey) return response.status(503).json({ error: 'Supabase não configurado' });
  try {
    const current = await getDatabase();
    const currentRevision = revision(current);
    response.setHeader('ETag', `"${currentRevision}"`);
    response.setHeader('X-Data-Source', 'supabase');
    if (request.method === 'GET') return response.status(200).json(current);
    if (request.method !== 'PUT') return response.status(405).json({ error: 'Método não permitido' });
    const expected = (request.headers['if-match'] || '').replaceAll('"', '');
    if (expected && expected !== currentRevision) return response.status(412).json({ error: 'Dados alterados, recarregue a página' });
    const change = typeof request.body === 'string' ? JSON.parse(request.body) : request.body;
    if (!change?.data || !change.registro) return response.status(400).json({ error: 'Registro inválido' });
    await saveRecord(change.data, change.registro);
    const updated = await getDatabase();
    response.setHeader('ETag', `"${revision(updated)}"`);
    return response.status(200).json({ ok: true });
  } catch (error) {
    console.error(error);
    return response.status(500).json({ error: 'Não foi possível acessar o Supabase', detail: error.message });
  }
};
