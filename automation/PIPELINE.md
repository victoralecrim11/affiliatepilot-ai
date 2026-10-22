# Fluxo URL → rascunho → arte → aprovação (Garimpo da Vez)

## O que é automático e o que NÃO é
- **Autônomo por URL, quando disponível:** identifica MLB de anúncio individual, consulta `GET /items/{id}` via API oficial, tenta metadados públicos como fallback **não verificado**, sugere categoria, cria rascunho e gera arte com imagem autorizada.
- **Requer revisão:** foto/licença comercial, título/categoria, elegibilidade do link de afiliado e dados ausentes. Um `HTTP 403` não será contornado nem tratado como verificação bem-sucedida.
- **Nenhuma publicação automática:** revisão de criativo e autorização no Pinterest continuam obrigatórias. Links `meli.la` não são inventados e SKUs do vendedor não viram IDs MLB.
- **Local sem IA:** Pillow melhora apresentação e enquadramento; não é geração generativa.
- **IA generativa opcional:** `--provider openai --allow-paid-ai` usa API de imagens com `OPENAI_API_KEY` (cobrança independente do ChatGPT). Nunca ativa sozinho.
- **Design skill + knowledge:** `automation/skills/SKILL.md` contém as instruções centrais; `automation/knowledge/core/*.md` define regras gerais; `automation/knowledge/categories/*.md` reúne os textos por nicho; `automation/knowledge/catalog/profiles.json` mapeia nomes e títulos. Google Stitch não é usado como editor fotográfico. A edição via IA carrega os arquivos locais em cada execução, sem exigir mudanças no Python.
- **API oficial de categorias MLB:** `automation/knowledge/catalog/mlb_categories.json` foi preenchido usando `GET /sites/MLB/categories` com OAuth existente, e a atualização opcional é feita com `python automation/sync_categories.py --with-oauth`. Se a API retornar erro, mantém-se o último snapshot oficial; nunca se inventam IDs.

## Instalação
```powershell
python -m pip install -r automation/requirements.txt
# Opcional, para automatizar a Central de Afiliados no Edge:
python -m pip install -r automation/requirements-browser.txt
# Caso use --browser chromium, instale o navegador Playwright uma vez:
python -m playwright install chromium
```
Playwright usa `automation/data/browser-profile` (ignorado pelo Git). Cookies do perfil são sensíveis. Não envie para ninguém.

## 1. Uma URL de anúncio
```powershell
python automation/garimpo.py ingest-url "https://produto.mercadolivre.com.br/MLB-1234567890-anuncio"
```
O ID é exemplo: use URL verdadeira. O script retorna ID local `mlb1234567890` (se for anúncio) ou `url-...` (sem ID verificável).

Pode fornecer imagem local se API/página não permitirem baixar:
```powershell
python automation/garimpo.py ingest-url "URL_REAL" --image-file "C:\\caminho\\foto.webp" --confirm-image-rights --category casa --title "Título conferido"
```
Use `--confirm-image-rights` **somente** após verificar a licença/autorização de uso comercial. Com a flag e uma URL autorizada de mídia mlstatic o script tentará baixar a foto; sem ela não baixa imagem. Se a API falhar, título/categoria podem precisar ser informados.

## 2. Link de afiliado (opcional: navegador)
A Central de Afiliados exige sessão autenticada. Faça login **manualmente** no navegador aberto pelo Playwright. O assistente navega da página inicial para a Central, tenta o **Gerador de Links**, aceita interação manual se o layout não for reconhecido, e lê **somente uma URL do Mercado Livre** copiada. Não lê senha e não usa endpoint interno/privado.

```powershell
python automation/garimpo.py affiliate-link mlb1234567890 --product-url "URL_REAL_DO_ANUNCIO"
python automation/garimpo.py show mlb1234567890
python automation/garimpo.py confirm-link mlb1234567890 --confirm
```
Confirme que o URL capturado pertence ao produto certo e foi gerado na sua conta afiliada. `confirm-link` não publica nada. Se não quiser Playwright, informe o link obtido manualmente:
```powershell
python automation/garimpo.py review mlb1234567890 --affiliate-url "https://meli.la/LINK_REAL" --confirm-affiliate-link
```
Também disponível `ingest-url ... --affiliate-browser` ou `auto ... --affiliate-browser`; não use junto com `--affiliate-url`.

