# ------------------------------------------------------------------------------
# Refactor date: 2025-11-11
# Refactored by: Imaad Fakier
# Purpose: Align Discussion Generator micro-app with OES GenAI Streamlit standards.
# ------------------------------------------------------------------------------
"""
core_logic.data_storage (Refactored)
------------------------------------
Lightweight persistence layer for run logging.

This refactor introduces:
- `NullStorageHandler`: no-op fallback when neither GSheets nor SQL configured.
- Safer initialization to avoid crashes on missing env vars.
- Clean interface: get_runs_data() / post_runs_data(df)
"""

import os
import pandas as pd
import streamlit as st


# ------------------------------------------------------------------------------
# Storage Handlers
# ------------------------------------------------------------------------------
class NullStorageHandler:
    """
    A dummy handler used when no storage backend is configured.
    Keeps local app behavior consistent but avoids write errors.
    """

    def get_runs_data(self):
        st.info("⚠️ No storage backend configured. Returning empty DataFrame.")
        return pd.DataFrame()

    def post_runs_data(self, df):
        st.info("⚠️ No storage backend configured. Data not persisted.")
        return df


class GSheetsStorageHandler:
    """
    Placeholder for a Google Sheets implementation.
    If you later connect a proper GSheets client, implement here.
    """

    def __init__(self, sheet_url, worksheet="Sheet1"):
        self.sheet_url = sheet_url
        self.worksheet = worksheet

    def get_runs_data(self):
        try:
            # In a real impl, fetch via gspread or pygsheets
            return pd.DataFrame()
        except Exception as e:
            st.error(f"GSheets read failed: {e}")
            return pd.DataFrame()

    def post_runs_data(self, df):
        try:
            # Simulated write; replace with actual client call later
            st.success(f"✅ Would post {len(df)} rows to GSheets at {self.sheet_url}")
            return df
        except Exception as e:
            st.error(f"GSheets write failed: {e}")
            return df


# ------------------------------------------------------------------------------
# StorageManager façade
# ------------------------------------------------------------------------------
class StorageManager:
    """
    Singleton wrapper to provide a consistent storage instance
    regardless of which app calls it.
    """

    _storage = None

    @classmethod
    def initialize(cls, config):
        """
        Called once from core_logic.main.main() to set up storage backend.
        """
        gsheets_url = os.getenv("GSHEETS_URL") or config.get("GSHEETS_URL_OVERRIDE")
        sql_url = os.getenv("SQLALCHEMY_URL")

        # Default to NullStorage if no backend configured
        if not gsheets_url and not sql_url:
            cls._storage = NullStorageHandler()
            return

        # Prefer GSheets if configured
        if gsheets_url:
            worksheet = config.get("GSHEETS_WORKSHEET_OVERRIDE", "Sheet1")
            cls._storage = GSheetsStorageHandler(gsheets_url, worksheet)
            return

        # Future: SQLAlchemy handler stub
        cls._storage = NullStorageHandler()

    @classmethod
    def get_storage(cls):
        """
        Retrieve the current storage instance.
        """
        if cls._storage is None:
            cls._storage = NullStorageHandler()
        return cls._storage
