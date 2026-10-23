---
name: garimpo-da-vez-creative
description: Fotografia editorial natural e fiel ao produto com conhecimentos por categoria MLB.
---

# Skill — Garimpo da Vez

## Objetivo
Criar imagens naturais, inspiradoras e fotográficas, sem aparência de banner de venda. A fotografia original de uso comercial autorizado é a referência. Não inserir título, preço, desconto, logo, CTA nem aviso de afiliado sobre a imagem; essas informações entram nos campos nativos do Pinterest Business.

## Knowledge obrigatória
1. Ler automation/knowledge/core/guardrails.md e composition.md.
2. Escolher a categoria via select_knowledge(pin) em automation/prompt_templates.py.
3. Ler automation/knowledge/categories/<slug>.md. Aliases e nomes do Mercado Livre estão no catalog/profiles.json e catalog/mlb_categories.json (IDs oficiais, não inventados).
4. Conferir o prompt com python automation/garimpo.py knowledge ID --prompt.
5. Novos nichos devem ser adicionados somente em knowledge/categories e no catálogo. Não duplicar os textos na pasta skills.

## Criativo e publicação
- stylize com provider local é apenas correção fotográfica, sem IA. prepare cria JPG editorial 2:3 por padrão e permite --style branded para conteúdos institucionais.
- Se foto antiga contiver banner, preferir prepare ID --source original. A edição não elimina textos já embutidos na foto original.
- Edição remota exige direitos de imagem e licença comercial de modelo verificadas, consentimento para compartilhar com terceiros e revisão visual humana.
- export-business ID gera foto e campos para publicação manual no Pinterest Business, com link individual daquele produto. Marcação de conteúdo modificado por IA é checklist manual, não parâmetro de API inventado.
- Link de comissão é criado no Compartilhar/Gerador de Links da Central do Mercado Livre; a API ML fornece apenas dados de anúncio. Nunca criar link fixo ou reaproveitar URL de outro produto.
- Não inventar especificações, marcas, quantidade, garantias, depoimentos, avaliações ou elegibilidade de comissão. Nenhuma publicação sem revisão específica.
