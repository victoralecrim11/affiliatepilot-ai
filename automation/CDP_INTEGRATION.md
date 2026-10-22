
## Edge CDP (sessao persistente do navegador dedicado)

No Windows, inicie uma instancia separada do Edge com CDP local:

```powershell
$edge = "${env:ProgramFiles(x86)}\\Microsoft\\Edge\\Application\\msedge.exe"
& $edge --remote-debugging-address=127.0.0.1 --remote-debugging-port=9333 --user-data-dir="C:\\Desenvolvimento\\Projetos\\garimpo-da-vez\\automation\\data\\edge-cdp-profile"
```

Autentique-se manualmente na Central de Afiliados uma vez nesse perfil, quando permitido. O modo CDP nao acessa automaticamente o perfil Edge pessoal, nao contorna CAPTCHA e nao publica Pins.

```powershell
python automation/garimpo.py ingest-url "URL_REAL" --affiliate-browser --cdp-url http://127.0.0.1:9333
# ou para rascunho ja existente:
python automation/garimpo.py affiliate-link ID_LOCAL --cdp-url http://127.0.0.1:9333
python automation/garimpo.py confirm-link ID_LOCAL --confirm
```

O fluxo de dados de produto ja usa `ml_ingest.py` (API oficial `/items/{id}` com metadados publicos nao verificados como fallback) e `ml_oauth.py` (token seguro); esses modulos nao foram duplicados. A geracao do link permanece no gerador oficial, com confirmacao humana. Se CDP nao estiver disponivel, omita `--cdp-url` para usar o perfil Playwright antigo ou informe o link oficial por `review --affiliate-url`. Nunca copie tokens ou perfis para o repositorio.
