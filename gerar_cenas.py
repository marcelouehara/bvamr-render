"""Gera imagens e voz de um Short a partir do storyboard (roteiro.json com fala, ideia, tela).

Uso: python3 gerar_cenas.py PASTA [zimage|flux]
1. gpt-5 traduz cada IDEIA em prompt de imagem (prompts/imagens.md)
2. Gemini revisa e corrige os prompts (prompts/validar_prompt.md)
3. Gera 1 imagem por cena (Flux 3 Klein com o mascote de referência; z-image só texto)
4. Gemini confere se a imagem mostra a IDEIA; as reprovadas são refeitas até 2 vezes
5. Voz do Fish frase por frase, um pouco mais devagar
Ambiente: OPENAI_API_KEY, KIE_API_KEY, GEMINI_API_KEY, FISH_API_KEY, FISH_VOICE.
"""
import base64
import io
import json
import os
import re
import sys
import time
import urllib.request
from concurrent.futures import ThreadPoolExecutor

from PIL import Image

AQUI = os.path.dirname(os.path.abspath(__file__))
KIE = {"Authorization": "Bearer " + os.environ["KIE_API_KEY"], "Content-Type": "application/json"}
GEMINI = "gemini-3.5-flash"
REF_MASCOTE = os.path.join(AQUI, "assets", "mascote_ref.jpg")
ESTILO = "Crude MS Paint mouse drawing, thick wobbly black outlines, flat bright colours, no shading, no 3D."
MASCOTE = ("The mascot: perfectly round white bald head, beige band-aid on the upper left of the forehead, big round eyes "
           "with tired grey bags, white short-sleeve t-shirt, loose red necktie, blue jeans, thin stick-figure arms, black shoes.")
VELOCIDADE = 0.92   # fala um pouco mais devagar que o normal
custo = {"openai": 0.0, "kie_imagens": 0, "gemini_chamadas": 0}


def http(url, body=None, headers=None, timeout=300):
    req = urllib.request.Request(url, json.dumps(body).encode() if body is not None else None, headers or {})
    return json.load(urllib.request.urlopen(req, timeout=timeout))


def so_json(txt, abre="{", fecha="}"):
    return json.loads(txt[txt.index(abre):txt.rindex(fecha) + 1])


def gpt(prompt, esforco="low"):
    d = http("https://api.openai.com/v1/responses", {"model": "gpt-5", "reasoning": {"effort": esforco}, "input": prompt},
             {"Authorization": "Bearer " + os.environ["OPENAI_API_KEY"], "Content-Type": "application/json"}, 900)
    u = d["usage"]
    custo["openai"] += u["input_tokens"] * 1.25e-6 + u["output_tokens"] * 10e-6
    return "".join(c.get("text", "") for o in d["output"] if o["type"] == "message" for c in o["content"])


def gemini(partes):
    custo["gemini_chamadas"] += 1
    body = {"contents": [{"parts": partes}], "generationConfig": {"responseMimeType": "application/json"}}
    for t in range(4):
        try:
            d = http(f"https://generativelanguage.googleapis.com/v1beta/models/{GEMINI}:generateContent", body,
                     {"x-goog-api-key": os.environ["GEMINI_API_KEY"], "Content-Type": "application/json"}, 300)
            return "".join(p.get("text", "") for p in d["candidates"][0]["content"]["parts"])
        except Exception as e:  # noqa: BLE001
            print("gemini tentativa", t, e)
            time.sleep(5)
    raise RuntimeError("gemini falhou")


def kie(metodo, url, body=None):
    for t in range(6):
        try:
            req = urllib.request.Request(url, json.dumps(body).encode() if body else None, KIE, method=metodo)
            d = json.load(urllib.request.urlopen(req, timeout=60))
            if d.get("code") == 429:
                raise RuntimeError("429")
            return d
        except Exception:  # noqa: BLE001
            time.sleep(3 + 3 * t)
    raise RuntimeError("kie falhou: " + url)


