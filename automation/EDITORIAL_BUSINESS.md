# Garimpo da Vez — Fotografia natural + Pinterest Business

## Descoberta de produtos sem IDs manuais

O novo comando `python automation/garimpo.py ml-discover` apresenta categorias e subcategorias oficiais do Mercado Livre e tenta buscar anúncios reais. Basta escolher pelo **número**; o anúncio é importado como rascunho, sem link de afiliado inventado. Se a API de busca responder HTTP 403, continue copiando a URL real do anúncio para `ingest-url`. Os comandos por produto (`prepare`, `stylize`, `review`, `affiliate-link`, `show`, etc.) agora aceitam ID opcional e oferecem menu numerado e filtros `--choose-category`/`--choose-search`.

A melhoria fotográfica local `--provider opencv` usa CPU e exige apenas a instalação opcional `pip install -r automation/requirements-opencv.txt`. Veja [ML_DISCOVERY.md](ML_DISCOVERY.md) para documentação e comandos. Os links de afiliado continuam vindos exclusivamente da Central de Afiliados do Mercado Livre, por produto, jamais da API de anúncios.

**Objetivo:** preparar fotografias de produto com aparência orgânica e publicação manual,
não banners com preço, cabeçalho verde e chamadas publicitárias.

## Decisões preservadas

- Cada produto da fila tem seu próprio ID local, item MLB e link de afiliado;
  o script **não gera link de comissão pela API do Mercado Livre**.
- Link vem do Compartilhar/Copiar link na Central de Afiliados, via Playwright/Edge
  ou coleta manual, e deve ser confirmado contra o produto escolhido. Um link
  `meli.la` pode ocultar o MLB: a confirmação humana segue obrigatória.
- Não há link fixo global, publicação em massa, agendamento, compra, alteração
  de produto nem geração automática de comissão.
- Não publicamos Pins em nome do usuário sem confirmação separada.

## Instalação (PowerShell na raiz)

```powershell
git pull --ff-only origin main
.\.venv\Scripts\Activate.ps1
python -m pip install -r automation\requirements.txt
python -m unittest discover -s automation\tests -q
```

## A. Produto existente (exemplo: RS1033-VHDC)

Para partir da foto original, ignorando qualquer montagem antiga que contenha
banners, o novo modo editorial é:

```powershell
python automation\garimpo.py show RS1033-VHDC
python automation\garimpo.py knowledge RS1033-VHDC --prompt
python automation\garimpo.py prepare RS1033-VHDC --style editorial --source original
Start-Process .\automation\out\RS1033-VHDC.jpg
```

O modo editorial é **padrão**; `--source original` é recomendado para Pins
antigos que já tenham uma imagem estilizada com cabeçalho. Ele gera 1000 × 1500
sem sobrepor texto/logo. **Não consegue remover anúncios já impressos na foto
de origem.** Se a foto original já tiver propaganda, obtenha uma imagem limpa
com direitos de uso comercial.

Opcional: apenas melhorar cor/contraste localmente, sem IA nem serviço pago:

```powershell
python automation\garimpo.py stylize RS1033-VHDC --provider local
python automation\garimpo.py prepare RS1033-VHDC --style editorial
```

Modo antigo (somente quando solicitado):

```powershell
python automation\garimpo.py prepare RS1033-VHDC --style branded
```

## B. Novo produto: URL -> Central de Afiliados -> foto

```powershell
python automation\garimpo.py ingest-url "URL_REAL_DO_ANUNCIO"
python automation\garimpo.py list
python automation\garimpo.py show ID_LOCAL
python automation\garimpo.py knowledge ID_LOCAL --prompt
```

A consulta do Mercado Livre pode retornar HTTP 403 para anúncios de terceiros;
não presume título, foto ou categorias ausentes. Não gera link de comissão.

Revise/complemente metadados reais e indique uma foto permitida:

```powershell
python automation\garimpo.py review ID_LOCAL --title "TITULO_VERIFICADO" --category casa --image-file "C:\caminho\foto-autorizada.webp" --confirm-title --confirm-category --confirm-image-rights
```

