# Modo Cúmplice

Abra esta pasta no VS Code. Com Python 3.8 ou superior instalado, execute no terminal:

```powershell
py servidor.py
```

No macOS ou Linux, use `python3 servidor.py`. Abra http://127.0.0.1:8000 no navegador. O servidor usa apenas a biblioteca padrão. Para encerrar, pressione Ctrl+C.

## Arquivos

- `dist/index.html`, `dist/style.css` e `dist/app.js` contêm a interface do protótipo. As três imagens WebP estão na mesma pasta.
- `dados.json` é a base local. Cada chave em `registros` é uma data ISO. O registro reúne as marcações e a observação do casal, além dos votos por participante. Um voto pendente é representado por `null`. Média e sequência são calculadas na tela.
- `servidor.py` lê a base e grava cada alteração no arquivo da raiz. Use este servidor para testar a persistência. O Live Server do VS Code só serve arquivos estáticos.
- `.openai/hosting.json` é a configuração original da hospedagem estática. Para publicar a versão com escrita em arquivo seria necessário um ambiente que execute o servidor com disco persistente.
- `vercel.json` encaminha a interface e os assets da pasta `dist` para a Vercel. Sem as variáveis da API, o site usa o armazenamento local do navegador; com a API configurada, os registros são persistidos no `dados.json` do GitHub.
- A função `api/dados.js` permite persistir registros na Vercel fazendo commits no `dados.json` do GitHub. Configure na Vercel as variáveis `GITHUB_TOKEN`, `GITHUB_OWNER`, `GITHUB_REPO` e `GITHUB_BRANCH`; o token deve ter permissão de escrita no conteúdo do repositório e nunca deve ser colocado no frontend.

A semana de demonstração continua em 23–29/11/2026, com 25/11 como dia de referência. A base inicial contém os dois registros de exemplo do protótipo. Os votos feitos no site anteriormente estão no armazenamento do navegador usado para votar e não estão neste pacote. Faça uma cópia de dados.json para guardar o histórico.
