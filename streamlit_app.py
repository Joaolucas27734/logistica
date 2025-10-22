import streamlit as st
import pandas as pd
import plotly.express as px
import math
import requests
import gspread
from google.oauth2.service_account import Credentials
import json

# ===========================================================
# =================== CONFIGURAÇÃO GERAL ====================
# ===========================================================
st.set_page_config(page_title="Dashboard Interativo de Entregas + Estoque", layout="wide")
st.title("📦 Dashboard Interativo – Entregas & Estoque")

# --- Configurar Google Sheets ---
SCOPE = ["https://www.googleapis.com/auth/spreadsheets"]
creds_dict = json.loads(st.secrets["gcp_service_account"]["json"])
CREDS = Credentials.from_service_account_info(creds_dict, scopes=SCOPE)
GSHEET_CLIENT = gspread.authorize(CREDS)

SHEET_ID = "1dYVZjzCtDBaJ6QdM81WP2k51QodDGZHzKEhzKHSp7v8"
SHEET_NAME = "Pedidos"  # aba principal


# ===========================================================
# =================== FUNÇÕES AUXILIARES ====================
# ===========================================================
def salvar_status_no_gsheet(df):
    """Salva automaticamente a coluna Status na planilha Google Sheets"""
    try:
        sheet = GSHEET_CLIENT.open_by_key(SHEET_ID).worksheet(SHEET_NAME)
        col_idx = sheet.find("Status").col  # encontra a coluna "Status"
        for i, status in enumerate(df["Status"], start=2):  # linha 1 é cabeçalho
            sheet.update_cell(i, col_idx, status)
    except Exception as e:
        st.error(f"Erro ao salvar no Google Sheets: {e}")


def df_para_lista(df):
    """Converte DataFrame em lista de listas para enviar ao Google Sheets"""
    return [df.columns.tolist()] + df.astype(str).values.tolist()


# ===========================================================
# ====================== DADOS BASE =========================
# ===========================================================
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

# ===========================================================
# ==================== BARRA LATERAL ========================
# ===========================================================
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
    url_estoque = f"https://docs.google.com/spreadsheets/d/{SHEET_ID}/gviz/tq?tqx=out:csv&sheet={aba_estoque}"

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
# ================ MÓDULO: LOGÍSTICA GERAL ==================
# ===========================================================
elif opcao == "🚚 Logística Geral":
    st.subheader("🚚 Logística Geral – Pedidos Shopify")

    sheet_id = SHEET_ID
    sh = GSHEET_CLIENT.open_by_key(sheet_id)
    aba_shopify = "Pedidos Shopify"

    try:
        worksheet = sh.worksheet(aba_shopify)
    except gspread.exceptions.WorksheetNotFound:
        worksheet = sh.add_worksheet(title=aba_shopify, rows="1000", cols="20")

    # --- Função para carregar pedidos pagos da Shopify ---
    def carregar_dados_shopify():
        SHOP_NAME = st.secrets["shopify"]["shop_name"]
        ACCESS_TOKEN = st.secrets["shopify"]["access_token"]

        url_base = f"https://{SHOP_NAME}/admin/api/2023-10/orders.json?status=any&limit=250"
        headers = {"X-Shopify-Access-Token": ACCESS_TOKEN}

        pedidos_total = []
        url = url_base
        contador = 0

        while url and contador < 4:
            response = requests.get(url, headers=headers)
            if response.status_code != 200:
                st.error(f"Erro ao acessar a Shopify: {response.status_code}")
                break

            data = response.json()
            pedidos = data.get("orders", [])
            pedidos_total.extend(pedidos)
            contador += 1

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
            # 🔹 FILTRA APENAS PAGOS
            if pedido.get("financial_status") not in ["paid", "partially_paid"]:
                continue

            line_items = pedido.get("line_items", [])
            if not line_items:
                continue
            for item in line_items:
                linha = {
                    "data": pedido.get("created_at"),
                    "cliente": (pedido.get("customer") or {}).get("first_name", "") + " " +
                               (pedido.get("customer") or {}).get("last_name", ""),
                    "Status": pedido.get("fulfillment_status") or "Aguardando",
                    "produto": item.get("title"),
                    "variante": item.get("variant_title"),
                    "itens": item.get("quantity"),
                    "forma_entrega": (pedido.get("shipping_lines")[0]["title"]
                                      if pedido.get("shipping_lines") else "N/A"),
                    "estado": (pedido.get("shipping_address") or {}).get("province", "N/A"),
                    "cidade": (pedido.get("shipping_address") or {}).get("city", "N/A"),
                    "pagamento": pedido.get("financial_status", "desconhecido")
                }
                linhas.append(linha)

        df = pd.DataFrame(linhas)
        df["data"] = pd.to_datetime(df["data"], errors="coerce")
        return df

    # --- Carregar e salvar dados ---
    df_shopify = carregar_dados_shopify()
    if df_shopify.empty:
        st.stop()

    worksheet.clear()
    worksheet.update(df_para_lista(df_shopify))
    st.success(f"✅ Dados da Shopify (apenas pagos) salvos na aba '{aba_shopify}'")

    df_shopify = df_shopify.sort_values("data", ascending=False)

    # ===========================================================
    # ======================= ABAS ==============================
    # ===========================================================
    tab1, tab2, tab3, tab4, tab5 = st.tabs([
        "📋 Pedidos Pagos",
        "📦 Análises por Produto",
        "🏙️ Análises por Localização",
        "📈 Tendência por Variante",
        "⚖️ Comparar Variantes"
    ])

    # ======================= TAB 1 ==============================
