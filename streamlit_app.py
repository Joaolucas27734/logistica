import streamlit as st
import pandas as pd
import plotly.express as px
import math
import requests
import gspread
from google.oauth2.service_account import Credentials

# --- Configuração da página ---
st.set_page_config(page_title="Dashboard Interativo de Entregas + Estoque", layout="wide")
st.title("📦 Dashboard Interativo – Entregas & Estoque")

# --- Configurar Google Sheets ---
SCOPE = ["https://www.googleapis.com/auth/spreadsheets"]
CREDS = Credentials.from_service_account_info(st.secrets["gcp_service_account"], scopes=SCOPE)
GSHEET_CLIENT = gspread.authorize(CREDS)
SHEET_ID = "1dYVZjzCtDBaJ6QdM81WP2k51QodDGZHzKEhzKHSp7v8"
SHEET_NAME = "Pedidos"  # nome da aba onde será salvo

def salvar_status_no_gsheet(df):
    """Salva automaticamente a coluna Status na planilha Google Sheets"""
    try:
        sheet = GSHEET_CLIENT.open_by_key(SHEET_ID).worksheet(SHEET_NAME)
        col_idx = sheet.find("Status").col  # encontra a coluna "Status"
        # Atualiza cada célula da coluna Status
        for i, status in enumerate(df["Status"], start=2):  # assumindo que linha 1 é cabeçalho
            sheet.update_cell(i, col_idx, status)
    except Exception as e:
        st.error(f"Erro ao salvar no Google Sheets: {e}")

# --- Ler planilha de pedidos ---
url = f"https://docs.google.com/spreadsheets/d/{SHEET_ID}/export?format=csv&sheet={SHEET_NAME}"
df = pd.read_csv(url)

# --- Processar datas ---
df["data_envio"] = pd.to_datetime(df.iloc[:, 1], errors="coerce")
df["data_entrega"] = pd.to_datetime(df.iloc[:, 2], errors="coerce")
df["dias_entrega"] = (df["data_entrega"] - df["data_envio"]).dt.days

# --- Colunas de estado e cidade ---
df["estado"] = df.iloc[:, 3].str.upper()
df["cidade"] = df.iloc[:, 4].astype(str).str.title()

# --- Status de entrega ---
df["Status"] = df["data_entrega"].apply(lambda x: "Entregue" if pd.notna(x) else "Não entregue")

# --- Código de rastreio e link ---
df["Código Rastreio"] = df.iloc[:, 5].astype(str)
df["Link J&T"] = "https://www2.jtexpress.com.br/rastreio/track?codigo=" + df["Código Rastreio"]

# --- Filtros na barra lateral ---
st.sidebar.subheader("📅 Filtrar por Data de Envio")
data_min = df["data_envio"].min()
data_max = df["data_envio"].max()
data_inicio, data_fim = st.sidebar.date_input("Selecione o período:", [data_min, data_max])

st.sidebar.markdown("---")
opcao = st.sidebar.radio("📋 Selecione o módulo:", ["📦 Estoque", "🚚 Logística Geral"])

