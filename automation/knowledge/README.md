# Biblioteca de conhecimentos de produto

Organização canônica:
- `../skills/SKILL.md`: instrução principal da skill e ponte para esta biblioteca.
- `core/guardrails.md`: regras obrigatórias sobre fidelidade, riscos, segurança e direitos.
- `core/composition.md`: princípios gráficos da marca e Pinterest.
- `categories/<slug>.md`: instruções especializadas por nicho (editáveis).
- `catalog/profiles.json`: alias e palavras-chave para a seleção automática.
- `catalog/mlb_categories.json`: opcional, somente categorias **realmente obtidas** pela API oficial (nunca IDs presumidos).

`prompt_templates.make_prompt(pin)` lê os arquivos a cada execução, seleciona o documento mais específico por título/categoria oficial e adiciona regras globais. Novos textos `.md` podem ser incluídos com uma entrada correspondente em `catalog/profiles.json`, sem mudar o código da skill.

A árvore do Mercado Livre pode mudar. Execute `python automation/sync_categories.py` para tentar atualizar o catálogo de IDs/nome quando a API permitir. Em HTTP 403, o snapshot anterior é preservado e o mapeamento editorial continua funcionando offline. A curadoria dos textos é própria, **não** é documentação oficial do Mercado Livre.

A seleção de categoria por palavras-chave é heurística visual, não confirma a classificação do anúncio nem faz afirmações sobre estoque/comissão.
