import streamlit as st
import pandas as pd
import plotly.express as px

# --- Configuração da página ---
st.set_page_config(page_title="Dashboard Interativo de Entregas + Estoque", layout="wide")
st.title("📦 Dashboard Interativo – Entregas & Estoque")

# --- Ler planilha de pedidos ---
sheet_id = "1dYVZjzCtDBaJ6QdM81WP2k51QodDGZHzKEhzKHSp7v8"
url = f"https://docs.google.com/spreadsheets/d/{sheet_id}/export?format=csv"
df = pd.read_csv(url)

# --- Processar datas ---
df["data_envio"] = pd.to_datetime(df.iloc[:,1], errors="coerce")
df["data_entrega"] = pd.to_datetime(df.iloc[:,2], errors="coerce")
df["dias_entrega"] = (df["data_entrega"] - df["data_envio"]).dt.days

# --- Colunas de estado e cidade ---
df["estado"] = df.iloc[:,3].str.upper()
df["cidade"] = df.iloc[:,4].astype(str).str.title()

# --- Status de entrega ---
df["Status"] = df["data_entrega"].apply(lambda x: "Entregue" if pd.notna(x) else "Não entregue")

# --- Código de rastreio e link ---
df["Código Rastreio"] = df.iloc[:,5].astype(str)
df["Link J&T"] = "https://www2.jtexpress.com.br/rastreio/track?codigo=" + df["Código Rastreio"]

# --- Filtro por data ---
st.sidebar.subheader("📅 Filtrar por Data de Envio")
data_min = df["data_envio"].min()
data_max = df["data_envio"].max()
data_inicio, data_fim = st.sidebar.date_input("Selecione o período:", [data_min, data_max])
df_filtrado = df[(df["data_envio"] >= pd.to_datetime(data_inicio)) & (df["data_envio"] <= pd.to_datetime(data_fim))]

# --- Dados válidos ---
df_valid = df_filtrado.dropna(subset=["dias_entrega"])
total = len(df_valid)
media = df_valid["dias_entrega"].mean() if total>0 else 0
mediana = df_valid["dias_entrega"].median() if total>0 else 0
pct_ate3 = (df_valid["dias_entrega"]<=3).sum()/total*100 if total>0 else 0
pct_atraso5 = (df_valid["dias_entrega"]>5).sum()/total*100 if total>0 else 0
desvio = df_valid["dias_entrega"].std() if total>0 else 0

# --- Contagem entregues/não entregues ---
qtd_entregue = (df_filtrado["Status"]=="Entregue").sum()
qtd_nao_entregue = (df_filtrado["Status"]=="Não entregue").sum()

# --- Tabs ---
tab1, tab2, tab3, tab4 = st.tabs([
    "📊 Dashboard", 
    "📝 Resumo de Pedidos", 
    "📈 Probabilidade de Entrega",
    "📦 Controle de Estoque"
])

# ==================== TAB 1 - Dashboard ====================
with tab1:
    st.subheader("📊 Principais Métricas")
    col1, col2, col3, col4, col5, col6 = st.columns(6)
    col1.metric("Tempo médio (dias)", f"{media:.1f}")
    col2.metric("Mediana (dias)", f"{mediana:.0f}")
    col3.metric("% Entregas ≤3 dias", f"{pct_ate3:.1f}%")
    col4.metric("% Atrasos (>5 dias)", f"{pct_atraso5:.1f}%")
    col5.metric("Desvio Padrão", f"{desvio:.1f}")
    col6.metric("Entregues / Não", f"{qtd_entregue} / {qtd_nao_entregue}")

    # --- Resumo por estado ---
    resumo_estado = df_valid.groupby("estado")["dias_entrega"].agg([
        ("Total Pedidos","count"),
        ("% Entregas ≤3 dias", lambda x: (x<=3).sum()/len(x)*100)
    ]).reset_index()

    # --- Mapa do Brasil ---
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
        center={"lat":-14.2350,"lon":-51.9253},
        opacity=0.6
    )
    st.plotly_chart(fig_map, use_container_width=True)

    # --- Dropdown para selecionar estado ---
    st.subheader("📈 Gráfico de Entregas por Cidade")
    estados = sorted(df_valid["estado"].unique())
    estado_sel = st.selectbox("Selecione um estado para ver as cidades", ["Todos"] + estados)

    if estado_sel == "Todos":
        fig_estado = px.bar(
            resumo_estado,
            x="estado",
            y="% Entregas ≤3 dias",
            hover_data=["Total Pedidos"],
            color="% Entregas ≤3 dias",
            color_continuous_scale="Greens",
            title="Entregas ≤3 dias por Estado"
        )
        st.plotly_chart(fig_estado, use_container_width=True)
    else:
        df_cidades = df_valid[df_valid["estado"]==estado_sel]
        resumo_cidade = df_cidades.groupby("cidade")["dias_entrega"].agg([
            ("Total Pedidos","count"),
            ("Média Dias","mean"),
            ("Mediana Dias","median")
        ]).reset_index()

        fig_box = px.box(
            df_cidades,
            x="cidade",
            y="dias_entrega",
            color="cidade",
            title=f"Distribuição de Dias de Entrega por Cidade - {estado_sel}",
            points="all"
        )
        st.plotly_chart(fig_box, use_container_width=True)

    st.subheader("📊 Distribuição de Dias de Entrega")
    freq = df_valid["dias_entrega"].value_counts().sort_index()
    st.bar_chart(freq)

