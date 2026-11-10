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


PLANILHA_POCOS = BANCO / "dados_base" / "pocos_ANP_isolados.xlsx"


def camadas_planilha_pocos(f_relevo, nomes_permitidos):
    """Soleiras (intervalos topo-base) e topos de unidade dos pocos da planilha PMP/ANP, referidos ao relevo do DEM.
    f_relevo(xs, ys) -> z do terreno; so os pocos em nomes_permitidos entram. Retorna None se a planilha nao existe."""
    import pandas as _pd
    if not PLANILHA_POCOS.exists():
        return None
    xl = _pd.read_excel(PLANILHA_POCOS, sheet_name=None)
    res = xl["Resumo"].set_index("Poco")[["E_utm22s", "N_utm22s"]]
    res = res[res.index.isin(list(nomes_permitidos))]
    if not len(res):
        return None
    zt = dict(zip(res.index, np.asarray(f_relevo(res["E_utm22s"].values, res["N_utm22s"].values), float)))
    ex, ey = res["E_utm22s"].to_dict(), res["N_utm22s"].to_dict()
    sx, sy, sz = [], [], []
    sol = xl["Corpos_intrusivos"]
    for r in sol[sol["Poco"].isin(res.index)].itertuples():
        x, y, z0 = ex[r.Poco], ey[r.Poco], zt[r.Poco]
        sx += [x, x, None]; sy += [y, y, None]; sz += [z0 - r.prof_topo_m, z0 - r.prof_base_m, None]
    tx, ty, tz, tt = [], [], [], []
    top = xl["Topos_unidades"]
    for r in top[top["Poco"].isin(res.index) & top["prof_topo_m"].notna()].itertuples():
        x, y, z0 = ex[r.Poco], ey[r.Poco], zt[r.Poco]
        zc = z0 - r.prof_topo_m
        tx.append(x); ty.append(y); tz.append(zc)
        tt.append(f"<b>{r.Poco}</b><br>{r.nome_unidade}<br>topo a {r.prof_topo_m:.0f} m (cota {zc:.0f} m)")
    return sx, sy, sz, tx, ty, tz, tt


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
    for categoria, cor, larg in (("Falha", "#2563EB", 4), ("Fratura", "#D81B73", 2)):
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
                                   line=dict(width=1, color="#13BBE6")), text=txt, hoverinfo="text", name="Poços (ANP/SAG)", meta="pocos"))
        # hastes verticais mostrando a profundidade (exagero igual ao do relevo)
        hx, hy, hz = [], [], []
        for x, y, p in zip(px, py, pocos["profundidade_m"].fillna(0)):
            zt = float(z_em([x], [y], 0)[0])
            hx += [x, x, np.nan]; hy += [y, y, np.nan]; hz += [zt, zt - float(p), np.nan]
        fig.add_trace(go.Scatter3d(x=hx, y=hy, z=hz, mode="lines", line=dict(color="#13BBE6", width=4), showlegend=False,
                                   hoverinfo="skip", meta="pocos"))
    print(f"  {len(pocos)} poços dentro do panorama")
    # ---- soleiras (intervalos) e topos de unidade dos pocos da planilha PMP/ANP ----
    plan = camadas_planilha_pocos(lambda xs, ys: z_em(xs, ys, 0), set(pocos['nome']))
    if plan is not None:
        sx, sy, sz, tx, ty, tz, tt = plan
        fig.add_trace(go.Scatter3d(x=sx, y=sy, z=sz, mode="lines", line=dict(color="#FF493D", width=9), name="Soleiras (poços PMP/ANP)",
                                   meta="pocos", hoverinfo="skip"))
        fig.add_trace(go.Scatter3d(x=tx, y=ty, z=tz, mode="markers", marker=dict(size=4, symbol="diamond", color="#F1F5F9"), text=tt,
                                   hoverinfo="text", name="Topos de unidade (poços PMP/ANP)", meta="pocos"))

    # ---- direcoes dos lineamentos: segmentos (x1,y1,z1,x2,y2,z2,azimute) pra roseta e filtro por direcao (JS) ----
    from shapely.geometry import Point as _Pt
    poly_buf = box(*TAIO_AREA).buffer(5000.0)  # area de estudo + 5 km
    cont_fid = [0]

    def segmentos(geoms, passo, extra_z):
        out = []
        for g in geoms:
            inter = g.intersection(janela)
            for seg in ([inter] if inter.geom_type == "LineString" else list(getattr(inter, "geoms", []))):
                if seg.geom_type != "LineString" or seg.length < 100:
                    continue
                n = max(int(seg.length // passo), 2)
                cont_fid[0] += 1
                pts = [(seg.interpolate(d).x, seg.interpolate(d).y) for d in np.linspace(0, seg.length, n)]
                zs = z_em([q[0] for q in pts], [q[1] for q in pts], extra_z)
                for k in range(len(pts) - 1):
                    az = float(np.degrees(np.arctan2(pts[k + 1][0] - pts[k][0], pts[k + 1][1] - pts[k][1])) % 180)
                    dentro_buf = int(poly_buf.contains(_Pt((pts[k][0] + pts[k + 1][0]) / 2, (pts[k][1] + pts[k + 1][1]) / 2)))
                    out.append([round(pts[k][0]), round(pts[k][1]), round(float(zs[k])), round(pts[k + 1][0]),
                                round(pts[k + 1][1]), round(float(zs[k + 1])), round(az, 1), cont_fid[0], dentro_buf])
        return out

    ds = {
        "falha": dict(nome="Falhas (CPRM)", cor="#2563EB", traco="Falha (CPRM)",
                      seg=segmentos(est.loc[est["categoria"] == "Falha", "geometry"], 1000, ELEV_LINHA + 20)),
        "fratura": dict(nome="Fraturas (CPRM)", cor="#D81B73", traco="Fratura (CPRM)",
                        seg=segmentos(est.loc[est["categoria"] == "Fratura", "geometry"], 1000, ELEV_LINHA + 20)),
        "dique": dict(nome="Diques (CPRM)", cor=v.COR_DIQUE, traco="Diques (CPRM)", seg=segmentos(dq.geometry, 1000, ELEV_LINHA + 40)),
        "loc_pos": dict(nome="Lineamentos locais (+)", cor=COR_LINEAMENTO["Positivo"], traco="Lineamento positivo",
                        seg=segmentos(lineas.loc[lineas["tipo"] == "Positivo", "geometry"], 700, ELEV_LINHA)),
        "loc_neg": dict(nome="Lineamentos locais (−)", cor=COR_LINEAMENTO["Negativo"], traco="Lineamento negativo",
                        seg=segmentos(lineas.loc[lineas["tipo"] == "Negativo", "geometry"], 700, ELEV_LINHA)),
    }
    print("  segmentos p/ rosetas:", {k: len(d["seg"]) for k, d in ds.items()})
    import json
    ds_json = json.dumps(ds, ensure_ascii=False)
    # trace de contexto (o que fica fora da direcao selecionada)
    fig.add_trace(go.Scatter3d(x=[], y=[], z=[], mode="lines", line=dict(color="#8A94A6", width=1.5), opacity=0.3,
                               name="Fora da seleção", showlegend=False, hoverinfo="skip", meta="ctx"))
    fig.add_trace(go.Scatter3d(x=[], y=[], z=[], mode="lines", line=dict(color="#FFFFFF", width=9),
                               name="Direção selecionada (roseta 1)", showlegend=False, hoverinfo="skip", meta="selA"))
    bx_, by_ = zip(*poly_buf.exterior.coords)
    fig.add_trace(go.Scatter3d(x=list(bx_), y=list(by_), z=z_em(list(bx_), list(by_), 150), mode="lines",
                               line=dict(color="#13BBE6", width=4, dash="dash"), name="Buffer de 5 km (Taió)", meta="corpos",
                               hoverinfo="name"))
    fig.add_trace(go.Scatter3d(x=[], y=[], z=[], mode="lines", line=dict(color="#FFD54A", width=9),
                               name="Direção selecionada (roseta 2)", showlegend=False, hoverinfo="skip", meta="selB"))

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
 #corpo {{ display:flex; }}
 #plot {{ flex:1; min-width:0; }}
 #lateral {{ width:660px; flex-shrink:0; background:var(--painel); border-left:2px solid var(--ac); padding:10px 12px; overflow-y:auto; font-size:12px; }}
 #roses {{ display:flex; gap:8px; }}
 .rosa-bloco {{ flex:1; min-width:0; }}
 .rosa-bloco h3 {{ font-size:12px; margin:6px 0 0 0; opacity:.85; }}
 @media (max-width:1150px) {{ #lateral {{ width:340px; }} #roses {{ flex-direction:column; }} }}
 #lateral h2 {{ font-size:13px; margin:0 0 6px 0; text-transform:uppercase; letter-spacing:.05em; color:var(--ac); }}
 #lateral label.ds {{ display:flex; align-items:center; gap:6px; margin:2px 0; cursor:pointer; }}
 #lateral label.ds i {{ width:12px; height:4px; border-radius:2px; flex-shrink:0; }}
 #lateral label.ds span {{ margin-left:auto; opacity:.65; }}
 #lateral .linha {{ display:flex; gap:6px; align-items:center; margin:6px 0; flex-wrap:wrap; }}
 #lateral input[type=number] {{ width:56px; background:var(--bg); color:var(--txt); border:1px solid var(--ac); border-radius:4px; padding:3px; }}
 .stats {{ background:var(--bg); border-radius:6px; padding:8px; line-height:1.6; margin-top:4px; min-height:70px; }}
 .stats b {{ color:var(--ac); }}
 .chip {{ display:inline-block; width:10px; height:10px; border-radius:50%; margin-right:4px; }}
 .ds-lista {{ margin-bottom:2px; }}
 #lateral .dica {{ opacity:.65; font-size:11px; line-height:1.45; }}
</style></head><body>
<img id="logo" src="data:image/png;base64,{logo}">
<div id="barra"><h1><b>Panorama 3D</b> — norte de SC</h1>
 <div class="grupo"><label>Textura</label><button class="tex ativo" data-t="tex_satelite">Satélite</button><button class="tex" data-t="tex_geologia">Geologia SC (CPRM)</button><button class="tex" data-t="tex_hipsometria">Hipsometria + batimetria</button></div>
 <div class="grupo"><label>Exagero vertical</label><select id="exag"><option value="1">1×</option><option value="3">3×</option><option value="5">5×</option><option value="8" selected>8×</option><option value="12">12×</option><option value="20">20×</option></select></div>
 <div class="grupo"><label>Camadas</label><button class="cam ativo" data-m="lineamentos">Lineamentos</button><button class="cam ativo" data-m="cprm">Estruturas CPRM</button><button class="cam ativo" data-m="corpos">Corpos / Taió</button><button class="cam ativo" data-m="pocos">Poços</button></div>
 <div class="grupo"><label>Vista</label><button class="cm" data-c="-0.5,-0.85,0.55">Oblíqua</button><button class="cm" data-c="0,-0.01,1.5">Planta</button><button class="cm" data-c="0,-1.3,0.2">Perfil O→L</button><button class="cm" data-c="-1.3,0,0.2">Perfil S→N</button></div>
 <div class="grupo"><label>Direções</label><button id="btn-lateral">Rosetas</button></div>
 <div id="info">Relevo/batimetria: AWS Terrain Tiles · satélite: Esri · {len(pocos)} poços · área ≈ {dx / 1000:.0f} × {dy / 1000:.0f} km</div></div>
<div id="corpo"><div id="plot"></div>
<aside id="lateral" style="display:none">
 <h2>Direções dos lineamentos — comparar</h2>
 <div id="roses">
  <div class="rosa-bloco">
   <h3><i class="chip" style="background:#FFFFFF"></i> Roseta 1</h3>
   <div class="linha"><label>Área</label><select id="area-A"><option value="pan">Panorama inteiro</option><option value="taio">Taió + buffer de 5 km</option></select></div>
   <div class="ds-lista" id="ds-A"></div>
   <div id="roseta" style="width:100%;height:280px"></div>
   <div class="stats" id="stats"></div>
   <div class="linha"><button id="pref-A">Direção preferencial</button><button id="sub-A">Direção subordinada</button><button id="lim-A">Limpar</button></div>
  </div>
  <div class="rosa-bloco">
   <h3><i class="chip" style="background:#FFD54A"></i> Roseta 2</h3>
   <div class="linha"><label>Área</label><select id="area-B"><option value="pan">Panorama inteiro</option><option value="taio">Taió + buffer de 5 km</option></select></div>
   <div class="ds-lista" id="ds-B"></div>
   <div id="roseta2" style="width:100%;height:280px"></div>
   <div class="stats" id="stats2"></div>
   <div class="linha"><button id="pref-B">Direção preferencial</button><button id="sub-B">Direção subordinada</button><button id="lim-B">Limpar</button></div>
  </div>
 </div>
 <div class="linha"><label><input type="checkbox" id="escala-comum" checked> mesma escala radial nas duas</label></div>
 <p class="dica">Cada roseta tem seus próprios conjuntos (marque o que quer comparar) e sua própria seleção. Roseta por comprimento (km) em classes de 10°, simétrica (0–180°). <b>Preferencial</b> = classe de maior comprimento (±10°); <b>subordinada</b> = a maior classe a pelo menos 30° da preferencial. A seleção da roseta 1 aparece em <b>branco</b> no 3D e a da roseta 2 em <b>amarelo</b>; o restante dos conjuntos marcados fica em cinza.</p>
</aside></div>
<script>{get_plotlyjs()}</script>
<script>
var FIG = {fig_json}, AR = {{x: {ar['x']}, y: {ar['y']}, z: {ar['z']}}};
var textura = 'tex_satelite', EXAG = {EXAGERO_PADRAO}, camadasOn = {{lineamentos: true, cprm: true, corpos: true, pocos: true}};
var gd = document.getElementById('plot');
var DS = {ds_json};
var dsOn = {{falha: true, fratura: true, dique: true, loc_pos: true, loc_neg: true}}, bins = {{}};
var NOME_DS = {{}}; Object.keys(DS).forEach(function(k) {{ NOME_DS[DS[k].traco] = k; }});
function altura() {{ return window.innerHeight - document.getElementById('barra').offsetHeight; }}
function aplicar() {{
  var vis = FIG.data.map(function(t) {{ var m = t.meta;
    if (m && m.indexOf('tex_') === 0) return m === textura;
    if (m && camadasOn.hasOwnProperty(m)) return camadasOn[m] && (!NOME_DS[t.name] || dsOn[NOME_DS[t.name]]);
    return true; }});
  Plotly.restyle(gd, {{visible: vis}});
  Plotly.relayout(gd, {{'scene.aspectratio': {{x: AR.x, y: AR.y, z: AR.z * EXAG}}}});
}}
gd.style.height = altura() + 'px'; document.getElementById('lateral').style.height = altura() + 'px';
Plotly.newPlot(gd, FIG.data, FIG.layout, {{responsive: true, displaylogo: false}}).then(function() {{ aplicar(); atualizar3d(); }});
document.querySelectorAll('.tex').forEach(function(b) {{ b.onclick = function() {{ textura = b.dataset.t;
  document.querySelectorAll('.tex').forEach(function(x) {{ x.classList.toggle('ativo', x === b); }}); aplicar(); }}; }});
document.querySelectorAll('.cam').forEach(function(b) {{ b.onclick = function() {{ camadasOn[b.dataset.m] = !camadasOn[b.dataset.m];
  b.classList.toggle('ativo', camadasOn[b.dataset.m]); aplicar(); }}; }});
document.querySelectorAll('.cm').forEach(function(b) {{ b.onclick = function() {{ var c = b.dataset.c.split(',').map(parseFloat);
  Plotly.relayout(gd, {{'scene.camera.eye': {{x: c[0], y: c[1], z: c[2]}}, 'scene.camera.up': {{x: 0, y: 0, z: 1}}}}); }}; }});
document.getElementById('exag').onchange = function() {{ EXAG = parseFloat(this.value); aplicar(); }};
window.addEventListener('resize', function() {{ gd.style.height = altura() + 'px'; document.getElementById('lateral').style.height = altura() + 'px'; Plotly.Plots.resize(gd); Plotly.Plots.resize(document.getElementById('roseta')); Plotly.Plots.resize(document.getElementById('roseta2')); }});

// ---------------- rosetas de direcao dos lineamentos (2 rosetas iguais, cada uma com seus conjuntos e sua selecao) ----------------
var NB = 18;
var ROSAS = [
  {{id: 'A', div: document.getElementById('roseta'), stats: 'stats', lista: 'ds-A', on: {{falha: true, fratura: true, dique: true, loc_pos: true, loc_neg: true}}, bins: {{}}, area: 'pan', trace: 'selA'}},
  {{id: 'B', div: document.getElementById('roseta2'), stats: 'stats2', lista: 'ds-B', on: {{falha: true, fratura: true, dique: true, loc_pos: true, loc_neg: true}}, bins: {{}}, area: 'pan', trace: 'selB'}},
];
function binDe(az) {{ return Math.floor(az / 10) % NB; }}
function nSel(r) {{ return Object.keys(r.bins).length; }}
Object.keys(DS).forEach(function(k) {{
  var d = DS[k]; d.km = d.seg.map(function(s) {{ var dx = s[3] - s[0], dy = s[4] - s[1]; return Math.sqrt(dx * dx + dy * dy) / 1000; }});
  d.bins = new Array(NB).fill(0); d.binsT = new Array(NB).fill(0);
  d.seg.forEach(function(s, i) {{ d.bins[binDe(s[6])] += d.km[i]; if (s[8]) d.binsT[binDe(s[6])] += d.km[i]; }});
  d.totalT = d.binsT.reduce(function(a, b) {{ return a + b; }}, 0);
  d.total = d.km.reduce(function(a, b) {{ return a + b; }}, 0);
}});
function rotuloAz(az) {{ az = ((az % 180) + 180) % 180; return az <= 90 ? 'N' + az.toFixed(0) + '°E' : 'N' + (180 - az).toFixed(0) + '°O'; }}
function uniao() {{ Object.keys(DS).forEach(function(k) {{ dsOn[k] = ROSAS[0].on[k] || ROSAS[1].on[k]; }}); }}
ROSAS.forEach(function(r) {{
  var el = document.getElementById(r.lista);
  el.innerHTML = Object.keys(DS).map(function(k) {{
    return '<label class="ds"><input type="checkbox" data-k="' + k + '" checked><i style="background:' + DS[k].cor + '"></i>' + DS[k].nome +
           '<span>' + DS[k].total.toFixed(0) + ' km</span></label>';
  }}).join('');
  el.querySelectorAll('input').forEach(function(c) {{ c.onchange = function() {{ r.on[c.dataset.k] = c.checked; r.bins = {{}}; uniao(); aplicar(); atualizarDirecoes(); }}; }});
}});
function somaBins(r) {{
  var soma = new Array(NB).fill(0);
  Object.keys(DS).forEach(function(k) {{ if (r.on[k]) (r.area === 'taio' ? DS[k].binsT : DS[k].bins).forEach(function(km, b) {{ soma[b] += km; }}); }});
  return soma;
}}
function distBin(a, b) {{ var d = Math.abs(a - b) % NB; return Math.min(d, NB - d); }}
function janela(ip) {{ var o = {{}}; [ip - 1, ip, ip + 1].forEach(function(b) {{ o[(b + NB) % NB] = true; }}); return o; }}
function selecionarPref(r) {{
  var s = somaBins(r), ip = s.indexOf(Math.max.apply(null, s)); if (s[ip] > 0) r.bins = janela(ip);
}}
function selecionarSub(r) {{
  var s = somaBins(r), ip = s.indexOf(Math.max.apply(null, s)), melhor = -1, mv = 0;
  for (var b = 0; b < NB; b++) if (distBin(b, ip) >= 3 && s[b] > mv) {{ mv = s[b]; melhor = b; }}
  if (melhor >= 0) r.bins = janela(melhor);
}}
function binsPorConjunto(r) {{
  var out = {{}};
  Object.keys(DS).forEach(function(k) {{ out[k] = DS[k].bins; }});
  return out;
}}
function rmaxDe(r) {{
  var s = somaBins(r); return Math.max.apply(null, s.concat([0]));
}}
function desenhar(r, rmax) {{
  var cor = '{v.MARCA_CINZA_CLARO}', sel = nSel(r) > 0;
  var tr = Object.keys(DS).filter(function(k) {{ return r.on[k]; }}).map(function(k) {{
    var th = [], rr = [], op = [];
    for (var b = 0; b < NB; b++) {{ [b * 10 + 5, b * 10 + 185].forEach(function(a) {{ th.push(a); rr.push((r.area === 'taio' ? DS[k].binsT : DS[k].bins)[b]); op.push(!sel || r.bins[b] ? 1 : 0.3); }}); }}
    return {{type: 'barpolar', theta: th, r: rr, width: 10, name: DS[k].nome, marker: {{color: DS[k].cor, opacity: op, line: {{color: '#071729', width: 0.5}}}},
            hovertemplate: '%{{theta}}°: %{{r:.1f}} km<extra>' + DS[k].nome + '</extra>'}};
  }});
  var rad = {{color: cor, gridcolor: '#2A4663', ticksuffix: ' km', angle: 45, tickangle: 45}};
  if (rmax) rad.range = [0, rmax * 1.05];
  Plotly.react(r.div, tr, {{
    paper_bgcolor: 'rgba(0,0,0,0)', font: {{color: cor, size: 11}}, margin: {{l: 32, r: 32, t: 8, b: 16}}, showlegend: false,
    polar: {{bgcolor: 'rgba(0,0,0,0)', barmode: 'stack',
      angularaxis: {{rotation: 90, direction: 'clockwise', tickmode: 'array', tickvals: [0, 45, 90, 135, 180, 225, 270, 315],
                    ticktext: ['N', 'NE', 'L', 'SE', 'S', 'SO', 'O', 'NO'], color: cor, gridcolor: '#2A4663'}},
      radialaxis: rad}},
  }}, {{displayModeBar: false, responsive: true}});
}}
function resumo(r) {{
  var sx = 0, sy = 0, tot = 0, sel = nSel(r) > 0, soma = somaBins(r);
  soma.forEach(function(km, b) {{ if (sel && !r.bins[b]) return; var a = (b * 10 + 5) * Math.PI / 90; sx += km * Math.cos(a); sy += km * Math.sin(a); tot += km; }});
  var ip = soma.indexOf(Math.max.apply(null, soma));
  if (!tot) return 'Nenhum lineamento nesta seleção/área.';
  var med = ((Math.atan2(sy, sx) * 90 / Math.PI) + 180) % 180, R = Math.sqrt(sx * sx + sy * sy) / tot;
  var total = soma.reduce(function(a, b) {{ return a + b; }}, 0);
  var feats = {{}}, nf = 0;
  Object.keys(DS).forEach(function(k) {{ if (!r.on[k]) return; DS[k].seg.forEach(function(s) {{
    if (r.area === 'taio' && !s[8]) return; if (sel && !r.bins[binDe(s[6])]) return; if (!feats[s[7]]) {{ feats[s[7]] = 1; nf++; }} }}); }});
  return '<b>' + (r.area === 'taio' ? 'Taió + 5 km · ' : 'Panorama · ') + (sel ? 'Seleção' : 'Conjuntos marcados') + '</b>: ' + tot.toFixed(0) + ' km · ' + nf + ' lineamentos' + (sel ? ' (' + (100 * tot / total).toFixed(0) + '% do total)' : '') +
    '<br>Direção média: <b>' + rotuloAz(med) + '</b> (' + med.toFixed(0) + '°) · R = ' + R.toFixed(2) +
    '<br>Classe dominante: <b>' + ip * 10 + '–' + (ip * 10 + 10) + '°</b> (' + rotuloAz(ip * 10 + 5) + ')';
}}
function atualizarRosetas() {{
  var comum = document.getElementById('escala-comum').checked, rmax = comum ? Math.max(rmaxDe(ROSAS[0]), rmaxDe(ROSAS[1])) : 0;
  ROSAS.forEach(function(r) {{ desenhar(r, rmax); document.getElementById(r.stats).innerHTML = resumo(r); }});
}}
function atualizar3d() {{
  var idx = [], X = [], Y = [], Z = [], cx = [], cy = [], cz = [];
  var alg = ROSAS.some(function(r) {{ return nSel(r) > 0 || r.area === 'taio'; }});
  var hl = ROSAS.map(function() {{ return {{x: [], y: [], z: []}}; }});
  Object.keys(DS).forEach(function(k) {{
    var ti = FIG.data.findIndex(function(t) {{ return t.name === DS[k].traco; }});
    if (ti < 0) return;
    var x = [], y = [], z = [];
    if (dsOn[k]) DS[k].seg.forEach(function(s) {{
      var b = binDe(s[6]), dest = false;
      ROSAS.forEach(function(r, q) {{
        if (r.on[k] && (r.area === 'pan' || s[8]) && (nSel(r) > 0 ? r.bins[b] : r.area === 'taio')) {{ dest = true; var h = hl[q]; h.x.push(s[0], s[3], null); h.y.push(s[1], s[4], null); h.z.push(s[2] + 8 + q * 4, s[5] + 8 + q * 4, null); }}
      }});
      if (dest) return;
      var A = alg ? [cx, cy, cz] : [x, y, z];
      A[0].push(s[0], s[3], null); A[1].push(s[1], s[4], null); A[2].push(s[2], s[5], null);
    }});
    idx.push(ti); X.push(x); Y.push(y); Z.push(z);
  }});
  idx.push(FIG.data.findIndex(function(t) {{ return t.meta === 'ctx'; }})); X.push(cx); Y.push(cy); Z.push(cz);
  ROSAS.forEach(function(r, q) {{ idx.push(FIG.data.findIndex(function(t) {{ return t.meta === r.trace; }})); X.push(hl[q].x); Y.push(hl[q].y); Z.push(hl[q].z); }});
  Plotly.restyle(gd, {{x: X, y: Y, z: Z}}, idx);
}}
function atualizarDirecoes() {{ atualizarRosetas(); atualizar3d(); }}
atualizarRosetas();
ROSAS.forEach(function(r) {{
  document.getElementById('area-' + r.id).onchange = function() {{ r.area = this.value; r.bins = {{}}; atualizarDirecoes(); }};
  document.getElementById('pref-' + r.id).onclick = function() {{ selecionarPref(r); atualizarDirecoes(); }};
  document.getElementById('sub-' + r.id).onclick = function() {{ selecionarSub(r); atualizarDirecoes(); }};
  document.getElementById('lim-' + r.id).onclick = function() {{ r.bins = {{}}; atualizarDirecoes(); }};
}});
document.getElementById('escala-comum').onchange = atualizarRosetas;
document.getElementById('btn-lateral').onclick = function() {{
  var l = document.getElementById('lateral'), vis = l.style.display !== 'none';
  l.style.display = vis ? 'none' : 'block'; this.classList.toggle('ativo', !vis);
  Plotly.Plots.resize(gd); if (!vis) ROSAS.forEach(function(r) {{ Plotly.Plots.resize(r.div); }});
}};
</script></body></html>"""
    OUT_HTML.write_text(html, encoding="utf-8")
    sys.path.insert(0, str(Path(__file__).parent)) if 'sys' in globals() else __import__('sys').path.insert(0, str(Path(__file__).parent))
    import tps_i18n  # botao de idioma (PT/EN) e volta ao hub
    tps_i18n.injetar(OUT_HTML, css="#barra{padding-right:200px}")
    print(f"Salvo em: {OUT_HTML} ({OUT_HTML.stat().st_size / 1e6:.1f} MB)")


if __name__ == "__main__":
    main()
