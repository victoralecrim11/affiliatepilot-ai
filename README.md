# AffiliatePilot AI — site institucional

Site estático para apresentação do projeto e Política de Privacidade. **Não é o aplicativo n8n.**

## Estrutura
- `index.html` — apresentação do projeto.
- `privacy/index.html` — Política de Privacidade pública.
- `assets/styles.css` — estilos responsivos.
- `assets/favicon.svg` — ícone.

## Publicar no GitHub Pages
1. Criar um repositório **público** chamado `affiliatepilot-ai` na conta `victoralecrim11`.
2. Enviar o **conteúdo desta pasta para a raiz** do repositório, preservando `privacy/` e `assets/`.
3. Em **Settings → Pages → Build and deployment**, selecionar **Deploy from a branch**, branch `main`, pasta `/(root)` e salvar.
4. Aguardar o deployment e abrir os links (não use antes de verificar):
   - https://victoralecrim11.github.io/affiliatepilot-ai/
   - https://victoralecrim11.github.io/affiliatepilot-ai/privacy/
5. Somente depois de conferir ambas as páginas, colar URLs no formulário Pinterest Developers.

## Cuidados
- O site descreve um **projeto em desenvolvimento**. Não sugere que integrações já estão ativas.
- A Política de Privacidade é um rascunho inicial que deve ser revisado antes de liberar OAuth ou acesso a terceiros, inclusive para detalhar retenção, provedores, base legal aplicável e canal privado de contato.
- Não incluir client secrets, tokens, senhas, e-mails pessoais ou credenciais no repositório.
- Revisar texto da política para assegurar aderência às práticas reais antes de enviar para revisão de terceiros.
