# 3D regional (panorama) — norte de Santa Catarina

**Versão 1.0** · Projeto *Taió Plumbing System* (Mestrado em Geologia, UFSC)

🔗 **Acesso:** <https://thubaraleii.github.io/PANORAMA/panorama_3d_taio.html>

Panorama 3D (Plotly, HTML autônomo) de 350 × 180 km do norte de Santa Catarina (Alto Vale, Serra, Itajaí e plataforma
continental), para análise regional de lineamentos, poços e geologia, como base para a reconstrução cinemática.

## Funcionalidades

**Barra superior**
- **Textura:** satélite (Esri), geologia SC (CPRM, 1:500.000) ou hipsometria com batimetria.
- **Camadas:** lineamentos locais, estruturas CPRM (falhas, fraturas e diques), corpos/Taió (soleiras, diques, área de estudo e buffer de 5 km) e poços.
- **Vista:** oblíqua, planta, perfil O→L e perfil S→N; **exagero vertical** de 1× a 20× (padrão 8×).

**Painel de rosetas** (botão *Rosetas*; inicia fechado)
- **Duas rosetas independentes** (comparação lado a lado), em classes de 10°, por comprimento (km), simétricas (0–180°), com escala radial comum opcional.
- Cada roseta tem seus **conjuntos** (falhas CPRM, fraturas CPRM, diques CPRM, lineamentos locais + e −), sua **área** (panorama inteiro ou **área de estudo + buffer de 5 km**) e sua **seleção de direção**: *preferencial* (classe de maior comprimento, ±10°) e *subordinada* (maior classe a pelo menos 30° da preferencial).
- Estatísticas por roseta: comprimento, número de lineamentos, direção média (e concentração R) e classe dominante.
- No 3D, a seleção da roseta 1 aparece em branco e a da roseta 2 em amarelo; o restante dos conjuntos marcados fica em cinza.

**Poços:** poços (ANP e SAG) dentro do recorte, como marcadores com haste proporcional à profundidade total.

## Dados e métodos

- Relevo e batimetria: AWS Terrain Tiles (Terrarium); textura de satélite: Esri World Imagery (mosaicos baixados uma vez e guardados em cache).
- Lineamentos locais (positivos e negativos) do mapeamento do autor; falhas, fraturas e diques regionais do SIG SC (CPRM).
- Roseta: azimute de cada segmento (~0,7–1 km) ponderado pelo comprimento; direção média pelo método do ângulo duplicado.

## Idioma e navegação

- **Idioma:** o botão **EN / PT**, ao lado do logotipo, alterna a interface entre português e inglês em tempo real (menus, legendas, dicas, popups, rótulos e textos 3D). O padrão é **sempre o português**; o inglês vale na página aberta com `?lang=en`, parâmetro que o botão e os links entre as páginas repassam.
- **Hub:** o botão **← Hub** volta à página inicial do projeto, mantendo o idioma.
- **Tradução:** feita no navegador por dicionário (`tps_i18n_dict.py`, embutido na página por `tps_i18n.py` ao gerar o HTML). Dados de origem em português (por exemplo, descrições de campo e nomes próprios de unidades) permanecem no idioma original.

## Uso

Abra `panorama_3d_taio.html` no navegador ou acesse a versão publicada. Clique em **Rosetas** para abrir o painel de direções.

## Regenerar os produtos

O repositório contém o HTML publicado e o script gerador. Para regenerar é necessário o conjunto de dados do projeto
(modelo digital de elevação, litologia, pontos de campo, lineamentos, poços), que **não é distribuído** neste repositório.

```bash
python gerar_panorama_3d.py
```

Dependências Python: `numpy`, `pandas`, `geopandas`, `shapely`, `pyproj`, `rasterio`, `scipy`, `plotly`, `contextily`.

## Estrutura

```
panorama_3d_taio.html     produto gerado
gerar_panorama_3d.py      gerador
assets/                   logotipo e ícones
```

## Referências

