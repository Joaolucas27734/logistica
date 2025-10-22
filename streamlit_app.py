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
st.set_page_config(
    page_title="Dashboard Interativo de Entregas + Estoque",
    layout="wide"
)
st.title("📦 Dashboard Interativo – Entregas & Estoque")
st.markdown(
    "Bem-vindo! Aqui você pode analisar **estoque**, **logística** e **comparar variantes de pedidos** de forma dinâmica."
)

# --- Configurar Google Sheets ---
SCOPE = ["https://www.googleapis.com/auth/spreadsheets"]
creds_dict = json.loads(st.secrets["gcp_service_account"]["json"])
CREDS = Credentials.from_service_account_info(creds_dict, scopes=SCOPE)
GSHEET_CLIENT = gspread.authorize(CREDS)
SHEET_ID = "1dYVZjzCtDBaJ6QdM81WP2k51QodDGZHzKEhzKHSp7v8"

# ===========================================================
# =================== FUNÇÕES AUXILIARES ====================
# ===========================================================
def salvar_status_no_gsheet(df):
    """Salva automaticamente a coluna Status na planilha Google Sheets"""
    try:
        sheet = GSHEET_CLIENT.open_by_key(SHEET_ID).worksheet("Pedidos")
        col_idx = sheet.find("Status").col
        for i, status in enumerate(df["Status"], start=2):
            sheet.update_cell(i, col_idx, status)
    except Exception as e:
        st.error(f"Erro ao salvar no Google Sheets: {e}")

def df_para_lista(df):
    """Converte DataFrame em lista de listas para enviar ao Google Sheets"""
    return [df.columns.tolist()] + df.astype(str).values.tolist()

# ===========================================================
# ====================== DADOS BASE ========================
# ===========================================================
url = f"https://docs.google.com/spreadsheets/d/{SHEET_ID}/export?format=csv&sheet=Pedidos"
df = pd.read_csv(url)

# Processar datas
df["data_envio"] = pd.to_datetime(df.iloc[:, 1], errors="coerce")
df["data_entrega"] = pd.to_datetime(df.iloc[:, 2], errors="coerce")
df["dias_entrega"] = (df["data_entrega"] - df["data_envio"]).dt.days

# Estado e cidade
df["estado"] = df.iloc[:, 3].str.upper()
df["cidade"] = df.iloc[:, 4].astype(str).str.title()

# Status de entrega
df["Status"] = df["data_entrega"].apply(lambda x: "Entregue" if pd.notna(x) else "Não entregue")

# Código rastreio e link
df["Código Rastreio"] = df.iloc[:, 5].astype(str)
df["Link J&T"] = "https://www2.jtexpress.com.br/rastreio/track?codigo=" + df["Código Rastreio"]

# ===========================================================
# ==================== BARRA LATERAL ========================
# ===========================================================
st.sidebar.subheader("📅 Filtrar por Data de Envio")
data_min = df["data_envio"].min()
data_max = df["data_envio"].max()
data_inicio, data_fim = st.sidebar.date_input(
    "Selecione o período:", [data_min, data_max],
    help="Escolha o período que deseja analisar os pedidos"
)

st.sidebar.markdown("---")
opcao = st.sidebar.radio(
    "📋 Selecione o módulo:",
    ["📦 Estoque", "🚚 Logística Geral"],
    help="Escolha entre visualizar o estoque ou os pedidos/logística"
)

