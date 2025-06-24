import subprocess, json, threading
import queue
import time
import os
from langchain.tools import StructuredTool
from pydantic import create_model
from langchain.tools import StructuredTool
from typing import Any

# --- 1. Configuración y Ruta del Servidor MCP ---
AZURE_DEVOPS_ORG_NAME = "camilabperez" 
NODE_PATH = "C:/Program Files/nodejs/node.exe"
MCP_SERVER_INDEX_JS_PATH = "C:/Users/Socius/AppData/Roaming/npm/node_modules/@azure-devops/mcp/dist/index.js" # <-- ¡ESTA ES LA RUTA A VERIFICAR!

# El comando para iniciar el nuevo servidor MCP globalmente.
MCP_COMMAND = [NODE_PATH, MCP_SERVER_INDEX_JS_PATH, AZURE_DEVOPS_ORG_NAME]


# --- 2. Clase Cliente MCP para STDIN/STDOUT ---
class AzureDevOpsMCPClient:
    _instance = None # Patrón Singleton
    _lock = threading.Lock()

    def __new__(cls, *args, **kwargs):
        with cls._lock:
            if cls._instance is None:
                cls._instance = super(AzureDevOpsMCPClient, cls).__new__(cls)
            return cls._instance

    def __init__(self, command: list[str]):
        if not hasattr(self, '_initialized'):
            self.command = command
            self.process = None
            self.response_queue = queue.Queue()
            self.request_id = 0
            self.call_lock = threading.Lock()
            self._initialized = True
            self._start_server()

    def _start_server(self):
        if self.process and self.process.poll() is None:
            return

        print(f"Iniciando Azure DevOps MCP Server con comando: {' '.join(self.command)}")
        try:
            self.process = subprocess.Popen(
                self.command,
                stdin=subprocess.PIPE,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
                bufsize=1,
                env=os.environ.copy() # Herada variables de entorno como AZDO_ORG_URL, AZDO_PAT
            )
            print("Proceso MCP Server iniciado.")

            self.stdout_reader_thread = threading.Thread(target=self._read_stdout)
            self.stdout_reader_thread.daemon = True
            self.stdout_reader_thread.start()

            self.stderr_reader_thread = threading.Thread(target=self._read_stderr)
            self.stderr_reader_thread.daemon = True
            self.stderr_reader_thread.start()

            time.sleep(5) # Dar tiempo para inicialización y autenticación

        except FileNotFoundError:
            print(f"Error: Comando '{self.command[0]}' no encontrado. Asegúrate de que Node.js/npm esté instalado y en tu PATH.")
            self.process = None
        except Exception as e:
            print(f"Error al iniciar el MCP Server: {e}")
            self.process = None

    def _read_stdout(self):
        while True:
            if not self.process or self.process.poll() is not None:
                break
            try:
                line = self.process.stdout.readline()
                if not line:
                    break
                try:
                    response_data = json.loads(line.strip())
                    self.response_queue.put(response_data)
                except json.JSONDecodeError:
                    print(f"MCP Server STDOUT (non-JSON): {line.strip()}")
            except ValueError:
                break
            except Exception as e:
                print(f"Error inesperado leyendo stdout del MCP Server: {e}")
                break

    def _read_stderr(self):
        while True:
            if not self.process or self.process.poll() is not None:
                break
            try:
                line = self.process.stderr.readline()
                if not line:
                    break
                print(f"MCP Server STDERR: {line.strip()}")
            except ValueError:
                break
            except Exception as e:
                print(f"Error inesperado leyendo stderr del MCP Server: {e}")
                break

    def call_tool(self, tool_name: str, args: dict = {}) -> dict:
        """Envía una llamada de herramienta al servidor MCP y espera la respuesta."""
        with self.call_lock:
            if not self.process or self.process.poll() is not None:
                print("MCP Server no está corriendo o se cerró. Intentando iniciar...")
                self._start_server()
                if not self.process or self.process.poll() is not None:
                    raise Exception("Fallo al iniciar o reconectar con el MCP Server. Revisa logs.")

            self.request_id += 1
            current_request_id = self.request_id

            request_payload = {
                "jsonrpc": "2.0",
                "id": current_request_id,
                "method": "tools/call",
                "params": {
                    "name": tool_name,
                    "arguments": args
                }
            }
            json_request = json.dumps(request_payload) + "\n"

            try:
                self.process.stdin.write(json_request)
                self.process.stdin.flush()
            except Exception as e:
                raise Exception(f"Error al escribir en stdin del MCP Server: {e}")

            timeout_seconds = 60
            start_time = time.time()
            while time.time() - start_time < timeout_seconds:
                try:
                    response = self.response_queue.get(timeout=1)
                    if response.get("id") == current_request_id:
                        if "result" in response:
                            return response["result"]
                        elif "error" in response:
                            error_message = response['error'].get('message', str(response['error']))
                            raise Exception(f"MCP Server devolvió un error para la herramienta '{tool_name}': {error_message}")
                        else:
                            return {"message": f"Respuesta inesperada del MCP Server: {response}"}
                    else:
                        self.response_queue.put(response)
                        time.sleep(0.01)
                except queue.Empty:
                    continue
                except Exception as e:
                    raise Exception(f"Error al leer/procesar respuesta del MCP Server: {e}")

            raise Exception(f"Timeout esperando respuesta del MCP Server para herramienta '{tool_name}' (ID: {current_request_id}).")

    def convertir_tool_mcp_a_structuredtool(self, tool_def: dict) -> StructuredTool:
        nombre = tool_def["name"]
        descripcion = tool_def.get("description", "")
        schema = tool_def.get("inputSchema", {})

        # Crear un modelo Pydantic a partir del JSON Schema
        pydantic_fields = {}
        required_fields = schema.get("required", [])
        properties = schema.get("properties", {})

        for param, spec in properties.items():
            tipo = str  # Default
            if spec.get("type") == "integer":
                tipo = int
            elif spec.get("type") == "boolean":
                tipo = bool
            elif spec.get("type") == "number":
                tipo = float

            default = ... if param in required_fields else None
            pydantic_fields[param] = (tipo, default)

        InputModel = create_model(f"{nombre}_InputModel", **pydantic_fields)

        # Define la función que llama al MCP
        def _tool_caller(**kwargs: Any) -> Any:
            return self.call_tool(nombre, kwargs)

        _tool_caller.__name__ = nombre
        _tool_caller.__doc__ = descripcion

        # Retornar como StructuredTool usando el modelo de entrada
        return StructuredTool.from_function(_tool_caller, args_schema=InputModel)

    def list_mcp_tools(self) -> list[dict]:
        """
        Retrieves a list of all tools supported by the Azure DevOps MCP Server,
        including their names, descriptions, and input schemas.
        """
        with self.call_lock:
            if not self.process or self.process.poll() is not None:
                print("MCP Server no está corriendo o se cerró. Intentando iniciar...")
                self._start_server()
                if not self.process or self.process.poll() is not None:
                    raise Exception("Fallo al iniciar o reconectar con el MCP Server. Revisa logs.")

            self.request_id += 1
            current_request_id = self.request_id

            request_payload = {
                "jsonrpc": "2.0",
                "id": current_request_id,
                "method": "tools/list", 
                "params": {}            
            }
            json_request = json.dumps(request_payload) + "\n"

            try:
                self.process.stdin.write(json_request)
                self.process.stdin.flush()
            except Exception as e:
                raise Exception(f"Error al escribir en stdin para listar herramientas del MCP Server: {e}")

            timeout_seconds = 60
            start_time = time.time()
            while time.time() - start_time < timeout_seconds:
                try:
                    response = self.response_queue.get(timeout=1)
                    if response.get("id") == current_request_id:
                        if "result" in response:
                            # El resultado de "tools/list" tiene una clave 'tools'
                            return response["result"].get("tools", [])
                        elif "error" in response:
                            error_message = response['error'].get('message', str(response['error']))
                            raise Exception(f"MCP Server devolvió un error al listar herramientas: {error_message}")
                        else:
                            return {"message": f"Respuesta inesperada del MCP Server al listar herramientas: {response}"}
                    else:
                        self.response_queue.put(response)
                        time.sleep(0.01)
                except queue.Empty:
                    continue
                except Exception as e:
                    raise Exception(f"Error al leer/procesar respuesta para listar herramientas del MCP Server: {e}")

            raise Exception(f"Timeout esperando respuesta del MCP Server para listar herramientas (ID: {current_request_id}).")

    def list_mcp_tools_structuredtool(self)-> StructuredTool:
        tools = self.list_mcp_tools()
        structured_tools = [self.convertir_tool_mcp_a_structuredtool(t) for t in tools]
        return structured_tools
    
