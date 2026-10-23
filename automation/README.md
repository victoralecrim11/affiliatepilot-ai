# Garimpo da Vez — Assistente de Pins (Python)

## Descoberta de produtos sem IDs manuais

O novo comando `python automation/garimpo.py ml-discover` apresenta categorias e subcategorias oficiais do Mercado Livre e tenta buscar anúncios reais. Basta escolher pelo **número**; o anúncio é importado como rascunho, sem link de afiliado inventado. Se a API de busca responder HTTP 403, continue copiando a URL real do anúncio para `ingest-url`. Os comandos por produto (`prepare`, `stylize`, `review`, `affiliate-link`, `show`, etc.) agora aceitam ID opcional e oferecem menu numerado e filtros `--choose-category`/`--choose-search`.

A melhoria fotográfica local `--provider opencv` usa CPU e exige apenas a instalação opcional `pip install -r automation/requirements-opencv.txt`. Veja [ML_DISCOVERY.md](ML_DISCOVERY.md) para documentação e comandos. Os links de afiliado continuam vindos exclusivamente da Central de Afiliados do Mercado Livre, por produto, jamais da API de anúncios.


**Exportação sem ID:** `python automation/garimpo.py export-business` exporta todos os Pins preparados/aprovados que passam nas confirmações de foto e link individual. `--latest` exporta apenas o mais recente; informar `ID_LOCAL` continua opcional para escolher um produto específico. O comando não cria links pela API Mercado Livre e não publica nada.
## Novo: Pins naturais + publicação manual no Pinterest Business

O modo padrão de `prepare` agora é **editorial**: foto vertical 2:3 sem cabeçalho, título nem logo sobrepostos. O estilo antigo continua opt-in com `--style branded`. Se a imagem estilizada antiga tiver banner, use `--source original` e uma foto original autorizada. O provider Pillow local agora somente ajusta cor e contraste, sem moldura publicitária.

```powershell
python automation/garimpo.py prepare RS1033-VHDC --style editorial --source original
python automation/garimpo.py export-business RS1033-VHDC
```

O segundo comando gera **apenas arquivos locais** em `automation/out/business/ID/`: `pin.jpg`, `fields.json`, `copy.txt` e `checklist.md`. Preencha os campos da tela Pinterest Business manualmente e escolha a pasta, indicação de IA (quando aplicável) e data de publicação. Cada pacote usa o link de afiliado **confirmado daquele item**. Links de comissão vêm do Compartilhar/Gerador de Links da Central de Afiliados; a API ML é de consulta, não geração de links. Leia [EDITORIAL_BUSINESS.md](EDITORIAL_BUSINESS.md) para o fluxo completo.

**Providers gratuitos remotos (opcionais):** AI Horde (img2img) e Hugging Face Spaces públicos. Sem GPU local e sem API paga, mas exigem consentimento explícito para enviar imagens, licença comercial do modelo conferida e revisão da imagem gerada. Veja [CLOUD_IMAGE_PROVIDERS.md](CLOUD_IMAGE_PROVIDERS.md). Exemplo: `stylize ID --provider aihorde --allow-public-processing --confirm-model-license` com `AIHORDE_MODEL` configurado; `hf-spaces` precisa de Space/endpoint compatíveis. Ambos podem ficar indisponíveis e nunca publicam automaticamente.

Ferramenta local para organizar produtos **reais** do programa de afiliados do Mercado Livre, preparar Pins verticais com a identidade Garimpo da Vez, revisar cada criação e publicar **um Pin por ação explícita** via API oficial do Pinterest.

**Novo pipeline por URL + auxílio do navegador + edição visual opcional:** consulte [PIPELINE.md](PIPELINE.md), com os comandos `ingest-url`, `affiliate-link`, `review`, `stylize`, `auto`, `knowledge` e `confirm-link`. O fluxo exige revisão de direitos da imagem, dados do produto e vínculo de afiliado. A etapa `local` é tratamento gráfico **não generativo**; a edição com IA é opcional e pode ser cobrada.