# ===========================================================
# ==================== MÓDULO: ESTOQUE =====================
# ===========================================================
if opcao == "📦 Estoque":
    df_filtrado = df[
        (df["data_envio"] >= pd.to_datetime(data_inicio)) &
        (df["data_envio"] <= pd.to_datetime(data_fim))
    ]
    
    st.subheader("📊 Principais Métricas de Entregas")
    df_valid = df_filtrado.dropna(subset=["dias_entrega"])
    total = len(df_valid)
    media = df_valid["dias_entrega"].mean() if total > 0 else 0
    mediana = df_valid["dias_entrega"].median() if total > 0 else 0
    pct_ate3 = (df_valid["dias_entrega"] <= 3).sum() / total * 100 if total > 0 else 0
    pct_atraso5 = (df_valid["dias_entrega"] > 5).sum() / total * 100 if total > 0 else 0
    desvio = df_valid["dias_entrega"].std() if total > 0 else 0
    qtd_entregue = (df_filtrado["Status"] == "Entregue").sum()
    qtd_nao_entregue = (df_filtrado["Status"] == "Não entregue").sum()

    col1, col2, col3, col4, col5, col6 = st.columns(6)
    col1.metric("Tempo médio (dias)", f"{media:.1f}")
    col2.metric("Mediana (dias)", f"{mediana:.0f}")
    col3.metric("% Entregas ≤3 dias", f"{pct_ate3:.1f}%")
    col4.metric("% Atrasos (>5 dias)", f"{pct_atraso5:.1f}%")
    col5.metric("Desvio Padrão", f"{desvio:.1f}")
    col6.metric("Entregues / Não", f"{qtd_entregue} / {qtd_nao_entregue}")

    # --- Mapa do Brasil ---
    resumo_estado = df_valid.groupby("estado")["dias_entrega"].agg([
        ("Total Pedidos", "count"),
        ("% Entregas ≤3 dias", lambda x: (x <= 3).sum() / len(x) * 100)
    ]).reset_index()

    st.subheader("🌎 Mapa do Brasil – % Entregas ≤3 dias")
    fig_map = px.choropleth_mapbox(
        resumo_estado,
        geojson="https://raw.githubusercontent.com/codeforamerica/click_that_hood/master/public/data/brazil-states.geojson",
        locations="estado",
        featureidkey="properties.sigla",
        color="% Entregas ≤3 dias",
        hover_data=["Total Pedidos"],
        color_continuous_scale="Greens",
        mapbox_style="carto-positron",
        zoom=3.5,
        center={"lat": -14.2350, "lon": -51.9253},
        opacity=0.6
    )
    st.plotly_chart(fig_map, use_container_width=True)

    # --- Controle de Estoque ---
    st.subheader("📦 Controle de Estoque Interno")
    aba_estoque = "Estoque"
    url_estoque = f"https://docs.google.com/spreadsheets/d/{sheet_id}/gviz/tq?tqx=out:csv&sheet={aba_estoque}"

    try:
        df_estoque = pd.read_csv(url_estoque)
        df_estoque.columns = ["Produto", "Quantidade", "Estoque Mínimo", "Ja Gasto"]
    except Exception as e:
        st.error(f"❌ Não foi possível ler a aba 'Estoque'. Erro: {e}")
        df_estoque = pd.DataFrame(columns=["Produto", "Quantidade", "Estoque Mínimo", "Ja Gasto"])

    df_estoque["Quantidade"] = pd.to_numeric(df_estoque["Quantidade"], errors="coerce").fillna(0)
    df_estoque["Estoque Mínimo"] = pd.to_numeric(df_estoque["Estoque Mínimo"], errors="coerce").fillna(0)
    df_estoque["Ja Gasto"] = pd.to_numeric(df_estoque["Ja Gasto"], errors="coerce").fillna(0)
    df_estoque["Produto"] = df_estoque["Produto"].astype(str).str.strip()
    df_estoque["Quantidade_Atual"] = (df_estoque["Quantidade"] - df_estoque["Ja Gasto"]).clip(lower=0)
    df_estoque["Pacotes (20 peças)"] = df_estoque["Quantidade_Atual"].apply(lambda x: math.floor(x / 20))

    st.session_state.df_estoque_atual = df_estoque.copy()
    df_estoque_atual = st.session_state.df_estoque_atual.copy()

    estoque_baixo = df_estoque_atual[df_estoque_atual["Quantidade_Atual"] <= df_estoque_atual["Estoque Mínimo"]]
    if not estoque_baixo.empty:
        st.warning("⚠️ Produtos com estoque baixo!")
        st.dataframe(estoque_baixo)

    st.subheader("📝 Estoque Atual")
    st.dataframe(df_estoque_atual[["Produto", "Quantidade", "Ja Gasto", "Quantidade_Atual", "Pacotes (20 peças)", "Estoque Mínimo"]])