1. Milani, E. J.; Melo, J. H. G.; Souza, P. A.; Fernandes, L. A.; França, A. B. (2007). Bacia do Paraná. *Boletim de Geociências da Petrobras*, 15(2), 265–287.
2. Schneider, R. L.; Mühlmann, H.; Tommasi, E.; Medeiros, R. A.; Daemon, R. F.; Nogueira, A. A. (1974). Revisão estratigráfica da Bacia do Paraná. In: *Anais do 28º Congresso Brasileiro de Geologia*, Porto Alegre, SBG, 1, 41–65.
3. Frank, H. T.; Gomes, M. E. B.; Formoso, M. L. L. (2009). Review of the areal extent and the volume of the Serra Geral Formation, Paraná Basin, South America. *Pesquisas em Geociências*, 36(1), 49–57.
4. Peate, D. W. (1997). The Paraná–Etendeka Province. In: Mahoney, J. J.; Coffin, M. F. (eds.), *Large Igneous Provinces*. AGU Geophysical Monograph 100, 217–245.
5. Mardia, K. V.; Jupp, P. E. (2000). *Directional Statistics*. Chichester: John Wiley & Sons.
6. Fisher, N. I. (1993). *Statistical Analysis of Circular Data*. Cambridge: Cambridge University Press.
7. Agafonkin, V. **Leaflet** — an open-source JavaScript library for interactive maps. <https://leafletjs.com>
8. Plotly Technologies Inc. (2015). **Collaborative data science** (Plotly.js). Montréal. <https://plot.ly>
9. Mapzen / Amazon Web Services. **Terrain Tiles** (formato Terrarium). <https://registry.opendata.aws/terrain-tiles/>
10. OpenStreetMap contributors. **OpenStreetMap**. <https://www.openstreetmap.org/copyright>
11. CPRM/SGB — Serviço Geológico do Brasil. **Geologia e Recursos Minerais do Estado de Santa Catarina — Mapa Geológico 1:500.000 (SIG SC)**. <https://geosgb.sgb.gov.br>
12. ANP — Agência Nacional do Petróleo, Gás Natural e Biocombustíveis. **Dados abertos — poços**. <https://www.gov.br/anp>
13. Harris, C. R. et al. (2020). Array programming with NumPy. *Nature*, 585, 357–362.
14. Virtanen, P. et al. (2020). SciPy 1.0: fundamental algorithms for scientific computing in Python. *Nature Methods*, 17, 261–272.
15. Jordahl, K. et al. **GeoPandas**. Zenodo. <https://geopandas.org>; Gillies, S. et al. **Shapely** e **Rasterio**. <https://github.com/shapely/shapely>, <https://github.com/rasterio/rasterio>.

## Licença e uso

- **Código** (scripts de geração e JavaScript das páginas): licença **MIT** — ver [`LICENSE`](LICENSE).
- **Produtos gerados** (HTML, figuras, tabelas derivadas): **CC BY 4.0** — uso, adaptação e redistribuição permitidos com atribuição ao autor.
- **Dados de terceiros** incorporados mantêm as licenças e os termos das fontes originais (tabela em *Créditos e fontes de dados*).
- Os modelos são **interpretativos** e dependem da qualidade e da densidade dos dados de entrada; **não substituem** estudo geológico, hidrogeológico ou geotécnico de detalhe, nem devem ser usados como base única para decisões de engenharia, perfuração ou licenciamento.
- Fornecido “como está”, sem garantias de qualquer tipo.

## Créditos e fontes de dados

| Fonte | Uso | Termos |
|---|---|---|
| Levantamento de campo do autor (pontos, estruturas, geoquímica, MDE de drone) | Dados primários da área de Taió | CC BY 4.0 (autor) |
| CPRM/SGB — Mapa Geológico do Estado de Santa Catarina 1:500.000 (SIG SC) | Geologia regional, falhas, fraturas e diques regionais | Dados abertos CPRM/SGB — citar a fonte |
| ANP — Tabela de poços (dados abertos) | Poços de petróleo/gás (posição e profundidade total) | Dados abertos ANP — citar a fonte |
| Cadastro de poços do Sistema Aquífero Guarani (SAG) | Poços do SAG (posição e profundidade), arquivo KML do projeto | Citar a fonte original do cadastro |
| OpenStreetMap contributors | Rios, estradas e localidades | ODbL 1.0 — © OpenStreetMap contributors |
| Esri World Imagery | Imagem de satélite (tiles e textura) | Termos da Esri — uso com atribuição |
| CARTO / OpenTopoMap | Mapas base do webmap | Atribuição nos próprios mapas (OSM, SRTM, OpenTopoMap CC-BY-SA) |
| AWS Terrain Tiles (formato Terrarium) | Relevo e batimetria regionais (derivados de SRTM, GEBCO e outras fontes) | Atribuição conforme o provedor dos tiles |
| Plotly.js (MIT), Leaflet (BSD-2-Clause) | Bibliotecas de visualização embutidas/carregadas nas páginas | Licenças originais |

## Como citar

> JESUS, A. H. de. **3D regional (panorama) — norte de Santa Catarina**, versão 1.0. 2026. Projeto *Taió Plumbing System* — Mestrado em Geologia, UFSC. Disponível em: <https://thubaraleii.github.io/PANORAMA/panorama_3d_taio.html>.

## Autoria

**Afonso Henrique de Jesus** — Mestrado em Geologia, Universidade Federal de Santa Catarina (UFSC).
Projeto: *Architecture and Geochemical Evolution of the Taió Intrusive Plumbing System* (Taió, SC — Bacia do Paraná).
