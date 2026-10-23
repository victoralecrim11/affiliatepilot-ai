# Garimpo da Vez — Seletor de Produtos e Categorias via Mercado Livre

## Catálogo Excel automático (novo padrão; CSV é legado)

O sistema agora mantém **automation/data/produtos.xlsx** automaticamente a partir da fila local: cada anúncio descoberto, revisão, link individual de afiliado confirmado ou criativo preparado atualiza a planilha, sem digitar ID nem preencher CSV. O Excel tem abas **Produtos**, **Resumo** e **Categorias oficiais**. Para gerar a planilha dos produtos já existentes, use `python automation/garimpo.py excel-sync`. Para importar novos registros de uma planilha padrão, use `python automation/garimpo.py import-xlsx minha-planilha.xlsx`. A fila JSON continua responsável por aprovações e publicação; o Excel é um catálogo sincronizado. Alterações manuais são detectadas e preservadas, com reconciliação explícita via `excel-sync --force`. Consulte [EXCEL_CATALOG.md](EXCEL_CATALOG.md) para detalhes e segurança.

## Objetivo

Escolher produtos por **categoria → subcategoria → palavras-chave → anúncio**,
sem informar manualmente códigos `MLB...`, mantendo **um link de afiliado
separado por produto** e publicação manual no Pinterest Business.

Importante: o ID de **categoria** (`MLB...`), o ID de **produto de catálogo**
(`MLBU...` ou outro identificador do catálogo) e o ID de **anúncio**
(`MLB...` na resposta de listagens) não são intercambiáveis.

### APIs oficiais consultadas

| Recurso | Campos úteis | Limite |
|---|---|---|
| `GET /sites/MLB/categories` | `id`, `name` | Categorias raiz; cache oficial disponível em `knowledge/catalog/mlb_categories.json` |
| `GET /categories/{id}` | `id`, `name`, `children_categories`, `path_from_root` | Pode requerer autorização |
| `GET /sites/MLB/search?q=...&category=...` | `results[].id`, `title`, `permalink`, `price`, `currency_id`, `category_id`, `status` | Pode ser negado com HTTP 403; nenhum contorno |
| `GET /items/{id}` | `id`, `title`, `category_id`, `pictures`, `price`, `status` | Anúncios de terceiros podem retornar 403 |
| `GET /products/search` | `results[].id`, `name`, `domain_id`, `status` | **Catálogo**, não equivale a anúncio nem gera link afiliado |

Os resultados da busca são somente **candidatos**; conferir disponibilidade,
imagem e dados reais antes de publicar. Valores de preços podem mudar.

## Instalação no PowerShell

```powershell
cd C:\Desenvolvimento\Projetos\garimpo-da-vez
git pull --ff-only origin main
.\.venv\Scripts\Activate.ps1
python -m unittest discover -s automation\tests -q
```

## A. Descobrir um anúncio SEM ID manual

```powershell
python automation\garimpo.py ml-discover
```

O menu consulta categorias raiz oficiais (cache quando necessário), permite
navegar até subcategorias, solicita palavras-chave, mostra **apenas anúncios
individuais** que têm permalink oficial compatível e pede um **número** para
escolher. Ao selecionar, cria um rascunho local e mostra sua identificação.
**Não cria, deduz nem reutiliza link de afiliado**, não presume licença de
imagem e não publica.

Para pesquisar sem navegar nas categorias:

```powershell
python automation\garimpo.py ml-discover --query "refletor LED" --any-category
```

Somente mostrar resultados (sem importar):

```powershell
python automation\garimpo.py ml-discover --query "notebook gamer" --any-category --list-only
```

Para execução não interativa, depois de inspecionar a lista acima:

```powershell
python automation\garimpo.py ml-discover --query "notebook gamer" --any-category --pick 2
```

A categoria pode ser especificada também por `--category-id` quando obtida
do catálogo oficial. Nunca inventar IDs.

**Se a busca retornar HTTP 401/403:** isso significa que o seu acesso não
permite listar anúncios por esse endpoint. Não há fallback para dados
fictícios nem conversão automática de IDs de catálogo em anúncio.
Selecione a URL do produto no próprio site e use:

