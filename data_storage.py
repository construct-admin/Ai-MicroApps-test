# ────────────────────────────────────────────────────────────────────────────────
# Refactor date: 2025-11-12
# 📗 OES GenAI Utility: Google Sheets CRUD Demo
# Author: OES GenAI Team | Maintained by: Imaad Fakier
# Purpose:
#   Demonstrates CRUD operations using Streamlit GSheetsConnection
#   with Service Account credentials for persistent storage.
#   Used internally for onboarding and prototype validation.
# ────────────────────────────────────────────────────────────────────────────────

import pandas as pd
import pandasql as psql
import streamlit as st
from streamlit_gsheets import GSheetsConnection

# ────────────────────────────────────────────────────────────────────────────────
# 🔤 Streamlit Page Config
# ────────────────────────────────────────────────────────────────────────────────
st.set_page_config(
    page_title="Google Sheets Data Storage",
    page_icon="🗗️",
    layout="centered",
)
st.title("🗗️ Google Sheets `st.connection` Demo (Service Account)")
st.caption(
    "Demonstrates CRUD + SQL-like querying for persistent data via Google Sheets."
)

# ────────────────────────────────────────────────────────────────────────────────
# 🧠 API Reference
# ────────────────────────────────────────────────────────────────────────────────
st.write("### 1. API Reference")
with st.echo():
    conn = st.connection("gsheets", type=GSheetsConnection)
    st.write(conn)
    st.help(conn)

# ────────────────────────────────────────────────────────────────────────────────
# 🧹 Setup Instructions
# ────────────────────────────────────────────────────────────────────────────────
docs_url = (
    "https://docs.streamlit.io/streamlit-community-cloud/get-started/"
    "deploy-an-app/connect-to-data-sources/secrets-management"
)
st.write("### 2. Initial Setup")
st.markdown(
    f"""
**Setup `.streamlit/secrets.toml`**

Follow the [Streamlit Secrets Management guide]({docs_url}) to configure your credentials.

1. Enable the Google Drive + Sheets APIs.
2. Create a Service Account and download its JSON key.
3. Share your target Sheet with the `client_email` from that key.
4. Add credentials to `.streamlit/secrets.toml` like this:

```toml
[connections.gsheets]
spreadsheet = "<spreadsheet-name-or-url>"
worksheet = "<worksheet-gid-or-folder-id>"
type = "service_account"
project_id = ""
private_key_id = ""
private_key = ""
client_email = ""
client_id = ""
auth_uri = ""
token_uri = ""
auth_provider_x509_cert_url = ""
client_x509_cert_url = ""
```
"""
)

# ────────────────────────────────────────────────────────────────────────────────
# 📤 Create Worksheet
# ────────────────────────────────────────────────────────────────────────────────
st.write("### 3. Create New Worksheet")
with st.echo():
    conn = st.connection("gsheets", type=GSheetsConnection)
    df = pd.DataFrame(
        {
            "name": ["Andy", "Alfred", "Ava"],
            "age": [35, 42, 55],
            "city": ["New York", "London", "Paris"],
        }
    )

    if st.button("Create new worksheet"):
        df = conn.create(worksheet="Example 1", data=df)
        st.cache_data.clear()
        st.rerun()

    st.dataframe(df.head(10))

# ────────────────────────────────────────────────────────────────────────────────
# 📥 Read Worksheet
# ────────────────────────────────────────────────────────────────────────────────
st.write("### 4. Read Worksheet as DataFrame")
st.info("If the sheet was deleted, press 'Create new worksheet' again.")
with st.echo():
    conn = st.connection("gsheets", type=GSheetsConnection)
    df = conn.read(worksheet="Example 1", usecols=[0, 1])
    st.dataframe(df)


# ────────────────────────────────────────────────────────────────────────────────
# ✏️ Update Worksheet
# ────────────────────────────────────────────────────────────────────────────────
st.write("### 5. Update Worksheet with New Data")
with st.echo():
    conn = st.connection("gsheets", type=GSheetsConnection)
    df = pd.DataFrame(
        {
            "name": ["Bill", "Bob", "Bonny"],
            "age": [35, 42, 55],
            "city": ["New York", "London", "Paris"],
        }
    )

    if st.button("Update worksheet"):
        df = conn.update(worksheet="Example 1", data=df)
        st.cache_data.clear()
        st.rerun()

    st.dataframe(df.head(10))

# ────────────────────────────────────────────────────────────────────────────────
# 🧮 Query Worksheet with SQL
# ────────────────────────────────────────────────────────────────────────────────
st.write("### 6. Query Google Sheet with SQL (DuckDB Dialect)")
st.info("Mutation queries are in-memory only and do not persist.")
with st.echo():
    conn = st.connection("gsheets", type=GSheetsConnection)
    sql = 'SELECT * FROM "Example 1"'
    df = conn.query(sql=sql, ttl=3600)
    st.dataframe(df.head(10))

# ────────────────────────────────────────────────────────────────────────────────
# 🧹 Clear / Delete Worksheet
# ────────────────────────────────────────────────────────────────────────────────
st.write("### 7. Clear or Delete Worksheet")
with st.echo():
    conn = st.connection("gsheets", type=GSheetsConnection)

    if st.button("Clear worksheet"):
        conn.clear(worksheet="Example 1")
        st.info("Worksheet cleared.")
        st.cache_data.clear()
        st.rerun()

    if st.button("Delete worksheet"):
        spreadsheet = conn.client._open_spreadsheet()  # type: ignore
        worksheet = spreadsheet.worksheet("Example 1")
        spreadsheet.del_worksheet(worksheet)
        st.cache_data.clear()
        st.rerun()
