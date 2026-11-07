"""Gera o panorama 3D regional (HTML autonomo, Plotly) do norte de Santa Catarina:
relevo + batimetria (AWS Terrain Tiles / Terrarium, derivado de SRTM e GEBCO), textura de
satelite (Esri World Imagery), lineamentos regionais, pocos (ANP + SAG), a area de estudo de
Taio e os corpos intrusivos -- base simplificada pra reconstrucao da cinematica do Gondwana.

Uso:  python gerar_panorama_3d.py   ->  panorama_3d_taio.html
Os mosaicos de elevacao e satelite sao baixados uma vez e guardados em cache/ (apagar pra rebaixar).
"""
import base64
import sys
from pathlib import Path

import geopandas as gpd
import numpy as np
import plotly.graph_objects as go
from plotly.offline import get_plotlyjs
from pyproj import Transformer
from scipy.ndimage import map_coordinates
from shapely.geometry import box

AQUI = Path(__file__).parent
MESTRADO = AQUI.parent.parent
sys.path.insert(0, str(MESTRADO / "4_GIT_TPS" / "mod3d"))
import gerar_visualizador_3d as v  # noqa: E402  (paleta e constantes da marca)

BANCO = MESTRADO / "2_Banco_de_Dados"
LINEAMENTOS_GPKG = BANCO / "Unificação" / "lineamentos_direcoes.gpkg"
GEOLOGIA_REGIONAL_GPKG = BANCO / "dados_base" / "geologia_regional_sc.gpkg"
POCOS_GPKG = BANCO / "Unificação" / "pocos_regionais.gpkg"
LOGO_PATH = AQUI / "assets" / "logo_taio.png"
CACHE = AQUI / "cache"
OUT_HTML = AQUI / "panorama_3d_taio.html"

CRS_UTM = "EPSG:31982"
# panorama: retangulo desenhado (Alto Vale, Serra, Itajai, plataforma) ampliado pra oeste pra incluir
# os pocos ANP/SAG (a maioria fica no interior). UTM 22S.
PANORAMA = (440000.0, 6930000.0, 790000.0, 7110000.0)
TAIO_AREA = (582500.0, 6995000.0, 604500.0, 7029000.0)
ZOOM_ELEV, ZOOM_SAT = 9, 10
N_X = 330                      # vertices em X (Y proporcional)
EXAGERO_PADRAO = 8
ELEV_LINHA = 40.0
COR_LINEAMENTO = {"Positivo": "#2E7D5B", "Negativo": "#E8A33D"}
URL_TERRARIUM = "https://s3.amazonaws.com/elevation-tiles-prod/terrarium/{z}/{x}/{y}.png"


def mosaico(nome, fonte, zoom):
    """Baixa (ou le do cache) o mosaico de tiles cobrindo o panorama. Devolve (array RGB, extent EPSG:3857)."""
    import contextily as ctx
    arq, arq_ext = CACHE / f"{nome}_z{zoom}.npy", CACHE / f"{nome}_z{zoom}_ext.npy"
    if arq.exists():
        return np.load(arq), np.load(arq_ext)
    print(f"Baixando {nome} (zoom {zoom})...")
    w, s, e, n = gpd.GeoSeries([box(*PANORAMA)], crs=CRS_UTM).to_crs(4326).total_bounds
    img, ext = ctx.bounds2img(w - 0.05, s - 0.05, e + 0.05, n + 0.05, ll=True, zoom=zoom, source=fonte, n_connections=8)
    CACHE.mkdir(exist_ok=True)
    np.save(arq, img[:, :, :3]); np.save(arq_ext, np.array(ext))
    return img[:, :, :3], np.array(ext)


def amostrar(img, ext, gx, gy, ordem=1):
    """Amostra o mosaico (EPSG:3857) nos pontos (gx, gy) em UTM; devolve array (h, w, canais)."""
    lon, lat = Transformer.from_crs(CRS_UTM, 4326, always_xy=True).transform(gx, gy)
    mx, my = Transformer.from_crs(4326, 3857, always_xy=True).transform(lon, lat)
    h, w = img.shape[:2]
    col = (mx - ext[0]) / (ext[1] - ext[0]) * w - 0.5
    row = (ext[3] - my) / (ext[3] - ext[2]) * h - 0.5
    return np.stack([map_coordinates(img[:, :, c].astype(float), [row, col], order=ordem, mode="nearest") for c in range(img.shape[2])], axis=-1)


