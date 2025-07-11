import subprocess, json, threading
import queue
import time
import os
from langchain.tools import StructuredTool
from pydantic import create_model, Field
from langchain.tools import StructuredTool
from typing import Any, Dict, Optional, Union

# --- 1. Configuración y Ruta del Servidor MCP ---
AZURE_DEVOPS_ORG_NAME = "camilabperez" 
NODE_PATH = "C:/Program Files/nodejs/node.exe"
MCP_SERVER_INDEX_JS_PATH = "C:/Users/gasto/AppData/Roaming/npm/node_modules/@azure-devops/mcp/dist/index.js" 

# SOLUCIÓN PRINCIPAL: Configurar variables de entorno ANTES de crear el comando
def setup_environment():
    """Configura las variables de entorno necesarias para Azure DevOps MCP."""
    required_vars = {
        'AZDO_ORG_URL': f'https://dev.azure.com/{AZURE_DEVOPS_ORG_NAME}',
        'AZDO_DEFAULT_PROJECT': 'Prueba-MCP',
        'AZDO_PAT': os.getenv("AZDO_PAT", "")  # Debe ser configurado por el usuario
    }
    
    # Verificar si las variables están configuradas
    missing_vars = []
    for var, default_value in required_vars.items():
        if not os.getenv(var):
            if default_value:
                os.environ[var] = default_value
                print(f"✅ Variable {var} configurada automáticamente: {default_value}")
            else:
                missing_vars.append(var)
                print(f"❌ Variable {var} no encontrada")
    
    if missing_vars:
        print("🔧 Para solucionar el error TF400813, configura estas variables:")
        print("   export AZDO_PAT='tu_token_aqui'")
        print("   o en Windows: set AZDO_PAT=tu_token_aqui")
        return False
    
    return True

# Configurar el entorno al importar el módulo
if not setup_environment():
    print("⚠️  Configuración de entorno incompleta")

# El comando para iniciar el servidor MCP
MCP_COMMAND = [NODE_PATH, MCP_SERVER_INDEX_JS_PATH, AZURE_DEVOPS_ORG_NAME]