**Skill e base de conhecimento por categoria:** `automation/skills/SKILL.md` consulta `automation/knowledge/`, com textos editoriais específicos e um catálogo oficial MLB (IDs + nomes obtidos pela API). Veja [knowledge/README.md](knowledge/README.md). Para conferir a direção criativa escolhida use `python automation/garimpo.py knowledge ID_DO_PRODUTO --prompt`. Para sincronizar os nomes de categorias quando a API permitir: `python automation/sync_categories.py --with-oauth`.

## Requisitos e limites reais

- Python 3.11+ e Pillow. Windows PowerShell compatível.
- Consulta opcional de anúncios via API oficial `GET /items/{MLB_ID}`. HTTP 403 pode impedir acesso a anúncios de terceiros. A API não confirma comissão nem cria links de afiliado.
- Links de comissão: o assistente Playwright pode abrir a Central oficial para você copiar o link com autenticação interativa. Sem API privada nem credenciais no script; cada link precisa ser conferido.
- Use imagens próprias ou de uso comercial **autorizado**, retratando fielmente o produto. O download de uma imagem da vitrine só é permitido pelo comando após confirmação explícita dos direitos. O script não usa fotos do Pinterest nem fabrica avaliações, preços ou descontos.
- A postagem só funciona após aprovação da integração do Pinterest, OAuth 2.0 com permissão `pins:write` para sua conta Business, além de `boards:read` para listar pastas. O Pinterest exige consentimento por Pin; não é um bot de publicação em massa.
- **Publicar requer um ID de pasta (`board_id`)** na API oficial. Isso difere de certas telas do aplicativo, que podem oferecer publicação sem escolher pasta.
- Não adicionamos segredos ou tokens ao repositório. Use `PINTEREST_ACCESS_TOKEN` no ambiente. O script não automatiza autenticação nem contorna limitações da API.
- Não há publicação agendada ou repetição automática. Erros de rede entram em `needs_check` para conciliação manual e impedir Pins duplicados.
- O script cria imagens 1000 × 1500 com identidade Garimpo da Vez; pode usar tratamento local gratuito ou uma imagem modificada por IA, sujeita a revisão de fidelidade.

## Instalação (PowerShell)

Na raiz do repo `garimpo-da-vez`:

```powershell
py -3 -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r automation\requirements.txt
```

## Adicione um produto real

Crie uma pasta local e ponha nela uma foto de produto que você tem permissão para reutilizar comercialmente. Copie `automation/products.example.csv` para `automation/data/produtos.csv` e preencha uma linha com estes campos:

| Coluna | Como preencher |
| --- | --- |
| `id` | Identificador exclusivo, como `quadro-sala-01` |
| `title` | Título factual do produto (máx. 100 caracteres) |
| `category` | `casa`, `tecnologia`, `organizacao` ou `lifestyle` |
| `summary` | Descrição verificável (15 a 560 caracteres, sem alegações inventadas) |
| `affiliate_url` | HTTPS do Mercado Livre ou meli.la **gerado no painel de afiliados** |
| `image_path` | Caminho da fotografia autorizada (absoluto ou relativo ao CSV) |
| `image_license_confirmed` | `sim` somente se você tem direito de publicar/comercializar a imagem |\n| `item_id` | Opcional: identificador MLB do anúncio, para verificação de metadados por API oficial |

Não há produtos fictícios no CSV de exemplo; nenhuma publicação será criada até que você forneça seus dados reais.

### 1. Importar e preparar

```powershell
py -3 automation\garimpo.py import-csv automation\data\produtos.csv
py -3 automation\garimpo.py list
py -3 automation\garimpo.py prepare quadro-sala-01
```

Abra `automation/out/quadro-sala-01.jpg` e revise texto, imagem e link. O script adiciona um aviso explícito sobre o uso de links de afiliado.