def sobe_referencia():
    b64 = base64.b64encode(open(REF_MASCOTE, "rb").read()).decode()
    d = http("https://kieai.redpandaai.co/api/file-base64-upload",
             {"base64Data": "data:image/jpeg;base64," + b64, "uploadPath": "bvamr", "fileName": "ref_mascote.jpg"}, KIE)
    return d["data"]["downloadUrl"]


def corpo_imagem(modelo, cena, ref):
    if modelo == "flux":
        return {"model": "flux-3/klein-edit-image", "input": {
            "prompt": f"{ESTILO} {cena} Use the mascot from the reference image exactly (round bald head, band-aid, red necktie).",
            "image_urls": [ref], "aspect_ratio": "9:16"}}
    cab = 999 - len(ESTILO) - len(MASCOTE) - 2
    return {"model": "z-image", "input": {"prompt": f"{ESTILO} {cena[:cab]} {MASCOTE}", "aspect_ratio": "9:16"}}


def gera_imagens(pasta, cenas, modelo, ref, quais, versoes):
    os.makedirs(os.path.join(pasta, "cand"), exist_ok=True)
    tarefas = {}
    for i in quais:
        for v in versoes:
            tarefas[(i, v)] = kie("POST", "https://api.kie.ai/api/v1/jobs/createTask",
                                  corpo_imagem(modelo, cenas[i]["prompt"], ref))["data"]["taskId"]
            custo["kie_imagens"] += 1
            time.sleep(0.8)
    inicio = time.time()
    while tarefas and time.time() - inicio < 900:
        for k, t in list(tarefas.items()):
            d = kie("GET", f"https://api.kie.ai/api/v1/jobs/recordInfo?taskId={t}")["data"]
            if d["state"] == "success":
                urllib.request.urlretrieve(json.loads(d["resultJson"])["resultUrls"][0],
                                           os.path.join(pasta, "cand", f"{k[0]:02d}{k[1]}.png"))
                del tarefas[k]
            elif d["state"] == "fail":
                print("imagem falhou", k, d.get("failMsg"))
                del tarefas[k]
        time.sleep(5)


def img_b64(p):
    im = Image.open(p).convert("RGB")
    im.thumbnail((640, 640))
    b = io.BytesIO()
    im.save(b, "JPEG", quality=85)
    return base64.b64encode(b.getvalue()).decode()


def escolhe(pasta, cena, i, versoes):
    cands = [v for v in versoes if os.path.exists(os.path.join(pasta, "cand", f"{i:02d}{v}.png"))]
    partes = [{"text": (
        f"Você confere imagens de um vídeo educativo. FALA: \"{cena['fala']}\". IDEIA que a imagem precisa mostrar: "
        f"\"{cena['ideia']}\". Candidatas: {', '.join(c.upper() for c in cands)}. Regras: um único mascote (careca, cabeça "
        "redonda, curativo na testa, gravata vermelha), salvo se a ideia tiver um amigo boneco-palito sem rosto; nenhum "
        "texto, letra ou número escrito; os objetos da ideia aparecem e são fáceis de reconhecer; uma pessoa leiga entende a "
        "fala só olhando. Responda JSON {\"escolha\": \"letra ou NENHUMA\", \"nota\": 0-10, \"motivo\": \"curto\"}.")}]
    for c in cands:
        partes += [{"text": c.upper() + ":"}, {"inline_data": {"mime_type": "image/jpeg",
                                                              "data": img_b64(os.path.join(pasta, "cand", f"{i:02d}{c}.png"))}}]
    return so_json(gemini(partes))


def voz(pasta, i, fala):
    out = os.path.join(pasta, "audio", f"{i:02d}.mp3")
    body = {"text": fala, "reference_id": os.environ["FISH_VOICE"], "format": "mp3", "prosody": {"speed": VELOCIDADE}}
    for t in range(3):
        try:
            req = urllib.request.Request("https://api.fish.audio/v1/tts", json.dumps(body).encode(), {
                "Authorization": "Bearer " + os.environ["FISH_API_KEY"], "Content-Type": "application/json",
                "model": "s2.1-pro-free"})
            open(out, "wb").write(urllib.request.urlopen(req, timeout=180).read())
            return
        except Exception as e:  # noqa: BLE001
            print("voz tentativa", i, t, e)
            time.sleep(4)