class AzureDevOpsMCPClient:
    _instance = None
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
        
        # SOLUCIÓN CRÍTICA: Preparar variables de entorno correctamente
        env_vars = os.environ.copy()
        
        # Verificar token PAT
        pat_token = env_vars.get('AZDO_PAT')
        if not pat_token:
            raise Exception("❌ AZDO_PAT no está configurado. Configura tu token PAT primero.")
        
        # SOLUCIÓN 1: Usar el formato correcto de URL para la organización
        org_url = f"https://dev.azure.com/{AZURE_DEVOPS_ORG_NAME}"
        env_vars['AZDO_ORG_URL'] = org_url
        
        # SOLUCIÓN 2: Configurar múltiples variantes del token PAT
        env_vars['AZURE_DEVOPS_EXT_PAT'] = pat_token
        env_vars['AZURE_DEVOPS_TOKEN'] = pat_token
        env_vars['SYSTEM_ACCESSTOKEN'] = pat_token
        
        # SOLUCIÓN 3: Configurar el proyecto por defecto
        env_vars['AZDO_DEFAULT_PROJECT'] = 'Prueba-MCP'
        
        # SOLUCIÓN 4: Configurar variables específicas del MCP
        env_vars['MCP_AZURE_DEVOPS_ORG'] = AZURE_DEVOPS_ORG_NAME
        env_vars['MCP_AZURE_DEVOPS_PROJECT'] = 'Prueba-MCP'
        
        # Log de configuración (sin mostrar el token completo)
        print("🔧 Configuración de variables de entorno:")
        print(f"   AZDO_ORG_URL: {env_vars['AZDO_ORG_URL']}")
        print(f"   AZDO_DEFAULT_PROJECT: {env_vars['AZDO_DEFAULT_PROJECT']}")
        print(f"   AZDO_PAT: {pat_token[:10]}...{'*' * (len(pat_token) - 10)}")

        try:
            # SOLUCIÓN 5: Usar shell=True en Windows para mejor compatibilidad
            import platform
            use_shell = platform.system() == "Windows"
            
            self.process = subprocess.Popen(
                self.command,
                stdin=subprocess.PIPE,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
                bufsize=1,
                env=env_vars,
                shell=use_shell  # Esto puede ayudar en Windows
            )
            print("✅ Proceso MCP Server iniciado.")

            self.stdout_reader_thread = threading.Thread(target=self._read_stdout)
            self.stdout_reader_thread.daemon = True
            self.stdout_reader_thread.start()

            self.stderr_reader_thread = threading.Thread(target=self._read_stderr)
            self.stderr_reader_thread.daemon = True
            self.stderr_reader_thread.start()

            # SOLUCIÓN 6: Esperar más tiempo y verificar que el proceso esté corriendo
            print("⏳ Esperando inicialización del servidor MCP...")
            time.sleep(10)  # Aumentar el tiempo de espera
            
            # Verificar que el proceso sigue corriendo
            if self.process.poll() is not None:
                print("❌ El proceso MCP Server se cerró durante la inicialización")
                print("   Revisa los logs de stderr para más detalles")

        except FileNotFoundError:
            print(f"❌ Error: Comando '{self.command[0]}' no encontrado.")
            print("   Asegúrate de que Node.js esté instalado y accesible")
            print("   Verifica la ruta: C:/Program Files/nodejs/node.exe")
            self.process = None
        except Exception as e:
            print(f"❌ Error al iniciar el MCP Server: {e}")
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
                    print(f"📋 MCP Server STDOUT: {line.strip()}")
            except ValueError:
                break
            except Exception as e:
                print(f"❌ Error inesperado leyendo stdout del MCP Server: {e}")
                break

    def _read_stderr(self):
        while True:
            if not self.process or self.process.poll() is not None:
                break
            try:
                line = self.process.stderr.readline()
                if not line:
                    break
                
                error_msg = line.strip()
                
                # SOLUCIÓN 7: Detectar errores específicos de autenticación
                if "TF400813" in error_msg:
                    print(f"🔐 Error de autorización detectado: {error_msg}")
                    print("💡 Soluciones posibles:")
                    print("   1. Verifica que el token PAT tenga permisos de 'Full access'")
                    print("   2. Asegúrate de que el token no haya expirado")
                    print("   3. Verifica que puedas acceder al proyecto desde el navegador")
                    print("   4. Intenta regenerar el token PAT")
                elif "authentication" in error_msg.lower():
                    print(f"🔑 Error de autenticación: {error_msg}")
                elif "ENOENT" in error_msg:
                    print(f"📁 Error de archivo no encontrado: {error_msg}")
                    print("   Verifica la ruta del servidor MCP")
                else:
                    print(f"⚠️  MCP Server STDERR: {error_msg}")
                    
            except ValueError:
                break
            except Exception as e:
                print(f"❌ Error inesperado leyendo stderr del MCP Server: {e}")
                break

    def call_tool(self, tool_name: str, args: dict = {}) -> dict:
        """Envía una llamada de herramienta al servidor MCP y espera la respuesta."""
        with self.call_lock:
            if not self.process or self.process.poll() is not None:
                print("🔄 MCP Server no está corriendo. Intentando reiniciar...")
                self._start_server()
                if not self.process or self.process.poll() is not None:
                    raise Exception("❌ No se pudo iniciar el MCP Server")

            self.request_id += 1
            current_request_id = self.request_id

            # SOLUCIÓN 8: Procesar argumentos correctamente
            processed_args = self._process_tool_args(tool_name, args)

            # SOLUCIÓN 9: NO incluir variables de entorno en la petición
            # El servidor MCP debe usar las variables de entorno del proceso
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
            print(f"📤 Enviando solicitud a MCP: {tool_name} con args: {processed_args}")

            try:
                self.process.stdin.write(json_request)
                self.process.stdin.flush()
            except Exception as e:
                raise Exception(f"❌ Error al escribir en stdin del MCP Server: {e}")

            # Esperar respuesta
            timeout_seconds = 60
            start_time = time.time()
            while time.time() - start_time < timeout_seconds:
                try:
                    response = self.response_queue.get(timeout=1)
                    if response.get("id") == current_request_id:
                        print(f"📥 Respuesta recibida de MCP: {response}")
                        
                        if "result" in response:
                            result = response["result"]
                            
                            # SOLUCIÓN 10: Manejo mejorado de errores
                            if isinstance(result, dict) and result.get("isError"):
                                error_content = result.get("content", [])
                                if error_content and isinstance(error_content, list):
                                    error_text = error_content[0].get("text", "")
                                    
                                    if "TF400813" in error_text:
                                        print("🔧 Diagnóstico del error TF400813:")
                                        print("   1. El token PAT puede estar configurado incorrectamente")
                                        print("   2. El usuario puede no tener permisos en el proyecto")
                                        print("   3. La URL de la organización puede ser incorrecta")
                                        print("   4. El proyecto puede no existir o no ser accesible")
                                        
                                        raise Exception(f"❌ Error de autorización: {error_text}")
                                    else:
                                        raise Exception(f"❌ Error del servidor MCP: {error_text}")
                            
                            return result
                            
                        elif "error" in response:
                            error_message = response['error'].get('message', str(response['error']))
                            raise Exception(f"❌ Error del MCP Server: {error_message}")
                        else:
                            return {"message": f"Respuesta inesperada: {response}"}
                    else:
                        # Respuesta para otro request, volver a la cola
                        self.response_queue.put(response)
                        time.sleep(0.01)
                except queue.Empty:
                    continue
                except Exception as e:
                    raise Exception(f"❌ Error procesando respuesta: {e}")

            raise Exception(f"⏰ Timeout esperando respuesta para '{tool_name}'")

    def _process_tool_args(self, tool_name: str, args: dict) -> dict:
        """Procesa los argumentos de la herramienta para asegurar el formato correcto."""
        processed_args = {}
        
        # SOLUCIÓN 11: Valores por defecto específicos para herramientas de wiki
        if tool_name.startswith('wiki_'):
            # Usar el proyecto por defecto
            processed_args['project'] = args.get('project', 'Prueba-MCP')
            
            # Manejar wikiIdentifier correctamente
            if 'wikiIdentifier' in args:
                wiki_id = args['wikiIdentifier']
                if isinstance(wiki_id, dict):
                    processed_args['wikiIdentifier'] = wiki_id.get('wikiIdentifier', 'Prueba-MCP.wiki')
                else:
                    processed_args['wikiIdentifier'] = str(wiki_id)
            else:
                # Usar el ID del wiki por defecto
                processed_args['wikiIdentifier'] = 'be312b6f-60a0-4e82-a5cd-6ff888ce5c19'
        
        # Copiar el resto de argumentos
        for key, value in args.items():
            if key not in processed_args:
                processed_args[key] = value
        
        return processed_args

    # [El resto de los métodos permanece igual...]
    def convertir_tool_mcp_a_structuredtool(self, tool_def: dict) -> StructuredTool:
        nombre = tool_def["name"]
        descripcion = tool_def.get("description", "")
        schema = tool_def.get("inputSchema", {})

        pydantic_fields = {}
        required_fields = schema.get("required", [])
        properties = schema.get("properties", {})

        for param, spec in properties.items():
            tipo = str
            default_value = None
            
            if spec.get("type") == "integer":
                tipo = int
            elif spec.get("type") == "boolean":
                tipo = bool
            elif spec.get("type") == "number":
                tipo = float
            elif spec.get("type") == "object":
                tipo = Union[Dict[str, Any], str]
            elif spec.get("type") == "array":
                tipo = list

            if param == "project":
                default_value = "Prueba-MCP"
                tipo = str
            elif param == "wikiIdentifier":
                default_value = "be312b6f-60a0-4e82-a5cd-6ff888ce5c19"
                tipo = str
            elif param == "query":
                default_value = ""
                tipo = str
            else:
                if param in required_fields and default_value is None:
                    default_value = ...
                elif default_value is None:
                    default_value = None

            field_description = spec.get("description", f"Parámetro {param}")
            if default_value is ...:
                pydantic_fields[param] = (tipo, Field(..., description=field_description))
            else:
                pydantic_fields[param] = (tipo, Field(default=default_value, description=field_description))

        InputModel = create_model(f"{nombre}_InputModel", **pydantic_fields)

        def _tool_caller(*args, **kwargs) -> Any:
            if args:
                print(f"⚠️  Argumentos posicionales ignorados para {nombre}: {args}")
            
            processed_kwargs = {}
            
            if not kwargs:
                if nombre.startswith('wiki_'):
                    processed_kwargs = {
                        'project': 'Prueba-MCP',
                        'wikiIdentifier': 'be312b6f-60a0-4e82-a5cd-6ff888ce5c19'
                    }
            else:
                for key, value in kwargs.items():
                    if key == "wikiIdentifier":
                        if isinstance(value, dict):
                            processed_kwargs[key] = value.get('wikiIdentifier', 'be312b6f-60a0-4e82-a5cd-6ff888ce5c19')
                        elif isinstance(value, str):
                            processed_kwargs[key] = value
                        else:
                            processed_kwargs[key] = 'be312b6f-60a0-4e82-a5cd-6ff888ce5c19'
                    else:
                        processed_kwargs[key] = value
            
            return self.call_tool(nombre, processed_kwargs)

        _tool_caller.__name__ = nombre
        _tool_caller.__doc__ = descripcion

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
        with self.call_lock:
            if not self.process or self.process.poll() is not None:
                print("🔄 MCP Server no está corriendo. Intentando iniciar...")
                self._start_server()
                if not self.process or self.process.poll() is not None:
                    raise Exception("❌ No se pudo iniciar el MCP Server")

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
                raise Exception(f"❌ Error al escribir en stdin: {e}")

            timeout_seconds = 60
            start_time = time.time()
            while time.time() - start_time < timeout_seconds:
                try:
                    response = self.response_queue.get(timeout=1)
                    if response.get("id") == current_request_id:
                        if "result" in response:
                            tools_list = response["result"].get("tools", [])
                            print(f"✅ Herramientas MCP encontradas: {len(tools_list)}")
                            for tool in tools_list:
                                print(f"  - {tool.get('name', 'Sin nombre')}: {tool.get('description', 'Sin descripción')}")
                            return tools_list
                        elif "error" in response:
                            error_message = response['error'].get('message', str(response['error']))
                            raise Exception(f"❌ Error al listar herramientas: {error_message}")
                        else:
                            return {"message": f"Respuesta inesperada: {response}"}
                    else:
                        self.response_queue.put(response)
                        time.sleep(0.01)
                except queue.Empty:
                    continue
                except Exception as e:
                    raise Exception(f"❌ Error procesando respuesta: {e}")

            raise Exception(f"⏰ Timeout esperando lista de herramientas")

    def list_mcp_tools_structuredtool(self) -> tuple[list[str], list[StructuredTool]]:
        """Retorna los nombres y herramientas estructuradas de MCP."""
        tools = self.list_mcp_tools()
        names = self.list_mcp_tools_names(tools)
        structured_tools = [self.convertir_tool_mcp_a_structuredtool(t) for t in tools]
        return names, structured_tools