### 2. Verificar anúncio no Mercado Livre (opcional, API oficial)

Após cadastrar e autenticar uma aplicação em [Mercado Livre Developers](https://developers.mercadolivre.com.br/), obtenha um token autorizado à consulta de itens. Não é necessário para gerar imagens nem para publicar no Pinterest, mas é necessário para a verificação.

```powershell
$env:MERCADOLIVRE_ACCESS_TOKEN = 'TOKEN_ML_LOCAL_NAO_VERSIONADO'
py -3 automation\\garimpo.py verify-ml quadro-sala-01 --item-id MLB123456789
```

O ID acima é **somente um placeholder de formato**. Use o ID real do produto. O script rejeita anúncios que a API não confirmar como ativos; essa checagem não confirma comissão nem licença da imagem e não substitui seu link de afiliado.

### 3. Configurar token e consultar suas pastas

Obtenha token OAuth **oficial** para sua conta `@garimpodavez_` pela documentação do Pinterest Developers. Nunca cole o token em chats, issues ou arquivos versionados.

```powershell
$env:PINTEREST_ACCESS_TOKEN = 'COLE_SEU_TOKEN_LOCALMENTE'
py -3 automation\garimpo.py boards
```

Use o ID numérico da pasta retornado. Se o token/permissão não existir, apenas preparar e revisar continua funcionando offline.

### 4. Aprovar e publicar um Pin

```powershell
py -3 automation\garimpo.py approve quadro-sala-01 --board-id 123456789012345678 --confirm
py -3 automation\garimpo.py publish quadro-sala-01 --confirm
```

**Atenção:** `123456789012345678` acima é **placeholder para o ID da pasta**, não uma pasta existente. Substitua pelo valor retornado em `boards`. A publicação envia o Pin imediatamente quando a API permite. Um Pin publicado não será enviado novamente pela fila.

### 5. Em caso de falha ou timeout

Quando o status for `needs_check` **ou** `publishing` após uma falha do processo, veja seu perfil no Pinterest e confirme se o Pin não foi criado antes de executar:

```powershell
py -3 automation\garimpo.py reset quadro-sala-01 --confirmed-not-published
```

Prepare ou aprove novamente, conforme necessário. **Não repita automaticamente** uma requisição cujo sucesso é incerto. O arquivo local `*.publish.lock` impede publicações simultâneas. Se sobrar após um encerramento abrupto, remova-o manualmente **apenas após conferir que nenhuma outra publicação está em andamento e conciliar no Pinterest**.

## Segurança e transparência

- Respeite as políticas de conteúdo comercial e desenvolvedores do Pinterest; só crie Pins que você aprova individualmente.
- A descrição informa comissão, e a imagem inclui aviso de afiliado.
- O programa não gerencia vendas, pagamentos, analytics ou inventário. A criação do link ocorre no portal oficial de afiliados, por interação no navegador (assistida e não garantida), não pela API oficial de itens.
- A fila e criativos são armazenados sob `automation/data` e `automation/out` (gitignored).
- Não versione arquivos com links comerciais, fotos de terceiros, dados de clientes, tokens, credenciais, etc.

## Rodar testes

```powershell
py -3 -m unittest discover -s automation/tests -v
```

Referências oficiais: [Pinterest Developer Guidelines](https://policy.pinterest.com/en/developer-guidelines), [Criar boards/Pins via API](https://developer.pinterest.com/docs/work-with-organic-content-and-users/create-boards-and-pins/), [Pinterest OAuth](https://developer.pinterest.com/docs/getting-started/set-up-authentication-and-authorization/), [Mercado Livre Afiliados](https://www.mercadolivre.com.br/l/comece-a-recomendar).

## OAuth automático Mercado Livre (Authorization Code + PKCE)

O script utiliza OAuth 2.0 e PKCE S256. O Client Secret, Access Token e Refresh Token ficam **somente no cofre seguro do sistema operacional** (Windows Credential Manager, macOS Keychain ou SecretService/KWallet no Linux). Nunca gravamos tokens em JSON, .env, GitHub ou GitHub Actions.

**AÇÃO OBRIGATÓRIA NO DEV CENTER ANTES DO LOGIN:** a URI usada inicialmente na criação da aplicação
(`https://victoralecrim11.github.io/garimpo-da-vez/`) é apenas a página inicial e **não** recebe o código OAuth.
Em *Minhas aplicações → Garimpo da Vez → Configuração e escopos → URIs de redirect*,
substitua/adicone a URI de callback abaixo, clique em **Adicionar URI de redirect** quando necessário
e salve a alteração. O endereço deve ser cadastrado *exatamente*, inclusive a barra final:

    https://victoralecrim11.github.io/garimpo-da-vez/oauth/callback/

Depois de salvar, confirme se a página do callback está publicada no GitHub Pages antes de iniciar o login.
**Não coloque Client Secret, código de autorização, access_token ou refresh_token na página.**

A página HTTPS do GitHub Pages é uma ponte estática: encaminha apenas o código temporário de autorização e o state para o servidor local Python em http://127.0.0.1:8765/callback. O código de autorização transita pelo host GitHub Pages, mas só pode ser resgatado com PKCE e Client Secret locais. Essa é uma solução para **uso pessoal com uma conta**, não para aplicações multiusuário. Para vários usuários, prefira backend HTTPS dedicado e cofre central com controle de acesso.

### Primeiro login (Windows PowerShell)

```powershell
git pull
py -3 -m pip install -r automation/requirements.txt
$env:MERCADOLIVRE_CLIENT_ID = 'SEU_APP_ID'
py -3 automation/ml_oauth.py login
```

Quando não houver `MERCADOLIVRE_CLIENT_SECRET` na sessão do terminal, o script **abre automaticamente o DevCenter** (`https://developers.mercadolivre.com.br/devcenter`) **antes de solicitar** a chave. Entre em *Minhas aplicações → Garimpo da Vez → Editar → Chave secreta*, copie e cole a chave no prompt oculto (nenhum caractere aparece ao colar). O script não consegue ler o Client Secret por API. Depois, abre uma **segunda página** de autorização OAuth para sua conta Mercado Livre. Deixe o terminal aberto: ele escuta apenas `127.0.0.1:8765` e recebe o retorno pelo callback HTTPS. Se o navegador não abrir, os links são exibidos para abertura manual. `--no-browser` **não abre nenhuma das duas páginas**; você deverá abri-las manualmente. Se a variável `MERCADOLIVRE_CLIENT_SECRET` já estiver definida, o DevCenter não será aberto e o fluxo seguirá diretamente à autorização. Nunca compartilhe o secret, tokens ou a URL de retorno contendo `code`. Não use GitHub Pages para processar tokens nem coloque credenciais na página estática.

### Consultar, renovar e sair

```powershell
py -3 automation/ml_oauth.py status
py -3 automation/garimpo.py verify-ml ID_DO_PIN --item-id MLB123456789
py -3 automation/ml_oauth.py refresh
py -3 automation/ml_oauth.py logout
```

O ID MLB acima é apenas exemplo de formato. A consulta verifica metadados permitidos de um item; ela não gera nem valida comissões de afiliado.

Na consulta, o script usa o token do cofre caso MERCADOLIVRE_ACCESS_TOKEN não esteja definido. Quando próximo do vencimento, renova automaticamente e substitui imediatamente o Refresh Token antigo por um novo, sob lock de processo. O Refresh Token do Mercado Livre é de **uso único**: não compartilhe o cofre entre várias máquinas e não remova um lock de autenticação residual sem confirmar que nenhum processo está rodando. Em falha incerta ou revogação, pode ser necessário repetir login.

Documentação oficial: https://developers.mercadolivre.com.br/autenticacao-e-autorizacao