# ===========================================================
# ================= MÓDULO: LOGÍSTICA GERAL =================
# ===========================================================
# ===========================================================
if opcao == "🚚 Logística Geral":
    st.subheader("🚚 Logística Geral – Pedidos Shopify")

    import requests
    import pandas as pd
    import plotly.express as px

    # --- Função para carregar pedidos ---
    def carregar_dados_shopify():
        SHOP_NAME = st.secrets["shopify"]["shop_name"]
        ACCESS_TOKEN = st.secrets["shopify"]["access_token"]

        url_base = f"https://{SHOP_NAME}/admin/api/2023-10/orders.json?status=any&limit=250"
        headers = {"X-Shopify-Access-Token": ACCESS_TOKEN}

        pedidos_total = []
        url = url_base
        contador = 0

        while url and contador < 4:  # até 1000 pedidos
            response = requests.get(url, headers=headers)
            if response.status_code != 200:
                st.error(f"Erro ao acessar a Shopify: {response.status_code}")
                break

            data = response.json()
            pedidos = data.get("orders", [])
            pedidos_total.extend(pedidos)
            contador += 1

            # Paginação
            link_header = response.headers.get("Link", "")
            next_url = None
            if 'rel="next"' in link_header:
                partes = link_header.split(",")
                for parte in partes:
                    if 'rel="next"' in parte:
                        next_url = parte.split(";")[0].strip("<> ")
                        break
            url = next_url

        if not pedidos_total:
            st.warning("Nenhum pedido encontrado.")
            return pd.DataFrame()

        linhas = []
        for pedido in pedidos_total:
            if pedido.get("financial_status") != "paid":
                continue  # ✅ Apenas pedidos pagos

            line_items = pedido.get("line_items", [])
            for item in line_items:
                linha = {
                    "id": pedido.get("id"),
                    "data": pedido.get("created_at"),
                    "cliente": (pedido.get("customer") or {}).get("first_name", "") + " " +
                               (pedido.get("customer") or {}).get("last_name", ""),
                    "Status": pedido.get("fulfillment_status") or "Não entregue",
                    "produto": item.get("title"),
                    "variante": item.get("variant_title"),
                    "itens": item.get("quantity"),
                    "forma_entrega": (pedido.get("shipping_lines")[0]["title"]
                                      if pedido.get("shipping_lines") else "N/A"),
                    "estado": (pedido.get("shipping_address") or {}).get("province", "N/A"),
                    "cidade": (pedido.get("shipping_address") or {}).get("city", "N/A")
                }
                linhas.append(linha)

        df = pd.DataFrame(linhas)
        df["data"] = pd.to_datetime(df["data"], errors="coerce")
        return df

    # --- Carregar dados ---
    df_shopify = carregar_dados_shopify()
    if df_shopify.empty:
        st.stop()

    df_shopify = df_shopify.sort_values("data", ascending=False)

    # --- Criar abas ---
    aba1, aba2, aba3, aba4, aba5 = st.tabs([
        "📋 Pedidos Normalizados",
        "📦 Produtos & Variantes",
        "🏙️ Cidades & Estados",
        "📈 Tendência de Variante",
        "⚖️ Comparar Variantes"
    ])

    # --- Aba 1: Pedidos Normalizados ---
