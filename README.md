# TV Display

Controla uma TV Android (TV Box/Smart TV) pelo navegador do notebook.

- `server.py`: servidor local (Python, sem dependências). Painel em `http://localhost:8000/` (senha gerada em `senha.txt`).
- `control.html`: painel de controle.
- `tv.html`: página exibida na TV.
- `tv-app/`: app Android (WebView) que abre `tv.html`. Na primeira abertura, ou ao apertar OK/Menu, pergunta o IP do notebook.
- `speak.ps1`: voz (pt-BR) via Windows, usada pelo "Falar".
- `media/`: arquivos locais (mp3, html, APK). Não versionados.

## Uso

```bash
python3 server.py
```

Compile o APK pelo Android Studio (Build > Build APK) e instale na TV. Troque o IP no app ao mudar de rede.
