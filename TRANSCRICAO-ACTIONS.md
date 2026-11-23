# Transcrição de áudio longo no GitHub Actions

O workflow manual transcreve em português com Faster Whisper em CPU (int8).
Ele divide o arquivo em blocos de 30 minutos e só gera a legenda final quando
todos os blocos terminam. A saída final inclui SRT e TXT. O áudio fica no disco
temporário do runner.

## Configurar uma vez

1. Crie um repositório vazio na sua conta do GitHub, sem README inicial.
   Use um repositório privado para material pessoal. Em repositório público,
   trate os artefatos de transcrição como públicos.
2. Neste clone, publique a versão preparada como branch padrão do seu repositório:

   ```powershell
   git push https://github.com/SEU-USUARIO/SEU-REPO.git HEAD:main
   ```

   O comando usa sua autenticação do GitHub e preserva o repositório original
   como remote do clone.
3. No repositório novo, vá em **Settings → Secrets and variables → Actions**.
   Crie **STT_AUDIO_URL** com um link HTTPS de download direto para o arquivo.
   Pode ser uma URL assinada de um armazenamento privado. Um link para uma
   página de visualização ou que exige login no navegador não funciona.

## Rodar

1. Abra **Actions → Transcrever áudio longo → Run workflow**.
2. Comece com **model = small** e **max_blocks = 1** para medir até 30 minutos.
3. Abra a execução e veja o tempo de cada bloco no passo **Transcrever**.
   Para continuar, volte a **Run workflow**, deixe **max_blocks = 0**, mantenha
   o mesmo modelo e informe **resume_run_id** com o número depois de
   `/actions/runs/` na URL da primeira execução.
4. Quando todos os blocos terminarem, baixe **transcricao** em **Artifacts**.

**blocos-stt** contém os blocos concluídos e o manifesto de retomada. Ambos
os artefatos expiram em 7 dias. Para retomar de novo, use o ID da execução mais
recente que guardou os blocos. O workflow baixa novamente o mesmo áudio e
confere o SHA-256 antes de reaproveitar resultados. Você pode renovar o link
no secret desde que ele continue entregando exatamente o mesmo arquivo.

Se um lote estiver chegando ao limite de execução, use um valor menor em
**max_blocks**. Para trocar de arquivo ou modelo, deixe **resume_run_id** vazio.

## Usar pela IA com MCP

O cliente MCP só aciona e consulta o GitHub. A transcrição roda nos runners e
continua mesmo se você fechar a IA depois de receber o ID.

1. Crie um [token fine-grained](https://github.com/settings/personal-access-tokens/new)
   limitado ao repositório **vini-ronin/LocalCaption** com permissão
   **Actions: Read and write**. Configure-o no ambiente do cliente MCP como
   **LOCALCAPTION_GITHUB_TOKEN**.
2. Para a IA poder enviar um link diferente por tarefa, gere uma chave:

   ```powershell
   uv run --no-project --with-requirements requirements-mcp.txt python -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())"
   ```

   Guarde o mesmo valor como **STT_INPUT_KEY** em dois lugares: nos secrets de
   Actions do repo e no ambiente do cliente MCP. O link vai criptografado
   no disparo do workflow. Se você preferir usar só o link pré-configurado via
   **STT_AUDIO_URL**, pode pular este passo e pedir à IA para deixar
   `audio_url` vazio.
3. Cadastre um servidor MCP **stdio**, com comando `uv` e os argumentos abaixo.
   Use o caminho absoluto do clone e injete as variáveis acima pelo mecanismo
   de segredos ou configuração privada do seu cliente.

   ```json
   {
     "command": "uv",
     "args": [
       "run", "--no-project", "--with-requirements",
       "C:/Users/viniandrade/Documents/ViniProject/pesquisas/stt-repos/localcaption/requirements-mcp.txt",
       "python",
       "C:/Users/viniandrade/Documents/ViniProject/pesquisas/stt-repos/localcaption/scripts/localcaption_mcp.py"
     ]
   }
   ```

Peça, por exemplo: “Inicie a transcrição deste link em português e me dê o
ID. Depois consulte o ID e me passe o SRT quando estiver pronto.”

- **iniciar_transcricao** devolve o ID da execução sem esperar o áudio inteiro.
- **consultar_transcricao** informa o estado, se há resultado e se dá para retomar.
- **ler_transcricao** devolve uma página do texto ou SRT e o link do artefato
  completo. Para um arquivo longo, prefira baixar o artefato inteiro.

O MCP aceita links de download direto e v?deos p?blicos do YouTube.
Se o YouTube exigir login ou verifica??o no runner, use um link direto do arquivo.
Para arquivos do PC, envie primeiro
para um armazenamento que forneça um link HTTPS. Em repositório público,
trate a transcrição nos artefatos como pública.

Para integrar sem MCP, use a
[REST API de Actions](https://docs.github.com/en/rest/actions/workflows#create-a-workflow-dispatch-event)
com a versão `2026-03-10`. Dispare `transcrever-audio.yml` na branch `main` e
use o `workflow_run_id` retornado para consultar o job e seus artefatos. Deixe
`encrypted_source` de fora para usar o secret já configurado no repo.
