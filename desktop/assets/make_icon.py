"""Identidade visual do Pons (mesma família do Dispersio PDF, Convergio, Instantia e Ratio).

Gera: logo.png (1024), pons.png (256), pons.ico (16–256), as imagens do instalador e o ícone do Android.
"""
import math
import os

from PIL import Image, ImageDraw, ImageFilter, ImageChops

S = 2048
U = S / 1024
INDIGO_1, INDIGO_2 = (24, 16, 70), (70, 38, 176)
VIOLETA, AZUL, DOURADO = (186, 140, 255), (100, 150, 255), (255, 182, 80)


def u(*v):
    return [x * U for x in v]


def gradiente(size, stops, angulo=90):
    """Gradiente linear em qualquer ângulo; stops = [(pos, (r,g,b[,a])), ...]."""
    n = 256
    g = Image.new("RGBA", (n, n))
    px = g.load()
    ca, sa = math.cos(math.radians(angulo)), math.sin(math.radians(angulo))
    for y in range(n):
        for x in range(n):
            t = ((x / (n - 1) - .5) * ca + (y / (n - 1) - .5) * sa) / (abs(ca) * .5 + abs(sa) * .5) * .5 + .5
            t = min(1, max(0, t))
            for i in range(len(stops) - 1):
                p0, c0 = stops[i]
                p1, c1 = stops[i + 1]
                if p0 <= t <= p1:
                    f = (t - p0) / max(1e-6, p1 - p0)
                    c0 = c0 + (255,) * (4 - len(c0))
                    c1 = c1 + (255,) * (4 - len(c1))
                    px[x, y] = tuple(int(c0[j] + (c1[j] - c0[j]) * f) for j in range(4))
                    break
    return g.resize(size, Image.BICUBIC)


def radial(centro, raio, cor, forca=1.0, expo=2.0):
    m = Image.new("L", (160, 160), 0)
    cx, cy, r = centro[0] / S * 159, centro[1] / S * 159, raio / S * 159
    px = m.load()
    for y in range(160):
        for x in range(160):
            px[x, y] = int(255 * forca * max(0.0, 1 - math.hypot(x - cx, y - cy) / r) ** expo)
    c = Image.new("RGBA", (S, S), cor + (0,))
    c.putalpha(m.resize((S, S), Image.BICUBIC))
    return c