# ===========================================================
# ==================== MÓDULO: ESTOQUE =====================
# ===========================================================
if opcao == "📦 Estoque":
    st.subheader("📊 Principais Métricas de Entregas")
    
    df_filtrado = df[
        (df["data_envio"] >= pd.to_datetime(data_inicio)) &
        (df["data_envio"] <= pd.to_datetime(data_fim))
    ]
    
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

    # Mapa de entregas
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

    # Controle de estoque
    st.subheader("📦 Controle de Estoque Interno")
    url_estoque = f"https://docs.google.com/spreadsheets/d/{SHEET_ID}/gviz/tq?tqx=out:csv&sheet=Estoque"
    try:
        df_estoque = pd.read_csv(url_estoque)
        df_estoque.columns = ["Produto", "Quantidade", "Estoque Mínimo", "Ja Gasto"]
    except:
        df_estoque = pd.DataFrame(columns=["Produto", "Quantidade", "Estoque Mínimo", "Ja Gasto"])
    
    df_estoque["Quantidade_Atual"] = (df_estoque["Quantidade"] - df_estoque["Ja Gasto"]).clip(lower=0)
    df_estoque["Pacotes (20 peças)"] = df_estoque["Quantidade_Atual"].apply(lambda x: math.floor(x / 20))

    st.session_state.df_estoque_atual = df_estoque.copy()
    st.subheader("📝 Estoque Atual")
    st.dataframe(df_estoque[["Produto", "Quantidade", "Ja Gasto", "Quantidade_Atual", "Pacotes (20 peças)", "Estoque Mínimo"]])

