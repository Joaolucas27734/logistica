import streamlit as st
import streamlit_authenticator as stauth
import yaml
from yaml.loader import SafeLoader

st.set_page_config(page_title="Dashboard Protegido", layout="wide")

# --- Carregar usuários e permissões do YAML
with open('users.yaml') as file:
    config = yaml.load(file, Loader=SafeLoader)

authenticator = stauth.Authenticate(
    config['credentials'],
    config['cookie']['name'],
    config['cookie']['key'],
    config['cookie']['expiry_days']
)

# --- Tela de login (corrigido com location="main")
name, authentication_status, username = authenticator.login("Login", location="main")

if authentication_status:
    st.sidebar.success(f"Bem-vindo, {name} 👋")
    role = config['credentials']['usernames'][username]['role']

    # --- Controle por nível de acesso
    if role == "admin":
        st.title("📊 Dashboard Administrativo")
        st.write("Aqui o admin vê tudo.")
    elif role == "logistica":
        st.title("🚚 Dashboard de Logística")
        st.write("Aqui aparecem apenas os dados da logística.")
    elif role == "suporte":
        st.title("💬 Painel de Suporte")
        st.write("Aqui ficam as solicitações de clientes.")
    else:
        st.warning("Nível de acesso não reconhecido.")

elif authentication_status == False:
    st.error("Usuário ou senha incorretos.")
elif authentication_status == None:
    st.warning("Por favor, insira suas credenciais.")