# SOLUCIÓN 12: Función de diagnóstico
def diagnosticar_configuracion():
    """Función para diagnosticar la configuración de Azure DevOps."""
    print("🔍 Diagnóstico de configuración Azure DevOps MCP:")
    print("=" * 50)
    
    # Verificar variables de entorno
    required_vars = ['AZDO_PAT', 'AZDO_ORG_URL', 'AZDO_DEFAULT_PROJECT']
    for var in required_vars:
        value = os.getenv(var)
        if value:
            if var == 'AZDO_PAT':
                print(f"✅ {var}: {value[:10]}...{'*' * (len(value) - 10)}")
            else:
                print(f"✅ {var}: {value}")
        else:
            print(f"❌ {var}: NO CONFIGURADA")
    
    # Verificar archivos
    print(f"\n📁 Verificando archivos:")
    print(f"   Node.js: {os.path.exists(NODE_PATH)}")
    print(f"   MCP Server: {os.path.exists(MCP_SERVER_INDEX_JS_PATH)}")
    
    print(f"\n🔧 Comandos para configurar variables (ejecutar en terminal):")
    print(f"   Windows: set AZDO_PAT=tu_token_aqui")
    print(f"   Linux/Mac: export AZDO_PAT=tu_token_aqui")
    print(f"   O crear archivo .env con las variables necesarias")