def preencher(mascara, cor_ou_grad):
    if isinstance(cor_ou_grad, tuple):
        cam = Image.new("RGBA", (S, S), cor_ou_grad[:3] + (255,))
        a = mascara if len(cor_ou_grad) == 3 else mascara.point(lambda v: v * cor_ou_grad[3] // 255)
    else:
        cam = cor_ou_grad.copy()
        a = ImageChops.multiply(cam.getchannel("A"), mascara)
    cam.putalpha(a)
    return cam


def arredondar(mascara, raio):
    """Arredonda os cantos de uma máscara (desfoque + limiar)."""
    m = mascara.filter(ImageFilter.GaussianBlur(raio)).point(lambda v: 255 if v > 128 else 0)
    return m.filter(ImageFilter.GaussianBlur(1.2 * U))


def poligono(pts, raio=0):
    m = Image.new("L", (S, S), 0)
    ImageDraw.Draw(m).polygon([(x * U, y * U) for x, y in pts], fill=255)
    return arredondar(m, raio * U) if raio else m


def brilho(camada, raio, vezes=2):
    g = camada.filter(ImageFilter.GaussianBlur(raio * U))
    out = Image.new("RGBA", (S, S), (0, 0, 0, 0))
    for _ in range(vezes):
        out.alpha_composite(g)
    return out


def sombra(mascara, raio=22, dy=14, forca=0.5):
    a = mascara.filter(ImageFilter.GaussianBlur(raio * U)).point(lambda v: int(v * forca))
    c = Image.new("RGBA", (S, S), (8, 4, 30, 0))
    c.putalpha(a)
    out = Image.new("RGBA", (S, S), (0, 0, 0, 0))
    out.alpha_composite(c, (0, int(dy * U)))
    return out


CAIXA = u(56, 56, 968, 968)
RAIO = int(210 * U)


def fundo():
    img = gradiente((S, S), [(0, INDIGO_1), (1, INDIGO_2)], 60)
    img.alpha_composite(radial(u(512, 470), 520 * U, (124, 58, 237), 0.9))
    img.alpha_composite(radial(u(512, 980), 420 * U, (10, 6, 40), 0.55))
    return img


def acabar(img):
    borda = Image.new("RGBA", (S, S), (0, 0, 0, 0))
    ImageDraw.Draw(borda).rounded_rectangle(CAIXA, radius=RAIO, outline=(255, 255, 255, 46), width=int(5 * U))
    # reflexo suave no topo
    topo = gradiente((S, S), [(0, (255, 255, 255, 34)), (0.42, (255, 255, 255, 0)), (1, (255, 255, 255, 0))], 90)
    img.alpha_composite(topo)
    img.alpha_composite(borda)
    m = Image.new("L", (S, S), 0)
    ImageDraw.Draw(m).rounded_rectangle(CAIXA, radius=RAIO, fill=255)
    img.putalpha(ImageChops.multiply(img.getchannel("A"), m))
    return img.resize((1024, 1024), Image.LANCZOS)


def contorno_de(m, enc=14, forca=.45):
    inn = m.filter(ImageFilter.MinFilter(int(enc * U) // 2 * 2 + 1))
    return ImageChops.subtract(m, inn).point(lambda v: int(v * forca))


def vidro(img, m, forca_sombra=.65):
    img.alpha_composite(sombra(m, 26, 18, forca_sombra))
    g = gradiente((S, S), [(0, (255, 255, 255)), (0.7, (232, 222, 255)), (1, (205, 186, 255))], 90)
    img.alpha_composite(brilho(preencher(m, (200, 170, 255)), 30, 1))
    img.alpha_composite(preencher(m, g))
    img.alpha_composite(preencher(contorno_de(m, 14, .9), (255, 255, 255)))


def _retangulos(lst, raio=10):
    m = Image.new("L", (S, S), 0)
    d = ImageDraw.Draw(m)
    for r in lst:
        d.rectangle(u(*r), fill=255)
    return arredondar(m, raio * U)




def _arco(cx, cy, rx, ry, esp, a0=180, a1=360):
    m = Image.new("L", (S, S), 0)
    ImageDraw.Draw(m).arc(u(cx - rx, cy - ry, cx + rx, cy + ry), a0, a1, fill=255, width=int(esp * U))
    return m


def _rr(x0, y0, x1, y1, r, esp=None):
    m = Image.new("L", (S, S), 0)
    d = ImageDraw.Draw(m)
    if esp:
        d.rounded_rectangle(u(x0, y0, x1, y1), radius=int(r * U), outline=255, width=int(esp * U))
    else:
        d.rounded_rectangle(u(x0, y0, x1, y1), radius=int(r * U), fill=255)
    return m


def _dourado(img, m, brilho_r=26):
    r = Image.new("RGBA", (S, S), (0, 0, 0, 0))
    r.alpha_composite(preencher(m, gradiente((S, S), [(0, DOURADO), (1, (255, 120, 90))], 0)))
    img.alpha_composite(brilho(r, brilho_r, 2))
    img.alpha_composite(r)


# A: ponte em arco de vidro sobre dois pilares, com o arco dourado (a ligação)
def opcao_ponte():
    img = fundo()
    pilares = _retangulos([(250, 560, 330, 800), (694, 560, 774, 800), (180, 560, 844, 620)], 14)
    vidro(img, pilares)
    _dourado(img, arredondar(_arco(512, 600, 300, 300, 62), 12 * U))
    # tirantes
    t = _retangulos([(x - 9, 600 - math.sqrt(272 ** 2 - (x - 512) ** 2) + 6, x + 9, 560) for x in (372, 442, 512, 582, 652)], 6)
    vidro(img, t, .4)
    return acabar(img)


# B: celular e monitor de vidro ligados por um arco dourado
def opcao_aparelhos():
    img = fundo()
    cel = ImageChops.subtract(_rr(170, 430, 390, 820, 44), _rr(196, 470, 364, 760, 16))
    cel = ImageChops.add(cel, _rr(258, 778, 302, 794, 8))
    mon = ImageChops.subtract(_rr(470, 300, 880, 600, 34), _rr(500, 330, 850, 570, 12))
    mon = ImageChops.add(mon, _retangulos([(645, 600, 705, 690), (575, 680, 775, 716)], 10))
    vidro(img, arredondar(cel, 4 * U))
    vidro(img, arredondar(mon, 4 * U))
    _dourado(img, arredondar(_arco(400, 470, 150, 150, 40, 205, 335), 10 * U))
    # ponto de chegada
    p = Image.new("L", (S, S), 0)
    ImageDraw.Draw(p).ellipse(u(620, 400, 700, 480), fill=255)
    _dourado(img, p)
    p2 = Image.new("L", (S, S), 0)
    ImageDraw.Draw(p2).ellipse(u(252, 536, 308, 592), fill=255)
    _dourado(img, p2)
    return acabar(img)


# C: duas setas de vidro em arco (vai e volta), uma dourada
def opcao_vaivem():
    img = fundo()
    # seta de cima: termina à direita apontando para baixo-direita → simplificada como ponta triangular
    m1 = _arco(512, 560, 290, 230, 66, 195, 335)
    d = ImageDraw.Draw(m1)
    d.polygon([tuple(u(700, 360)), tuple(u(850, 440)), tuple(u(730, 520))], fill=255)
    vidro(img, arredondar(m1, 12 * U))
    m2 = _arco(512, 464, 290, 230, 66, 15, 155)
    d = ImageDraw.Draw(m2)
    d.polygon([tuple(u(324, 664)), tuple(u(174, 584)), tuple(u(294, 504))], fill=255)
    _dourado(img, arredondar(m2, 12 * U))
    return acabar(img)


OPCOES = {"a": opcao_ponte, "b": opcao_aparelhos, "c": opcao_vaivem}
ESCOLHA = "a"


def icone():
    return OPCOES[ESCOLHA]()


def _android(grande, raiz):
    """Ícone do celular: PNGs nas densidades do Android (o desenho já tem o fundo)."""
    for pasta, t in (("mipmap-mdpi", 48), ("mipmap-hdpi", 72), ("mipmap-xhdpi", 96), ("mipmap-xxhdpi", 144), ("mipmap-xxxhdpi", 192)):
        d = os.path.join(raiz, pasta)
        os.makedirs(d, exist_ok=True)
        grande.resize((t, t), Image.LANCZOS).save(os.path.join(d, "ic_launcher.png"))


if __name__ == "__main__":
    import sys
    aqui = os.path.dirname(os.path.abspath(__file__))
    if len(sys.argv) > 1 and sys.argv[1] == "opcoes":
        quadro = Image.new("RGBA", (3 * 440 + 40, 520), (245, 243, 250, 255))
        dq = ImageDraw.Draw(quadro)
        for i, k in enumerate("abc"):
            quadro.alpha_composite(OPCOES[k]().resize((400, 400), Image.LANCZOS), (40 + i * 440, 30))
            dq.text((40 + i * 440 + 190, 450), k.upper(), fill=(40, 20, 90))
        quadro.convert("RGB").save(os.path.join(aqui, "opcoes.png"))
        sys.exit()
    grande = icone()
    grande.save(os.path.join(aqui, "logo.png"))
    grande.resize((256, 256), Image.LANCZOS).save(os.path.join(aqui, "pons.png"))
    tamanhos = [16, 20, 24, 32, 40, 48, 64, 128, 256]
    imgs = [grande.resize((t, t), Image.LANCZOS) for t in tamanhos]
    imgs[-1].save(os.path.join(aqui, "pons.ico"), sizes=[(t, t) for t in tamanhos], append_images=imgs[:-1])
    lateral = gradiente((328, 628), [(0, INDIGO_1), (1, INDIGO_2)], 70)
    lateral.alpha_composite(grande.resize((220, 220), Image.LANCZOS), (54, 160))
    lateral.convert("RGB").save(os.path.join(aqui, "wizard.bmp"))
    pequena = Image.new("RGBA", (110, 116), (255, 255, 255, 255))
    pequena.alpha_composite(grande.resize((100, 100), Image.LANCZOS), (5, 8))
    pequena.convert("RGB").save(os.path.join(aqui, "wizard_small.bmp"))
    _android(grande, os.path.join(aqui, "..", "..", "android", "app", "src", "main", "res"))
    print("ícones gerados")
