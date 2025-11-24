"""
P&L Analysis page.
"""

import streamlit as st
import sys
from pathlib import Path

# Add project root to path
project_root = Path(__file__).parent.parent.parent
sys.path.insert(0, str(project_root))

st.title("P&L Analysis")
st.info("P&L analysis will be implemented in the next phase. This will show profit/loss calculations based on historical prices.")

# Placeholder for future implementation
st.subheader("Coming Soon")
st.markdown("""
- Daily/Weekly/Monthly P&L
- Position-level P&L attribution
- Historical performance chart
- Realized vs Unrealized gains
""")
