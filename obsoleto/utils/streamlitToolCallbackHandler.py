from langchain.callbacks.base import BaseCallbackHandler
import streamlit as st

class StreamlitToolCallbackHandler(BaseCallbackHandler):
    def __init__(self):
        self.tool_used = None
        self.tool_input = None

    def on_tool_start(self, serialized: dict, input_str: str, **kwargs) -> None:
        """Called when tool starts running."""
        self.tool_used = serialized.get("name")
        self.tool_input = input_str
        st.info(f"**El agente está usando la herramienta:** `{self.tool_used}` con la entrada: `{self.tool_input}`")

    def on_tool_end(self, output: str, **kwargs) -> None:
        """Called when tool ends running."""
        #st.success(f"**La herramienta `{self.tool_used}` ha finalizado.** Resultado: `{output}`")
        # Aquí puedes resetear tool_used si solo quieres mostrar la última herramienta
        self.tool_used = None
        self.tool_input = None