Para obter o **link desse mesmo produto** pela Central de Afiliados:

```powershell
python automation\garimpo.py affiliate-link ID_LOCAL --product-url "URL_REAL_DO_ANUNCIO"
python automation\garimpo.py show ID_LOCAL
python automation\garimpo.py confirm-link ID_LOCAL --confirm
```

Ou cole diretamente o link individual gerado no Compartilhar oficial:

```powershell
python automation\garimpo.py review ID_LOCAL --affiliate-url "https://meli.la/LINK_REAL_DO_PRODUTO" --confirm-affiliate-link
```

**Nunca reutilize o URL copiado de outro item.** Confirme a correspondência
entre título/MLB/categoria do anúncio exibido e o produto selecionado no painel.

## Exportação sem digitar o ID do produto

A fila local já relaciona **ID local**, **ID MLB**, **categoria**, **imagem** e
**link de afiliado individual**. Portanto, não é necessário identificar o
produto novamente no comando de exportação:

```powershell
# Exporta TODOS os Pins preparados/aprovados e prontos para publicação assistida
python automation\garimpo.py export-business

# Se preferir somente o último Pin preparado e elegível
python automation\garimpo.py export-business --latest

# Ainda é possível exportar um produto específico
python automation\garimpo.py export-business RS1033-VHDC
```

O script verifica **cada Pin isoladamente**: foto disponível com direitos
confirmados, `status=prepared`/`approved`, link pessoal do produto previamente
confirmado e campos revisados quando a origem é URL. Pins em rascunho,
publicados ou com pendências são ignorados no modo automático. Se nenhum estiver
pronto, aparece um erro com instruções para `list`/`show`.

Cada item elegível gera sua própria subpasta dentro de
`automation/out/business/`, com o seu link de comissão preservado. **Nenhum
link é gerado pela API do Mercado Livre, e nenhuma publicação ocorre.**
Usar `--latest` seleciona pelo `prepared_at` (ou `created_at` em cadastros
anteriores), nunca um link genérico.

## C. Produzir e exportar para Pinterest Business

```powershell
python automation\garimpo.py prepare ID_LOCAL --style editorial --source original
python automation\garimpo.py export-business ID_LOCAL
```

O comando cria, localmente:

- `automation/out/business/ID_LOCAL/pin.jpg` — fotografia 2:3;
- `fields.json` — título, descrição, alt text, link de destino **daquele item**
  e indicação de IA, quando o provider for generativo;
- `copy.txt` — textos para copiar/colar;
- `checklist.md` — confirmação de foto, link, categoria, pasta e IA.

No Pinterest Business:
1. Abrir **Criar Pin** na conta Garimpo da Vez.
2. Enviar `pin.jpg` (ou uma fotografia autorizada e revisada).
3. Preencher título, descrição e texto alternativo pelo `copy.txt`.
4. Escolher uma **pasta existente e correspondente à categoria**, por exemplo
   Iluminação e Áreas Externas. O script não inventa IDs de pasta.
5. Colar o link de comissão individual retornado na Central.
6. Se usou IA generativa de fato, revisar a opção **Marcar como modificado por IA**
   na interface. A API do Pinterest não recebeu nenhum parâmetro de IA não documentado.
7. Publicar ou agendar **manualmente**. Os comandos `export-business` e `auto`
   não publicam nem agendam.

Se preferir API, os comandos legados `approve ID --board-id ... --confirm` e
`publish ID --confirm` continuam separados e exigem OAuth oficial, mas não
substituem as opções da interface Business (agendamento/marcação IA).

## IA na nuvem (opcional)

Providers gratuitos podem falhar/ficar sem cotas: AI Horde e HF Spaces devem
receber imagem autorizada, consentimento explícito e licença comercial de modelo
verificada. Veja `automation/CLOUD_IMAGE_PROVIDERS.md`. Qwen ZeroGPU já
apresentou erro remoto e não deve ser tratado como geração garantida.
Se a IA editar características do produto, descarte a variação e volte
a `prepare ... --source original`.
