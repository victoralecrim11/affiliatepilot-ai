# Garimpo da Vez — Assistente de Pins (Python)

Ferramenta local para organizar produtos **reais** do programa de afiliados do Mercado Livre, preparar Pins verticais com a identidade Garimpo da Vez, revisar cada criação e publicar **um Pin por ação explícita** via API oficial do Pinterest.

## Requisitos e limites reais

- Python 3.11+ e Pillow. Windows PowerShell compatível.
- Os links **não são gerados** pelo script. Copie-os da Barra/Central de Afiliados do Mercado Livre. Não faça scraping, não utilize dados inventados e não use credenciais do Mercado Livre neste programa.
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
| `image_license_confirmed` | `sim` somente se você tem direito de publicar/comercializar a imagem |

Não há produtos fictícios no CSV de exemplo; nenhuma publicação será criada até que você forneça seus dados reais.

### 1. Importar e preparar

```powershell
py -3 automation\garimpo.py import-csv automation\data\produtos.csv
py -3 automation\garimpo.py list
py -3 automation\garimpo.py prepare quadro-sala-01
```

Abra `automation/out/quadro-sala-01.jpg` e revise texto, imagem e link. O script adiciona um aviso explícito sobre o uso de links de afiliado.

### 2. Configurar token e consultar suas pastas

Obtenha token OAuth **oficial** para sua conta `@garimpodavez_` pela documentação do Pinterest Developers. Nunca cole o token em chats, issues ou arquivos versionados.

```powershell
$env:PINTEREST_ACCESS_TOKEN = 'COLE_SEU_TOKEN_LOCALMENTE'
py -3 automation\garimpo.py boards
```

Use o ID numérico da pasta retornado. Se o token/permissão não existir, apenas preparar e revisar continua funcionando offline.

### 3. Aprovar e publicar um Pin

```powershell
py -3 automation\garimpo.py approve quadro-sala-01 --board-id 123456789012345678 --confirm
py -3 automation\garimpo.py publish quadro-sala-01 --confirm
```

**Atenção:** `123456789012345678` acima é **placeholder para o ID da pasta**, não uma pasta existente. Substitua pelo valor retornado em `boards`. A publicação envia o Pin imediatamente quando a API permite. Um Pin publicado não será enviado novamente pela fila.

### 4. Em caso de falha ou timeout

Quando o status for `needs_check`, veja seu perfil no Pinterest e confirme se o Pin não foi criado antes de executar:

```powershell
py -3 automation\garimpo.py reset quadro-sala-01 --confirmed-not-published
```

Prepare ou aprove novamente, conforme necessário. **Não repita automaticamente** uma requisição cujo sucesso é incerto.

## Segurança e transparência

- Respeite as políticas de conteúdo comercial e desenvolvedores do Pinterest; só crie Pins que você aprova individualmente.
- A descrição informa comissão, e a imagem inclui aviso de afiliado.
- O programa não gerencia vendas, pagamentos, analytics, inventário, nem qualquer API privada do Mercado Livre.
- A fila e criativos são armazenados sob `automation/data` e `automation/out` (gitignored).
- Não versione arquivos com links comerciais, fotos de terceiros, dados de clientes, tokens, credenciais, etc.

## Rodar testes

```powershell
py -3 -m unittest discover -s automation/tests -v
```

Referências oficiais: [Pinterest Developer Guidelines](https://policy.pinterest.com/en/developer-guidelines), [Criar boards/Pins via API](https://developer.pinterest.com/docs/work-with-organic-content-and-users/create-boards-and-pins/), [Pinterest OAuth](https://developer.pinterest.com/docs/getting-started/set-up-authentication-and-authorization/), [Mercado Livre Afiliados](https://www.mercadolivre.com.br/l/comece-a-recomendar).
