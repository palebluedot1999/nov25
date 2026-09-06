# dashboard/Home.py
import sys
import streamlit as st
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

st.set_page_config(page_title="Strategy Dashboard", layout="wide")
st.switch_page("pages/1_Dashboard.py")
