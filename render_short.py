"""Monta o Short vertical (1080x1920) do Bem-vindo ao Mundo Real.

Uso: python3 render_short.py PASTA
PASTA tem: roteiro.json (cenas com "fala" e "tela"), audio/00.mp3... (uma fala por cena), img/00.png...
Cada imagem dura exatamente a sua fala + uma pausa curta, então imagem, voz e legenda nunca se desencontram.
Na tela: o texto curto da cena ("tela") em cima, com efeito de entrada; a legenda palavra a palavra embaixo.
Música opcional: PASTA/musica.mp3 (fica 20 dB abaixo da voz).
"""
import json
import os
import re
import subprocess
import sys

W, H, FPS = 1080, 1920, 30
PAUSA = 0.3  # respiro depois de cada frase
AQUI = os.path.dirname(os.path.abspath(__file__))
FONTES = os.path.join(AQUI, "assets")
_whisper = None


def run(*a):
    subprocess.run(a, check=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)


def duracao(p):
    err = subprocess.run(["ffmpeg", "-i", p], capture_output=True, text=True).stderr
    h, m, s = re.search(r"Duration: (\d+):(\d+):([\d.]+)", err).groups()
    return int(h) * 3600 + int(m) * 60 + float(s)


def tempos_palavras(mp3, texto):
    """Whisper marca o tempo de cada palavra da frase; o texto exibido é sempre o do roteiro."""
    global _whisper
    import numpy as np
    from faster_whisper import WhisperModel
    if _whisper is None:
        _whisper = WhisperModel("base", device="cpu", compute_type="int8")
    pcm = subprocess.run(["ffmpeg", "-v", "error", "-i", mp3, "-ar", "16000", "-ac", "1", "-f", "f32le", "-"],
                         check=True, capture_output=True).stdout
    segs, _ = _whisper.transcribe(np.frombuffer(pcm, np.float32), language="pt", word_timestamps=True,
                                  initial_prompt=texto)
    ouvidas = [(w.start, w.end) for s in segs for w in (s.words or [])]
    roteiro = texto.split()
    if len(ouvidas) == len(roteiro):
        return [(a, b, w) for (a, b), w in zip(ouvidas, roteiro)]
    ini = ouvidas[0][0] if ouvidas else 0.0
    fim = ouvidas[-1][1] if ouvidas else duracao(mp3)
    pesos = [len(re.sub(r"\W", "", w)) + 1 for w in roteiro]
    total, t, out = sum(pesos), ini, []
    for w, p in zip(roteiro, pesos):
        d = (fim - ini) * p / total
        out.append((t, t + d, w))
        t += d
    return out


def t_ass(t):
    cs = int(round(t * 100))
    return f"{cs // 360000}:{cs // 6000 % 60:02d}:{cs // 100 % 60:02d}.{cs % 100:02d}"


def legenda(palavras, fim_cena):
    linhas, grupos = [], [palavras[i:i + 3] for i in range(0, len(palavras), 3)]
    for g, grupo in enumerate(grupos):
        fim_g = grupos[g + 1][0][0] if g + 1 < len(grupos) else fim_cena
        for k, (ini, _, _) in enumerate(grupo):
            fim = grupo[k + 1][0] if k + 1 < len(grupo) else fim_g
            txt = " ".join((f"{{\\c&H00E5FF&}}{w.upper()}{{\\c&HFFFFFF&}}" if j == k else w.upper())
                           for j, (_, _, w) in enumerate(grupo))
            linhas.append(f"Dialogue: 0,{t_ass(ini)},{t_ass(fim)},Cap,,0,0,0,,{txt}")
    return linhas