def hex_rgb(h):
    h = h.lstrip("#")
    return np.array([int(h[i:i + 2], 16) for i in (0, 2, 4)], dtype=float)


def cores_hipsometricas(z):
    """Terra: rampa hipsometrica da marca; mar: azuis por profundidade."""
    terra = np.array([hex_rgb(c) for c in v.CORES_HIPSOMETRICAS])
    zt = np.clip(z / 1100.0, 0, 1) * (len(terra) - 1)
    lo = np.floor(zt).astype(int).clip(0, len(terra) - 2)
    fr = (zt - lo)[..., None]
    c_terra = terra[lo] * (1 - fr) + terra[lo + 1] * fr
    mar_raso, mar_fundo = hex_rgb("#5BA3D9"), hex_rgb("#0A2A4A")
    ft = np.clip(-z / 2500.0, 0, 1)[..., None]
    c_mar = mar_raso * (1 - ft) + mar_fundo * ft
    return np.where((z >= 0)[..., None], c_terra, c_mar).astype(np.uint8)


def triangulos_grade(ny, nx):
    idx = np.arange(ny * nx).reshape(ny, nx)
    a, b, c, d = idx[:-1, :-1].ravel(), idx[:-1, 1:].ravel(), idx[1:, :-1].ravel(), idx[1:, 1:].ravel()
    return np.concatenate([a, b]), np.concatenate([b, d]), np.concatenate([c, c])


