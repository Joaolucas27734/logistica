import streamlit as st
import pandas as pd
from datetime import datetime

# -------------------------------
# Função para carregar dados da Shopify
# -------------------------------
def carregar_dados_shopify():
    try:
        import requests

        # Substitua pelos seus dados da API
        url = "https://sualoja.myshopify.com/admin/api/2023-07/orders.json?status=any&limit=250"
        headers = {
            "Content-Type": "application/json",
            "X-Shopify-Access-Token": "SEU_TOKEN_AQUI"
        }

        resposta = requests.get(url, headers=headers)
        pedidos = resposta.json().get("orders", [])

        # 👇 Mostra os dados brutos pra ver a estrutura real
        st.write("📦 Exemplo de dados brutos da Shopify:", pedidos[:2])

        if not pedidos:
            st.warning("Nenhum pedido encontrado na Shopify.")
            return pd.DataFrame()

        # Normaliza os dados com segurança
        df = pd.json_normalize(
            pedidos,
            record_path=["line_items"],
            meta=[
                "id",
                "created_at",
                "financial_status",
                "fulfillment_status",
                "customer.first_name",
                "customer.last_name",
                "shipping_lines",
            ],
            errors="ignore"
        )

        # -------------------------------
        # Ajusta e renomeia colunas principais
        # -------------------------------
        df["data"] = pd.to_datetime(df["created_at"], errors="coerce")
        df["cliente"] = df["customer.first_name"].fillna('') + " " + df["customer.last_name"].fillna('')
        df["produto"] = df["title"]
        df["variante"] = df.get("variant_title", "")
        df["itens"] = df.get("quantity", 1)
        df["status"] = df["financial_status"].fillna("Desconhecido")

        # Forma de entrega
        df["forma_entrega"] = df["shipping_lines"].apply(
            lambda x: x[0]["title"] if isinstance(x, list) and len(x) > 0 and "title" in x[0] else "Não informado"
        )

        # Seleciona apenas as colunas pedidas
        df = df[["data", "cliente", "status", "produto", "variante", "itens", "forma_entrega"]]

        return df

    except Exception as e:
        st.error(f"Erro ao carregar dados da Shopify: {e}")
        return pd.DataFrame()

# -------------------------------
# Exemplo de uso no app principal
# -------------------------------
st.title("📦 Dashboard de Logística - Shopify")

df_shopify = carregar_dados_shopify()

if not df_shopify.empty:
    # 🔹 Filtro por data
    data_inicio = st.date_input("Data inicial")
    data_fim = st.date_input("Data final")

    # Converte colunas de data e aplica filtro com segurança
    df_shopify["data"] = pd.to_datetime(df_shopify["data"], errors="coerce")
    data_inicio_dt = pd.to_datetime(data_inicio)
    data_fim_dt = pd.to_datetime(data_fim)

    df_filtrado = df_shopify[
        (df_shopify["data"] >= data_inicio_dt) &
        (df_shopify["data"] <= data_fim_dt)
    ]

    st.write("📊 Pedidos filtrados:", df_filtrado)

    # Agrupa por produto
    st.subheader("📦 Quantidade de pedidos por produto")
    agrupado = df_filtrado.groupby("produto")["itens"].sum().reset_index()
    st.dataframe(agrupado)
else:
    st.info("Nenhum dado para exibir ainda.")
