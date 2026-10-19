# Garimpo da Vez — site público

Landing page estática de curadoria de conteúdos e recomendações de produtos, hospedada pelo GitHub Pages. Marca pública substitui a antiga apresentação de ferramenta interna **AffiliatePilot AI**.

## Site público e estrutura

- Site atual: https://victoralecrim11.github.io/affiliatepilot-ai/
- `index.html`: apresentação, categorias, curadoria e transparência.
- `privacy/index.html`: privacidade aplicável à página estática atual.
- `assets/styles.css`: identidade visual e responsividade.
- `assets/favicon.svg`: símbolo da marca.

Não há checkout, API, n8n, autenticação, catálogo automatizado, pixel próprio nem scripts de rastreamento implementados neste site. Os cartões são **categorias informativas**, não produtos fictícios nem links de compra.

## Atualizar a identidade nas redes

Nome de exibição sugerido: **Garimpo da Vez | Achadinhos**. O arroba `@garimpodavezbr` é uma sugestão **não confirmada como disponível**.

**Importante:** o link para Pinterest em `index.html` aponta temporariamente para a conta atual conhecida `https://www.pinterest.com/affiliatepilotai/`. Assim que a alteração de arroba estiver concluída, confirme a URL pública real e atualize o endereço. Não assuma que arrobas sugeridos existem.

## Publicação no GitHub Pages

Configuração existente: repositório `victoralecrim11/affiliatepilot-ai`, branch `main`, pasta `/(root)` (confirmar em Settings → Pages). Os caminhos HTML/CSS são relativos e funcionam neste subdiretório.

**Não renomear o repositório diretamente sem planejar redirecionamento.** Uma renomeação muda o endereço GitHub Pages; pode quebrar a URL colocada na bio do Pinterest, cadastros de afiliado e eventual verificação de domínio. Primeiro publicar e validar a nova identidade no endereço atual; depois planejar migração para URL com nova marca e atualizar links externos. O meta `og:url` acompanha a URL atual.

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