def main():
    x0, y0, x1, y1 = PANORAMA
    dx, dy = x1 - x0, y1 - y0
    nx, ny = N_X, int(N_X * dy / dx)
    gx, gy = np.meshgrid(np.linspace(x0, x1, nx), np.linspace(y0, y1, ny))

    elev_img, elev_ext = mosaico("terrarium", URL_TERRARIUM, ZOOM_ELEV)
    import contextily as ctx
    sat_img, sat_ext = mosaico("esri", ctx.providers.Esri.WorldImagery, ZOOM_SAT)
    rgb = amostrar(elev_img, elev_ext, gx, gy)
    gz = rgb[..., 0] * 256 + rgb[..., 1] + rgb[..., 2] / 256 - 32768
    gz = np.round(gz, 0)
    print(f"Relevo: {gz.min():.0f} a {gz.max():.0f} m")
    cor_sat = amostrar(sat_img, sat_ext, gx, gy).reshape(-1, 3).astype(np.uint8)
    cor_hip = cores_hipsometricas(gz).reshape(-1, 3)
    # satelite so na terra; no mar usa as cores da batimetria (a imagem Esri no mar e uniforme)
    cor_sat = np.where((gz.ravel() >= 0)[:, None], cor_sat, cores_hipsometricas(gz).reshape(-1, 3))

    # textura geologica regional (CPRM SC 1:500.000): poligonos rasterizados em 400 m e amostrados nos vertices
    from rasterio import features
    from rasterio.transform import from_bounds
    geo = gpd.read_file(GEOLOGIA_REGIONAL_GPKG, layer="litologia")
    res = 400.0
    w_r, h_r = int((x1 - x0) / res), int((y1 - y0) / res)
    shapes = [(g, k + 1) for k, g in enumerate(geo.geometry)]
    raster = features.rasterize(shapes, out_shape=(h_r, w_r), transform=from_bounds(x0, y0, x1, y1, w_r, h_r), fill=0, dtype="uint16")
    col = np.clip(((gx - x0) / (x1 - x0) * (w_r - 1)).astype(int), 0, w_r - 1)
    row = np.clip(((y1 - gy) / (y1 - y0) * (h_r - 1)).astype(int), 0, h_r - 1)
    idx_geo = raster[row, col]
    paleta_geo = np.array([[0, 0, 0]] + [hex_rgb(c) for c in geo["cor"]], dtype=float)
    cor_geo = paleta_geo[idx_geo].reshape(-1, 3)
    sem_poligono = (idx_geo == 0).ravel()
    cor_geo[sem_poligono] = cor_hip[sem_poligono]
    # no mar mantem as cores da batimetria
    mar = (gz.ravel() < 0)
    cor_geo[mar] = cor_hip[mar]
    cor_geo = cor_geo.astype(np.uint8)

    ti, tj, tk = triangulos_grade(ny, nx)
    base = dict(x=np.round(gx.ravel(), 0), y=np.round(gy.ravel(), 0), z=gz.ravel(), i=ti, j=tj, k=tk)
    fig = go.Figure()
    for nome, cores, vis in (("tex_satelite", cor_sat, True), ("tex_geologia", cor_geo, False), ("tex_hipsometria", cor_hip, False)):
        fig.add_trace(go.Mesh3d(**base, vertexcolor=cores, name=nome, visible=vis, showlegend=False, hoverinfo="skip", meta=nome,
                                lighting=dict(ambient=0.85, diffuse=0.45, specular=0.02)))

    # saia do bloco (paredes) ate o piso
    zmin = float(gz.min()) - 300
    px_, py_, pz_, pi_, pj_, pk_ = v.paredes_caixa(gx, gy, gz, np.full_like(gz, zmin))
    fig.add_trace(go.Mesh3d(x=np.round(px_, 0), y=np.round(py_, 0), z=pz_, i=pi_, j=pj_, k=pk_, color="#2A4663",
                            flatshading=False, hoverinfo="skip", showlegend=False, lighting=dict(ambient=0.9, diffuse=0.1)))

    def z_em(xs, ys, extra):
        r = amostrar(elev_img, elev_ext, np.asarray(xs, float), np.asarray(ys, float))
        return r[..., 0] * 256 + r[..., 1] + r[..., 2] / 256 - 32768 + extra

    janela = box(*PANORAMA)
    # lineamentos regionais
    lineas = gpd.read_file(LINEAMENTOS_GPKG).to_crs(CRS_UTM)
    for tipo, cor in COR_LINEAMENTO.items():
        xs, ys = [], []
        for g in lineas.loc[lineas["tipo"] == tipo, "geometry"]:
            inter = g.intersection(janela)
            for seg in ([inter] if inter.geom_type == "LineString" else list(getattr(inter, "geoms", []))):
                if seg.geom_type != "LineString" or seg.length < 100:
                    continue
                pts = [(seg.interpolate(d).x, seg.interpolate(d).y) for d in np.linspace(0, seg.length, max(int(seg.length // 700), 2))]
                xs += [p[0] for p in pts] + [np.nan]; ys += [p[1] for p in pts] + [np.nan]
        if xs:
            fig.add_trace(go.Scatter3d(x=xs, y=ys, z=z_em(np.nan_to_num(xs), np.nan_to_num(ys), ELEV_LINHA), mode="lines",
                                       line=dict(color=cor, width=4), name=f"Lineamento {tipo.lower()}", legendgroup="lin",
                                       meta="lineamentos", hoverinfo="name"))
    # estruturas (falhas/fraturas) e diques da CPRM (SIG SC)
    est = gpd.read_file(GEOLOGIA_REGIONAL_GPKG, layer="estrutura")
    for categoria, cor, larg in (("Falha", "#FF493D", 4), ("Fratura", "#9FB3C8", 2)):
        xs, ys = [], []
        for g in est.loc[est["categoria"] == categoria, "geometry"]:
            for seg in ([g] if g.geom_type == "LineString" else list(getattr(g, "geoms", []))):
                if seg.geom_type != "LineString" or seg.length < 1500:
                    continue
                pts = [(seg.interpolate(d).x, seg.interpolate(d).y) for d in np.linspace(0, seg.length, max(int(seg.length // 1500), 2))]
                xs += [q[0] for q in pts] + [np.nan]; ys += [q[1] for q in pts] + [np.nan]
        if xs:
            fig.add_trace(go.Scatter3d(x=xs, y=ys, z=z_em(np.nan_to_num(xs), np.nan_to_num(ys), ELEV_LINHA + 20), mode="lines",
                                       line=dict(color=cor, width=larg), name=f"{categoria} (CPRM)", legendgroup="cprm",
                                       meta="cprm", hoverinfo="name"))
    dq = gpd.read_file(GEOLOGIA_REGIONAL_GPKG, layer="dique")
    xs, ys = [], []
    for g in dq.geometry:
        for seg in ([g] if g.geom_type == "LineString" else list(getattr(g, "geoms", []))):
            if seg.geom_type != "LineString":
                continue
            pts = [(seg.interpolate(d).x, seg.interpolate(d).y) for d in np.linspace(0, seg.length, max(int(seg.length // 1500), 2))]
            xs += [q[0] for q in pts] + [np.nan]; ys += [q[1] for q in pts] + [np.nan]
    fig.add_trace(go.Scatter3d(x=xs, y=ys, z=z_em(np.nan_to_num(xs), np.nan_to_num(ys), ELEV_LINHA + 40), mode="lines",
                               line=dict(color=v.COR_DIQUE, width=6), name="Diques (CPRM)", legendgroup="cprm", meta="cprm", hoverinfo="name"))
    # corpos intrusivos (contornos) e area de estudo
    lito = gpd.read_file(v.LITOLOGIA_ATUALIZADA).to_crs(CRS_UTM)
    for nome, cor in (("Soleira", v.COR_SILL), ("Dique", v.COR_DIQUE)):
        xs, ys = [], []
        for g in lito.loc[lito["formacao"] == nome, "geometry"]:
            for p in ([g] if g.geom_type == "Polygon" else list(g.geoms)):
                c = np.array(p.exterior.coords)[::3]
                xs += list(c[:, 0]) + [np.nan]; ys += list(c[:, 1]) + [np.nan]
        fig.add_trace(go.Scatter3d(x=xs, y=ys, z=z_em(np.nan_to_num(xs), np.nan_to_num(ys), 70), mode="lines", line=dict(color=cor, width=3),
                                   name=nome, legendgroup="corpos", meta="corpos", hoverinfo="name"))
    tx0, ty0, tx1, ty1 = TAIO_AREA
    bx, by = [tx0, tx1, tx1, tx0, tx0], [ty0, ty0, ty1, ty1, ty0]
    fig.add_trace(go.Scatter3d(x=bx, y=by, z=z_em(bx, by, 120), mode="lines", line=dict(color="#FFFFFF", width=5), name="Área de estudo (Taió)",
                               meta="corpos", hoverinfo="name"))
    fig.add_trace(go.Scatter3d(x=[(tx0 + tx1) / 2], y=[ty1], z=[float(z_em([(tx0 + tx1) / 2], [ty1], 400)[0])], mode="text", text=["Taió"],
                               textfont=dict(size=14, color="#FFFFFF"), showlegend=False, hoverinfo="skip", meta="corpos"))
    # pocos
    pocos = gpd.read_file(POCOS_GPKG).to_crs(CRS_UTM)
    pocos = pocos[pocos.geometry.within(janela)]
    if len(pocos):
        px, py = pocos.geometry.x.values, pocos.geometry.y.values
        txt = [f"{n}<br>{p:.0f} m" if p == p else str(n) for n, p in zip(pocos["nome"], pocos["profundidade_m"])]
        fig.add_trace(go.Scatter3d(x=px, y=py, z=z_em(px, py, 60), mode="markers", marker=dict(size=5, symbol="diamond", color="#FFFFFF",
                                   line=dict(width=1, color="#FF493D")), text=txt, hoverinfo="text", name="Poços (ANP/SAG)", meta="pocos"))
        # hastes verticais mostrando a profundidade (exagero igual ao do relevo)
        hx, hy, hz = [], [], []
        for x, y, p in zip(px, py, pocos["profundidade_m"].fillna(0)):
            zt = float(z_em([x], [y], 0)[0])
            hx += [x, x, np.nan]; hy += [y, y, np.nan]; hz += [zt, zt - float(p), np.nan]
        fig.add_trace(go.Scatter3d(x=hx, y=hy, z=hz, mode="lines", line=dict(color="#FF493D", width=4), showlegend=False,
                                   hoverinfo="skip", meta="pocos"))
    print(f"  {len(pocos)} poços dentro do panorama")

    zmax = float(gz.max()) + 80
    fig.update_layout(
        paper_bgcolor=v.MARCA_NAVY, font=dict(family=v.MARCA_FONTE, color=v.MARCA_CINZA_CLARO), margin=dict(l=0, r=0, t=0, b=0),
        legend=dict(bgcolor="rgba(12,41,69,0.8)", bordercolor=v.MARCA_ROXO, borderwidth=1, x=0.01, y=0.99),
        scene=dict(
            xaxis=dict(title="X (UTM)", range=[x0 - 0.03 * dx, x1 + 0.03 * dx], backgroundcolor="#0C2945", gridcolor="#2A4663", color=v.MARCA_CINZA_CLARO),
            yaxis=dict(title="Y (UTM)", range=[y0 - 0.03 * dy, y1 + 0.03 * dy], backgroundcolor="#0C2945", gridcolor="#2A4663", color=v.MARCA_CINZA_CLARO),
            zaxis=dict(title="Z (m)", range=[zmin - 60, zmax], backgroundcolor="#0C2945", gridcolor="#2A4663", color=v.MARCA_CINZA_CLARO),
            aspectmode="manual", aspectratio=dict(x=1.06, y=1.06 * dy / dx, z=(zmax - zmin + 60) * EXAGERO_PADRAO / dx),
            camera=dict(eye=dict(x=-0.5, y=-0.85, z=0.55), center=dict(x=0, y=0, z=-0.15)),
        ),
    )
    fig_json = fig.to_json()
    ar = dict(x=1.06, y=round(1.06 * dy / dx, 4), z=round((zmax - zmin + 60) / dx, 6))

    logo = base64.b64encode(LOGO_PATH.read_bytes()).decode() if LOGO_PATH.exists() else ""
    html = f"""<!DOCTYPE html>
<html lang="pt-br"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width, initial-scale=1">
<title>Panorama 3D — Taió Plumbing System</title>
<link rel="icon" type="image/png" href="assets/favicon.png?v=2"><link rel="shortcut icon" href="assets/favicon.ico?v=2">
<link rel="apple-touch-icon" href="assets/apple-touch-icon.png?v=2">
<style>
 :root {{ --bg:{v.MARCA_NAVY}; --painel:{v.MARCA_ROXO_ESCURO}; --txt:{v.MARCA_CINZA_CLARO}; --ac:{v.MARCA_ROXO}; }}
 * {{ box-sizing:border-box; }}
 body {{ margin:0; background:var(--bg); color:var(--txt); font-family:{v.MARCA_FONTE}; overflow:hidden; }}
 #barra {{ display:flex; flex-wrap:wrap; gap:6px 14px; align-items:center; padding:8px 14px; background:var(--painel); border-bottom:2px solid var(--ac); }}
 #barra h1 {{ font-size:15px; margin:0 8px 0 0; }} #barra h1 b {{ color:var(--ac); }}
 .grupo {{ display:flex; gap:5px; align-items:center; font-size:12px; }}
 .grupo label {{ opacity:.7; text-transform:uppercase; font-size:10px; letter-spacing:.06em; }}
 button, select {{ background:var(--bg); color:var(--txt); border:1px solid var(--ac); border-radius:5px; padding:4px 9px; font:inherit; font-size:12px; cursor:pointer; }}
 button.ativo {{ background:var(--ac); color:var(--bg); }}
 #info {{ margin-left:auto; margin-right:56px; font-size:11px; opacity:.75; }}
 #logo {{ position:fixed; top:8px; right:12px; width:46px; height:46px; border-radius:50%; border:2px solid var(--ac); z-index:5; }}
 #plot {{ width:100%; }}
</style></head><body>
<img id="logo" src="data:image/png;base64,{logo}">
<div id="barra"><h1><b>Panorama 3D</b> — norte de SC</h1>
 <div class="grupo"><label>Textura</label><button class="tex ativo" data-t="tex_satelite">Satélite</button><button class="tex" data-t="tex_geologia">Geologia SC (CPRM)</button><button class="tex" data-t="tex_hipsometria">Hipsometria + batimetria</button></div>
 <div class="grupo"><label>Exagero vertical</label><select id="exag"><option value="1">1×</option><option value="3">3×</option><option value="5">5×</option><option value="8" selected>8×</option><option value="12">12×</option><option value="20">20×</option></select></div>
 <div class="grupo"><label>Camadas</label><button class="cam ativo" data-m="lineamentos">Lineamentos</button><button class="cam ativo" data-m="cprm">Estruturas CPRM</button><button class="cam ativo" data-m="corpos">Corpos / Taió</button><button class="cam ativo" data-m="pocos">Poços</button></div>
 <div class="grupo"><label>Vista</label><button class="cm" data-c="-0.5,-0.85,0.55">Oblíqua</button><button class="cm" data-c="0,-0.01,1.5">Planta</button><button class="cm" data-c="0,-1.3,0.2">Perfil O→L</button><button class="cm" data-c="-1.3,0,0.2">Perfil S→N</button></div>
 <div id="info">Relevo/batimetria: AWS Terrain Tiles · satélite: Esri · {len(pocos)} poços · área ≈ {dx / 1000:.0f} × {dy / 1000:.0f} km</div></div>
<div id="plot"></div>
<script>{get_plotlyjs()}</script>
<script>
var FIG = {fig_json}, AR = {{x: {ar['x']}, y: {ar['y']}, z: {ar['z']}}};
var textura = 'tex_satelite', EXAG = {EXAGERO_PADRAO}, camadasOn = {{lineamentos: true, cprm: true, corpos: true, pocos: true}};
var gd = document.getElementById('plot');
function altura() {{ return window.innerHeight - document.getElementById('barra').offsetHeight; }}
function aplicar() {{
  var vis = FIG.data.map(function(t) {{ var m = t.meta;
    if (m && m.indexOf('tex_') === 0) return m === textura;
    if (m && camadasOn.hasOwnProperty(m)) return camadasOn[m];
    return true; }});
  Plotly.restyle(gd, {{visible: vis}});
  Plotly.relayout(gd, {{'scene.aspectratio': {{x: AR.x, y: AR.y, z: AR.z * EXAG}}}});
}}
gd.style.height = altura() + 'px';
Plotly.newPlot(gd, FIG.data, FIG.layout, {{responsive: true, displaylogo: false}}).then(aplicar);
document.querySelectorAll('.tex').forEach(function(b) {{ b.onclick = function() {{ textura = b.dataset.t;
  document.querySelectorAll('.tex').forEach(function(x) {{ x.classList.toggle('ativo', x === b); }}); aplicar(); }}; }});
document.querySelectorAll('.cam').forEach(function(b) {{ b.onclick = function() {{ camadasOn[b.dataset.m] = !camadasOn[b.dataset.m];
  b.classList.toggle('ativo', camadasOn[b.dataset.m]); aplicar(); }}; }});
document.querySelectorAll('.cm').forEach(function(b) {{ b.onclick = function() {{ var c = b.dataset.c.split(',').map(parseFloat);
  Plotly.relayout(gd, {{'scene.camera.eye': {{x: c[0], y: c[1], z: c[2]}}, 'scene.camera.up': {{x: 0, y: 0, z: 1}}}}); }}; }});
document.getElementById('exag').onchange = function() {{ EXAG = parseFloat(this.value); aplicar(); }};
window.addEventListener('resize', function() {{ gd.style.height = altura() + 'px'; Plotly.Plots.resize(gd); }});
</script></body></html>"""
    OUT_HTML.write_text(html, encoding="utf-8")
    print(f"Salvo em: {OUT_HTML} ({OUT_HTML.stat().st_size / 1e6:.1f} MB)")


if __name__ == "__main__":
    main()
