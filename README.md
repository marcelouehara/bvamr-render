# bvamr-render

Short diário do canal "Bem-vindo ao Mundo Real" (GitHub Actions, todo dia 18h30 BRT, agenda no Buffer 20h30).

1. `escrever_roteiro.py`: próximo tema `fila` do `temas.md`; Gemini escreve o storyboard (fala, ideia da imagem, texto da tela) com busca no Google, gpt-5 revisa
2. `gerar_cenas.py`: gpt-5 escreve o prompt de cada imagem, Gemini revisa; Flux 3 Klein (mascote de referência) gera 1 imagem por cena, Gemini confere e refaz as reprovadas; voz do Fish frase por frase
3. `render_short.py`: vídeo 1080x1920, texto da tela, legenda palavra a palavra, trilha `assets/trilha.mp3`
4. `publicar.py`: agenda no Buffer (YouTube e TikTok conectados), marca o tema como feito e grava `historico.csv`

Segredos: OPENAI_API_KEY, KIE_API_KEY, GEMINI_API_KEY, FISH_API_KEY, FISH_VOICE, BUFFER_API_KEY.
