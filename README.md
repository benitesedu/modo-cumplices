# Modo Cúmplice

Abra esta pasta no VS Code. Com Python 3.8 ou superior instalado, execute no terminal:

```powershell
py servidor.py
```

No macOS ou Linux, use `python3 servidor.py`. Abra http://127.0.0.1:8000 no navegador. O servidor usa apenas a biblioteca padrão. Para encerrar, pressione Ctrl+C.

## Arquivos

- `dist/index.html`, `dist/style.css` e `dist/app.js` contêm a interface do protótipo. As três imagens WebP estão na mesma pasta.
- `supabase/schema.sql` cria as tabelas `dias` e `votos`, com as regras de validação e RLS ativado. Execute o script no SQL Editor do Supabase.
- `servidor.py` serve a interface local e usa exclusivamente o Supabase para ler e gravar registros. Crie um `.env` com `SUPABASE_URL` e `SUPABASE_SERVICE_ROLE_KEY` antes de executar.
- `.openai/hosting.json` é a configuração original da hospedagem estática. Para publicar a versão com escrita em arquivo seria necessário um ambiente que execute o servidor com disco persistente.
- `vercel.json` encaminha a interface, os assets e a API para a Vercel. Configure `SUPABASE_URL` e `SUPABASE_SERVICE_ROLE_KEY` nas variáveis do projeto.
- A função `api/dados.js` usa exclusivamente o Supabase. A service role key deve ficar somente nas variáveis do servidor e nunca no frontend.

Os 100 dias futuros são gerados na interface; somente dias efetivamente registrados são armazenados nas tabelas do Supabase.
