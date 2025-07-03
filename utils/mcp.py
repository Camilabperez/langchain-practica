import subprocess, json, threading
import queue
import time
import os
from langchain.tools import StructuredTool
from pydantic import create_model, Field
from langchain.tools import StructuredTool
from typing import Any, Dict, Optional, Union  # Mover Union a las importaciones principales

# --- 1. Configuración y Ruta del Servidor MCP ---
AZURE_DEVOPS_ORG_NAME = "camilabperez" 
NODE_PATH = "C:/Program Files/nodejs/node.exe"
MCP_SERVER_INDEX_JS_PATH = "C:/Users/gasto/AppData/Roaming/npm/node_modules/@azure-devops/mcp/dist/index.js" 

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

            # Asegurar que args es un diccionario válido
            processed_args = self._process_tool_args(tool_name, args)

            request_payload = {
                "jsonrpc": "2.0",
                "id": current_request_id,
                "method": "tools/call",
                "params": {
                    "name": tool_name,
                    "arguments": processed_args
                }
            }
            json_request = json.dumps(request_payload) + "\n"

            print(f"Enviando solicitud a MCP: {json_request.strip()}")

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
                        print(f"Respuesta recibida de MCP: {response}")
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

    def _process_tool_args(self, tool_name: str, args: dict) -> dict:
        """Procesa los argumentos de la herramienta para asegurar el formato correcto."""
        processed_args = {}
        
        # Casos especiales para herramientas específicas de Azure DevOps
        if tool_name.startswith('wiki_'):
            # Para herramientas de wiki, asegurar que project esté presente
            if 'project' not in args:
                processed_args['project'] = 'Prueba-MCP'  # Valor por defecto
            
            # Procesar wikiIdentifier si está presente
            if 'wikiIdentifier' in args:
                wiki_id = args['wikiIdentifier']
                if isinstance(wiki_id, dict):
                    # Si es un diccionario, usar solo el wikiIdentifier interno
                    processed_args['wikiIdentifier'] = wiki_id.get('wikiIdentifier', 'Prueba-MCP.wiki')
                else:
                    # Si ya es string, usarlo tal como está
                    processed_args['wikiIdentifier'] = wiki_id
            else:
                # Valor por defecto para wikiIdentifier como string simple
                processed_args['wikiIdentifier'] = 'Prueba-MCP.wiki'
        
        # Copiar el resto de argumentos
        for key, value in args.items():
            if key not in processed_args:
                processed_args[key] = value
        
        return processed_args

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
            default_value = None
            
            # Determinar el tipo basado en el schema
            if spec.get("type") == "integer":
                tipo = int
            elif spec.get("type") == "boolean":
                tipo = bool
            elif spec.get("type") == "number":
                tipo = float
            elif spec.get("type") == "object":
                # Para objetos, permitir tanto dict como string
                tipo = Union[Dict[str, Any], str]
            elif spec.get("type") == "array":
                tipo = list

            # Valores por defecto para campos específicos de Azure DevOps
            if param == "project":
                default_value = "Prueba-MCP"
                tipo = str
            elif param == "wikiIdentifier":
                default_value = "default"  # Cambiado a string simple
                tipo = str
            elif param == "query":
                default_value = ""
                tipo = str
            else:
                # Solo requerir el campo si está en required y no tiene valor por defecto
                if param in required_fields and default_value is None:
                    default_value = ...
                elif default_value is None:
                    default_value = None

            # Crear el campo con descripción si está disponible
            field_description = spec.get("description", f"Parámetro {param}")
            if default_value is ...:
                pydantic_fields[param] = (tipo, Field(..., description=field_description))
            else:
                pydantic_fields[param] = (tipo, Field(default=default_value, description=field_description))

        InputModel = create_model(f"{nombre}_InputModel", **pydantic_fields)

        def _tool_caller(*args, **kwargs) -> Any:
            """Función que llama a la herramienta MCP con los argumentos proporcionados."""
            # Si se pasan argumentos posicionales, los ignoramos y usamos solo kwargs
            if args:
                print(f"Argumentos posicionales ignorados para {nombre}: {args}")
            
            # Procesar argumentos específicos para evitar errores de validación
            processed_kwargs = {}
            
            # Si no hay argumentos, proporcionar valores por defecto según la herramienta
            if not kwargs:
                if nombre.startswith('wiki_'):
                    processed_kwargs = {
                        'project': 'Prueba-MCP',
                        'wikiIdentifier': 'Prueba-MCP.wiki'  # Cambiado a string simple
                    }
            else:
                for key, value in kwargs.items():
                    if key == "wikiIdentifier":
                        if isinstance(value, dict):
                            # Si es un diccionario, extraer el wikiIdentifier interno
                            processed_kwargs[key] = value.get('wikiIdentifier', 'default')
                        elif isinstance(value, str):
                            # Si ya es string, usarlo tal como está
                            processed_kwargs[key] = value
                        else:
                            # Si es otro tipo, usar valor por defecto
                            processed_kwargs[key] = 'default'
                    else:
                        processed_kwargs[key] = value
            
            return self.call_tool(nombre, processed_kwargs)

        _tool_caller.__name__ = nombre
        _tool_caller.__doc__ = descripcion

        # Retornar como StructuredTool
        return StructuredTool.from_function(
            func=_tool_caller,
            name=nombre,
            description=descripcion,
            args_schema=InputModel
        )
    
    def list_mcp_tools_names(self, tool_def: list) -> list:
        nombres = []
        for tool in tool_def:
            nombre = tool["name"]
            nombres.append(nombre)
        return nombres

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
                            tools_list = response["result"].get("tools", [])
                            print(f"Herramientas MCP encontradas: {len(tools_list)}")
                            for tool in tools_list:
                                print(f"- {tool.get('name', 'Sin nombre')}: {tool.get('description', 'Sin descripción')}")
                            return tools_list
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

    def list_mcp_tools_structuredtool(self) -> tuple[list[str], list[StructuredTool]]:
        """Retorna los nombres y herramientas estructuradas de MCP."""
        tools = self.list_mcp_tools()
        names = self.list_mcp_tools_names(tools)
        structured_tools = [self.convertir_tool_mcp_a_structuredtool(t) for t in tools]
        return names, structured_tools