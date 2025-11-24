"""
Tracking Error page.
"""

import streamlit as st
import sys
from pathlib import Path

# Add project root to path
project_root = Path(__file__).parent.parent.parent
sys.path.insert(0, str(project_root))

st.title("Tracking Error")
st.info("Tracking error analysis will compare portfolio returns against the benchmark (XBI).")

st.subheader("Coming Soon")
st.markdown("""
- Portfolio vs Benchmark returns
- Rolling tracking error
- Information ratio
- Beta and Alpha calculations
""")