# ==================== TAB 2 - Resumo de Pedidos ====================
with tab2:
    st.subheader("📝 Tabela de Pedidos")
    tabela_resumo = df_filtrado[[df.columns[0], "data_envio", "data_entrega", "dias_entrega", "estado", "cidade", "Status", "Código Rastreio", "Link J&T"]].sort_values("data_envio")
    tabela_resumo = tabela_resumo.rename(columns={df.columns[0]: "Número do Pedido"})
    st.dataframe(tabela_resumo)

# ==================== TAB 3 - Probabilidade de Entrega ====================
with tab3:
    st.subheader("📈 Probabilidade de Entrega por Estado")
    prob_estado = df_valid.groupby("estado")["dias_entrega"].agg([
        ("Total Pedidos", "count"),
        ("Prob ≤3 dias", lambda x: int(round((x <= 3).sum() / len(x) * 100))),
        ("Prob ≤5 dias", lambda x: int(round((x <= 5).sum() / len(x) * 100)))
    ]).reset_index()
    st.table(prob_estado.sort_values("Prob ≤3 dias", ascending=False))

# ==================== TAB 4 - Controle de Estoque ====================
with tab4:
    st.subheader("📦 Controle de Estoque Interno")

    # --- Ler a aba Estoque ---
    sheet_id = "1dYVZjzCtDBaJ6QdM81WP2k51QodDGZHzKEhzKHSp7v8"
    aba_estoque = "Estoque"
    url_estoque = f"https://docs.google.com/spreadsheets/d/{sheet_id}/gviz/tq?tqx=out:csv&sheet={aba_estoque}"

    try:
        df_estoque = pd.read_csv(url_estoque)
        # Supondo que a planilha tem colunas: Produto | Quantidade | Estoque Mínimo | Já Gasto
        df_estoque.columns = ["Produto", "Quantidade", "Estoque Mínimo", "Ja Gasto"]
    except Exception as e:
        st.error(f"❌ Não foi possível ler a aba 'Estoque'. Erro: {e}")
        df_estoque = pd.DataFrame(columns=["Produto", "Quantidade", "Estoque Mínimo", "Ja Gasto"])

    # --- Garantir tipos corretos ---
    df_estoque["Quantidade"] = pd.to_numeric(df_estoque["Quantidade"], errors="coerce").fillna(0)
    df_estoque["Estoque Mínimo"] = pd.to_numeric(df_estoque["Estoque Mínimo"], errors="coerce").fillna(0)
    df_estoque["Ja Gasto"] = pd.to_numeric(df_estoque["Ja Gasto"], errors="coerce").fillna(0)
    df_estoque["Produto"] = df_estoque["Produto"].astype(str).str.strip()

    # --- Calcular estoque atual subtraindo o que já foi gasto ---
    df_estoque["Quantidade_Atual"] = (df_estoque["Quantidade"] - df_estoque["Ja Gasto"]).clip(lower=0)

    # --- Calcular pacotes completos de 20 peças restantes ---
    import math
    df_estoque["Pacotes (20 peças)"] = df_estoque["Quantidade_Atual"].apply(lambda x: math.floor(x / 20))

    # --- Persistir alterações no session_state ---
    st.session_state.df_estoque_atual = df_estoque.copy()
    df_estoque_atual = st.session_state.df_estoque_atual.copy()

    # --- Alerta de estoque baixo ---
    estoque_baixo = df_estoque_atual[df_estoque_atual["Quantidade_Atual"] <= df_estoque_atual["Estoque Mínimo"]]
    if not estoque_baixo.empty:
        st.warning("⚠️ Produtos com estoque baixo!")
        st.dataframe(estoque_baixo)

    # --- Tabela completa de estoque ---
    st.subheader("📝 Estoque Atual")
    st.dataframe(df_estoque_atual[["Produto", "Quantidade", "Ja Gasto", "Quantidade_Atual", "Pacotes (20 peças)", "Estoque Mínimo"]])

    # --- Gráfico de barras quantidade vs estoque mínimo ---
    st.subheader("📊 Estoque Atual x Estoque Mínimo")
    if not df_estoque_atual.empty:
        fig_estoque = px.bar(
            df_estoque_atual,
            x="Produto",
            y=["Quantidade_Atual", "Estoque Mínimo"],
            barmode="group",
            color_discrete_sequence=["#1f77b4", "#ff7f0e"],
            text_auto=True,
            title="Quantidade Atual em Estoque vs Estoque Mínimo"
        )
        st.plotly_chart(fig_estoque, use_container_width=True)