with aba1:
        st.subheader("📋 Pedidos Normalizados (editável)")

        df_editado = st.data_editor(
            df_shopify[[
                "data", "cliente", "Status", "produto", "variante", "itens", "forma_entrega", "estado", "cidade"
            ]],
            columns={
                "Status": st.column_config.SelectboxColumn("Status", options=["Aguardando", "Entregue", "Não entregue"])
            },
            disabled=[col for col in df_shopify.columns if col != "Status"],
            num_rows="dynamic",
            use_container_width=True
        )
        # Salvar automaticamente alterações
        salvar_status_no_gsheet(df_editado)

    # --- Aba 2: Produtos e Variantes ---
    with aba2:
        pedidos_produto = df_shopify.groupby("produto")["itens"].sum().reset_index().sort_values("itens", ascending=False)
        pedidos_variante = df_shopify.groupby(["produto", "variante"])["itens"].sum().reset_index().sort_values("itens", ascending=False)

        st.subheader("📊 Pedidos por Produto")
        st.dataframe(pedidos_produto.rename(columns={"itens": "Qtd Pedidos"}))

        st.subheader("📊 Pedidos por Variante")
        st.dataframe(pedidos_variante.rename(columns={"itens": "Qtd Pedidos"}))

    # --- Aba 3: Cidades e Estados ---
    with aba3:
        pedidos_cidade = df_shopify.groupby("cidade")["itens"].sum().reset_index().sort_values("itens", ascending=False)
        pedidos_estado = df_shopify.groupby("estado")["itens"].sum().reset_index().sort_values("itens", ascending=False)

        st.subheader("🏙️ Pedidos por Cidade")
        st.dataframe(pedidos_cidade.rename(columns={"itens": "Qtd Pedidos"}))

        st.subheader("🗺️ Pedidos por Estado")
        st.dataframe(pedidos_estado.rename(columns={"itens": "Qtd Pedidos"}))

        if not pedidos_cidade.empty:
            cidade_top = pedidos_cidade.iloc[0]
            st.markdown(f"**Cidade com mais pedidos:** {cidade_top['cidade']} ({cidade_top['itens']} itens)")

    # --- Aba 4: Tendência de Variante ---
    with aba4:
        variantes_disponiveis = df_shopify["variante"].dropna().unique()
        variante_sel = st.selectbox("Selecione a variante:", variantes_disponiveis)
        df_variante = df_shopify[df_shopify["variante"] == variante_sel]
        df_tendencia = df_variante.groupby(df_variante["data"].dt.date)["itens"].sum().reset_index()
        df_tendencia = df_tendencia.rename(columns={"data": "Data", "itens": "Qtd Pedidos"})
        fig = px.line(df_tendencia, x="Data", y="Qtd Pedidos", markers=True, title=f"Tendência da Variante {variante_sel}")
        st.plotly_chart(fig, use_container_width=True)

    # --- Aba 5: Comparar Variantes ---
    with aba5:
        variantes_disponiveis = df_shopify["variante"].dropna().unique()
        num_comparacoes = st.number_input("Quantas comparações deseja?", min_value=1, max_value=5, value=2)

        df_todas = pd.DataFrame()
        for i in range(num_comparacoes):
            st.markdown(f"### Comparação {i+1}")
            var_sel = st.selectbox(f"Selecione a variante {i+1}:", variantes_disponiveis, key=f"var{i}")
            data_min, data_max = df_shopify["data"].min().date(), df_shopify["data"].max().date()
            data_inicio, data_fim = st.date_input(f"Período para {var_sel}:", [data_min, data_max], key=f"date{i}")

            df_var = df_shopify[
                (df_shopify["variante"] == var_sel) &
                (df_shopify["data"].dt.date >= data_inicio) &
                (df_shopify["data"].dt.date <= data_fim)
            ]
            df_var = df_var.groupby(df_var["data"].dt.date)["itens"].sum().reset_index()
            df_var["variante"] = f"{var_sel} (Comp {i+1})"
            df_var["x_ord"] = range(1, len(df_var)+1)
            df_todas = pd.concat([df_todas, df_var])

        if not df_todas.empty:
            fig = px.line(df_todas, x="x_ord", y="itens", color="variante", markers=True, hover_data=["data"])
            fig.update_layout(xaxis_title="Dia (comparativo)", yaxis_title="Qtd Pedidos")
            st.plotly_chart(fig, use_container_width=True)
        else:
            st.info("Nenhuma comparação disponível.")