def main(pasta, modelo):
    r = json.load(open(os.path.join(pasta, "roteiro.json")))
    cenas = r["cenas"]
    # 1. direção de arte
    ent = {str(i + 1): {"fala": c["fala"], "ideia": c["ideia"]} for i, c in enumerate(cenas)}
    o = so_json(gpt(open(os.path.join(AQUI, "prompts", "imagens.md")).read() + "\n\nCENAS:\n" + json.dumps(ent, ensure_ascii=False)))
    for i, c in enumerate(cenas):
        c["prompt"] = o[str(i + 1)]
    # 2. Gemini revisa os prompts
    ent = {str(i + 1): {"fala": c["fala"], "ideia": c["ideia"], "prompt": c["prompt"]} for i, c in enumerate(cenas)}
    v = so_json(gemini([{"text": open(os.path.join(AQUI, "prompts", "validar_prompt.md")).read() + "\n\nCENAS:\n" +
                         json.dumps(ent, ensure_ascii=False)}]))
    corrigidos = 0
    for i, c in enumerate(cenas):
        rv = v.get(str(i + 1), {})
        if rv.get("prompt") and rv["prompt"] != c["prompt"]:
            c["prompt_original"], c["prompt"] = c["prompt"], rv["prompt"]
            c["revisao"] = rv.get("problemas", "")
            corrigidos += 1
    print(f"prompts revisados pelo Gemini: {corrigidos} de {len(cenas)} corrigidos")
    json.dump(r, open(os.path.join(pasta, "roteiro.json"), "w"), ensure_ascii=False, indent=1)
    # 3 e 4. uma imagem por cena; o Gemini confere e só as reprovadas são refeitas (até 2 vezes)
    ref = sobe_referencia() if modelo == "flux" else None
    pendentes, rodada = list(range(len(cenas))), 0
    os.makedirs(os.path.join(pasta, "img"), exist_ok=True)
    while pendentes and rodada < 3:
        versoes = "abc"[rodada]
        gera_imagens(pasta, cenas, modelo, ref, pendentes, versoes)
        with ThreadPoolExecutor(5) as ex:
            res = list(ex.map(lambda i: (i, escolhe(pasta, cenas[i], i, versoes)), pendentes))
        pendentes = []
        for i, e in res:
            esc = str(e.get("escolha", "")).lower()
            cenas[i]["checagem"] = e
            cenas[i].setdefault("notas", {})[versoes] = e.get("nota", 0)
            if esc in versoes and e.get("nota", 0) >= 7:
                Image.open(os.path.join(pasta, "cand", f"{i:02d}{esc}.png")).convert("RGB").save(
                    os.path.join(pasta, "img", f"{i:02d}.png"))
            else:
                pendentes.append(i)
                if rodada == 2:  # terceira falha: usa a de melhor nota entre as tentativas
                    melhor = max("abc", key=lambda v: cenas[i].get("notas", {}).get(v, -1))
                    Image.open(os.path.join(pasta, "cand", f"{i:02d}{melhor}.png")).convert("RGB").save(
                        os.path.join(pasta, "img", f"{i:02d}.png"))
        print(f"rodada {rodada + 1}: reprovadas {[p + 1 for p in pendentes]}")
        rodada += 1
    json.dump(r, open(os.path.join(pasta, "roteiro.json"), "w"), ensure_ascii=False, indent=1)
    # 5. voz por frase
    os.makedirs(os.path.join(pasta, "audio"), exist_ok=True)
    with ThreadPoolExecutor(4) as ex:
        list(ex.map(lambda i: voz(pasta, i, cenas[i]["fala"]), range(len(cenas))))
    print(json.dumps({"openai_usd": round(custo["openai"], 3), "imagens_kie": custo["kie_imagens"],
                      "chamadas_gemini": custo["gemini_chamadas"]}))


if __name__ == "__main__":
    main(sys.argv[1], sys.argv[2] if len(sys.argv) > 2 else "zimage")
