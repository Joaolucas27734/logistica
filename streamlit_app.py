elif opcao == "🚚 Logística Geral":
    st.subheader("🚚 Logística Geral – Pedidos Shopify")

    import requests
    import pandas as pd
    import plotly.express as px

    # --- Função para carregar até 1000 pedidos pagos da Shopify com paginação ---
    def carregar_dados_shopify():
        SHOP_NAME = st.secrets["shopify"]["shop_name"]
        ACCESS_TOKEN = st.secrets["shopify"]["access_token"]

        # 🔹 Filtro para pegar só pedidos pagos (financial_status=paid)
        url_base = f"https://{SHOP_NAME}/admin/api/2023-10/orders.json?status=any&financial_status=paid&limit=250"
        headers = {"X-Shopify-Access-Token": ACCESS_TOKEN}

        pedidos_total = []
        url = url_base
        contador = 0

        while url and contador < 4:  # 4 * 250 = 1000 pedidos
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

    # --- Pedidos por Estado ---
    st.subheader("📊 Pedidos por Estado")
    pedidos_estado = df_shopify.groupby("estado")["itens"].sum().reset_index()
    pedidos_estado = pedidos_estado.rename(columns={"itens": "Qtd Pedidos"})
    pedidos_estado = pedidos_estado.sort_values("Qtd Pedidos", ascending=False)
    st.dataframe(pedidos_estado)

    # --- Tendência de crescimento de uma variante ---
    st.subheader("📈 Tendência de Crescimento de uma Variante")

    variantes_disponiveis = df_shopify["variante"].dropna().unique()
    variante_sel = st.selectbox("Selecione a variante:", variantes_disponiveis)

    df_variante = df_shopify[df_shopify["variante"] == variante_sel]
    df_tendencia = df_variante.groupby(df_variante["data"].dt.date)["itens"].sum().reset_index()
    df_tendencia = df_tendencia.rename(columns={"data": "Data", "itens": "Qtd Pedidos"})

    fig_tendencia = px.line(
        df_tendencia,
        x="Data",
        y="Qtd Pedidos",
        title=f"Tendência de Pedidos da Variante: {variante_sel}",
        markers=True
    )
    st.plotly_chart(fig_tendencia, use_container_width=True)

    # --- Comparar variantes ---
    st.subheader("📈 Comparar Quantidade de Pedidos por Variante (mesmo eixo X para datas)")

    variantes_disponiveis = df_shopify["variante"].dropna().unique()
    num_comparacoes = st.number_input("Quantas comparações deseja?", min_value=1, max_value=5, value=2)

    df_todas = pd.DataFrame()

    for i in range(num_comparacoes):
        st.markdown(f"### Comparação {i+1}")
        var_sel = st.selectbox(f"Selecione a variante para comparação {i+1}:", variantes_disponiveis, key=f"var{i}")
        
        data_min = df_shopify["data"].min().date()
        data_max = df_shopify["data"].max().date()
        data_inicio, data_fim = st.date_input(f"Selecione período para {var_sel}:", [data_min, data_max], key=f"date{i}")
        
        df_var = df_shopify[
            (df_shopify["variante"] == var_sel) &
            (df_shopify["data"].dt.date >= data_inicio) &
            (df_shopify["data"].dt.date <= data_fim)
        ]
        
        df_var = df_var.groupby(df_var["data"].dt.date)["itens"].sum().reset_index()
        df_var["variante"] = f"{var_sel} (Comp {i+1})"
        df_var = df_var.rename(columns={"data": "Data", "itens": "Qtd Pedidos"})
        df_var = df_var.sort_values("Data").reset_index(drop=True)
        df_var["x_ord"] = range(1, len(df_var)+1)
        
        df_todas = pd.concat([df_todas, df_var])

    if not df_todas.empty:
        fig = px.line(
            df_todas,
            x="x_ord",
            y="Qtd Pedidos",
            color="variante",
            markers=True,
            hover_data=["Data"]
        )
        fig.update_layout(
            xaxis_title="Dia do Período (comparação sequencial)",
            yaxis_title="Quantidade de Pedidos"
        )
        st.plotly_chart(fig, use_container_width=True)
    else:
        st.info("Nenhuma comparação foi selecionada ou não há dados para o período.")