# ===========================================================
# ================ MÓDULO: LOGÍSTICA GERAL ==================
# ===========================================================
elif opcao == "🚚 Logística Geral":
    st.subheader("🚚 Logística Geral – Pedidos Shopify")
    st.markdown(
        "💡 Este módulo permite visualizar, analisar e comparar os pedidos pagos da Shopify. "
        "Você pode editar o status, comparar variantes por períodos ou visualizar tendências."
    )

    sheet_id = SHEET_ID
    sh = GSHEET_CLIENT.open_by_key(sheet_id)
    aba_shopify = "Pedidos Shopify"

    # --- Garantir existência da aba ---
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

            # Paginação dinâmica
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

        # Processamento dinâmico dos itens
        linhas = []
        for pedido in pedidos_total:
            if pedido.get("financial_status") not in ["paid", "partially_paid"]:
                continue
            for item in pedido.get("line_items", []):
                linha = {
                    "data": pedido.get("created_at"),
                    "cliente": (pedido.get("customer") or {}).get("first_name", "") + " " +
                               (pedido.get("customer") or {}).get("last_name", ""),
                    "Status": pedido.get("fulfillment_status") or "Aguardando",
                    "produto": item.get("title"),
                    "variante": item.get("variant_title"),
                    "itens": item.get("quantity"),
                    "forma_entrega": (pedido.get("shipping_lines")[0]["title"] if pedido.get("shipping_lines") else "N/A"),
                    "estado": (pedido.get("shipping_address") or {}).get("province", "N/A"),
                    "cidade": (pedido.get("shipping_address") or {}).get("city", "N/A"),
                    "pagamento": pedido.get("financial_status", "desconhecido")
                }
                linhas.append(linha)

        df = pd.DataFrame(linhas)
        df["data"] = pd.to_datetime(df["data"], errors="coerce")
        return df

    # --- Carregar e atualizar dados ---
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
        st.info("👉 Edite o campo **Status** diretamente na tabela abaixo para atualizar no Google Sheets.")

        colunas = ["data", "cliente", "Status", "produto", "variante", "itens", "forma_entrega", "estado", "cidade", "pagamento"]

        if "df_shopify_editor" not in st.session_state:
            st.session_state.df_shopify_editor = df_shopify[colunas].copy()

        df_editado = st.data_editor(
            st.session_state.df_shopify_editor,
            key="editor_pedidos",
            hide_index=True,
            column_config={
                "Status": st.column_config.SelectboxColumn(
                    "Status", options=["Aguardando", "Em transporte", "Entregue", "Cancelado"], required=True
                ),
                "pagamento": st.column_config.TextColumn("Situação Pagamento", disabled=True),
                "data": st.column_config.DatetimeColumn("Data do Pedido", format="DD/MM/YYYY HH:mm")
            },
            disabled=["data", "cliente", "produto", "variante", "itens", "forma_entrega", "estado", "cidade", "pagamento"]
        )

        if st.button("💾 Salvar alterações no Status"):
            st.session_state.df_shopify_editor["Status"] = df_editado["Status"]
            try:
                worksheet.clear()
                worksheet.update(df_para_lista(st.session_state.df_shopify_editor))
                st.success("✅ Status atualizado com sucesso no Google Sheets!")
            except Exception as e:
                st.error(f"❌ Erro ao salvar no Google Sheets: {e}")

    # ======================= TAB 2 ==============================
    with tab2:
        st.subheader("📊 Comparação de Variantes por Produto")
        st.markdown(
            "💡 Selecione o produto, as variantes e dois períodos para comparar. "
            "O gráfico empilhado mostra a evolução das vendas por variante."
        )

        produtos_disponiveis = st.session_state.df_shopify_editor["produto"].dropna().unique()
        produto_sel = st.selectbox("Produto:", produtos_disponiveis)

        variantes_disponiveis = st.session_state.df_shopify_editor[
            st.session_state.df_shopify_editor["produto"] == produto_sel
        ]["variante"].dropna().unique()
        variantes_sel = st.multiselect(
            "Variantes:", variantes_disponiveis, default=list(variantes_disponiveis[:2])
        )
        if len(variantes_sel) < 2:
            st.warning("Selecione pelo menos 2 variantes para comparar.")
            st.stop()

        df_produto_total = st.session_state.df_shopify_editor[
            st.session_state.df_shopify_editor["produto"] == produto_sel
        ]
        data_min, data_max = df_produto_total["data"].min().date(), df_produto_total["data"].max().date()

        st.markdown("### Período 1")
        data_inicio1, data_fim1 = st.date_input("De/Até:", [data_min, data_max], key="total_periodo1")
        st.markdown("### Período 2")
        data_inicio2, data_fim2 = st.date_input("De/Até:", [data_min, data_max], key="total_periodo2")

        df_periodo1 = df_produto_total[
            (df_produto_total["variante"].isin(variantes_sel)) &
            (df_produto_total["data"].dt.date >= data_inicio1) &
            (df_produto_total["data"].dt.date <= data_fim1)
        ]
        df_periodo2 = df_produto_total[
            (df_produto_total["variante"].isin(variantes_sel)) &
            (df_produto_total["data"].dt.date >= data_inicio2) &
            (df_produto_total["data"].dt.date <= data_fim2)
        ]

        if df_periodo1.empty and df_periodo2.empty:
            st.info("Nenhum pedido disponível para os períodos selecionados e variantes escolhidas.")
        else:
            def agrupar_totais(df, label):
                df_group = df.groupby("variante")["itens"].sum().reset_index()
                df_group["%_Total"] = (df_group["itens"] / df_group["itens"].sum() * 100).round(2)
                return df_group.rename(columns={"itens": f"Pedidos ({label})", "%_Total": f"% ({label})"})

            df_total1 = agrupar_totais(df_periodo1, "Período 1")
            df_total2 = agrupar_totais(df_periodo2, "Período 2")
            df_comparacao = pd.merge(df_total1, df_total2, on="variante", how="outer").fillna(0)
            st.dataframe(df_comparacao.sort_values(f"Pedidos (Período 1)", ascending=False))

            # Gráfico empilhado
            df_grafico = pd.concat([
                df_periodo1.assign(Período=f"Período 1 ({data_inicio1} a {data_fim1})"),
                df_periodo2.assign(Período=f"Período 2 ({data_inicio2} a {data_fim2})")
            ])
            df_grafico = df_grafico.groupby(["Período", "variante"])["itens"].sum().reset_index()
            fig = px.bar(df_grafico, x="Período", y="itens", color="variante", barmode="stack",
                         text="itens", labels={"itens": "Pedidos", "variante": "Variante"})
            st.plotly_chart(fig, use_container_width=True)

            # Insights
            st.markdown("### 📝 Insights")
            for label, df_p in zip([f"Período 1", f"Período 2"], [df_periodo1, df_periodo2]):
                total_pedidos = df_p["itens"].sum()
                if total_pedidos > 0:
                    top_var = df_p.groupby("variante")["itens"].sum().idxmax()
                    qtd_top = df_p.groupby("variante")["itens"].sum().max()
                    pct_top = qtd_top / total_pedidos * 100
                    st.write(f"- {label}: Total de pedidos: **{total_pedidos}**, Variante mais vendida: **{top_var} ({qtd_top} pedidos, {pct_top:.2f}%)**")