## 3. Completar revisão antes de publicar
```powershell
python automation/garimpo.py review mlb1234567890 --title "Título real" --category casa --affiliate-url "https://meli.la/LINK_REAL" --image-file "C:\\caminho\\foto.webp" --confirm-title --confirm-category --confirm-affiliate-link --confirm-image-rights
```
Os sinais de confirmação são decisões humanas: **o script não pode certificar licença nem comissões**.

## 4. Selecionar conhecimento e gerar criativo

Antes da edição generativa, confira qual documento é escolhido automaticamente para o produto:
```powershell
python automation/garimpo.py knowledge RS1033-VHDC
python automation/garimpo.py knowledge RS1033-VHDC --prompt
```
O refletor deve usar `knowledge/categories/iluminacao_jardim.md`, não uma instrução genérica de Casa. Em outros produtos, o código prioriza título especializado, depois nome oficial da categoria MLB quando disponível e, por fim, compatibilidade com `casa`, `tecnologia`, `organizacao` e `lifestyle`. A classificação é heurística e não substitui verificação do anúncio.

Para atualizar apenas a árvore raiz oficial:
```powershell
python automation/sync_categories.py --with-oauth
```
Quando a API bloquear a consulta, o snapshot anterior é preservado. Para adicionar nicho, crie `.md` em `knowledge/categories` e atualize `knowledge/catalog/profiles.json`.

```powershell
python automation/garimpo.py stylize mlb1234567890 --provider local
python automation/garimpo.py prepare mlb1234567890
```
Gera `automation/out/styled/mlb1234567890-styled.png` e `automation/out/mlb1234567890.jpg` (1000 × 1500). Revise fidelidade visual ao produto.

Para gerar uma nova cena ilustrativa via IA (somente se autorizou o uso da imagem e aceitou cobrança), defina `OPENAI_API_KEY` **somente localmente** e execute:
```powershell
python automation/garimpo.py stylize mlb1234567890 --provider openai --allow-paid-ai
python automation/garimpo.py prepare mlb1234567890
```
A IA pode alterar aparência/atributos: faça inspeção humana rigorosa. Uso da API de imagens pode ser cobrado.

## 5. Pipeline `auto` (não publica)
```powershell
python automation/garimpo.py auto "URL_REAL_DO_ANUNCIO" --image-file "C:\\caminho\\foto.webp" --confirm-image-rights --title "Título real" --category casa --affiliate-url "https://meli.la/LINK_REAL" --confirm-affiliate-link --provider local
```
`--provider none` pula stylize. `--provider openai --allow-paid-ai` envia imagem autorizada ao provedor. **Sem imagem ou direitos confirmados, `auto` cria draft e pausa a preparação**. Se o mesmo ID já existir, não sobrescreve.

## 6. Aprovar/publicar (Pinterest)
```powershell
python automation/garimpo.py list
python automation/garimpo.py boards
python automation/garimpo.py approve mlb1234567890 --board-id ID_REAL_DA_PASTA --confirm
python automation/garimpo.py publish mlb1234567890 --confirm
```
Aprovação só é permitida quando título, categoria, direitos da imagem e URL de afiliado forem confirmados para drafts criados por URL. O Pinterest precisa conceder `pins:write` e `boards:read`. Nada é publicado pelo comando `auto`.

## Limitações dos sites
- Barra/Central de Afiliados podem ter seletores variáveis e CAPTCHAs; o script **não os contorna** e pode solicitar cliques manuais. Cadastro da rede Pinterest no programa afiliado deve cumprir regras do Mercado Livre.
- API de itens pode responder HTTP 403 a anúncios de terceiros. Não há garantias de extrair título/fotos por URL.
- Não acessar conteúdo privado nem redistribuir fotos sem direitos. Use o gerador oficial de links e revise se o produto dá direito a comissão.
