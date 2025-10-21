import streamlit as st
import pandas as pd
import plotly.express as px
import math
import requests

# --- Configuração da página ---
st.set_page_config(page_title="Dashboard Interativo de Entregas + Estoque", layout="wide")
st.title("📦 Dashboard Interativo – Entregas & Estoque")

# --- Ler planilha de pedidos ---
sheet_id = "1dYVZjzCtDBaJ6QdM81WP2k51QodDGZHzKEhzKHSp7v8"
url = f"https://docs.google.com/spreadsheets/d/{sheet_id}/export?format=csv"
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
elif opcao == "🚚 Logística Geral":
    st.subheader("🚚 Logística Geral – Pedidos Shopify")

    # --- Função para carregar dados da Shopify ---
    def carregar_dados_shopify():
        SHOP_NAME = st.secrets["shopify"]["shop_name"]
        ACCESS_TOKEN = st.secrets["shopify"]["access_token"]

        url = f"https://{SHOP_NAME}/admin/api/2023-10/orders.json?status=any&limit=250"
        headers = {"X-Shopify-Access-Token": ACCESS_TOKEN}

        response = requests.get(url, headers=headers)
        if response.status_code != 200:
            st.error(f"Erro ao acessar a Shopify: {response.status_code}")
            return pd.DataFrame()

        pedidos = response.json().get("orders", [])
        if not pedidos:
            st.warning("Nenhum pedido encontrado.")
            return pd.DataFrame()

        linhas = []
        for pedido in pedidos:
            line_items = pedido.get("line_items", [])
            if not line_items:
                continue
            for item in line_items:
                linha = {
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

    # --- Ordenar do mais recente para o mais antigo ---
    df_shopify = df_shopify.sort_values("data", ascending=False)

    # --- Mostrar tabela completa ---
    st.subheader("🧾 Pedidos Normalizados da Shopify")
    st.dataframe(df_shopify[[
        "data", "cliente", "Status", "produto", "variante", "itens", "forma_entrega", "estado", "cidade"
    ]])

    # --- Pedidos por Produto ---
    st.subheader("📊 Pedidos por Produto")
    pedidos_produto = df_shopify.groupby("produto")["itens"].sum().reset_index()
    pedidos_produto = pedidos_produto.rename(columns={"itens": "Qtd Pedidos"})
    pedidos_produto = pedidos_produto.sort_values("Qtd Pedidos", ascending=False)
    st.dataframe(pedidos_produto)

    # --- Pedidos por Variante ---
    st.subheader("📊 Pedidos por Variante")
    pedidos_variante = df_shopify.groupby(["produto", "variante"])["itens"].sum().reset_index()
    pedidos_variante = pedidos_variante.rename(columns={"itens": "Qtd Pedidos"})
    pedidos_variante = pedidos_variante.sort_values("Qtd Pedidos", ascending=False)
    st.dataframe(pedidos_variante)

    # --- Pedidos por Cidade ---
    st.subheader("🏙️ Pedidos por Cidade")
    pedidos_cidade = df_shopify.groupby("cidade")["itens"].sum().reset_index()
    pedidos_cidade = pedidos_cidade.rename(columns={"itens": "Qtd Pedidos"})
    pedidos_cidade = pedidos_cidade.sort_values("Qtd Pedidos", ascending=False)
    st.dataframe(pedidos_cidade)

    # --- Cidade com mais pedidos ---
    if not pedidos_cidade.empty:
        cidade_top = pedidos_cidade.iloc[0]
        st.markdown(f"**Cidade com mais pedidos:** {cidade_top['cidade']} ({cidade_top['Qtd Pedidos']} itens)")
       # --- Contagem de pedidos por estado ---
st.subheader("📊 Pedidos por Estado")
pedidos_estado = df_shopify.groupby("estado")["itens"].sum().reset_index()
pedidos_estado = pedidos_estado.rename(columns={"itens": "Qtd Pedidos"})
pedidos_estado = pedidos_estado.sort_values("Qtd Pedidos", ascending=False)  # Mais pedidos no topo

st.dataframe(pedidos_estado)

# --- Tendência de crescimento de uma variante ---
st.subheader("📈 Tendência de Crescimento de uma Variante")

# Seleção da variante
variantes_disponiveis = df_shopify["variante"].dropna().unique()
variante_sel = st.selectbox("Selecione a variante:", variantes_disponiveis)

# Filtrar apenas a variante selecionada
df_variante = df_shopify[df_shopify["variante"] == variante_sel]

# Agrupar por data e somar itens
df_tendencia = df_variante.groupby(df_variante["data"].dt.date)["itens"].sum().reset_index()
df_tendencia = df_tendencia.rename(columns={"data": "Data", "itens": "Qtd Pedidos"})

# Plotar gráfico de linha
import plotly.express as px

fig_tendencia = px.line(
    df_tendencia,
    x="Data",
    y="Qtd Pedidos",
    title=f"Tendência de Pedidos da Variante: {variante_sel}",
    markers=True
)
st.plotly_chart(fig_tendencia, use_container_width=True)