def main(pasta):
    cenas = json.load(open(os.path.join(pasta, "roteiro.json")))["cenas"]
    work = os.path.join(pasta, "work")
    os.makedirs(work, exist_ok=True)
    partes, audios, eventos, t0 = [], [], [], 0.0
    for i, c in enumerate(cenas):
        mp3 = os.path.join(pasta, "audio", f"{i:02d}.mp3")
        d = duracao(mp3) + PAUSA
        fr = max(1, int(round(d * FPS)))
        img = os.path.join(pasta, "img", f"{i:02d}.png")
        z = f"1.0+0.06*on/{fr}" if i % 2 == 0 else f"1.06-0.06*on/{fr}"
        vf = (f"scale={W}:{H}:force_original_aspect_ratio=increase,crop={W}:{H},scale={W * 2}:{H * 2},"
              f"zoompan=z='{z}':x='iw/2-(iw/zoom/2)':y='ih/2-(ih/zoom/2)':d={fr}:s={W}x{H}:fps={FPS},format=yuv420p")
        out = os.path.join(work, f"c{i:02d}.mp4")
        run("ffmpeg", "-y", "-loop", "1", "-i", img, "-vf", vf, "-frames:v", str(fr), "-r", str(FPS),
            "-c:v", "libx264", "-preset", "veryfast", "-crf", "20", out)
        partes.append(out)
        wav = os.path.join(work, f"a{i:02d}.wav")  # fala + pausa, no tamanho exato do clipe
        run("ffmpeg", "-y", "-i", mp3, "-af", f"apad=whole_dur={fr / FPS:.3f}", "-ar", "44100", "-ac", "2", wav)
        audios.append(wav)
        fim = t0 + fr / FPS
        eventos += legenda([(t0 + a, t0 + b, w) for a, b, w in tempos_palavras(mp3, c["fala"])], fim)
        if c.get("tela"):  # texto curto em cima, entrando com um "pulo"
            eventos.append(f"Dialogue: 1,{t_ass(t0 + 0.05)},{t_ass(fim)},Tela,,0,0,0,,"
                           f"{{\\fscx140\\fscy140\\t(0,180,\\fscx100\\fscy100)}}{c['tela'].upper()}")
        t0 = fim

    with open(os.path.join(work, "v.txt"), "w") as f:
        f.writelines(f"file '{os.path.basename(p)}'\n" for p in partes)
    run("ffmpeg", "-y", "-f", "concat", "-safe", "0", "-i", os.path.join(work, "v.txt"), "-c", "copy",
        os.path.join(work, "mudo.mp4"))
    with open(os.path.join(work, "a.txt"), "w") as f:
        f.writelines(f"file '{os.path.basename(a)}'\n" for a in audios)
    run("ffmpeg", "-y", "-f", "concat", "-safe", "0", "-i", os.path.join(work, "a.txt"), "-c", "copy",
        os.path.join(work, "voz.wav"))

    # voz tratada: corta graves, realça a fala, comprime, -14 LUFS (padrão de Shorts)
    filtro = ("highpass=f=80,equalizer=f=3000:t=q:w=1:g=2,"
              "acompressor=threshold=-20dB:ratio=3:attack=5:release=80:makeup=2,loudnorm=I=-14:TP=-1.5:LRA=7")
    musica = os.path.join(pasta, "musica.mp3")
    audio = os.path.join(work, "audio.wav")
    if os.path.exists(musica):
        run("ffmpeg", "-y", "-i", os.path.join(work, "voz.wav"), "-stream_loop", "-1", "-i", musica, "-filter_complex",
            f"[0:a]{filtro}[v];[1:a]volume=-20dB[m];[v][m]amix=inputs=2:duration=first[a]", "-map", "[a]", audio)
    else:
        run("ffmpeg", "-y", "-i", os.path.join(work, "voz.wav"), "-af", filtro, "-ar", "44100", "-ac", "2", audio)

    ass = os.path.join(work, "leg.ass")
    with open(ass, "w") as f:
        f.write(f"""[Script Info]
ScriptType: v4.00+
PlayResX: {W}
PlayResY: {H}

[V4+ Styles]
Format: Name, Fontname, Fontsize, PrimaryColour, SecondaryColour, OutlineColour, BackColour, Bold, Italic, Underline, StrikeOut, ScaleX, ScaleY, Spacing, Angle, BorderStyle, Outline, Shadow, Alignment, MarginL, MarginR, MarginV, Encoding
Style: Cap,Luckiest Guy,76,&H00FFFFFF,&H00FFFFFF,&H00000000,&H80000000,0,0,0,0,100,100,1,0,1,7,3,2,60,60,330,1
Style: Tela,Luckiest Guy,118,&H0000E5FF,&H0000E5FF,&H00000000,&H80000000,0,0,0,0,100,100,2,0,1,9,4,8,50,50,170,1

[Events]
Format: Layer, Start, End, Style, Name, MarginL, MarginR, MarginV, Effect, Text
""" + "\n".join(eventos) + "\n")
    saida = os.path.join(pasta, "short.mp4")
    run("ffmpeg", "-y", "-i", os.path.join(work, "mudo.mp4"), "-i", audio, "-vf", f"ass={ass}:fontsdir={FONTES}",
        "-c:v", "libx264", "-preset", "veryfast", "-crf", "20", "-c:a", "aac", "-b:a", "160k", "-shortest",
        "-movflags", "+faststart", saida)
    print(json.dumps({"video": saida, "duracao_s": round(duracao(saida), 1), "cenas": len(cenas)}))


if __name__ == "__main__":
    main(sys.argv[1])
