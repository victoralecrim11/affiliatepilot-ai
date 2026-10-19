# Garimpo da Vez — site público

Landing page estática de curadoria de conteúdos e recomendações de produtos, hospedada pelo GitHub Pages. Marca pública substitui a antiga apresentação de ferramenta interna **AffiliatePilot AI**.

## Site público e estrutura

- Site atual: https://victoralecrim11.github.io/garimpo-da-vez/
- `index.html`: apresentação, categorias, curadoria e transparência.
- `privacy/index.html`: privacidade aplicável à página estática atual.
- `assets/styles.css`: identidade visual e responsividade.
- `assets/favicon.svg`: símbolo da marca.

Não há checkout, API, n8n, autenticação, catálogo automatizado, pixel próprio nem scripts de rastreamento implementados neste site. Os cartões são **categorias informativas**, não produtos fictícios nem links de compra.

## Atualizar a identidade nas redes

Nome de exibição: **Garimpo da Vez | Achadinhos**. Nome de usuário confirmado pelo responsável: **`@garimpodavez_`**.

Link oficial informado pelo responsável e configurado em `index.html`: https://www.pinterest.com/garimpodavez_/. Se o perfil mudar de arroba, atualizar também o link do botão no site.

## Publicação no GitHub Pages

Repositório atual: `victoralecrim11/garimpo-da-vez`, branch `main`. Conferir em Settings → Pages se a fonte de publicação utiliza a branch `main` e a pasta `/(root)`. Os caminhos HTML/CSS são relativos e funcionam neste subdiretório.

**Migração de nome concluída:** o repositório foi renomeado para `garimpo-da-vez` e a URL canônica (`og:url`) aponta para o novo endereço. Confirmar o conteúdo efetivamente publicado em `https://victoralecrim11.github.io/garimpo-da-vez/` e `https://victoralecrim11.github.io/garimpo-da-vez/privacy/` após o deploy. O antigo endereço `https://victoralecrim11.github.io/affiliatepilot-ai/` não possui redirecionamento garantido e foi observado retornando 404 após a renomeação. Se for necessário preservar acessos antigos, um repositório separado com o nome `affiliatepilot-ai` pode hospedar um redirecionamento HTML para o novo endereço. Atualizar as URLs cadastradas no Pinterest e no programa de afiliados.

## Conteúdo comercial e conformidade

- Publicar links de afiliado somente de produtos elegíveis, gerados pelo painel oficial e dentro das regras vigentes do programa.
- Conferir se este domínio e o canal Pinterest estão cadastrados/permitidos no programa de afiliados do Mercado Livre.
- Identificar claramente o uso de links de afiliado junto às recomendações.
- Não inventar preço, desconto, avaliação, disponibilidade, comissões ou depoimentos.
- Usar imagens de produtos apenas com direitos/autorização adequados. A landing atual usa somente ilustração CSS e SVG próprios.
- Evitar publicações afiliadas repetitivas/em massa; conferir regras do Pinterest.
- Revisar a política de privacidade caso o site comece a coletar dados, hospedar fontes localmente, adicionar analytics ou integrar APIs.

Referências oficiais:
- https://policy.pinterest.com/pt-br/commercial-and-branded-content-guidelines
- https://www.mercadolivre.com.br/l/checklist
- https://www.mercadolivre.com.br/l/afiliados-compartilhamento-de-publicacao

## Validação básica

Conferir desktop/mobile, navegação interna, favicon e política de privacidade, além dos links externos e ortografia. Validar a URL pública após o deploy e revisar se o link de Pinterest está atualizado.