# Provedores gratuitos na nuvem (AI Horde e HF Spaces)

Sem GPU dedicada e sem contratar API de imagens. Tratamento Pillow local segue padrão.
O uso de qualquer serviço externo requer confirmação de direitos, licença e compartilhamento.

## Segurança e limites

- AI Horde: GPU de voluntários. Workers podem acessar imagem e prompt; anonimato não significa privacidade. Operação anônima tem fila e pode compartilhar resultados.
- Hugging Face: cada Space define sua própria API. Integração suporta somente 2 parâmetros configuráveis (foto e prompt). Escolha Space público, editor de imagem e modelo com licença comercial explicitamente verificada.
- Uso comercial: o serviço gratuito NÃO garante licença do modelo, LoRA ou fotografia. A flags --confirm-model-license não faz auditoria jurídica: expressa uma verificação humana.
- Só enviar foto com autorização de uso comercial. Use --allow-public-processing apenas quando concordar com o envio a terceiros.
- HF Spaces é acessado SEM TOKEN (token=False), evitando cobrança atrelada à conta e vazamento de credenciais; não chama duplicate/upgrades.
- A falha da nuvem não altera criativo antigo. --fallback-local, se solicitado, faz Pillow e registra provider real como local. Nada publica Pins automaticamente.
- IA pode deformar produto e inventar atributos. Compare com o anúncio real antes de aprovar.

## Instalação no PowerShell

    git pull --ff-only origin main
    .\.venv\Scripts\Activate.ps1
    python -m pip install -r automation\requirements-cloud.txt
    python -m unittest discover -s automation\tests -q

A dependência Gradio é necessária apenas para Hugging Face.

## AI Horde — modelo deve ser escolhido pela pessoa

Consulte os modelos ativos na interface/documentação AI Horde, confirme que
o modelo escolhido aceita img2img e que SUA licença permite uso comercial.
O script não escolhe um modelo desconhecido automaticamente.

    $env:AIHORDE_MODEL = "NOME_EXATO_DO_MODELO_COM_LICENCA_VERIFICADA"

    python automation\garimpo.py knowledge RS1033-VHDC --prompt
    python automation\garimpo.py stylize RS1033-VHDC --provider aihorde --allow-public-processing --confirm-model-license

O provedor envia a foto em WebP, img2img com força de alteração 0.27,
512 x 768, 20 steps e somente uma imagem. A fila pode exceder 180s.

Para fallback EXPLÍCITO sem IA:

    python automation\garimpo.py stylize RS1033-VHDC --provider aihorde --allow-public-processing --confirm-model-license --fallback-local

Chave pessoal AIHORDE_API_KEY é opcional; não a comite. Com uso anônimo o compartilhamento pode ser compulsório.

## Space verificado para começar — Qwen-Image-Edit

Em 22/10/2026, o endpoint público de Qwen/Qwen-Image-Edit respondeu à inspeção
real do Gradio com `/infer`, parâmetros obrigatórios `image` e `prompt`
e retorno de imagem. O modelo Qwen/Qwen-Image-Edit declara Apache 2.0
(modelo e licença podem mudar). O Space estava marcado como ZeroGPU.
A inspeção não gerou imagem, não utilizou GPU nem consumiu cotas.
Nenhuma disponibilidade futura, elegibilidade de uso comercial da sua foto
ou qualidade de geração pode ser garantida.

No PowerShell, para usar **um Pin preparado com imagem autorizada**:

    $env:HF_SPACE_ID = "Qwen/Qwen-Image-Edit"
    $env:HF_SPACE_API_NAME = "/infer"

    python automation\garimpo.py knowledge RS1033-VHDC --prompt
    python automation\garimpo.py stylize RS1033-VHDC --provider hf-spaces --allow-public-processing --confirm-model-license --fallback-local
    python automation\garimpo.py prepare RS1033-VHDC
    Start-Process .\automation\out\RS1033-VHDC.jpg

Com `--fallback-local`, indisponibilidade do Space resulta em tratamento
Pillow **sem IA**, claramente informado. Remova a flag para testar apenas IA
gratuita e receber o erro exato se não houver cota. A foto e o prompt serão
enviados ao Space público; só execute com direitos e consentimento.

Modelo: https://huggingface.co/Qwen/Qwen-Image-Edit
Space: https://huggingface.co/spaces/Qwen/Qwen-Image-Edit

## Hugging Face Space público

Identifique um Space GRADIO público com edição de imagem, verifique licença
comercial do modelo e clique em Use via API. Anote os nomes exatos da rota,
parâmetro de imagem e parâmetro de prompt. Não existe API padrão de edição
para todos os Spaces. Se exigir outros parâmetros, este adapter NÃO serve.

    $env:HF_SPACE_ID = "AUTOR/NOME_DO_SPACE"
    $env:HF_SPACE_API_NAME = "/ROTA_DE_EDICAO"

    python automation\garimpo.py stylize RS1033-VHDC --provider hf-spaces --hf-image-arg image --hf-prompt-arg prompt --allow-public-processing --confirm-model-license