with tab1:
    st.subheader("🧾 Pedidos Pagos da Shopify")

    colunas = [
        "data", "cliente", "Status", "produto", "variante",
        "itens", "forma_entrega", "estado", "cidade", "pagamento"
    ]

    # Inicializa o DataFrame do editor na sessão, se ainda não existir
    if "df_shopify_editor" not in st.session_state:
        st.session_state.df_shopify_editor = df_shopify[colunas].copy()

    st.info("👉 Você pode editar o campo **Status** diretamente na tabela abaixo.")
    
    df_editado = st.data_editor(
        st.session_state.df_shopify_editor,
        key="editor_pedidos",
        hide_index=True,
        column_config={
            "Status": st.column_config.SelectboxColumn(
                "Status",
                options=["Aguardando", "Em transporte", "Entregue", "Cancelado"],
                required=True
            ),
            "pagamento": st.column_config.TextColumn("Situação Pagamento", disabled=True),
            "data": st.column_config.DatetimeColumn("Data do Pedido", format="DD/MM/YYYY HH:mm")
        },
        disabled=["data", "cliente", "produto", "variante", "itens", "forma_entrega", "estado", "cidade", "pagamento"]
    )

    # Botão para salvar alterações
    if st.button("💾 Salvar alterações no Status"):
        st.session_state.df_shopify_editor["Status"] = df_editado["Status"]
        try:
            worksheet.clear()
            worksheet.update(df_para_lista(st.session_state.df_shopify_editor))
            st.success("✅ Status atualizado com sucesso no Google Sheets!")
        except Exception as e:
            st.error(f"❌ Erro ao salvar no Google Sheets: {e}")

# ======================= TAB: Comparar Variantes com 2 períodos ==============================
with tab5:
    st.subheader("⚖️ Comparar Variantes em 2 períodos")

    # Seleção de variantes
    variantes_disponiveis = st.session_state.df_shopify_editor["variante"].dropna().unique()
    var1 = st.selectbox("Variante 1:", variantes_disponiveis, key="var1_cmp")
    var2 = st.selectbox("Variante 2:", variantes_disponiveis, key="var2_cmp")

    # Seleção de períodos
    data_min_total = st.session_state.df_shopify_editor["data"].min().date()
    data_max_total = st.session_state.df_shopify_editor["data"].max().date()
    
    st.markdown("### Período 1")
    p1_inicio, p1_fim = st.date_input("Escolha o período 1:", [data_min_total, data_max_total], key="p1")
    
    st.markdown("### Período 2")
    p2_inicio, p2_fim = st.date_input("Escolha o período 2:", [data_min_total, data_max_total], key="p2")

    # Função para gerar gráfico de barras por variante e período
    def gerar_grafico(variante, inicio, fim):
        df_filtro = st.session_state.df_shopify_editor[
            (st.session_state.df_shopify_editor["variante"] == variante) &
            (st.session_state.df_shopify_editor["data"].dt.date >= inicio) &
            (st.session_state.df_shopify_editor["data"].dt.date <= fim)
        ]
        if df_filtro.empty:
            return None
        df_group = df_filtro.groupby(df_filtro["data"].dt.date)["itens"].sum().reset_index()
        df_group.columns = ["Data", "Qtd Pedidos"]
        df_group["Variante"] = variante
        fig = px.bar(
            df_group,
            x="Data",
            y="Qtd Pedidos",
            color="Variante",
            barmode="stack",
            text="Qtd Pedidos",
            color_discrete_sequence=px.colors.qualitative.Set3,
            title=f"{variante} de {inicio} a {fim}"
        )
        fig.update_layout(xaxis_tickformat="%d/%m/%Y")
        return fig, df_group

    # --- Gerar gráficos ---
    fig1, df1 = gerar_grafico(var1, p1_inicio, p1_fim) or (None, None)
    fig2, df2 = gerar_grafico(var2, p2_inicio, p2_fim) or (None, None)

    if fig1:
        st.plotly_chart(fig1, use_container_width=True)
    else:
        st.info(f"Nenhum pedido para {var1} no período 1.")

    if fig2:
        st.plotly_chart(fig2, use_container_width=True)
    else:
        st.info(f"Nenhum pedido para {var2} no período 2.")

    # --- Cards de resumo ---
    st.subheader("📌 Conclusões")
    col1, col2, col3, col4 = st.columns(4)

    total1 = df1["Qtd Pedidos"].sum() if df1 is not None else 0
    total2 = df2["Qtd Pedidos"].sum() if df2 is not None else 0

    media1 = df1["Qtd Pedidos"].mean() if df1 is not None else 0
    media2 = df2["Qtd Pedidos"].mean() if df2 is not None else 0

    max1 = df1["Qtd Pedidos"].max() if df1 is not None else 0
    max2 = df2["Qtd Pedidos"].max() if df2 is not None else 0

    col1.metric(f"{var1} - Total pedidos", total1)
    col2.metric(f"{var2} - Total pedidos", total2)
    col3.metric(f"{var1} - Média diária", f"{media1:.1f}")
    col4.metric(f"{var2} - Média diária", f"{media2:.1f}")

    st.markdown(f"✅ O período com mais pedidos foi **{var1 if total1 > total2 else var2}**")
    st.markdown(f"✅ Maior quantidade em um único dia: **{max(var1, var2)}**")



