# Garimpo da Vez — catálogo Excel automático

O arquivo Excel (XLSX) substitui o preenchimento manual de CSV no fluxo
normal. O programa cria e atualiza a planilha autonomamente enquanto você
descobre e prepara produtos.

## Arquitetura

- Fila operacional: automation/data/pins.json — fonte de verdade de
  aprovações, direitos, links individuais e estado da publicação.
- Catálogo automático: automation/data/produtos.xlsx — atualização a
  cada salvamento da fila.
- Proteção de alterações: automation/data/produtos.xlsx.sha256 — impede
  sobrescrever sem aviso uma planilha modificada manualmente.
- A pasta automation/data está no gitignore. O catálogo contém links
  comerciais e caminhos locais: NÃO publique o XLSX no GitHub.

A fila JSON é mantida porque a simples edição de células não pode
aprovar um Pin, autorizar direitos de imagem ou confirmar comissão.

## Três abas do XLSX

1. Produtos: filtros, ID local, ID de anúncio MLB, título, categoria,
   nicho, categoria MLB oficial, preço/moeda somente quando verificáveis,
   URL de anúncio, link individual do afiliado, confirmação, origem,
   caminho da imagem original e do Pin, direitos, estilo, provider,
   status, datas e notas.
2. Resumo: total de registros, links confirmados, criativos prontos
   e contagens de cada estado por fórmulas Excel.
3. Categorias: snapshot de categorias raiz da API oficial Mercado Livre.
   Essas categorias não comprovam elegibilidade de comissão.

## Uso sem CSV nem ID manual

### 1. Criar o Excel com os produtos já cadastrados

    python automation\garimpo.py excel-sync

Abra automation/data/produtos.xlsx para consultar. A atualização posterior
é AUTOMÁTICA após ingest-url, ml-discover, review, affiliate-link,
confirm-link, confirm-image-rights, stylize, prepare, approve, publish
e outras alterações persistidas na fila. Não precisa executar excel-sync
a cada novo produto.

### 2. Descobrir e registrar produtos novos

    python automation\garimpo.py ml-discover

Selecione categoria e subcategoria, pesquise por nome e escolha o anúncio
pelo número no terminal. A linha entra automaticamente na aba Produtos.

Se a API oficial retornar HTTP 403, forneça somente a URL real:

    python automation\garimpo.py ingest-url "URL_REAL_DO_ANUNCIO"

O ID local será gerado automaticamente. O link de comissão permanece vazio
até ser gerado na opção Compartilhar/Copiar link da Central de Afiliados
para o anúncio escolhido.

### 3. Completar o ciclo por produto

    python automation\garimpo.py show
    python automation\garimpo.py affiliate-link
    python automation\garimpo.py confirm-link --confirm
    python automation\garimpo.py stylize --provider opencv
    python automation\garimpo.py prepare --style editorial
    python automation\garimpo.py export-business --choose

A foto, o link e outros campos só são marcados como confirmados depois da
revisão humana adequada. O OpenCV precisa da dependência opcional documentada
em requirements-opencv.txt. Nada será publicado automaticamente.

## Importar um Excel existente

Também é possível cadastrar registros NOVOS a partir de um XLSX externo:

    python automation\garimpo.py import-xlsx "C:\caminho\minha-planilha.xlsx"

A planilha precisa ter uma aba chamada Produtos e os cabeçalhos correspondentes
ao XLSX gerado. Para facilitar, use excel-sync para criar um modelo vazio
e salve uma CÓPIA para preencher manualmente.

O importador aceita IDs locais ausentes (cria um ID local determinístico),
não inventa IDs MLB, exige título e categoria ampla válida (casa, tecnologia,
organizacao ou lifestyle), rejeita URLs inválidas, e ignora produtos já
cadastrados. Por segurança, dados da planilha entram como rascunhos:
NÃO herdam aprovação, direitos, nem confirmação do link de afiliado.

## Edições manuais e arquivo aberto no Excel

O XLSX automático é uma visão gerada da fila. Se editar o arquivo original
no Excel, a proteção SHA-256 impede sobrescrita automática e preserva os
dados JSON. Para incorporar novas linhas, importe uma cópia revisada por
import-xlsx; alterações de registros existentes devem ser confirmadas com
review no CLI.

Para recriar a planilha após conferir manualmente que suas edições não
precisam ser preservadas:

    python automation\garimpo.py excel-sync --force

Essa opção sobrescreve SOMENTE o Excel, nunca a fila JSON.

Se o Excel mantiver o arquivo bloqueado, feche-o e execute:

    python automation\garimpo.py excel-sync

## CSV legado

import-csv continua disponível somente por compatibilidade. Novos produtos
não precisam de CSV. Nenhuma API de geração de links de comissão foi incluída.

## Validar

    python -m unittest discover -s automation\tests -q