```powershell
python automation\garimpo.py ingest-url "URL_REAL_DO_ANUNCIO"
```

## B. Selecionar produtos JÁ importados sem ID

Os comandos que trabalham com um produto permitem **omitir o ID**. No
PowerShell interativo, quando há vários candidatos, aparece uma lista
numerada. `--choose-category` filtra por categoria ampla (casa,
tecnologia etc.), nicho da knowledge (iluminacao_jardim etc.), nome oficial
conhecido ou ID de categoria. `--choose-search` filtra pelo nome/ID.

```powershell
python automation\garimpo.py show
python automation\garimpo.py knowledge --choose-search refletor --prompt
python automation\garimpo.py prepare --choose-category iluminacao_jardim --style editorial --source original
python automation\garimpo.py stylize --provider opencv --choose-category tecnologia
python automation\garimpo.py affiliate-link --choose-search "Refletor" 
```

A interface de seleção também está disponível em `review`, `confirm-link`,
`confirm-image-rights`, `approve`, `publish`, `verify-ml` e `reset`,
mas comandos de aprovação e publicação **continuam exigindo suas flags
explícitas**. Nenhuma publicação automática é habilitada.

Em terminais não interativos, apenas um candidato filtrado pode ser
selecionado automaticamente; múltiplos itens resultam em erro para evitar
usar produto/link errado.

## C. Link de afiliado exclusivo por produto

A API oficial do Mercado Livre **não é usada para criar links de comissão**.
Depois de escolher o anúncio, execute:

```powershell
python automation\garimpo.py affiliate-link
python automation\garimpo.py show
python automation\garimpo.py confirm-link --confirm
```

Confirme na **Central de Afiliados** que o link copiado em **Compartilhar**
pertence ao anúncio escolhido. O script nunca reutiliza um link fixo global.

## D. Edição de imagem gratuita SEM GPU dedicada

A correção simples via Pillow já está no projeto:

```powershell
python automation\garimpo.py stylize --provider local
```

A nova opção **OpenCV via CPU** corrige o contraste local e a nitidez de modo
conservador, sem gerar um produto fictício. Instalação opcional:

```powershell
python -m pip install -r automation\requirements-opencv.txt
python automation\garimpo.py stylize --provider opencv
```

Depois:

```powershell
python automation\garimpo.py prepare --style editorial
python automation\garimpo.py export-business --choose
```

`export-business --choose` permite selecionar um único Pin já preparado.
Sem `--choose`, exporta todos os elegíveis; `--latest` exporta apenas o
mais recente. Mantém as subpastas `automation/out/business/ID_LOCAL`,
cada uma com sua própria URL individual.

**Atenção:** OpenCV e Pillow não recriam cenários fotográficos por prompt.
Para edição manual mais avançada, o [Photopea](https://www.photopea.com/)
é gratuito no navegador. [Cloudinary](https://cloudinary.com/pricing)
oferece plano free com créditos para transformações, mas implica conta e
upload à nuvem; não foi ativado no código nem é IA generativa ilimitada.

## Campos e limitações de segurança

- Categorias exibidas vêm da API oficial ou cache identificado como oficial.
- A API pode negar busca de listagens; não mascarar bloqueio com resultados
  sintéticos, scrapers ou chamadas privadas.
- Busca de catálogo `/products/search` não é fonte direta de links/IDs de
  anúncios para afiliação. O menu importa somente `results[].id` de anúncios
  e `permalink` consistente.
- Uma categoria/nicho não determina quem paga comissão. A Central de
  Afiliados e a elegibilidade do produto são checadas separadamente.
- O importador usa dados oficiais como sugestões e mantém revisões humanas de
  título, categoria, foto/direitos, link, indicação IA e publicação.
- Este roteiro não depende de GPU nem de API de imagens paga.

### Referências oficiais
- https://developers.mercadolivre.com.br/pt_br/categorias-e-publicacoes
- https://developers.mercadolivre.com.br/pt_br/itens-e-buscas
- https://developers.mercadolivre.com.br/buscador-de-produtos
- https://developers.mercadolivre.com.br/pt_br/publicacao-de-produtos/dump-de-categorias
