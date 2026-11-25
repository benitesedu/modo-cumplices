const owner = process.env.GITHUB_OWNER || 'benitesedu';
const repo = process.env.GITHUB_REPO || 'modo-cumplices';
const branch = process.env.GITHUB_BRANCH || 'main';
const path = 'dados.json';

function githubUrl() {
  return `https://api.github.com/repos/${owner}/${repo}/contents/${path}`;
}

function headers() {
  const result = {
    Accept: 'application/vnd.github+json',
    'X-GitHub-Api-Version': '2022-11-28'
  };
  if (process.env.GITHUB_TOKEN) result.Authorization = `Bearer ${process.env.GITHUB_TOKEN}`;
  return result;
}

async function getFile() {
  const response = await fetch(`${githubUrl()}?ref=${encodeURIComponent(branch)}`, { headers: headers() });
  if (!response.ok) throw new Error(`GitHub GET ${response.status}`);
  const file = await response.json();
  return { file, data: JSON.parse(Buffer.from(file.content, 'base64').toString('utf8')) };
}

module.exports = async function handler(request, response) {
  try {
    if (request.method === 'GET') {
      const { file, data } = await getFile();
      response.setHeader('ETag', `"${file.sha}"`);
      return response.status(200).json(data);
    }

    if (request.method !== 'PUT') return response.status(405).json({ error: 'Método não permitido' });
    if (!process.env.GITHUB_TOKEN) return response.status(503).json({ error: 'GITHUB_TOKEN não configurado' });
    const change = typeof request.body === 'string' ? JSON.parse(request.body) : request.body;
    if (!change?.data || !change.registro) return response.status(400).json({ error: 'Registro inválido' });

    const current = await getFile();
    const expected = (request.headers['if-match'] || '').replaceAll('"', '');
    if (expected && expected !== current.file.sha) return response.status(412).json({ error: 'Arquivo alterado' });

    current.data.registros[change.data] = change.registro;
    const content = Buffer.from(`${JSON.stringify(current.data, null, 2)}\n`).toString('base64');
    const commit = await fetch(githubUrl(), {
      method: 'PUT',
      headers: { ...headers(), 'Content-Type': 'application/json' },
      body: JSON.stringify({ message: `Atualiza registro de ${change.data}`, content, sha: current.file.sha, branch })
    });
    if (!commit.ok) throw new Error(`GitHub PUT ${commit.status}`);
    const result = await commit.json();
    response.setHeader('ETag', `"${result.content.sha}"`);
    return response.status(200).json({ ok: true });
  } catch (error) {
    return response.status(500).json({ error: 'Não foi possível atualizar dados.json' });
  }
}
