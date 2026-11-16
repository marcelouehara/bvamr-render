"""Escreve o storyboard do próximo Short: Gemini escreve (com busca no Google), gpt-5 revisa e ajusta.

Uso: python3 escrever_roteiro.py PASTA
Pega o primeiro tema com status "fila" do temas.md e grava PASTA/roteiro.json e PASTA/tema.json.
Ambiente: GEMINI_API_KEY, OPENAI_API_KEY.
"""
import json
import os
import re
import sys
import urllib.request

AQUI = os.path.dirname(os.path.abspath(__file__))
GEMINI = "gemini-3.5-flash"


def http(url, body, headers, timeout=600):
    req = urllib.request.Request(url, json.dumps(body).encode(), headers)
    return json.load(urllib.request.urlopen(req, timeout=timeout))


def so_json(txt):
    return json.loads(txt[txt.index("{"):txt.rindex("}") + 1])


def proximo_tema():
    for linha in open(os.path.join(AQUI, "temas.md")):
        cols = [c.strip() for c in linha.strip().strip("|").split("|")]
        if len(cols) == 6 and cols[0].isdigit() and cols[5] == "fila":
            return {"n": int(cols[0]), "area": cols[1], "titulo": cols[2], "analogia": cols[3], "fonte": cols[4]}
    raise SystemExit("fila de temas vazia")


def limpa(txt):
    txt = re.sub(r"\s*\(\[[^\]]*\]\([^)]*\)\)", "", txt)  # citação de busca colada na fala
    txt = re.sub(r"\s*\[\d+(?:,\s*\d+)*\]", "", txt)
    return txt.replace("—", ",").strip()


def main(pasta):
    os.makedirs(pasta, exist_ok=True)
    tema = proximo_tema()
    p = (open(os.path.join(AQUI, "prompts", "roteiro.md")).read()
         .replace("{{TITULO}}", tema["titulo"]).replace("{{ANALOGIA}}", tema["analogia"]).replace("{{FONTE}}", tema["fonte"]))
    # 1. Gemini escreve, pesquisando no Google
    d = http(f"https://generativelanguage.googleapis.com/v1beta/models/{GEMINI}:generateContent",
             {"contents": [{"parts": [{"text": p}]}], "tools": [{"google_search": {}}]},
             {"x-goog-api-key": os.environ["GEMINI_API_KEY"], "Content-Type": "application/json"})
    rascunho = so_json("".join(x.get("text", "") for x in d["candidates"][0]["content"]["parts"]))
    # 2. gpt-5 revisa e ajusta
    d = http("https://api.openai.com/v1/responses",
             {"model": "gpt-5", "reasoning": {"effort": "medium"},
              "input": open(os.path.join(AQUI, "prompts", "revisao.md")).read() + "\n\nSTORYBOARD:\n" +
              json.dumps(rascunho, ensure_ascii=False)},
             {"Authorization": "Bearer " + os.environ["OPENAI_API_KEY"], "Content-Type": "application/json"}, 900)
    u = d["usage"]
    r = so_json("".join(c.get("text", "") for o in d["output"] if o["type"] == "message" for c in o["content"]))
    for c in r["cenas"]:
        c["fala"] = limpa(c["fala"])
    r["titulo"] = r.get("titulo") or tema["titulo"]
    json.dump(r, open(os.path.join(pasta, "roteiro.json"), "w"), ensure_ascii=False, indent=1)
    json.dump(tema, open(os.path.join(pasta, "tema.json"), "w"), ensure_ascii=False)
    palavras = sum(len(c["fala"].split()) for c in r["cenas"])
    print(json.dumps({"tema": tema["titulo"], "cenas": len(r["cenas"]), "palavras": palavras,
                      "gpt5_usd": round(u["input_tokens"] * 1.25e-6 + u["output_tokens"] * 10e-6, 3),
                      "ajustes": r.get("ajustes", [])[:6]}, ensure_ascii=False))


if __name__ == "__main__":
    main(sys.argv[1])
