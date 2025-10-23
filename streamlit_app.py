
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

        # Verifica se há próxima página
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
                "pagamento": pedido.get("financial_status", "desconhecido"),
                "order_id": pedido.get("id")  # <-- ESSENCIAL para envio automático à Shopify
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

    # --- Colunas desejadas ---
    colunas = [
        "data", "cliente", "Status", "produto", "variante",
        "itens", "ID", "Codigo de rastreio", "Situacao",
        "forma_entrega", "estado", "cidade", "pagamento"
    ]

    # --- Garante que as colunas extras existam ---
    for col in ["ID", "Codigo de rastreio", "Situacao"]:
        if col not in df_shopify.columns:
            df_shopify[col] = ""

    # --- Inicializa o editor na sessão ---
    if "df_shopify_editor" not in st.session_state:
        st.session_state.df_shopify_editor = df_shopify[colunas].copy()

    st.info("👉 Você pode editar os campos **Status**, **Código de rastreio** e **Situação** diretamente na tabela abaixo.")

    # --- Editor interativo ---
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
            "Codigo de rastreio": st.column_config.TextColumn(
                "Código de Rastreio",
                help="Cole ou digite o código de rastreamento do pedido"
            ),
            "Situacao": st.column_config.SelectboxColumn(
                "Situação",
                options=["Aguardando envio", "Enviado", "Entregue", "Reenviado", "Problema"],
                help="Situação logística atual do pedido"
            ),
            "pagamento": st.column_config.TextColumn("Situação Pagamento", disabled=True),
            "data": st.column_config.DatetimeColumn("Data do Pedido", format="DD/MM/YYYY HH:mm"),
            "ID": st.column_config.TextColumn("ID do Pedido", disabled=True),
        },
        disabled=[
            "data", "cliente", "produto", "variante", "itens",
            "forma_entrega", "estado", "cidade", "pagamento", "ID"
        ]
    )
# --- Botão para salvar ---
if st.button("💾 Salvar alterações"):
    # Atualiza session_state com os valores editados
    st.session_state.df_shopify_editor["Status"] = df_editado["Status"]
    st.session_state.df_shopify_editor["Codigo de rastreio"] = df_editado["Codigo de rastreio"]
    st.session_state.df_shopify_editor["Situacao"] = df_editado["Situacao"]

    # Salva no Google Sheets
    try:
        worksheet.clear()
        worksheet.update(df_para_lista(st.session_state.df_shopify_editor))
        st.success("✅ Alterações salvas com sucesso no Google Sheets!")
    except Exception as e:
        st.error(f"❌ Erro ao salvar no Google Sheets: {e}")

    # --- Função para enviar códigos de rastreio para Shopify ---
    def enviar_codigos_shopify(df):
        SHOP_NAME = st.secrets["shopify"]["shop_name"]
        ACCESS_TOKEN = st.secrets["shopify"]["access_token"]
        url_base = f"https://{SHOP_NAME}/admin/api/2023-10"
        headers = {
            "Content-Type": "application/json",
            "X-Shopify-Access-Token": ACCESS_TOKEN
        }

        novos_codigos = df[df["Codigo de rastreio"].notna() & (df["Codigo de rastreio"] != "")]
        if novos_codigos.empty:
            st.info("Nenhum código de rastreio novo para enviar à Shopify.")
        else:
            for _, row in novos_codigos.iterrows():
                order_id = str(row["ID"]).strip()
                tracking_code = str(row["Codigo de rastreio"]).strip()
                if not order_id or not tracking_code:
                    continue

                fulfillment_data = {
                    "fulfillment": {
                        "tracking_number": tracking_code,
                        "notify_customer": True
                    }
                }

                try:
                    response = requests.post(
                        f"{url_base}/orders/{order_id}/fulfillments.json",
                        headers=headers,
                        json=fulfillment_data
                    )

                    if response.status_code in [200, 201]:
                        st.success(f"📦 Código {tracking_code} enviado com sucesso para o pedido #{order_id}.")
                    else:
                        st.warning(f"⚠️ Erro ao atualizar pedido #{order_id}: {response.text}")
                except Exception as e:
                    st.error(f"❌ Falha ao enviar código para pedido #{order_id}: {e}")

    # --- Chama a função para envio automático ---
    enviar_codigos_shopify(st.session_state.df_shopify_editor)




