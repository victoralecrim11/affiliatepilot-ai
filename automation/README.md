# Garimpo da Vez — Assistente de Pins (Python)

Ferramenta local para organizar produtos **reais** do programa de afiliados do Mercado Livre, preparar Pins verticais com a identidade Garimpo da Vez, revisar cada criação e publicar **um Pin por ação explícita** via API oficial do Pinterest.

## Requisitos e limites reais

- Python 3.11+ e Pillow. Windows PowerShell compatível.
- Consulta opcional de anúncios via API oficial `GET /items/{MLB_ID}` com `MERCADOLIVRE_ACCESS_TOKEN` autorizado: status, título e preço momentâneo. A API não confirma comissão nem cria links de afiliado.\n- Os links **não são gerados** pelo script. Copie-os da Barra/Central de Afiliados do Mercado Livre. Não faça scraping, não utilize dados inventados e não use credenciais do Mercado Livre neste programa.
- Prepare imagens próprias ou de uso comercial **autorizado**, retratando fielmente o produto. O script não baixa imagens de terceiros, não usa fotos do Pinterest nem fabrica avaliações, preços ou descontos.
- A postagem só funciona após aprovação da integração do Pinterest, OAuth 2.0 com permissão `pins:write` para sua conta Business, além de `boards:read` para listar pastas. O Pinterest exige consentimento por Pin; não é um bot de publicação em massa.
- **Publicar requer um ID de pasta (`board_id`)** na API oficial. Isso difere de certas telas do aplicativo, que podem oferecer publicação sem escolher pasta.
- Não adicionamos segredos ou tokens ao repositório. Use `PINTEREST_ACCESS_TOKEN` no ambiente. O script não automatiza autenticação nem contorna limitações da API.
- Não há publicação agendada ou repetição automática. Erros de rede entram em `needs_check` para conciliação manual e impedir Pins duplicados.
- O script cria imagens 1000 × 1500 com a fotografia original no centro (sem fazer montagens que deturpem o produto).

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
- O programa não gerencia vendas, pagamentos, analytics, inventário ou a criação de links de afiliado. A leitura de um anúncio via API oficial é opcional.
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

O terminal pede o Client Secret sem mostrar caracteres. Nunca compartilhe o secret, tokens ou a URL de retorno contendo code. Deixe o comando aberto: o script inicia um servidor apenas em 127.0.0.1:8765 e abre a autorização do Mercado Livre no navegador. Ao aceitar, a página de callback encaminha o retorno à porta local. Se o navegador não abrir, use a opção --no-browser. Não use GitHub Pages para processar tokens nem coloque credentials na página estática.

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