Hugging Face ZeroGPU oferece cotas públicas sujeitas à disponibilidade; sem token,
a cota anônima pode ser extremamente limitada. Não há promessa de edição
ilimitada, gratuita, nem licença comercial implícita.

## Gerar, revisar e preparar Pin final

    python automation\garimpo.py show RS1033-VHDC
    python automation\garimpo.py knowledge RS1033-VHDC --prompt
    python automation\garimpo.py prepare RS1033-VHDC
    Start-Process .\automation\out\RS1033-VHDC.jpg

Se a IA alterar atributos do produto, rode o modo local para retornar à foto real:

    python automation\garimpo.py stylize RS1033-VHDC --provider local
    python automation\garimpo.py prepare RS1033-VHDC

Para produto novo, use ingest-url, review e affiliate-link conforme
PIPELINE.md. O comando auto também aceita --provider aihorde ou hf-spaces,
com as mesmas flags explícitas de consentimento e licença.


## Diagnosticar falhas no Qwen / Hugging Face antes de tentar nova geração

### Ajuste Qwen para erros AppError sem diagnóstico

O código-fonte do Space `Qwen/Qwen-Image-Edit` declara `rewrite_prompt=True`
por padrão, utilizando internamente o DashScope para reformular prompts.
Se esse serviço remoto falhar, pode resultar em `AppError` sem mensagem.
Como o Garimpo já constrói o prompt com knowledge/skills, nosso adapter
envia `rewrite_prompt=False` e `num_inference_steps=20` **somente** para
`Qwen/Qwen-Image-Edit` na rota `/infer`. É uma medida de compatibilidade,
não um contorno de cota nem garantia de geração. Outros Spaces preservam
seus parâmetros-padrão.

Para nova tentativa, confirme direitos comerciais da foto e licença do
modelo, e aceite o envio público do conteúdo:

```powershell
python automation\garimpo.py hf-check --space Qwen/Qwen-Image-Edit --api-name /infer
python automation\garimpo.py stylize RS1033-VHDC --provider hf-spaces --hf-space Qwen/Qwen-Image-Edit --hf-api-name /infer --allow-public-processing --confirm-model-license
```

Se `AppError` persistir, o problema poderá estar na cota de acesso anônimo,
na instabilidade do ZeroGPU ou na execução do modelo. Não faça tentativas
repetidas em loop; consulte a interface do Space e considere AI Horde
ou o fallback local não generativo.

O erro antigo `Space gratuito indisponível, cota esgotada ou assinatura da API incompatível`
misturava causas distintas. A partir da correção, o erro é classificado sem exibir
tokens nem respostas sensíveis. Para verificar apenas API e metadados **sem GPU**
e **sem enviar imagem**, execute:

```powershell
python automation\garimpo.py hf-check --space Qwen/Qwen-Image-Edit --api-name /infer
```

Resultado esperado para a API observada em 22/10/2026: `stage=RUNNING`,
`hardware=zero-a10g`, `compatible=true`, parâmetros obrigatórios `image` e
`prompt`. Isso **não verifica cota, autorização ou geração real**; apenas
confirma que os parâmetros continuam compatíveis.

Conforme documentação ZeroGPU, solicitações anônimas dispõem de cerca de
**2 minutos de GPU por dia** e têm prioridade baixa; a interface autenticada
com conta Free possui cotas diferentes (5 minutos), mas este adapter envia
`token=False` para evitar consumo de créditos ou cobrança automatizada.
Acesse diretamente a interface gratuita no navegador para verificar se ela
exige login ou retorna erro de quota. **Não altere o script para enviar
seus tokens automaticamente**; contas elegíveis podem ter cobrança adicional
depois da cota gratuita.

Se aparecer:
- `limite`/`ZeroGPU`: há indicação de cota/uso anônimo esgotado;
- `autenticação`: o Space não permitiu a sessão anônima;
- `assinatura`: interface/rota/parâmetros podem ter mudado;
- `falha remota`: o serviço pode ocultar o erro original; não atribuir a cota
  sem evidência.

Alternativas: tentar novamente após o reinício de cota, usar outro Space
público de edição com licença e API compatíveis, ou o provider
`aihorde` com modelo comercialmente permitido. `--fallback-local`
aplica apenas Pillow, **não é IA generativa**.

Fontes: https://huggingface.co/docs/hub/spaces-zerogpu
e https://huggingface.co/docs/hub/spaces-api-endpoints

## Fontes oficiais consultadas (outubro/2026)

- https://aihorde.net/docs/image/settings/img2img/
- https://github.com/Haidra-Org/AI-Horde/blob/main/README_integration.md
- https://github.com/Haidra-Org/AI-Horde/blob/main/FAQ.md
- https://huggingface.co/docs/hub/spaces-api-endpoints
- https://huggingface.co/docs/hub/spaces-zerogpu
