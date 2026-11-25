const supabaseUrl = process.env.SUPABASE_URL?.replace(/\/$/, '');
const supabaseKey = process.env.SUPABASE_SERVICE_ROLE_KEY;
const types = ['Viagem', 'Passeio', 'Acontecimento'];
const participants = ['Eduardo', 'Jéssica', 'Ambos'];

function headers(prefer) {
  return { apikey: supabaseKey, Authorization: `Bearer ${supabaseKey}`, ...(prefer ? { Prefer: prefer } : {}) };
}

async function request(path, options = {}) {
  const response = await fetch(`${supabaseUrl}/rest/v1/${path}`, {
    ...options,
    headers: { ...headers(options.prefer), ...options.headers }
  });
  const body = await response.text();
  if (!response.ok) throw new Error(`Supabase ${response.status}: ${body}`);
  return body ? JSON.parse(body) : null;
}

function validDate(value) {
  return /^\d{4}-\d{2}-\d{2}$/.test(value) && !Number.isNaN(Date.parse(`${value}T00:00:00Z`));
}

function validateEvent(event) {
  if (!event || !types.includes(event.tipo) || !participants.includes(event.participante)) throw new Error('Tipo ou participante inválido');
  if (!validDate(event.dataInicio) || !validDate(event.dataFim) || event.dataFim < event.dataInicio) throw new Error('Período inválido');
  if (typeof event.descricao !== 'string') throw new Error('Descrição inválida');
  if (!Array.isArray(event.itens)) throw new Error('Itens inválidos');
  for (const item of event.itens) {
    if (!validDate(item.data) || item.data < event.dataInicio || item.data > event.dataFim || typeof item.observacao !== 'string' || !item.observacao.trim()) throw new Error('Item fora do período ou sem observação');
  }
}

module.exports = async function handler(req, response) {
  if (!supabaseUrl || !supabaseKey) return response.status(503).json({ error: 'Supabase não configurado' });
  try {
    if (req.method === 'GET') {
      const [events, items] = await Promise.all([
        request('eventos_especiais?select=id,tipo,participante,data_inicio,data_fim,descricao,criado_em&order=data_inicio.desc'),
        request('eventos_itens?select=id,evento_id,data,observacao&order=data.asc')
      ]);
      const result = events.map(event => ({
        id: event.id,
        tipo: event.tipo,
        participante: event.participante,
        dataInicio: event.data_inicio,
        dataFim: event.data_fim,
        descricao: event.descricao,
        itens: items.filter(item => item.evento_id === event.id).map(item => ({ id: item.id, data: item.data, observacao: item.observacao }))
      }));
      response.setHeader('X-Data-Source', 'supabase');
      return response.status(200).json(result);
    }
    if (req.method !== 'POST') return response.status(405).json({ error: 'Método não permitido' });
    const event = typeof req.body === 'string' ? JSON.parse(req.body) : req.body;
    validateEvent(event);
    const created = await request('eventos_especiais', { method: 'POST', prefer: 'return=representation', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify([{ tipo: event.tipo, participante: event.participante, data_inicio: event.dataInicio, data_fim: event.dataFim, descricao: event.descricao.trim() }]) });
    const id = created[0].id;
    if (event.itens.length) await request('eventos_itens', { method: 'POST', prefer: 'return=minimal', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(event.itens.map(item => ({ evento_id: id, data: item.data, observacao: item.observacao.trim() }))) });
    return response.status(201).json({ id });
  } catch (error) {
    console.error(error);
    return response.status(error.message.includes('inválido') || error.message.includes('Período') || error.message.includes('Item') ? 400 : 500).json({ error: error.message });
  }
};