MCP_PROVIDERS = {
    "azure": {
        "command": [
            "C:/Program Files/nodejs/node.exe",
            "C:/Users/gasto/AppData/Roaming/npm/node_modules/@azure-devops/mcp/dist/index.js",
            "camilabperez"
        ],
        "env": {
            "AZDO_ORG_URL": "https://dev.azure.com/camilabperez",
            "AZDO_DEFAULT_PROJECT": "Prueba-MCP",
            # El PAT debe venir de tu .env o variable de entorno
            "AZDO_PAT": os.getenv("AZDO_PAT", ""),
        }
    },
    "ibm": {
        "command": [
            "ruta/al/ibm_mcp",  # Cambia esto por el ejecutable real de IBM MCP
            "--org", "tu_organizacion_ibm",
            "--project", "tu_proyecto_ibm"
        ],
        "env": {
            "IBM_API_KEY": os.getenv("IBM_API_KEY", ""),
            # Agrega aquí otras variables necesarias para IBM
        }
    }
    # Puedes agregar más proveedores aquí
}

class MCPClient:
    def __init__(self, provider: str):
        if provider not in MCP_PROVIDERS:
            raise ValueError(f"Proveedor MCP '{provider}' no soportado.")
        self.provider = provider
        self.command = MCP_PROVIDERS[provider]["command"]
        # Mezcla las variables de entorno del sistema con las del proveedor
        self.env_vars = {**os.environ, **MCP_PROVIDERS[provider]["env"]}
        self.process = None

    def start_server(self):
        import platform
        use_shell = platform.system() == "Windows"
        print(f"Iniciando MCP Server para {self.provider} con comando: {' '.join(self.command)}")
        self.process = subprocess.Popen(
            self.command,
            env=self.env_vars,
            shell=use_shell
        )
        print("✅ Proceso MCP Server iniciado.")