"""Agenda o Short no Buffer (YouTube e TikTok, os canais conectados na organização) e registra o histórico.

Uso: python3 publicar.py PASTA URL_DO_VIDEO
Agenda para hoje às 11h de Brasília; se já passou (ou falta pouco), publica na hora.
Depois marca o tema como feito no temas.md e acrescenta uma linha no historico.csv.
Ambiente: BUFFER_API_KEY.
"""
import csv
import json
import os
import re
import sys
import urllib.request
from datetime import datetime, timedelta, timezone

AQUI = os.path.dirname(os.path.abspath(__file__))
ORG = "6af877f811bd01dafc36ae1d"
BRT = timezone(timedelta(hours=-3))
HORA = (11, 0)


def buffer(query):
    req = urllib.request.Request("https://api.buffer.com", json.dumps({"query": query}).encode(), {
        "Authorization": "Bearer " + os.environ["BUFFER_API_KEY"], "Content-Type": "application/json"})
    return json.load(urllib.request.urlopen(req, timeout=60))


def main(pasta, url):
    r = json.load(open(os.path.join(pasta, "roteiro.json")))
    tema = json.load(open(os.path.join(pasta, "tema.json")))
    s = json.dumps
    tags = " ".join("#" + re.sub(r"[^a-z0-9]", "", h.lower()) for h in r.get("hashtags", []))
    fontes = "\n".join(f"Fonte: {f['nome']} ({f['url']})" for f in r.get("fontes", [])[:2])
    aviso = "Conteúdo educativo. Não é aconselhamento financeiro ou jurídico."
    legenda = f"{r['descricao']}\n\nSeja bem-vindo ao mundo real.\n\n{tags}"
    desc_yt = f"{r['descricao']}\n\n{aviso}\n{fontes}\n\nSeja bem-vindo ao mundo real.\n\n{tags} #shorts"

    agora = datetime.now(BRT)
    alvo = agora.replace(hour=HORA[0], minute=HORA[1], second=0, microsecond=0)
    if alvo - agora > timedelta(minutes=10):
        quando = f"mode: customScheduled, dueAt: {s(alvo.astimezone(timezone.utc).strftime('%Y-%m-%dT%H:%M:%SZ'))}"
    else:
        quando = "mode: shareNow"

    canais = buffer(f'{{ channels(input: {{ organizationId: "{ORG}" }}) {{ id service isDisconnected }} }}')["data"]["channels"]
    resultado = {}
    for c in canais:
        if c["isDisconnected"] or c["service"] not in ("youtube", "tiktok"):
            continue
        if c["service"] == "youtube":
            texto, meta = desc_yt, ("{ youtube: { title: " + s(r["titulo"][:100]) +
                                    ', categoryId: "27", privacy: public, madeForKids: false, isAiGenerated: false } }')
        else:
            texto, meta = legenda, "{ tiktok: { isAiGenerated: false } }"
        q = (f"mutation {{ createPost(input: {{ channelId: {s(c['id'])}, text: {s(texto)}, schedulingType: automatic, "
             f"{quando}, assets: [{{ video: {{ url: {s(url)} }} }}], metadata: {meta} }}) "
             "{ ... on PostActionSuccess { post { id dueAt } } ... on MutationError { message } } }")
        resultado[c["service"]] = buffer(q).get("data", {}).get("createPost")
    print(json.dumps(resultado, ensure_ascii=False))
    if not any(v and v.get("post") for v in resultado.values()):
        sys.exit("nenhum post criado no Buffer")

    # fila e histórico
    p = os.path.join(AQUI, "temas.md")
    linhas = open(p).read().split("\n")
    for i, ln in enumerate(linhas):
        if ln.startswith(f"| {tema['n']} |") and ln.rstrip().endswith("| fila |"):
            linhas[i] = ln.rstrip()[:-len("| fila |")] + f"| feito {agora:%d/%m} |"
    open(p, "w").write("\n".join(linhas))
    with open(os.path.join(AQUI, "historico.csv"), "a", newline="") as f:
        cenas = r["cenas"]
        csv.writer(f).writerow([f"{agora:%Y-%m-%d}", tema["n"], r["titulo"], sum(len(c["fala"].split()) for c in cenas),
                                len(cenas), "", url])


if __name__ == "__main__":
    main(sys.argv[1], sys.argv[2])
