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