# ======================= TAB 2 ==============================
with tab2:
    st.subheader("📊 Comparação de Variantes por Produto (Totais por Período)")

    st.markdown("""
    💡 **Como usar:**  
    Selecione um produto, as variantes e dois períodos para comparar.  
    Você verá o total de pedidos de cada variante empilhados por período, junto com insights automáticos de desempenho.  
    """)

    # --- Seleção do produto ---
    produtos_disponiveis = st.session_state.df_shopify_editor["produto"].dropna().unique()
    produto_sel = st.selectbox("🧴 Selecione o produto:", produtos_disponiveis)

    # --- Seleção das variantes ---
    variantes_disponiveis = st.session_state.df_shopify_editor[
        st.session_state.df_shopify_editor["produto"] == produto_sel
    ]["variante"].dropna().unique()

    variantes_sel = st.multiselect(
        "🎨 Selecione as variantes para comparar:",
        variantes_disponiveis,
        default=list(variantes_disponiveis[:2])
    )

    if len(variantes_sel) < 2:
        st.warning("⚠️ Selecione pelo menos 2 variantes para comparar.")
        st.stop()

    # --- Seleção dos dois períodos ---
    df_produto_total = st.session_state.df_shopify_editor[
        st.session_state.df_shopify_editor["produto"] == produto_sel
    ]
    data_min, data_max = df_produto_total["data"].min().date(), df_produto_total["data"].max().date()

    col1, col2 = st.columns(2)
    with col1:
        st.markdown("#### 📅 Período 1")
        data_inicio1, data_fim1 = st.date_input("Selecione o intervalo:", [data_min, data_max], key="total_periodo1")
    with col2:
        st.markdown("#### 📅 Período 2")
        data_inicio2, data_fim2 = st.date_input("Selecione o intervalo:", [data_min, data_max], key="total_periodo2")

    # --- Filtrar DataFrames ---
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
        st.stop()

    # --- Agrupar total por variante ---
    def agrupar_totais(df, label):
        df_group = df.groupby("variante")["itens"].sum().reset_index()
        df_group["%_Total"] = (df_group["itens"] / df_group["itens"].sum() * 100).round(2)
        df_group = df_group.rename(columns={"itens": f"Pedidos ({label})", "%_Total": f"% ({label})"})
        return df_group

    df_total1 = agrupar_totais(df_periodo1, "Período 1")
    df_total2 = agrupar_totais(df_periodo2, "Período 2")

    # --- Combinar tabelas para comparação ---
    df_comparacao = pd.merge(df_total1, df_total2, on="variante", how="outer").fillna(0)

    # --- Exibir métricas principais ---
    total_p1 = df_periodo1["itens"].sum()
    total_p2 = df_periodo2["itens"].sum()
    dif_total = total_p2 - total_p1
    var_pct = (dif_total / total_p1 * 100) if total_p1 > 0 else 0

    col1, col2, col3 = st.columns(3)
    col1.metric("Total Período 1", total_p1)
    col2.metric("Total Período 2", total_p2, delta=f"{dif_total:+}")
    col3.metric("Variação (%)", f"{var_pct:+.2f}%")

    # --- Tabela de comparação ---
    st.markdown("### 📊 Tabela Comparativa por Variante")
    st.dataframe(df_comparacao.sort_values(f"Pedidos (Período 1)", ascending=False))

    # --- Gráfico empilhado ---
    st.markdown("### 📈 Comparativo Visual de Variantes")
    df_grafico = pd.concat([
        df_periodo1.assign(Período=f"Período 1 ({data_inicio1} a {data_fim1})"),
        df_periodo2.assign(Período=f"Período 2 ({data_inicio2} a {data_fim2})")
    ])
    df_grafico = df_grafico.groupby(["Período", "variante"])["itens"].sum().reset_index()

    fig = px.bar(
        df_grafico,
        x="Período",
        y="itens",
        color="variante",
        barmode="stack",
        text="itens",
        color_discrete_sequence=px.colors.qualitative.Vivid,
        labels={"itens": "Pedidos", "variante": "Variante"},
        title=f"Distribuição de pedidos por variante – {produto_sel}"
    )

    # Adicionar total no topo das barras
    totais = df_grafico.groupby("Período")["itens"].sum().reset_index()
    for idx, row in totais.iterrows():
        fig.add_annotation(
            x=row["Período"],
            y=row["itens"] + 0.5,
            text=f"Total: {int(row['itens'])}",
            showarrow=False,
            font=dict(size=13, color="black", weight="bold")
        )

    fig.update_traces(textposition='inside')
    fig.update_layout(
        plot_bgcolor="rgba(0,0,0,0)",
        yaxis_title="Total de Pedidos",
        xaxis_title=None,
        legend_title_text="Variante",
    )

    st.plotly_chart(fig, use_container_width=True)

    # --- Insights ---
    st.markdown("### 🧠 Insights Automáticos")
    for label, df_p in zip(
        [f"Período 1 ({data_inicio1} a {data_fim1})", f"Período 2 ({data_inicio2} a {data_fim2})"],
        [df_periodo1, df_periodo2]
    ):
        total_pedidos = df_p["itens"].sum()
        if total_pedidos > 0:
            top_var = df_p.groupby("variante")["itens"].sum().idxmax()
            qtd_top = df_p.groupby("variante")["itens"].sum().max()
            pct_top = qtd_top / total_pedidos * 100
            st.write(
                f"📦 **{label}**: Total de {total_pedidos} pedidos. "
                f"Variante mais vendida: **{top_var}** com **{qtd_top} pedidos ({pct_top:.2f}%)**."
            )

    # --- Insight de tendência ---
    if total_p1 > 0:
        if var_pct > 0:
            st.success(f"📈 Crescimento de **{var_pct:.2f}%** no total de pedidos entre os períodos.")
        elif var_pct < 0:
            st.warning(f"📉 Queda de **{abs(var_pct):.2f}%** no total de pedidos entre os períodos.")
        else:
            st.info("⚖️ Nenhuma variação significativa entre os períodos.")

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
    st.subheader("⚖️ Comparar Variantes por Pontos/Datas")
    
    variantes_disponiveis = df_shopify["variante"].dropna().unique()
    num_comparacoes = st.number_input("Quantas comparações deseja?", min_value=1, max_value=5, value=2)

    df_todas = pd.DataFrame()

    for i in range(num_comparacoes):
        st.markdown(f"### Comparação {i+1}")
        var_sel = st.selectbox(f"Selecione a variante {i+1}:", variantes_disponiveis, key=f"var{i}")

        # Definir período mínimo e máximo da variante selecionada
        df_var_total = df_shopify[df_shopify["variante"] == var_sel]
        data_min, data_max = df_var_total["data"].min().date(), df_var_total["data"].max().date()
        data_inicio, data_fim = st.date_input(f"Período para {var_sel}:", [data_min, data_max], key=f"date{i}")

        # Filtrar dados pelo período selecionado
        df_var = df_var_total[
            (df_var_total["data"].dt.date >= data_inicio) &
            (df_var_total["data"].dt.date <= data_fim)
        ]

        # Agrupar por dia e criar coluna de ponto
        df_var = df_var.groupby(df_var["data"].dt.date)["itens"].sum().reset_index()
        df_var["variante"] = f"{var_sel} (Comp {i+1})"
        df_var["Ponto"] = range(1, len(df_var) + 1)  # eixo X: ponto 1, 2, 3...

        df_todas = pd.concat([df_todas, df_var], ignore_index=True)

    if not df_todas.empty:
        fig = px.line(
            df_todas,
            x="Ponto",
            y="itens",
            color="variante",
            markers=True,
            hover_data={"data": True, "itens": True, "Ponto": True}
        )
        fig.update_layout(
            xaxis_title="Ponto (comparativo)",
            yaxis_title="Quantidade de Pedidos",
            legend_title="Variante (Comparativo)"
        )
        st.plotly_chart(fig, use_container_width=True)

        # --- Cards com Insights ---
        st.markdown("### 📊 Insights das Comparações")
        colunas_cards = st.columns(num_comparacoes)
        for i in range(num_comparacoes):
            df_comp = df_todas[df_todas["variante"].str.endswith(f"(Comp {i+1})")]
            total_itens = df_comp["itens"].sum()
            media_itens = df_comp["itens"].mean() if len(df_comp) > 0 else 0
            max_itens = df_comp["itens"].max() if len(df_comp) > 0 else 0
            colunas_cards[i].metric(f"Variante {i+1}", f"{total_itens} itens", f"Média: {media_itens:.1f}, Máx: {max_itens}")

    else:
        st.info("Nenhuma comparação disponível para os períodos selecionados.")