# ======================= TAB 3 ==============================
with tab3:
    st.subheader("🏙️ Pedidos por Localização")
    pedidos_estado = st.session_state.df_shopify_editor.groupby("estado")["itens"].sum().reset_index().sort_values("itens", ascending=False)
    pedidos_cidade = st.session_state.df_shopify_editor.groupby("cidade")["itens"].sum().reset_index().sort_values("itens", ascending=False)

    st.markdown("### 📍 Por Estado")
    st.dataframe(pedidos_estado)
    
    st.markdown("### 🏙️ Por Cidade")
    st.dataframe(pedidos_cidade)

# ======================= TAB 4 ==============================
with tab4:
    st.subheader("📈 Tendência de Pedidos por Variante")
    variantes_disponiveis = st.session_state.df_shopify_editor["variante"].dropna().unique()
    variante_sel = st.selectbox("Selecione a variante:", variantes_disponiveis)
    df_var = st.session_state.df_shopify_editor[st.session_state.df_shopify_editor["variante"] == variante_sel]
    df_trend = df_var.groupby(df_var["data"].dt.date)["itens"].sum().reset_index()
    df_trend.columns = ["Data", "Qtd Pedidos"]
    fig = px.line(df_trend, x="Data", y="Qtd Pedidos", markers=True, title=f"Tendência: {variante_sel}")
    st.plotly_chart(fig, use_container_width=True)

# ======================= TAB 5 ==============================
with tab5:
    st.subheader("⚖️ Comparar Variantes em 2 períodos")

    variantes_disponiveis = st.session_state.df_shopify_editor["variante"].dropna().unique()
    
    # Seleção de variantes
    var1 = st.selectbox("Variante Período 1:", variantes_disponiveis, key="var1_cmp")
    var2 = st.selectbox("Variante Período 2:", variantes_disponiveis, key="var2_cmp")

    data_min_total = st.session_state.df_shopify_editor["data"].min().date()
    data_max_total = st.session_state.df_shopify_editor["data"].max().date()

    # Seleção de datas
    p1_inicio, p1_fim = st.date_input("Período 1:", [data_min_total, data_max_total], key="p1_cmp")
    p2_inicio, p2_fim = st.date_input("Período 2:", [data_min_total, data_max_total], key="p2_cmp")

    def gerar_grafico(variante, inicio, fim, key):
        df_filtro = st.session_state.df_shopify_editor[
            (st.session_state.df_shopify_editor["variante"] == variante) &
            (st.session_state.df_shopify_editor["data"].dt.date >= inicio) &
            (st.session_state.df_shopify_editor["data"].dt.date <= fim)
        ]
        if df_filtro.empty:
            return None

        df_group = df_filtro.groupby(df_filtro["data"].dt.date)["itens"].sum().reset_index()
        df_group.columns = ["Data", "Qtd Pedidos"]
        df_group["Variante"] = variante

        fig = px.bar(
            df_group,
            x="Data",
            y="Qtd Pedidos",
            color="Variante",
            barmode="stack",
            text="Qtd Pedidos",
            color_discrete_sequence=px.colors.qualitative.Set3,
            title=f"{variante} de {inicio} a {fim}"
        )
        fig.update_layout(xaxis_tickformat="%d/%m/%Y")
        st.plotly_chart(fig, use_container_width=True, key=key)

    # Gerar gráficos com keys diferentes
    gerar_grafico(var1, p1_inicio, p1_fim, key="fig_cmp1")
    gerar_grafico(var2, p2_inicio, p2_fim, key="fig_cmp2")

    else:
        st.info(f"Nenhum pedido para {var2} no período 2.")
